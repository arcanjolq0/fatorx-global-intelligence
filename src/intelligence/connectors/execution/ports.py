"""Small injectable ports for monotonic time, waiting, jitter, and idempotency."""

import asyncio
import math
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from time import monotonic
from typing import Protocol, runtime_checkable

from intelligence.connectors.context import MonotonicDeadline
from intelligence.connectors.execution.contracts import (
    ConnectorExecutionItem,
    ConnectorExecutionResult,
)
from intelligence.connectors.identifiers import OperationId

type StoredConnectorExecutionResult = ConnectorExecutionResult[ConnectorExecutionItem]


@runtime_checkable
class MonotonicClock(Protocol):
    """Read the same monotonic time domain used by ``MonotonicDeadline``."""

    def now(self) -> float:
        """Return a finite non-negative monotonic value."""

        ...


@runtime_checkable
class ExecutionSleeper(Protocol):
    """Wait for deadline races and retry delays without owning policy."""

    async def sleep(self, delay: timedelta) -> None:
        """Wait for one non-negative retry delay."""

        ...

    async def sleep_until(self, deadline: MonotonicDeadline) -> None:
        """Wait until an absolute monotonic deadline."""

        ...


@runtime_checkable
class JitterSource(Protocol):
    """Provide a bounded non-negative additive delay without global randomness."""

    def jitter(self, *, attempt: int, backoff: timedelta) -> timedelta:
        """Return the additive jitter for the completed attempt."""

        ...


class IdempotencyClaimStatus(StrEnum):
    """Internal closed values returned by an atomic idempotency reservation."""

    ACQUIRED = "ACQUIRED"
    COMPLETED = "COMPLETED"
    WAIT = "WAIT"


@dataclass(frozen=True, slots=True, kw_only=True)
class IdempotencyClaim:
    """Atomic reservation decision with an optional completed result."""

    status: IdempotencyClaimStatus
    result: StoredConnectorExecutionResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, IdempotencyClaimStatus) or self.status not in {
            IdempotencyClaimStatus.ACQUIRED,
            IdempotencyClaimStatus.COMPLETED,
            IdempotencyClaimStatus.WAIT,
        }:
            raise ValueError("Idempotency claim status is invalid.")
        if (self.status is IdempotencyClaimStatus.COMPLETED) != (self.result is not None):
            raise ValueError("Only a completed idempotency claim may contain a result.")


@runtime_checkable
class IdempotencyStore(Protocol):
    """Atomic instance-scoped storage for one-process execution replay."""

    async def reserve(self, operation_id: OperationId, fingerprint: str) -> IdempotencyClaim:
        """Acquire, replay, wait for, or reject one logical operation."""

        ...

    async def wait(
        self,
        operation_id: OperationId,
        fingerprint: str,
    ) -> StoredConnectorExecutionResult | None:
        """Wait for completion; return ``None`` when the owner released its claim."""

        ...

    async def complete(
        self,
        operation_id: OperationId,
        fingerprint: str,
        result: StoredConnectorExecutionResult,
    ) -> None:
        """Publish one completed immutable result to current and future callers."""

        ...

    async def release(self, operation_id: OperationId, fingerprint: str) -> None:
        """Release an unfinished owner claim and wake concurrent callers."""

        ...


@dataclass(frozen=True, slots=True)
class SystemMonotonicClock:
    """Standard-library monotonic clock adapter for future local composition."""

    def now(self) -> float:
        return monotonic()


@dataclass(frozen=True, slots=True)
class AsyncioExecutionSleeper:
    """Standard-library local waiter; deterministic tests inject controlled doubles."""

    clock: MonotonicClock

    async def sleep(self, delay: timedelta) -> None:
        seconds = _seconds(delay)
        await asyncio.sleep(seconds)

    async def sleep_until(self, deadline: MonotonicDeadline) -> None:
        while True:
            remaining = deadline.value - _now(self.clock)
            if remaining <= 0:
                return
            await asyncio.sleep(remaining)


@dataclass(frozen=True, slots=True)
class ZeroJitter:
    """Safe production default that adds no randomness or hidden state."""

    def jitter(self, *, attempt: int, backoff: timedelta) -> timedelta:
        del attempt, backoff
        return timedelta(0)


def _seconds(value: timedelta) -> float:
    if not isinstance(value, timedelta) or value < timedelta(0):
        raise ValueError("Execution wait duration must be a non-negative timedelta.")
    seconds = value.total_seconds()
    if not math.isfinite(seconds):
        raise ValueError("Execution wait duration must be finite.")
    return seconds


def _now(clock: MonotonicClock) -> float:
    value = clock.now()
    if (
        isinstance(value, bool)
        or not isinstance(value, float)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("Monotonic clock returned an invalid value.")
    return value


__all__ = [
    "AsyncioExecutionSleeper",
    "ExecutionSleeper",
    "IdempotencyClaim",
    "IdempotencyClaimStatus",
    "IdempotencyStore",
    "JitterSource",
    "MonotonicClock",
    "StoredConnectorExecutionResult",
    "SystemMonotonicClock",
    "ZeroJitter",
]
