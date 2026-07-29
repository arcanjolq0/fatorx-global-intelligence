"""Preflight and runtime outcome validation for the single-operation runner."""

import re
from dataclasses import dataclass
from inspect import iscoroutinefunction
from typing import Never, cast

from intelligence.connectors.artifacts import ArtifactPayload, ArtifactReference
from intelligence.connectors.context import ConnectorContext
from intelligence.connectors.descriptor import (
    ConnectorDescriptor,
    validate_connector_descriptor,
)
from intelligence.connectors.enums import (
    ConnectorCapability,
    ConnectorCoverageKind,
    ConnectorErrorCode,
    ConnectorMode,
    ConnectorOutcomeStatus,
    ConnectorWarningCode,
)
from intelligence.connectors.execution.contracts import (
    ConnectorExecutionItem,
    ConnectorOperationRequest,
    FetchDetailsConnectorOperation,
    FetchDocumentConnectorOperation,
    SearchConnectorOperation,
)
from intelligence.connectors.execution.errors import ConnectorExecutionPreflightError
from intelligence.connectors.execution.policies import validate_execution_policy
from intelligence.connectors.observations import CandidateObservation, Observation
from intelligence.connectors.outcomes import (
    ConnectorOutcome,
    ConnectorWarning,
    Pagination,
)
from intelligence.connectors.protocol import Connector
from intelligence.connectors.queries import CandidateRef, CompanyQuery
from intelligence.connectors.versions import SUPPORTED_CONTRACT_MAJORS
from intelligence.domain.geography import CountryCode
from intelligence.domain.money import CurrencyCode

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)
_FORBIDDEN_PUBLIC_MARKERS = (
    "://",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "stack trace",
    "token",
    "traceback",
)


