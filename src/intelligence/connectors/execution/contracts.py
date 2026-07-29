"""Typed public requests, results, and safe structural execution events."""

import re
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum

from intelligence.connectors.artifacts import ArtifactPayload, ArtifactReference
from intelligence.connectors.context import ConnectorContext
from intelligence.connectors.enums import (
    ConnectorCapability,
    ConnectorErrorCode,
    ConnectorOperation,
    ConnectorOutcomeStatus,
    ConnectorWarningCode,
)
from intelligence.connectors.execution.policies import ConnectorExecutionPolicy
from intelligence.connectors.identifiers import ConnectorId, OperationId
from intelligence.connectors.observations import CandidateObservation, Observation
from intelligence.connectors.outcomes import ConnectorOutcome, ConnectorUsage
from intelligence.connectors.protocol import Connector
from intelligence.connectors.queries import CandidateRef, CompanyQuery
from intelligence.connectors.versions import SemanticVersion
from intelligence.domain.geography import CountryCode
from intelligence.domain.money import Money

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)

type ConnectorExecutionItem = CandidateObservation | Observation | ArtifactPayload


class ConnectorExecutionEventKind(StrEnum):
    RESERVED = "RESERVED"
    ATTEMPT_STARTED = "ATTEMPT_STARTED"
    ATTEMPT_COMPLETED = "ATTEMPT_COMPLETED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    BUDGET_BLOCKED = "BUDGET_BLOCKED"
    REPLAYED = "REPLAYED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    COMPLETED = "COMPLETED"


class ConnectorExecutionControlCode(StrEnum):
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    DEADLINE_EXPIRED = "DEADLINE_EXPIRED"
    CANCELLATION_OBSERVED = "CANCELLATION_OBSERVED"
    BUDGET_BLOCKED = "BUDGET_BLOCKED"
    INVALID_CONNECTOR_RESPONSE = "INVALID_CONNECTOR_RESPONSE"
    CONNECTOR_EXCEPTION = "CONNECTOR_EXCEPTION"


class ConnectorExecutionIdempotencyStatus(StrEnum):
    NOT_RESERVED = "NOT_RESERVED"
    EXECUTED = "EXECUTED"
    REPLAYED = "REPLAYED"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True, kw_only=True)
class SearchConnectorOperation:
    """Strict request for one connector search operation."""

    connector: Connector = field(repr=False, compare=False)
    capability: ConnectorCapability
    country: CountryCode
    query: CompanyQuery = field(repr=False)
    context: ConnectorContext = field(repr=False, compare=False)
    policy: ConnectorExecutionPolicy
    operation: ConnectorOperation = field(init=False, default=ConnectorOperation.SEARCH)


@dataclass(frozen=True, slots=True, kw_only=True)
class FetchDetailsConnectorOperation:
    """Strict request for one connector details operation."""

    connector: Connector = field(repr=False, compare=False)
    capability: ConnectorCapability
    country: CountryCode
    candidate: CandidateRef = field(repr=False)
    context: ConnectorContext = field(repr=False, compare=False)
    policy: ConnectorExecutionPolicy
    operation: ConnectorOperation = field(init=False, default=ConnectorOperation.FETCH_DETAILS)


@dataclass(frozen=True, slots=True, kw_only=True)
class FetchDocumentConnectorOperation:
    """Strict request for one connector document operation."""

    connector: Connector = field(repr=False, compare=False)
    capability: ConnectorCapability
    country: CountryCode
    document: ArtifactReference = field(repr=False)
    context: ConnectorContext = field(repr=False, compare=False)
    policy: ConnectorExecutionPolicy
    operation: ConnectorOperation = field(init=False, default=ConnectorOperation.FETCH_DOCUMENT)


