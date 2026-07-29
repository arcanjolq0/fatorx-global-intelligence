"""Explicit canonical SHA-256 encoders for requests and structural results."""

import hashlib
from datetime import datetime, timedelta
from decimal import Decimal

from intelligence.connectors.artifacts import ArtifactPayload, ArtifactReference
from intelligence.connectors.descriptor import ConnectorDescriptor
from intelligence.connectors.execution.contracts import (
    ConnectorExecutionItem,
    ConnectorExecutionMetadata,
    ConnectorOperationRequest,
    FetchDetailsConnectorOperation,
    FetchDocumentConnectorOperation,
    SearchConnectorOperation,
)
from intelligence.connectors.outcomes import ConnectorOutcome, ConnectorUsage
from intelligence.connectors.queries import (
    BusinessIdentifier,
    CandidateRef,
    CompanyQuery,
    SearchAddress,
)
from intelligence.domain.money import Money


class _CanonicalEncoder:
    """Length-prefixed encoder with no generic object or repr fallback."""

    def __init__(self) -> None:
        self._content = bytearray()

    def text(self, name: str, value: str) -> None:
        encoded_name = name.encode("ascii")
        encoded_value = value.encode("utf-8")
        self._content.extend(len(encoded_name).to_bytes(2, "big"))
        self._content.extend(encoded_name)
        self._content.extend(len(encoded_value).to_bytes(8, "big"))
        self._content.extend(encoded_value)

    def optional_text(self, name: str, value: str | None) -> None:
        self.text(f"{name}.present", "1" if value is not None else "0")
        if value is not None:
            self.text(name, value)

    def integer(self, name: str, value: int) -> None:
        self.text(name, str(value))

    def boolean(self, name: str, value: bool) -> None:
        self.text(name, "1" if value else "0")

    def decimal(self, name: str, value: Decimal) -> None:
        normalized = value.normalize()
        self.text(name, "0" if normalized == 0 else format(normalized, "f"))

    def optional_integer(self, name: str, value: int | None) -> None:
        self.optional_text(name, str(value) if value is not None else None)

    def optional_datetime(self, name: str, value: datetime | None) -> None:
        self.optional_text(
            name,
            value.isoformat(timespec="microseconds") if value is not None else None,
        )

    def duration(self, name: str, value: timedelta) -> None:
        microseconds = value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds
        self.integer(name, microseconds)

    def money(self, name: str, value: Money) -> None:
        self.decimal(f"{name}.amount", value.amount)
        self.text(f"{name}.currency", value.currency.value)

    def optional_money(self, name: str, value: Money | None) -> None:
        self.boolean(f"{name}.present", value is not None)
        if value is not None:
            self.money(name, value)

    def digest(self) -> str:
        return hashlib.sha256(bytes(self._content)).hexdigest()


def connector_request_fingerprint(
    request: ConnectorOperationRequest,
    descriptor: ConnectorDescriptor,
    *,
    credential_reference: str | None,
) -> str:
    """Hash only explicitly encoded public request semantics."""

    encoder = _CanonicalEncoder()
    encoder.text("schema", "connector-execution-request-v1")
    context = request.context
    encoder.text("workspace_id", str(context.workspace_id))
    encoder.text("investigation_id", str(context.investigation_id))
    encoder.text("connector_id", descriptor.connector_id.value)
    encoder.text("connector_version", str(descriptor.version))
    encoder.text("contract_version", str(descriptor.contract_version))
    encoder.text("operation", request.operation.value)
    encoder.text("capability", request.capability.value)
    encoder.text("country", request.country.value)
    encoder.text("mode", context.mode.value)
    encoder.text("source_policy_version", context.source_policy_version.value)
    encoder.text("execution_policy_version", request.policy.version.value)
    encoder.optional_text("credential_reference", credential_reference)
    for index, locale in enumerate(context.accepted_locales):
        encoder.text(f"accepted_locale.{index}", locale.value)
    _encode_execution_policy(encoder, request)
    if isinstance(request, SearchConnectorOperation):
        _encode_query(encoder, request.query)
    elif isinstance(request, FetchDetailsConnectorOperation):
        _encode_candidate(encoder, request.candidate)
    elif isinstance(request, FetchDocumentConnectorOperation):
        _encode_document(encoder, request.document)
    else:
        raise TypeError("Connector operation request has an incompatible type.")
    return encoder.digest()


def connector_execution_digest(
    *,
    fingerprint: str,
    metadata: ConnectorExecutionMetadata,
    outcome: ConnectorOutcome[ConnectorExecutionItem],
    attempts_started: int,
    total_usage: ConnectorUsage,
) -> str:
    """Hash structural allowlisted metadata without items, messages, or cursors."""

    encoder = _CanonicalEncoder()
    encoder.text("schema", "connector-execution-result-v1")
    encoder.text("fingerprint", fingerprint)
    encoder.text("connector_id", metadata.connector_id.value)
    encoder.text("connector_version", str(metadata.connector_version))
    encoder.text("contract_version", str(metadata.contract_version))
    encoder.text("operation", metadata.operation.value)
    encoder.text("capability", metadata.capability.value)
    encoder.text("country", metadata.country.value)
    encoder.text("status", outcome.status.value)
    encoder.optional_text("error_code", outcome.error.code.value if outcome.error else None)
    encoder.integer("attempts_started", attempts_started)
    _encode_usage(encoder, "total_usage", total_usage)
    encoder.optional_text("response_digest", outcome.response_digest)
    encoder.integer("item_count", len(outcome.items))
    encoder.integer("artifact_count", len(outcome.artifacts))
    for index, artifact_digest in enumerate(_artifact_digests(outcome)):
        encoder.text(f"artifact_digest.{index}", artifact_digest)
    encoder.integer("warning_count", len(outcome.warnings))
    for index, warning in enumerate(outcome.warnings):
        encoder.text(f"warning_code.{index}", warning.code.value)
    return encoder.digest()