class InvalidRuntimeConnectorOutcomeError(Exception):
    """A connector returned an object that cannot be safely published."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectorPreflight:
    """Validated immutable data needed after the no-I/O preflight."""

    descriptor: ConnectorDescriptor
    credential_reference: str | None


def validate_execution_preflight(request: object) -> ConnectorPreflight:
    """Validate all static support and request invariants before connector I/O."""

    if not isinstance(
        request,
        (
            SearchConnectorOperation,
            FetchDetailsConnectorOperation,
            FetchDocumentConnectorOperation,
        ),
    ):
        _preflight_error(ConnectorErrorCode.INVALID_REQUEST, "Execution request type is invalid")
    connector_object: object = request.connector
    if not isinstance(connector_object, Connector):
        _preflight_error(
            ConnectorErrorCode.INVALID_REQUEST,
            "Connector does not implement the required protocol",
        )
    if any(
        not iscoroutinefunction(getattr(connector_object, method_name))
        for method_name in ("search", "fetch_details", "fetch_document")
    ):
        _preflight_error(
            ConnectorErrorCode.INVALID_REQUEST,
            "Connector operations must be asynchronous",
        )
    capability_object: object = request.capability
    if not isinstance(capability_object, ConnectorCapability):
        _preflight_error(ConnectorErrorCode.INVALID_REQUEST, "Execution capability type is invalid")
    country_object: object = request.country
    if not isinstance(country_object, CountryCode):
        _preflight_error(ConnectorErrorCode.INVALID_REQUEST, "Execution country type is invalid")
    context_object: object = request.context
    if not isinstance(context_object, ConnectorContext) or context_object.attempt != 1:
        _preflight_error(
            ConnectorErrorCode.INVALID_REQUEST,
            "Base connector context must begin with attempt one",
        )
    try:
        validate_execution_policy(request.policy)
    except Exception as error:
        raise ConnectorExecutionPreflightError(
            ConnectorErrorCode.INVALID_REQUEST,
            "Connector execution policy is invalid",
        ) from error

    descriptor = _stable_descriptor(request.connector)
    if descriptor.contract_version.major not in SUPPORTED_CONTRACT_MAJORS:
        _preflight_error(
            ConnectorErrorCode.INVALID_REQUEST,
            "Connector contract major is not supported",
        )
    if not descriptor.supports(
        country=request.country,
        capability=request.capability,
        operation=request.operation,
        mode=request.context.mode,
    ):
        _raise_unsupported(request, descriptor)
    _validate_operation_input(request, descriptor)
    credential_reference = _validate_credential(request, descriptor)
    budget = request.context.budget_remaining
    estimate = request.policy.estimated_attempt_cost
    if budget is not None:
        if estimate is None:
            _preflight_error(
                ConnectorErrorCode.INVALID_REQUEST,
                "Budget enforcement requires an estimated attempt cost",
            )
        if budget.currency != estimate.currency:
            _preflight_error(
                ConnectorErrorCode.INVALID_REQUEST,
                "Budget and estimated attempt cost currencies are incompatible",
            )
    return ConnectorPreflight(
        descriptor=descriptor,
        credential_reference=credential_reference,
    )


def validate_descriptor_stability(
    connector: Connector,
    expected: ConnectorDescriptor,
) -> None:
    """Reject a descriptor that changes after an operation."""

    try:
        actual = connector.describe()
        validate_connector_descriptor(actual)
    except Exception as error:
        raise InvalidRuntimeConnectorOutcomeError(
            "Connector descriptor became invalid after execution."
        ) from error
    if actual != expected:
        raise InvalidRuntimeConnectorOutcomeError("Connector descriptor changed during execution.")


def validate_and_limit_outcome(
    *,
    request: ConnectorOperationRequest,
    descriptor: ConnectorDescriptor,
    outcome: object,
    expected_cost_currency: CurrencyCode | None,
) -> ConnectorOutcome[ConnectorExecutionItem]:
    """Validate untrusted runtime semantics and enforce one-page content limits."""

    if not isinstance(outcome, ConnectorOutcome):
        raise InvalidRuntimeConnectorOutcomeError(
            "Connector operation returned an incompatible outcome."
        )
    try:
        _validate_common_outcome(request, descriptor, outcome, expected_cost_currency)
        _validate_items(request, descriptor, outcome)
        return _limit_outcome(request, descriptor, outcome)
    except InvalidRuntimeConnectorOutcomeError:
        raise
    except Exception as error:
        raise InvalidRuntimeConnectorOutcomeError(
            "Connector operation returned an incompatible outcome."
        ) from error


def _stable_descriptor(connector: Connector) -> ConnectorDescriptor:
    try:
        first = connector.describe()
        second = connector.describe()
        validate_connector_descriptor(first)
        validate_connector_descriptor(second)
    except Exception as error:
        raise ConnectorExecutionPreflightError(
            ConnectorErrorCode.INVALID_REQUEST,
            "Connector descriptor is invalid",
        ) from error
    if first != second:
        _preflight_error(
            ConnectorErrorCode.INVALID_REQUEST,
            "Connector descriptor is not stable",
        )
    return first


def _raise_unsupported(
    request: ConnectorOperationRequest,
    descriptor: ConnectorDescriptor,
) -> None:
    if not (
        descriptor.coverage_kind is ConnectorCoverageKind.GLOBAL
        or request.country in descriptor.countries
    ):
        _preflight_error(
            ConnectorErrorCode.UNSUPPORTED_COUNTRY,
            "Connector does not support the requested country",
        )
    if request.capability not in descriptor.capabilities:
        _preflight_error(
            ConnectorErrorCode.UNSUPPORTED_CAPABILITY,
            "Connector does not support the requested capability",
        )
    if request.operation not in descriptor.operations:
        _preflight_error(
            ConnectorErrorCode.UNSUPPORTED_OPERATION,
            "Connector does not support the requested operation",
        )
    if request.context.mode is ConnectorMode.TEST and not descriptor.supports_test_mode:
        _preflight_error(
            ConnectorErrorCode.POLICY_BLOCKED,
            "Connector does not support test mode",
        )
    _preflight_error(ConnectorErrorCode.INVALID_REQUEST, "Connector support matrix is invalid")


def _validate_operation_input(
    request: ConnectorOperationRequest,
    descriptor: ConnectorDescriptor,
) -> None:
    if isinstance(request, SearchConnectorOperation):
        query_object: object = request.query
        if not isinstance(query_object, CompanyQuery) or query_object.country != request.country:
            _preflight_error(
                ConnectorErrorCode.INVALID_REQUEST,
                "Search input is incompatible with the requested operation",
            )
        return
    if isinstance(request, FetchDetailsConnectorOperation):
        candidate_object: object = request.candidate
        if not isinstance(candidate_object, CandidateRef):
            _preflight_error(
                ConnectorErrorCode.INVALID_REQUEST,
                "Details input is incompatible with the requested operation",
            )
        if candidate_object.connector_id != descriptor.connector_id:
            _preflight_error(
                ConnectorErrorCode.INVALID_REQUEST,
                "Candidate belongs to a different connector",
            )
        if candidate_object.country != request.country:
            _preflight_error(
                ConnectorErrorCode.INVALID_REQUEST,
                "Candidate country differs from the requested country",
            )
        return
    document_object: object = request.document
    if not isinstance(document_object, ArtifactReference):
        _preflight_error(
            ConnectorErrorCode.INVALID_REQUEST,
            "Document input is incompatible with the requested operation",
        )


def _validate_credential(
    request: ConnectorOperationRequest,
    descriptor: ConnectorDescriptor,
) -> str | None:
    handle = request.context.credential_handle
    expected = descriptor.credential_ref_name
    if expected is None:
        if handle is not None:
            _preflight_error(
                ConnectorErrorCode.INVALID_REQUEST,
                "Connector does not declare a credential reference",
            )
        return None
    if handle is None:
        _preflight_error(
            ConnectorErrorCode.AUTH_REQUIRED,
            "Connector requires a credential reference",
        )
    try:
        actual = handle.reference_name
    except Exception as error:
        raise ConnectorExecutionPreflightError(
            ConnectorErrorCode.AUTH_REQUIRED,
            "Credential reference could not be validated",
        ) from error
    if not isinstance(actual, str) or actual != expected:
        _preflight_error(
            ConnectorErrorCode.AUTH_REQUIRED,
            "Credential reference does not match the connector declaration",
        )
    return actual


def _validate_common_outcome(
    request: ConnectorOperationRequest,
    descriptor: ConnectorDescriptor,
    outcome: ConnectorOutcome[object],
    expected_cost_currency: CurrencyCode | None,
) -> None:
    if (
        outcome.source_snapshot is not None
        and outcome.source_snapshot.source_id != descriptor.source_id
    ):
        raise InvalidRuntimeConnectorOutcomeError("Source snapshot does not match the connector.")
    if outcome.pagination is not None and outcome.pagination.returned_count != len(outcome.items):
        raise InvalidRuntimeConnectorOutcomeError("Pagination count contradicts returned items.")
    if outcome.status in {ConnectorOutcomeStatus.FAILED, ConnectorOutcomeStatus.CANCELLED} and (
        outcome.items or outcome.artifacts or outcome.pagination is not None
    ):
        raise InvalidRuntimeConnectorOutcomeError("Failed outcome contains publishable content.")
    if outcome.status is ConnectorOutcomeStatus.NO_RESULTS and (
        outcome.pagination is not None and outcome.pagination.has_more
    ):
        raise InvalidRuntimeConnectorOutcomeError("Empty outcome contradicts pagination state.")
    if (
        outcome.response_digest is not None
        and _SHA256_PATTERN.fullmatch(outcome.response_digest) is None
    ):
        raise InvalidRuntimeConnectorOutcomeError("Connector response digest is invalid.")
    sensitive_values = _sensitive_input_values(request)
    if outcome.error is not None:
        _validate_public_message(outcome.error.message, sensitive_values)
    for warning in outcome.warnings:
        _validate_public_message(warning.message, sensitive_values)
    cost = outcome.usage.cost
    if (
        cost is not None
        and expected_cost_currency is not None
        and cost.currency != expected_cost_currency
    ):
        raise InvalidRuntimeConnectorOutcomeError("Connector usage currency is incompatible.")


def _validate_items(
    request: ConnectorOperationRequest,
    descriptor: ConnectorDescriptor,
    outcome: ConnectorOutcome[object],
) -> None:
    if isinstance(request, SearchConnectorOperation):
        for item in outcome.items:
            if not isinstance(item, CandidateObservation):
                raise InvalidRuntimeConnectorOutcomeError(
                    "Search returned an incompatible item type."
                )
            if item.candidate.connector_id != descriptor.connector_id:
                raise InvalidRuntimeConnectorOutcomeError(
                    "Search candidate belongs to a different connector."
                )
        return
    if isinstance(request, FetchDetailsConnectorOperation):
        for item in outcome.items:
            if not isinstance(item, Observation):
                raise InvalidRuntimeConnectorOutcomeError(
                    "Details returned an incompatible item type."
                )
            if item.subject_candidate_ref != request.candidate:
                raise InvalidRuntimeConnectorOutcomeError(
                    "Detail observation belongs to a different candidate."
                )
        return
    if any(not isinstance(item, ArtifactPayload) for item in outcome.items):
        raise InvalidRuntimeConnectorOutcomeError("Document returned an incompatible item type.")


def _limit_outcome(
    request: ConnectorOperationRequest,
    descriptor: ConnectorDescriptor,
    outcome: ConnectorOutcome[object],
) -> ConnectorOutcome[ConnectorExecutionItem]:
    item_limit = request.policy.max_items
    if descriptor.max_page_size is not None:
        item_limit = min(item_limit, descriptor.max_page_size)
    items = tuple(outcome.items[:item_limit])
    artifacts = tuple(outcome.artifacts[: request.policy.max_artifacts])
    items_truncated = len(items) < len(outcome.items)
    artifacts_truncated = len(artifacts) < len(outcome.artifacts)
    pagination_limited = outcome.pagination is not None and outcome.pagination.has_more
    if not (items_truncated or artifacts_truncated or pagination_limited):
        return cast(ConnectorOutcome[ConnectorExecutionItem], outcome)
    if not items and not artifacts:
        raise InvalidRuntimeConnectorOutcomeError(
            "Content limits removed all usable connector content."
        )
    warnings = list(outcome.warnings)
    if (items_truncated or artifacts_truncated) and not any(
        warning.code is ConnectorWarningCode.TRUNCATED for warning in warnings
    ):
        warnings.append(
            ConnectorWarning(
                ConnectorWarningCode.TRUNCATED,
                "Result content was limited by execution policy",
            )
        )
    if pagination_limited and not any(
        warning.code is ConnectorWarningCode.PAGINATION_LIMITED for warning in warnings
    ):
        warnings.append(
            ConnectorWarning(
                ConnectorWarningCode.PAGINATION_LIMITED,
                "Additional pages were not followed by this operation",
            )
        )
    pagination = (
        Pagination(returned_count=len(items), has_more=False)
        if outcome.pagination is not None or items_truncated
        else None
    )
    typed_items = cast(tuple[ConnectorExecutionItem, ...], items)
    return ConnectorOutcome(
        status=ConnectorOutcomeStatus.PARTIAL,
        items=typed_items,
        artifacts=artifacts,
        source_snapshot=outcome.source_snapshot,
        pagination=pagination,
        usage=outcome.usage,
        warnings=warnings,
        error=outcome.error,
        response_digest=outcome.response_digest,
    )


def _sensitive_input_values(request: ConnectorOperationRequest) -> tuple[str, ...]:
    values: list[str] = []
    if isinstance(request, SearchConnectorOperation):
        values.extend((request.query.original_name, request.query.normalized_name))
        for identifier in request.query.identifiers:
            values.extend((identifier.original_value, identifier.normalized_value))
        if request.query.domain is not None:
            values.append(request.query.domain.value)
        if request.query.address is not None:
            values.extend(request.query.address.lines)
            values.extend(
                value
                for value in (
                    request.query.address.locality,
                    request.query.address.administrative_area,
                    request.query.address.postal_code,
                )
                if value is not None
            )
    elif isinstance(request, FetchDetailsConnectorOperation):
        values.extend((request.candidate.display_name, request.candidate.snapshot.summary))
        if request.candidate.primary_identifier is not None:
            values.extend(
                (
                    request.candidate.primary_identifier.original_value,
                    request.candidate.primary_identifier.normalized_value,
                )
            )
        if request.candidate.domain is not None:
            values.append(request.candidate.domain.value)
    else:
        values.extend(
            value
            for value in (
                request.document.logical_name,
                request.document.origin_reference.value,
            )
            if value is not None
        )
    return tuple(value.casefold() for value in values if len(value) >= 4)


def _validate_public_message(message: str, sensitive_values: tuple[str, ...]) -> None:
    if not isinstance(message, str):
        raise InvalidRuntimeConnectorOutcomeError("Connector message is not public text.")
    lowered = message.casefold()
    if (
        not message
        or len(message) > 256
        or any(character in "\r\n\x00" for character in message)
        or any(marker in lowered for marker in _FORBIDDEN_PUBLIC_MARKERS)
        or any(value in lowered for value in sensitive_values)
    ):
        raise InvalidRuntimeConnectorOutcomeError("Connector message contains unsafe content.")


def _preflight_error(code: ConnectorErrorCode, message: str) -> Never:
    raise ConnectorExecutionPreflightError(code, message)


__all__ = [
    "ConnectorPreflight",
    "InvalidRuntimeConnectorOutcomeError",
    "validate_and_limit_outcome",
    "validate_descriptor_stability",
    "validate_execution_preflight",
]
