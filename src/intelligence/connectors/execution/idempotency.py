"""Atomic in-memory idempotency adapter for one asynchronous process."""

import asyncio
import re
from dataclasses import dataclass

from intelligence.connectors.execution.errors import (
    IdempotencyConflictError,
    IdempotencyStoreError,
)
from intelligence.connectors.execution.ports import (
    IdempotencyClaim,
    IdempotencyClaimStatus,
    StoredConnectorExecutionResult,
)
from intelligence.connectors.identifiers import OperationId

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


@dataclass(slots=True)
class _Entry:
    fingerprint: str
    completed: StoredConnectorExecutionResult | None
    changed: asyncio.Event


class InMemoryIdempotencyStore:
    """Instance-scoped store coordinating equal concurrent requests atomically."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._entries: dict[OperationId, _Entry] = {}

    async def reserve(self, operation_id: OperationId, fingerprint: str) -> IdempotencyClaim:
        _validate_key(operation_id, fingerprint)
        async with self._lock:
            entry = self._entries.get(operation_id)
            if entry is None:
                self._entries[operation_id] = _Entry(
                    fingerprint=fingerprint,
                    completed=None,
                    changed=asyncio.Event(),
                )
                return IdempotencyClaim(status=IdempotencyClaimStatus.ACQUIRED)
            _require_matching_fingerprint(entry, fingerprint)
            if entry.completed is not None:
                return IdempotencyClaim(
                    status=IdempotencyClaimStatus.COMPLETED,
                    result=entry.completed,
                )
            return IdempotencyClaim(status=IdempotencyClaimStatus.WAIT)

    async def wait(
        self,
        operation_id: OperationId,
        fingerprint: str,
    ) -> StoredConnectorExecutionResult | None:
        _validate_key(operation_id, fingerprint)
        while True:
            async with self._lock:
                entry = self._entries.get(operation_id)
                if entry is None:
                    return None
                _require_matching_fingerprint(entry, fingerprint)
                if entry.completed is not None:
                    return entry.completed
                changed = entry.changed
            await changed.wait()

    async def complete(
        self,
        operation_id: OperationId,
        fingerprint: str,
        result: StoredConnectorExecutionResult,
    ) -> None:
        _validate_key(operation_id, fingerprint)
        async with self._lock:
            entry = self._entries.get(operation_id)
            if entry is None:
                raise IdempotencyStoreError(
                    "Cannot complete an idempotency operation without an active reservation."
                )
            _require_matching_fingerprint(entry, fingerprint)
            if entry.completed is not None:
                raise IdempotencyStoreError(
                    "Cannot complete an idempotency operation more than once."
                )
            entry.completed = result
            entry.changed.set()

    async def release(self, operation_id: OperationId, fingerprint: str) -> None:
        _validate_key(operation_id, fingerprint)
        async with self._lock:
            entry = self._entries.get(operation_id)
            if entry is None:
                return
            _require_matching_fingerprint(entry, fingerprint)
            if entry.completed is not None:
                return
            del self._entries[operation_id]
            entry.changed.set()


def _validate_key(operation_id: OperationId, fingerprint: str) -> None:
    if not isinstance(operation_id, OperationId):
        raise IdempotencyStoreError("Idempotency operation identifier has an invalid type.")
    if not isinstance(fingerprint, str) or _SHA256_PATTERN.fullmatch(fingerprint) is None:
        raise IdempotencyStoreError("Idempotency fingerprint must be a canonical SHA-256 digest.")


def _require_matching_fingerprint(entry: _Entry, fingerprint: str) -> None:
    if entry.fingerprint != fingerprint:
        raise IdempotencyConflictError(
            "Operation identifier is already reserved for a different request."
        )


__all__ = ["InMemoryIdempotencyStore"]
