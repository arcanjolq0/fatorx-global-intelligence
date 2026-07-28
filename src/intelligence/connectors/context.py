"""Immutable call context contracts without clocks, waiting, or cancellation logic."""

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from intelligence.connectors.enums import ConnectorMode
from intelligence.connectors.errors import InvalidConnectorContextError
from intelligence.connectors.identifiers import OperationId, RequestId
from intelligence.connectors.versions import SourcePolicyVersion
from intelligence.domain.identifiers import CorrelationId, InvestigationId, WorkspaceId
from intelligence.domain.money import Money

_LOCALE_PATTERN = re.compile(
    r"([A-Za-z]{2,3})(?:-([A-Za-z]{4}))?(?:-([A-Za-z]{2}|[0-9]{3}))?",
    flags=re.ASCII,
)


@dataclass(frozen=True, slots=True)
class LocaleTag:
    """Small canonical BCP 47 subset sufficient for declared accepted locales."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidConnectorContextError("LocaleTag must be canonical text.")
        match = _LOCALE_PATTERN.fullmatch(self.value)
        if match is None:
            raise InvalidConnectorContextError("LocaleTag must be canonical BCP 47 text.")
        language, script, region = match.groups()
        parts = [language.lower()]
        if script is not None:
            parts.append(script.title())
        if region is not None:
            parts.append(region.upper())
        object.__setattr__(self, "value", "-".join(parts))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class MonotonicDeadline:
    """Absolute monotonic-clock value for a future execution controller."""

    value: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.value, bool)
            or not isinstance(self.value, float)
            or not math.isfinite(self.value)
            or self.value < 0
        ):
            raise InvalidConnectorContextError(
                "MonotonicDeadline must be a finite non-negative float."
            )


@runtime_checkable
class CredentialHandle(Protocol):
    """Opaque non-serializable credential handle supplied by a future boundary."""

    @property
    def reference_name(self) -> str:
        """Return only the non-secret configuration reference name."""

        ...


@runtime_checkable
class CancellationSignal(Protocol):
    """Cooperative cancellation contract with no implementation in F3.1."""

    def is_cancelled(self) -> bool:
        """Return whether cancellation was requested without blocking."""

        ...


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class ConnectorContext:
    """Typed metadata supplied to one future connector operation."""

    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    operation_id: OperationId
    attempt: int
    correlation_id: CorrelationId
    request_id: RequestId
    deadline: MonotonicDeadline
    budget_remaining: Money | None
    accepted_locales: tuple[LocaleTag, ...]
    source_policy_version: SourcePolicyVersion
    mode: ConnectorMode
    cancellation_signal: CancellationSignal = field(
        repr=False,
        compare=False,
        hash=False,
    )
    credential_handle: CredentialHandle | None = field(
        default=None,
        repr=False,
        compare=False,
        hash=False,
    )

    def __init__(
        self,
        *,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
        operation_id: OperationId,
        attempt: int,
        correlation_id: CorrelationId,
        request_id: RequestId,
        deadline: MonotonicDeadline,
        budget_remaining: Money | None,
        accepted_locales: Iterable[LocaleTag],
        source_policy_version: SourcePolicyVersion,
        mode: ConnectorMode,
        cancellation_signal: CancellationSignal,
        credential_handle: CredentialHandle | None = None,
    ) -> None:
        object.__setattr__(self, "workspace_id", workspace_id)
        object.__setattr__(self, "investigation_id", investigation_id)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "attempt", attempt)
        object.__setattr__(self, "correlation_id", correlation_id)
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "deadline", deadline)
        object.__setattr__(self, "budget_remaining", budget_remaining)
        object.__setattr__(self, "accepted_locales", tuple(accepted_locales))
        object.__setattr__(self, "source_policy_version", source_policy_version)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "credential_handle", credential_handle)
        object.__setattr__(self, "cancellation_signal", cancellation_signal)
        self._validate()

    def _validate(self) -> None:
        expected_types = (
            (self.workspace_id, WorkspaceId, "workspace_id"),
            (self.investigation_id, InvestigationId, "investigation_id"),
            (self.operation_id, OperationId, "operation_id"),
            (self.correlation_id, CorrelationId, "correlation_id"),
            (self.request_id, RequestId, "request_id"),
            (self.deadline, MonotonicDeadline, "deadline"),
            (self.source_policy_version, SourcePolicyVersion, "source_policy_version"),
            (self.mode, ConnectorMode, "mode"),
        )
        for value, expected_type, field_name in expected_types:
            if not isinstance(value, expected_type):
                raise InvalidConnectorContextError(
                    f"ConnectorContext {field_name} has an invalid type."
                )
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
            raise InvalidConnectorContextError("ConnectorContext attempt must be at least one.")
        if self.budget_remaining is not None:
            if not isinstance(self.budget_remaining, Money):
                raise InvalidConnectorContextError(
                    "ConnectorContext budget_remaining must be Money."
                )
            if self.budget_remaining.amount < 0:
                raise InvalidConnectorContextError(
                    "ConnectorContext budget_remaining cannot be negative."
                )
        if not self.accepted_locales or any(
            not isinstance(locale, LocaleTag) for locale in self.accepted_locales
        ):
            raise InvalidConnectorContextError(
                "ConnectorContext accepted_locales must contain canonical LocaleTag values."
            )
        if len(set(self.accepted_locales)) != len(self.accepted_locales):
            raise InvalidConnectorContextError(
                "ConnectorContext accepted_locales cannot contain duplicates."
            )
        if self.credential_handle is not None and not isinstance(
            self.credential_handle, CredentialHandle
        ):
            raise InvalidConnectorContextError(
                "ConnectorContext credential_handle has an incompatible protocol."
            )
        if not isinstance(self.cancellation_signal, CancellationSignal):
            raise InvalidConnectorContextError(
                "ConnectorContext cancellation_signal has an incompatible protocol."
            )


__all__ = [
    "CancellationSignal",
    "ConnectorContext",
    "CredentialHandle",
    "LocaleTag",
    "MonotonicDeadline",
]
