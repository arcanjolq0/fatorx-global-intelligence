"""Immutable connector result metadata and contradiction-free generic outcomes."""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from intelligence.connectors.artifacts import ArtifactPayload, ArtifactReference
from intelligence.connectors.enums import (
    ConnectorErrorCode,
    ConnectorOutcomeStatus,
    ConnectorWarningCode,
    UsageCostKind,
)
from intelligence.connectors.errors import InvalidConnectorOutcomeError
from intelligence.connectors.identifiers import OriginReferenceId, SourceId
from intelligence.domain.errors import InvalidDateTimeError
from intelligence.domain.money import Money
from intelligence.domain.time import normalize_utc

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)
_FORBIDDEN_PUBLIC_MESSAGE_MARKERS = (
    "://",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "token",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceSnapshot:
    """Source and logical origin observed at one UTC instant."""

    source_id: SourceId
    origin_reference: OriginReferenceId
    retrieved_at: datetime
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, SourceId):
            raise InvalidConnectorOutcomeError("SourceSnapshot source_id must be a SourceId.")
        if not isinstance(self.origin_reference, OriginReferenceId):
            raise InvalidConnectorOutcomeError(
                "SourceSnapshot origin_reference must be an OriginReferenceId."
            )
        object.__setattr__(self, "retrieved_at", _utc(self.retrieved_at, "retrieved_at"))
        if self.published_at is not None:
            object.__setattr__(
                self,
                "published_at",
                _utc(self.published_at, "published_at"),
            )