type ConnectorOperationRequest = (
    SearchConnectorOperation | FetchDetailsConnectorOperation | FetchDocumentConnectorOperation
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectorExecutionMetadata:
    """Allowlisted identity of one logical execution, without request content."""

    connector_id: ConnectorId
    connector_version: SemanticVersion
    contract_version: SemanticVersion
    operation_id: OperationId
    operation: ConnectorOperation
    capability: ConnectorCapability
    country: CountryCode

    def __post_init__(self) -> None:
        expected_types = (
            (self.connector_id, ConnectorId),
            (self.connector_version, SemanticVersion),
            (self.contract_version, SemanticVersion),
            (self.operation_id, OperationId),
            (self.operation, ConnectorOperation),
            (self.capability, ConnectorCapability),
            (self.country, CountryCode),
        )
        if any(not isinstance(value, expected) for value, expected in expected_types):
            raise TypeError("Execution metadata contains an incompatible type.")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectorExecutionEvent:
    """Immutable allowlisted observability record with no payload or message."""

    kind: ConnectorExecutionEventKind
    metadata: ConnectorExecutionMetadata
    fingerprint: str
    attempt: int | None = None
    status: ConnectorOutcomeStatus | None = None
    error_code: ConnectorErrorCode | None = None
    warning_codes: tuple[ConnectorWarningCode, ...] = ()
    delay: timedelta | None = None
    total_cost: Money | None = None
    digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ConnectorExecutionEventKind) or not isinstance(
            self.metadata, ConnectorExecutionMetadata
        ):
            raise TypeError("Execution event kind and metadata must use public types.")
        if (
            not isinstance(self.fingerprint, str)
            or _SHA256_PATTERN.fullmatch(self.fingerprint) is None
        ):
            raise ValueError("Execution event fingerprint must be a canonical SHA-256 digest.")
        if self.attempt is not None and (
            isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1
        ):
            raise ValueError("Execution event attempt must be positive when present.")
        if self.delay is not None and (
            not isinstance(self.delay, timedelta) or self.delay < timedelta(0)
        ):
            raise ValueError("Execution event delay cannot be negative.")
        if self.status is not None and not isinstance(self.status, ConnectorOutcomeStatus):
            raise TypeError("Execution event status must use the closed vocabulary.")
        if self.error_code is not None and not isinstance(self.error_code, ConnectorErrorCode):
            raise TypeError("Execution event error code must use the closed vocabulary.")
        if self.total_cost is not None and (
            not isinstance(self.total_cost, Money) or self.total_cost.amount < 0
        ):
            raise TypeError("Execution event total cost must be Money.")
        if self.digest is not None and (
            not isinstance(self.digest, str) or _SHA256_PATTERN.fullmatch(self.digest) is None
        ):
            raise ValueError("Execution event digest must be a canonical SHA-256 digest.")
        if any(not isinstance(code, ConnectorWarningCode) for code in self.warning_codes):
            raise ValueError("Execution event warning codes must use the closed vocabulary.")
        object.__setattr__(self, "warning_codes", tuple(self.warning_codes))


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectorExecutionResult[T]:
    """Final source outcome plus controls and aggregate accounting for one operation."""

    outcome: ConnectorOutcome[T] = field(repr=False)
    attempts_started: int
    total_usage: ConnectorUsage
    fingerprint: str
    digest: str
    idempotency_status: ConnectorExecutionIdempotencyStatus
    metadata: ConnectorExecutionMetadata
    events: tuple[ConnectorExecutionEvent, ...]
    control_code: ConnectorExecutionControlCode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ConnectorOutcome):
            raise TypeError("Execution result outcome must be a ConnectorOutcome.")
        if (
            isinstance(self.attempts_started, bool)
            or not isinstance(self.attempts_started, int)
            or self.attempts_started < 0
        ):
            raise ValueError("Execution result attempts_started cannot be negative.")
        if not isinstance(self.total_usage, ConnectorUsage):
            raise TypeError("Execution result total_usage must be ConnectorUsage.")
        if (
            not isinstance(self.fingerprint, str)
            or _SHA256_PATTERN.fullmatch(self.fingerprint) is None
        ):
            raise ValueError("Execution result fingerprint must be a canonical SHA-256 digest.")
        if not isinstance(self.digest, str) or _SHA256_PATTERN.fullmatch(self.digest) is None:
            raise ValueError("Execution result digest must be a canonical SHA-256 digest.")
        if any(not isinstance(event, ConnectorExecutionEvent) for event in self.events):
            raise TypeError("Execution result events must be structural execution events.")
        if not isinstance(
            self.idempotency_status, ConnectorExecutionIdempotencyStatus
        ) or not isinstance(self.metadata, ConnectorExecutionMetadata):
            raise TypeError("Execution result metadata and idempotency status are invalid.")
        if self.control_code is not None and not isinstance(
            self.control_code, ConnectorExecutionControlCode
        ):
            raise TypeError("Execution result control code must use the closed vocabulary.")
        object.__setattr__(self, "events", tuple(self.events))

    @property
    def replayed(self) -> bool:
        """Return whether this invocation reused an already completed logical result."""

        return self.idempotency_status is ConnectorExecutionIdempotencyStatus.REPLAYED


__all__ = [
    "ConnectorExecutionControlCode",
    "ConnectorExecutionEvent",
    "ConnectorExecutionEventKind",
    "ConnectorExecutionIdempotencyStatus",
    "ConnectorExecutionItem",
    "ConnectorExecutionMetadata",
    "ConnectorExecutionResult",
    "ConnectorOperationRequest",
    "FetchDetailsConnectorOperation",
    "FetchDocumentConnectorOperation",
    "SearchConnectorOperation",
]
