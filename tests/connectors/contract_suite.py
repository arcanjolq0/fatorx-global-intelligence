"""Reusable typed conformity checks for connectors implementing contract 1.x."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from intelligence.connectors.artifacts import ArtifactPayload, ArtifactReference
from intelligence.connectors.context import ConnectorContext
from intelligence.connectors.descriptor import ConnectorDescriptor, validate_connector_descriptor
from intelligence.connectors.enums import (
    ConnectorErrorCode,
    ConnectorOperation,
    ConnectorOutcomeStatus,
)
from intelligence.connectors.observations import CandidateObservation, Observation
from intelligence.connectors.outcomes import ConnectorOutcome
from intelligence.connectors.protocol import Connector
from intelligence.connectors.queries import CandidateRef, CompanyQuery
from intelligence.connectors.versions import SUPPORTED_CONTRACT_MAJORS

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
_FORBIDDEN_REPR_MARKERS = (
    "://",
    "api_key",
    "apikey",
    "authorization=",
    "cookie=",
    "password=",
    "traceback",
)


class ConnectorContractViolation(AssertionError):
    """A connector result or descriptor violated the reusable contract suite."""


@dataclass(frozen=True, slots=True)
class OperationExpectation:
    """Expected minimum status for one explicitly exercised operation."""

    operation: ConnectorOperation
    status: ConnectorOutcomeStatus
    error_code: ConnectorErrorCode | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectorContractCase:
    """Inputs and expectations needed to validate any connector implementation."""

    connector_factory: Callable[[], Connector]
    expected_descriptor: ConnectorDescriptor
    query: CompanyQuery
    context: ConnectorContext
    details_candidate: CandidateRef | None
    expectations: tuple[OperationExpectation, ...]
    document_reference: ArtifactReference | None = None


async def validate_connector_contract(case: ConnectorContractCase) -> None:
    """Validate protocol, descriptor, determinism, typed items, and provenance."""

    _require(isinstance(case, ConnectorContractCase), "case must be a ConnectorContractCase")
    connector = _create_connector(case.connector_factory)
    _require(isinstance(connector, Connector), "object does not satisfy Connector Protocol")

    descriptor = _describe(connector)
    repeated_descriptor = _describe(connector)
    _require(descriptor == repeated_descriptor, "descriptor changed between describe calls")
    _require(descriptor == case.expected_descriptor, "descriptor differs from expectation")
    _require(
        descriptor.contract_version.major in SUPPORTED_CONTRACT_MAJORS,
        "descriptor declares an unsupported contract major",
    )
    _require(descriptor.supports_test_mode, "contract test connector must support TEST mode")
    _require(_is_frozen_dataclass(descriptor), "descriptor must be an immutable dataclass")
    context_representation = repr(case.context)
    _validate_representation(context_representation)
    if case.context.credential_handle is not None:
        _require(
            repr(case.context.credential_handle) not in context_representation,
            "credential handle appears in context representation",
        )

    _require(bool(case.expectations), "contract case must exercise at least one operation")
    for expectation in case.expectations:
        _require(
            expectation.operation in descriptor.operations,
            f"exercised operation {expectation.operation} is not declared",
        )

    fresh_connector = _create_connector(case.connector_factory)
    _require(isinstance(fresh_connector, Connector), "fresh object does not satisfy Protocol")
    _require(_describe(fresh_connector) == descriptor, "fresh connector descriptor changed")

    for expectation in case.expectations:
        first = await _execute(connector, case, expectation.operation)
        second = await _execute(connector, case, expectation.operation)
        fresh = await _execute(fresh_connector, case, expectation.operation)
        _require(first == second, f"{expectation.operation} is not deterministic per instance")
        _require(first == fresh, f"{expectation.operation} differs across equal instances")
        _validate_outcome(
            outcome=first,
            descriptor=descriptor,
            expectation=expectation,
            details_candidate=case.details_candidate,
        )
        _require(
            _describe(connector) == descriptor,
            "descriptor changed after executing an operation",
        )


def _create_connector(factory: Callable[[], Connector]) -> Connector:
    try:
        return factory()
    except Exception as error:
        raise ConnectorContractViolation("connector factory raised an exception") from error


def _describe(connector: Connector) -> ConnectorDescriptor:
    try:
        descriptor = connector.describe()
        validate_connector_descriptor(descriptor)
    except Exception as error:
        if isinstance(error, ConnectorContractViolation):
            raise
        raise ConnectorContractViolation("describe returned an invalid descriptor") from error
    return descriptor


async def _execute(
    connector: Connector,
    case: ConnectorContractCase,
    operation: ConnectorOperation,
) -> ConnectorOutcome[object]:
    try:
        if operation is ConnectorOperation.SEARCH:
            outcome = cast(
                ConnectorOutcome[object],
                await connector.search(case.query, case.context),
            )
        elif operation is ConnectorOperation.FETCH_DETAILS:
            if case.details_candidate is None:
                raise ConnectorContractViolation("details candidate is required")
            outcome = cast(
                ConnectorOutcome[object],
                await connector.fetch_details(case.details_candidate, case.context),
            )
        else:
            if case.document_reference is None:
                raise ConnectorContractViolation("document reference is required")
            outcome = cast(
                ConnectorOutcome[object],
                await connector.fetch_document(case.document_reference, case.context),
            )
    except ConnectorContractViolation:
        raise
    except Exception as error:
        raise ConnectorContractViolation(f"{operation} raised an external exception") from error
    _require(isinstance(outcome, ConnectorOutcome), f"{operation} returned an invalid outcome")
    return outcome


def _validate_outcome(
    *,
    outcome: ConnectorOutcome[object],
    descriptor: ConnectorDescriptor,
    expectation: OperationExpectation,
    details_candidate: CandidateRef | None,
) -> None:
    _require(outcome.status is expectation.status, "outcome status differs from expectation")
    actual_error_code = outcome.error.code if outcome.error is not None else None
    _require(actual_error_code is expectation.error_code, "outcome error code differs")
    _require(_is_frozen_dataclass(outcome), "outcome must be an immutable dataclass")
    _require(isinstance(outcome.items, tuple), "outcome items must be immutable")
    _require(isinstance(outcome.artifacts, tuple), "outcome artifacts must be immutable")
    _require(isinstance(outcome.warnings, tuple), "outcome warnings must be immutable")
    _require(
        all(_is_frozen_dataclass(item) for item in outcome.items),
        "outcome items must be immutable dataclasses",
    )
    _require(
        all(_is_frozen_dataclass(artifact) for artifact in outcome.artifacts),
        "outcome artifacts must be immutable dataclasses",
    )

    if outcome.source_snapshot is not None:
        _require(
            outcome.source_snapshot.source_id == descriptor.source_id,
            "source snapshot does not match descriptor source_id",
        )

    if expectation.operation is ConnectorOperation.SEARCH:
        _require(
            all(isinstance(item, CandidateObservation) for item in outcome.items),
            "search returned an item other than CandidateObservation",
        )
        for item in outcome.items:
            candidate_item = _as_candidate_observation(item)
            _require(
                candidate_item.candidate.connector_id == descriptor.connector_id,
                "search candidate does not match descriptor connector_id",
            )
    elif expectation.operation is ConnectorOperation.FETCH_DETAILS:
        _require(
            all(isinstance(item, Observation) for item in outcome.items),
            "fetch_details returned an item other than Observation",
        )
        _require(details_candidate is not None, "details candidate is required")
        for item in outcome.items:
            observation_item = _as_observation(item)
            _require(
                observation_item.subject_candidate_ref == details_candidate,
                "detail observation does not reference the supplied candidate",
            )
    else:
        _require(
            all(isinstance(item, ArtifactPayload) for item in outcome.items),
            "fetch_document returned an item other than ArtifactPayload",
        )

    if outcome.status is ConnectorOutcomeStatus.NO_RESULTS:
        _require(
            not outcome.items and not outcome.artifacts and outcome.error is None,
            "NO_RESULTS is not a valid result",
        )
    if outcome.status is ConnectorOutcomeStatus.PARTIAL:
        _require(bool(outcome.warnings or outcome.error), "PARTIAL does not declare its gap")
    if outcome.status is ConnectorOutcomeStatus.CANCELLED:
        _require(
            not outcome.items and not outcome.artifacts and outcome.pagination is None,
            "CANCELLED published late content",
        )

    if outcome.error is not None:
        _require(
            isinstance(outcome.error.code, ConnectorErrorCode),
            "outcome error does not use the closed error vocabulary",
        )
        _validate_public_text(outcome.error.message)
    for warning in outcome.warnings:
        _validate_public_text(warning.message)
    outcome_representation = repr(outcome)
    _validate_representation(outcome_representation)
    if outcome.pagination is not None and outcome.pagination.continuation is not None:
        _require(
            outcome.pagination.continuation.value not in outcome_representation,
            "pagination cursor appears in outcome representation",
        )
    for artifact in outcome.artifacts:
        if isinstance(artifact, ArtifactPayload):
            _require(
                artifact.content.decode(errors="replace") not in outcome_representation,
                "artifact content appears in outcome representation",
            )


def _as_candidate_observation(value: object) -> CandidateObservation:
    if not isinstance(value, CandidateObservation):
        raise ConnectorContractViolation("search item has an invalid type")
    return value


def _as_observation(value: object) -> Observation:
    if not isinstance(value, Observation):
        raise ConnectorContractViolation("details item has an invalid type")
    return value


def _validate_public_text(value: str) -> None:
    lowered = value.lower()
    _require(bool(value), "public message is empty")
    _require(len(value) <= 256, "public text is too long")
    _require(
        all(marker not in lowered for marker in _FORBIDDEN_PUBLIC_MARKERS),
        "public message contains a forbidden marker",
    )


def _validate_representation(value: str) -> None:
    lowered = value.lower()
    _require(
        all(marker not in lowered for marker in _FORBIDDEN_REPR_MARKERS),
        "public representation contains a forbidden marker",
    )


def _is_frozen_dataclass(value: object) -> bool:
    parameters = getattr(type(value), "__dataclass_params__", None)
    return parameters is not None and bool(parameters.frozen)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConnectorContractViolation(message)


__all__ = [
    "ConnectorContractCase",
    "ConnectorContractViolation",
    "OperationExpectation",
    "validate_connector_contract",
]