@dataclass(frozen=True, slots=True)
class ContinuationToken:
    """Opaque pagination cursor whose value is always redacted from repr."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or not self.value
            or len(self.value) > 512
            or any(character in "\r\n\x00" for character in self.value)
        ):
            raise InvalidConnectorOutcomeError(
                "ContinuationToken must contain bounded opaque text."
            )

    def __repr__(self) -> str:
        return "ContinuationToken(<redacted>)"


@dataclass(frozen=True, slots=True, kw_only=True)
class Pagination:
    """Coherent pagination metadata without a persistable secret cursor."""

    returned_count: int
    has_more: bool
    continuation: ContinuationToken | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.returned_count, bool)
            or not isinstance(self.returned_count, int)
            or self.returned_count < 0
        ):
            raise InvalidConnectorOutcomeError(
                "Pagination returned_count must be a non-negative integer."
            )
        if not isinstance(self.has_more, bool):
            raise InvalidConnectorOutcomeError("Pagination has_more must be boolean.")
        if self.has_more and not isinstance(self.continuation, ContinuationToken):
            raise InvalidConnectorOutcomeError(
                "Pagination with more results requires an opaque continuation token."
            )
        if not self.has_more and self.continuation is not None:
            raise InvalidConnectorOutcomeError(
                "Pagination without more results cannot expose a continuation token."
            )

    def __repr__(self) -> str:
        continuation = "<redacted>" if self.continuation is not None else "None"
        return (
            f"Pagination(returned_count={self.returned_count}, has_more={self.has_more}, "
            f"continuation={continuation})"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectorUsage:
    """Non-negative usage accounting with exact optional monetary cost."""

    calls: int
    bytes_received: int
    duration: timedelta
    cost: Money | None = None
    cost_kind: UsageCostKind | None = None

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.calls, "calls"),
            (self.bytes_received, "bytes_received"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise InvalidConnectorOutcomeError(
                    f"ConnectorUsage {field_name} must be a non-negative integer."
                )
        if not isinstance(self.duration, timedelta) or self.duration < timedelta(0):
            raise InvalidConnectorOutcomeError(
                "ConnectorUsage duration must be a non-negative timedelta."
            )
        if (self.cost is None) != (self.cost_kind is None):
            raise InvalidConnectorOutcomeError(
                "ConnectorUsage cost and cost_kind must be supplied together."
            )
        if self.cost is not None:
            if not isinstance(self.cost, Money) or self.cost.amount < 0:
                raise InvalidConnectorOutcomeError(
                    "ConnectorUsage cost must be non-negative Money."
                )
            if not isinstance(self.cost_kind, UsageCostKind):
                raise InvalidConnectorOutcomeError(
                    "ConnectorUsage cost_kind must be a UsageCostKind."
                )


@dataclass(frozen=True, slots=True)
class ConnectorWarning:
    """Closed warning code with a bounded public message."""

    code: ConnectorWarningCode
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, ConnectorWarningCode):
            raise InvalidConnectorOutcomeError(
                "ConnectorWarning code must be a ConnectorWarningCode."
            )
        object.__setattr__(self, "message", _public_message(self.message, "warning"))


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectorError:
    """Typed provider-facing failure without stack, payload, or retry decision."""

    code: ConnectorErrorCode
    message: str
    retry_after: timedelta | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ConnectorErrorCode):
            raise InvalidConnectorOutcomeError("ConnectorError code must be a ConnectorErrorCode.")
        if self.retry_after is not None and (
            not isinstance(self.retry_after, timedelta) or self.retry_after < timedelta(0)
        ):
            raise InvalidConnectorOutcomeError(
                "ConnectorError retry_after must be a non-negative timedelta."
            )
        object.__setattr__(self, "message", _public_message(self.message, "error"))


ArtifactResult = ArtifactPayload | ArtifactReference


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class ConnectorOutcome[T]:
    """Generic immutable result whose status and content cannot contradict."""

    status: ConnectorOutcomeStatus
    items: tuple[T, ...]
    artifacts: tuple[ArtifactResult, ...]
    source_snapshot: SourceSnapshot | None
    pagination: Pagination | None
    usage: ConnectorUsage
    warnings: tuple[ConnectorWarning, ...]
    error: ConnectorError | None
    response_digest: str | None

    def __init__(
        self,
        *,
        status: ConnectorOutcomeStatus,
        items: Iterable[T],
        artifacts: Iterable[ArtifactResult],
        source_snapshot: SourceSnapshot | None,
        pagination: Pagination | None,
        usage: ConnectorUsage,
        warnings: Iterable[ConnectorWarning] = (),
        error: ConnectorError | None = None,
        response_digest: str | None = None,
    ) -> None:
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "items", tuple(items))
        object.__setattr__(self, "artifacts", tuple(artifacts))
        object.__setattr__(self, "source_snapshot", source_snapshot)
        object.__setattr__(self, "pagination", pagination)
        object.__setattr__(self, "usage", usage)
        object.__setattr__(self, "warnings", tuple(warnings))
        object.__setattr__(self, "error", error)
        object.__setattr__(self, "response_digest", response_digest)
        self._validate()

    def _validate(self) -> None:
        if not isinstance(self.status, ConnectorOutcomeStatus):
            raise InvalidConnectorOutcomeError(
                "ConnectorOutcome status must be a ConnectorOutcomeStatus."
            )
        if any(
            not isinstance(artifact, (ArtifactPayload, ArtifactReference))
            for artifact in self.artifacts
        ):
            raise InvalidConnectorOutcomeError(
                "ConnectorOutcome artifacts contain an incompatible type."
            )
        if self.source_snapshot is not None and not isinstance(
            self.source_snapshot, SourceSnapshot
        ):
            raise InvalidConnectorOutcomeError(
                "ConnectorOutcome source_snapshot has an incompatible type."
            )
        if self.pagination is not None and not isinstance(self.pagination, Pagination):
            raise InvalidConnectorOutcomeError(
                "ConnectorOutcome pagination has an incompatible type."
            )
        if not isinstance(self.usage, ConnectorUsage):
            raise InvalidConnectorOutcomeError("ConnectorOutcome usage must be ConnectorUsage.")
        if any(not isinstance(warning, ConnectorWarning) for warning in self.warnings):
            raise InvalidConnectorOutcomeError(
                "ConnectorOutcome warnings contain an incompatible type."
            )
        if self.error is not None and not isinstance(self.error, ConnectorError):
            raise InvalidConnectorOutcomeError("ConnectorOutcome error has an incompatible type.")
        if self.response_digest is not None and (
            not isinstance(self.response_digest, str)
            or _SHA256_PATTERN.fullmatch(self.response_digest) is None
        ):
            raise InvalidConnectorOutcomeError(
                "ConnectorOutcome response_digest must be a canonical SHA-256 digest."
            )
        if self.pagination is not None and self.pagination.returned_count != len(self.items):
            raise InvalidConnectorOutcomeError(
                "ConnectorOutcome pagination count must match the returned items."
            )
        if (
            self.error is not None
            and self.error.code is ConnectorErrorCode.CANCELLED
            and self.status is not ConnectorOutcomeStatus.CANCELLED
        ):
            raise InvalidConnectorOutcomeError("CANCELLED errors require CANCELLED outcome status.")
        if (
            self.status
            in {
                ConnectorOutcomeStatus.SUCCEEDED,
                ConnectorOutcomeStatus.NO_RESULTS,
                ConnectorOutcomeStatus.PARTIAL,
            }
            and self.source_snapshot is None
        ):
            raise InvalidConnectorOutcomeError(
                "Usable connector outcomes require a source snapshot."
            )
        self._validate_status_state()

    def _validate_status_state(self) -> None:
        has_usable_content = bool(self.items or self.artifacts)
        if self.status is ConnectorOutcomeStatus.SUCCEEDED:
            if not has_usable_content or self.error is not None:
                raise InvalidConnectorOutcomeError(
                    "SUCCEEDED requires usable content and no error."
                )
            return
        if self.status is ConnectorOutcomeStatus.NO_RESULTS:
            if has_usable_content or self.error is not None:
                raise InvalidConnectorOutcomeError(
                    "NO_RESULTS cannot contain usable content or an error."
                )
            return
        if self.status is ConnectorOutcomeStatus.PARTIAL:
            if not has_usable_content or (not self.warnings and self.error is None):
                raise InvalidConnectorOutcomeError(
                    "PARTIAL requires usable content and a declared gap."
                )
            return
        if self.status is ConnectorOutcomeStatus.FAILED:
            if self.error is None or self.items:
                raise InvalidConnectorOutcomeError(
                    "FAILED requires an error and cannot contain usable items."
                )
            if self.pagination is not None and self.source_snapshot is None:
                raise InvalidConnectorOutcomeError(
                    "FAILED cannot paginate without a source response snapshot."
                )
            return
        if self.items or self.artifacts or self.pagination is not None:
            raise InvalidConnectorOutcomeError(
                "CANCELLED cannot publish late content or pagination."
            )
        if self.error is not None and self.error.code is not ConnectorErrorCode.CANCELLED:
            raise InvalidConnectorOutcomeError("CANCELLED may contain only a CANCELLED error.")


def _utc(value: datetime, field_name: str) -> datetime:
    try:
        return normalize_utc(value)
    except InvalidDateTimeError as error:
        raise InvalidConnectorOutcomeError(
            f"SourceSnapshot {field_name} must include timezone information."
        ) from error


def _public_message(value: str, kind: str) -> str:
    if not isinstance(value, str):
        raise InvalidConnectorOutcomeError(f"Connector {kind} message must be text.")
    canonical = value.strip()
    lowered = canonical.lower()
    if (
        not canonical
        or len(canonical) > 256
        or any(character in "\r\n\x00" for character in canonical)
        or any(marker in lowered for marker in _FORBIDDEN_PUBLIC_MESSAGE_MARKERS)
    ):
        raise InvalidConnectorOutcomeError(
            f"Connector {kind} message must be bounded and public-safe."
        )
    return canonical


__all__ = [
    "ArtifactResult",
    "ConnectorError",
    "ConnectorOutcome",
    "ConnectorUsage",
    "ConnectorWarning",
    "ContinuationToken",
    "Pagination",
    "SourceSnapshot",
]
