"""Immutable retry, budget, and content limits for one connector operation."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from intelligence.connectors.enums import ConnectorErrorCode
from intelligence.connectors.execution.errors import InvalidConnectorExecutionPolicyError
from intelligence.domain.money import Money

MAX_EXECUTION_ATTEMPTS = 5
MAX_EXECUTION_ITEMS = 10_000
MAX_EXECUTION_ARTIFACTS = 100
MAX_BACKOFF = timedelta(hours=1)
MAX_JITTER = timedelta(minutes=5)

DEFAULT_RETRIABLE_CODES = frozenset(
    {
        ConnectorErrorCode.RATE_LIMITED,
        ConnectorErrorCode.TIMEOUT,
        ConnectorErrorCode.UNAVAILABLE,
    }
)
ALLOWED_RETRIABLE_CODES = DEFAULT_RETRIABLE_CODES | frozenset(
    {
        ConnectorErrorCode.INVALID_RESPONSE,
        ConnectorErrorCode.INTERNAL_ERROR,
    }
)
_POLICY_VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*", flags=re.ASCII)


@dataclass(frozen=True, slots=True)
class ConnectorExecutionPolicyVersion:
    """Stable version of one execution-control policy."""

    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or not self.value
            or len(self.value) > 64
            or _POLICY_VERSION_PATTERN.fullmatch(self.value) is None
        ):
            raise InvalidConnectorExecutionPolicyError(
                "Execution policy version must be a canonical public reference."
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class ConnectorExecutionPolicy:
    """Bounded controls applied to exactly one logical connector operation."""

    version: ConnectorExecutionPolicyVersion
    max_attempts: int
    retriable_codes: frozenset[ConnectorErrorCode]
    base_backoff: timedelta
    max_backoff: timedelta
    max_jitter: timedelta
    estimated_attempt_cost: Money | None
    max_items: int
    max_artifacts: int

    def __init__(
        self,
        *,
        version: ConnectorExecutionPolicyVersion,
        max_attempts: int = 3,
        retriable_codes: Iterable[ConnectorErrorCode] = DEFAULT_RETRIABLE_CODES,
        base_backoff: timedelta = timedelta(seconds=1),
        max_backoff: timedelta = timedelta(seconds=30),
        max_jitter: timedelta = timedelta(0),
        estimated_attempt_cost: Money | None = None,
        max_items: int = 100,
        max_artifacts: int = 10,
    ) -> None:
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "max_attempts", max_attempts)
        object.__setattr__(self, "retriable_codes", frozenset(retriable_codes))
        object.__setattr__(self, "base_backoff", base_backoff)
        object.__setattr__(self, "max_backoff", max_backoff)
        object.__setattr__(self, "max_jitter", max_jitter)
        object.__setattr__(self, "estimated_attempt_cost", estimated_attempt_cost)
        object.__setattr__(self, "max_items", max_items)
        object.__setattr__(self, "max_artifacts", max_artifacts)
        validate_execution_policy(self)


def validate_execution_policy(policy: ConnectorExecutionPolicy) -> None:
    """Validate a policy again at the runtime boundary before connector I/O."""

    if not isinstance(policy, ConnectorExecutionPolicy):
        raise InvalidConnectorExecutionPolicyError(
            "Connector execution policy has an incompatible type."
        )
    if not isinstance(policy.version, ConnectorExecutionPolicyVersion):
        raise InvalidConnectorExecutionPolicyError(
            "Connector execution policy version has an incompatible type."
        )
    if (
        isinstance(policy.max_attempts, bool)
        or not isinstance(policy.max_attempts, int)
        or not 1 <= policy.max_attempts <= MAX_EXECUTION_ATTEMPTS
    ):
        raise InvalidConnectorExecutionPolicyError(
            f"Execution max_attempts must be between 1 and {MAX_EXECUTION_ATTEMPTS}."
        )
    if (
        not isinstance(policy.retriable_codes, frozenset)
        or any(not isinstance(code, ConnectorErrorCode) for code in policy.retriable_codes)
        or not policy.retriable_codes.issubset(ALLOWED_RETRIABLE_CODES)
    ):
        raise InvalidConnectorExecutionPolicyError(
            "Execution retry codes must use the explicitly allowed closed set."
        )
    _bounded_duration(policy.base_backoff, "base_backoff", MAX_BACKOFF)
    _bounded_duration(policy.max_backoff, "max_backoff", MAX_BACKOFF)
    _bounded_duration(policy.max_jitter, "max_jitter", MAX_JITTER)
    if policy.base_backoff > policy.max_backoff:
        raise InvalidConnectorExecutionPolicyError(
            "Execution base_backoff cannot exceed max_backoff."
        )
    if policy.estimated_attempt_cost is not None:
        if not isinstance(policy.estimated_attempt_cost, Money):
            raise InvalidConnectorExecutionPolicyError(
                "Execution estimated_attempt_cost must be Money."
            )
        if policy.estimated_attempt_cost.amount < 0:
            raise InvalidConnectorExecutionPolicyError(
                "Execution estimated_attempt_cost cannot be negative."
            )
    _bounded_count(policy.max_items, "max_items", MAX_EXECUTION_ITEMS)
    _bounded_count(policy.max_artifacts, "max_artifacts", MAX_EXECUTION_ARTIFACTS)


def _bounded_duration(value: timedelta, name: str, upper_bound: timedelta) -> None:
    if not isinstance(value, timedelta) or value < timedelta(0) or value > upper_bound:
        raise InvalidConnectorExecutionPolicyError(
            f"Execution {name} must be a bounded non-negative timedelta."
        )


def _bounded_count(value: int, name: str, upper_bound: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper_bound:
        raise InvalidConnectorExecutionPolicyError(
            f"Execution {name} must be between 1 and {upper_bound}."
        )


__all__ = [
    "ALLOWED_RETRIABLE_CODES",
    "DEFAULT_RETRIABLE_CODES",
    "MAX_EXECUTION_ARTIFACTS",
    "MAX_EXECUTION_ATTEMPTS",
    "MAX_EXECUTION_ITEMS",
    "ConnectorExecutionPolicy",
    "ConnectorExecutionPolicyVersion",
    "validate_execution_policy",
]