def _encode_execution_policy(
    encoder: _CanonicalEncoder,
    request: ConnectorOperationRequest,
) -> None:
    policy = request.policy
    encoder.integer("policy.max_attempts", policy.max_attempts)
    for index, code in enumerate(sorted(policy.retriable_codes, key=lambda value: value.value)):
        encoder.text(f"policy.retriable_code.{index}", code.value)
    encoder.duration("policy.base_backoff", policy.base_backoff)
    encoder.duration("policy.max_backoff", policy.max_backoff)
    encoder.duration("policy.max_jitter", policy.max_jitter)
    encoder.optional_money("policy.estimated_attempt_cost", policy.estimated_attempt_cost)
    encoder.integer("policy.max_items", policy.max_items)
    encoder.integer("policy.max_artifacts", policy.max_artifacts)


def _encode_query(encoder: _CanonicalEncoder, query: CompanyQuery) -> None:
    encoder.text("input.kind", "SEARCH")
    encoder.text("query.country", query.country.value)
    encoder.text("query.original_name", query.original_name)
    encoder.text("query.normalized_name", query.normalized_name)
    for index, identifier in enumerate(query.identifiers):
        _encode_identifier(encoder, f"query.identifier.{index}", identifier)
    encoder.optional_text("query.domain", query.domain.value if query.domain else None)
    _encode_address(encoder, query.address)


def _encode_address(encoder: _CanonicalEncoder, address: SearchAddress | None) -> None:
    encoder.boolean("query.address.present", address is not None)
    if address is None:
        return
    encoder.text("query.address.country", address.country.value)
    for index, line in enumerate(address.lines):
        encoder.text(f"query.address.line.{index}", line)
    encoder.optional_text("query.address.locality", address.locality)
    encoder.optional_text("query.address.administrative_area", address.administrative_area)
    encoder.optional_text("query.address.postal_code", address.postal_code)


def _encode_identifier(
    encoder: _CanonicalEncoder,
    prefix: str,
    identifier: BusinessIdentifier,
) -> None:
    encoder.text(f"{prefix}.type", identifier.identifier_type.value)
    encoder.text(f"{prefix}.original", identifier.original_value)
    encoder.text(f"{prefix}.normalized", identifier.normalized_value)


def _encode_candidate(encoder: _CanonicalEncoder, candidate: CandidateRef) -> None:
    encoder.text("input.kind", "FETCH_DETAILS")
    encoder.text("candidate.id", str(candidate.candidate_ref_id))
    encoder.text("candidate.connector_id", candidate.connector_id.value)
    encoder.text("candidate.snapshot", candidate.snapshot.summary)
    encoder.text("candidate.country", candidate.country.value)
    encoder.text("candidate.display_name", candidate.display_name)
    encoder.boolean(
        "candidate.primary_identifier.present", candidate.primary_identifier is not None
    )
    if candidate.primary_identifier is not None:
        _encode_identifier(encoder, "candidate.primary_identifier", candidate.primary_identifier)
    encoder.optional_text("candidate.domain", candidate.domain.value if candidate.domain else None)


def _encode_document(encoder: _CanonicalEncoder, document: ArtifactReference) -> None:
    encoder.text("input.kind", "FETCH_DOCUMENT")
    encoder.text("document.id", str(document.artifact_ref_id))
    encoder.text("document.media_type", document.media_type)
    encoder.text("document.retention", document.retention.value)
    encoder.text("document.origin_reference", document.origin_reference.value)
    encoder.optional_integer("document.size", document.size)
    encoder.optional_text("document.sha256", document.sha256)
    encoder.optional_datetime("document.expires_at", document.expires_at)
    encoder.optional_text("document.logical_name", document.logical_name)


def _encode_usage(encoder: _CanonicalEncoder, prefix: str, usage: ConnectorUsage) -> None:
    encoder.integer(f"{prefix}.calls", usage.calls)
    encoder.integer(f"{prefix}.bytes_received", usage.bytes_received)
    encoder.duration(f"{prefix}.duration", usage.duration)
    encoder.optional_money(f"{prefix}.cost", usage.cost)
    encoder.optional_text(
        f"{prefix}.cost_kind",
        usage.cost_kind.value if usage.cost_kind is not None else None,
    )


def _artifact_digests(
    outcome: ConnectorOutcome[ConnectorExecutionItem],
) -> tuple[str, ...]:
    values: list[str] = []
    for item in outcome.items:
        if isinstance(item, ArtifactPayload):
            values.append(item.sha256)
    for artifact in outcome.artifacts:
        if artifact.sha256 is not None:
            values.append(artifact.sha256)
    return tuple(values)


__all__ = ["connector_execution_digest", "connector_request_fingerprint"]
