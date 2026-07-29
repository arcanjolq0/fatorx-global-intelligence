"""Defensive public contract, local port, and idempotency-store tests."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import cast

import pytest

from intelligence.connectors.context import MonotonicDeadline
from intelligence.connectors.enums import (
    ConnectorErrorCode,
    ConnectorOutcomeStatus,
    ConnectorWarningCode,
)
from intelligence.connectors.execution import (
    AsyncioExecutionSleeper,
    ConnectorExecutionEvent,
    ConnectorExecutionEventKind,
    ConnectorExecutionIdempotencyStatus,
    ConnectorExecutionMetadata,
    ConnectorExecutionPolicy,
    ConnectorExecutionPolicyVersion,
    ConnectorExecutionResult,
    IdempotencyConflictError,
    IdempotencyStoreError,
    InMemoryIdempotencyStore,
    InvalidConnectorExecutionPolicyError,
    SystemMonotonicClock,
    ZeroJitter,
)
from intelligence.connectors.execution.policies import validate_execution_policy
from intelligence.connectors.execution.ports import (
    IdempotencyClaim,
    IdempotencyClaimStatus,
    StoredConnectorExecutionResult,
)
from intelligence.connectors.identifiers import ConnectorId, OperationId
from intelligence.domain.money import CurrencyCode, Money
from tests.connectors.execution.doubles import (
    ControlledConnector,
    ManualClock,
    connector_context,
    execution_policy,
    operation_runner,
    run_async,
    search_request,
)

pytestmark = pytest.mark.allow_hosts(["127.0.0.1"])


def test_event_rejects_every_incompatible_public_field() -> None:
    result = run_async(operation_runner().execute(search_request(ControlledConnector())))
    event = result.events[0]
    invalid_changes: tuple[dict[str, object], ...] = (
        {"kind": "RESERVED"},
        {"metadata": object()},
        {"fingerprint": "invalid"},
        {"attempt": 0},
        {"attempt": True},
        {"delay": timedelta(seconds=-1)},
        {"delay": "one second"},
        {"status": "FAILED"},
        {"error_code": "TIMEOUT"},
        {"total_cost": "1 USD"},
        {"total_cost": Money(Decimal("-1"), CurrencyCode("USD"))},
        {"digest": "invalid"},
        {"warning_codes": ("TRUNCATED",)},
    )

    for changes in invalid_changes:
        with pytest.raises((TypeError, ValueError)):
            replace(event, **changes)  # type: ignore[arg-type]


def test_result_and_metadata_reject_incompatible_public_fields() -> None:
    result = run_async(operation_runner().execute(search_request(ControlledConnector())))
    invalid_result_changes: tuple[dict[str, object], ...] = (
        {"outcome": "invalid"},
        {"attempts_started": -1},
        {"attempts_started": True},
        {"total_usage": "invalid"},
        {"fingerprint": "invalid"},
        {"digest": "invalid"},
        {"events": ("invalid",)},
        {"idempotency_status": "EXECUTED"},
        {"metadata": object()},
        {"control_code": "TIMEOUT"},
    )
    for changes in invalid_result_changes:
        with pytest.raises((TypeError, ValueError)):
            replace(result, **changes)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        replace(result.metadata, connector_id=cast(ConnectorId, "connector"))


@pytest.mark.parametrize("value", ["", "bad version", "x" * 65, 1])
def test_execution_policy_version_is_canonical(value: object) -> None:
    with pytest.raises(InvalidConnectorExecutionPolicyError):
        ConnectorExecutionPolicyVersion(cast(str, value))
    assert str(ConnectorExecutionPolicyVersion("policy-1")) == "policy-1"


def test_runtime_policy_revalidation_rejects_corrupted_types_and_negative_cost() -> None:
    with pytest.raises(InvalidConnectorExecutionPolicyError):
        validate_execution_policy(cast(ConnectorExecutionPolicy, object()))

    wrong_version = execution_policy()
    object.__setattr__(wrong_version, "version", "policy-1")
    with pytest.raises(InvalidConnectorExecutionPolicyError):
        validate_execution_policy(wrong_version)

    wrong_retry_collection = execution_policy()
    object.__setattr__(wrong_retry_collection, "retriable_codes", (ConnectorErrorCode.TIMEOUT,))
    with pytest.raises(InvalidConnectorExecutionPolicyError):
        validate_execution_policy(wrong_retry_collection)

    wrong_cost_type = execution_policy()
    object.__setattr__(wrong_cost_type, "estimated_attempt_cost", Decimal("1"))
    with pytest.raises(InvalidConnectorExecutionPolicyError):
        validate_execution_policy(wrong_cost_type)

    with pytest.raises(InvalidConnectorExecutionPolicyError):
        execution_policy(estimated_attempt_cost=Money(Decimal("-1"), CurrencyCode("USD")))


def test_claim_contract_rejects_invalid_status_result_combinations() -> None:
    result = run_async(operation_runner().execute(search_request(ControlledConnector())))
    stored = cast(StoredConnectorExecutionResult, result)

    with pytest.raises(ValueError):
        IdempotencyClaim(status=cast(IdempotencyClaimStatus, "UNKNOWN"))
    with pytest.raises(ValueError):
        IdempotencyClaim(status=IdempotencyClaimStatus.COMPLETED)
    with pytest.raises(ValueError):
        IdempotencyClaim(status=IdempotencyClaimStatus.ACQUIRED, result=stored)


def test_zero_jitter_and_system_clock_implement_local_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jitter = ZeroJitter()
    clock = SystemMonotonicClock()
    monkeypatch.setattr("intelligence.connectors.execution.ports.monotonic", lambda: 42.0)

    assert jitter.jitter(attempt=2, backoff=timedelta(seconds=3)) == timedelta(0)
    assert clock.now() == 42.0


def test_asyncio_sleeper_validates_delay_and_uses_injected_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        calls.append(seconds)

    class SequenceClock:
        def __init__(self) -> None:
            self.values = iter((100.0, 101.0))

        def now(self) -> float:
            return next(self.values)

    monkeypatch.setattr("intelligence.connectors.execution.ports.asyncio.sleep", fake_sleep)

    async def scenario() -> None:
        sleeper = AsyncioExecutionSleeper(SequenceClock())
        sleep_for = sleeper.sleep
        await sleep_for(timedelta(milliseconds=250))
        await sleeper.sleep_until(MonotonicDeadline(101.0))

    run_async(scenario())

    assert calls == [0.25, 1.0]
    with pytest.raises(ValueError):
        sleep_for = AsyncioExecutionSleeper(ManualClock()).sleep
        run_async(sleep_for(timedelta(seconds=-1)))


@pytest.mark.parametrize("value", [True, 1, float("inf"), -1.0])
def test_asyncio_sleeper_rejects_invalid_monotonic_clock_values(value: object) -> None:
    class InvalidClock:
        def now(self) -> float:
            return cast(float, value)

    with pytest.raises(ValueError):
        run_async(AsyncioExecutionSleeper(InvalidClock()).sleep_until(MonotonicDeadline(100.0)))


def test_in_memory_store_validates_keys_completion_and_release() -> None:
    result = run_async(operation_runner().execute(search_request(ControlledConnector())))
    stored = cast(StoredConnectorExecutionResult, result)
    operation_id = connector_context().operation_id
    fingerprint = "a" * 64

    async def scenario() -> None:
        store = InMemoryIdempotencyStore()
        assert await store.wait(operation_id, fingerprint) is None
        await store.release(operation_id, fingerprint)
        with pytest.raises(IdempotencyStoreError):
            await store.reserve(cast(OperationId, "invalid"), fingerprint)
        with pytest.raises(IdempotencyStoreError):
            await store.reserve(operation_id, "invalid")
        claim = await store.reserve(operation_id, fingerprint)
        assert claim.status is IdempotencyClaimStatus.ACQUIRED
        await store.complete(operation_id, fingerprint, stored)
        assert await store.wait(operation_id, fingerprint) == stored
        completed = await store.reserve(operation_id, fingerprint)
        assert completed.status is IdempotencyClaimStatus.COMPLETED
        await store.release(operation_id, fingerprint)
        with pytest.raises(IdempotencyStoreError):
            await store.complete(operation_id, fingerprint, stored)
        with pytest.raises(IdempotencyConflictError):
            await store.wait(operation_id, "b" * 64)

        missing = InMemoryIdempotencyStore()
        with pytest.raises(IdempotencyStoreError):
            await missing.complete(operation_id, fingerprint, stored)

    run_async(scenario())


def test_released_waiter_observes_none_and_can_reserve_again() -> None:
    async def scenario() -> None:
        store = InMemoryIdempotencyStore()
        operation_id = connector_context().operation_id
        fingerprint = "a" * 64
        await store.reserve(operation_id, fingerprint)
        waiter = asyncio.create_task(store.wait(operation_id, fingerprint))
        await store.release(operation_id, fingerprint)
        assert await waiter is None
        claim = await store.reserve(operation_id, fingerprint)
        assert claim.status is IdempotencyClaimStatus.ACQUIRED

    run_async(scenario())


def test_valid_event_can_include_closed_status_warning_and_digest() -> None:
    result = run_async(operation_runner().execute(search_request(ControlledConnector())))
    metadata: ConnectorExecutionMetadata = result.metadata
    event = ConnectorExecutionEvent(
        kind=ConnectorExecutionEventKind.COMPLETED,
        metadata=metadata,
        fingerprint="a" * 64,
        attempt=1,
        status=ConnectorOutcomeStatus.PARTIAL,
        error_code=ConnectorErrorCode.UNAVAILABLE,
        warning_codes=(ConnectorWarningCode.TRUNCATED,),
        delay=timedelta(0),
        total_cost=Money(Decimal("1"), CurrencyCode("USD")),
        digest="b" * 64,
    )

    assert event.warning_codes == (ConnectorWarningCode.TRUNCATED,)
    assert result.idempotency_status is ConnectorExecutionIdempotencyStatus.EXECUTED
    assert result.control_code is None
    assert isinstance(result, ConnectorExecutionResult)
