"""Budget accounting, replay, collision, and atomic concurrency tests."""

import asyncio
from dataclasses import replace
from decimal import Decimal

import pytest

from intelligence.connectors.enums import ConnectorErrorCode, ConnectorOutcomeStatus
from intelligence.connectors.execution import (
    ConnectorExecutionControlCode,
    ConnectorExecutionIdempotencyStatus,
    ConnectorExecutionResult,
    InMemoryIdempotencyStore,
)
from intelligence.connectors.execution.ports import IdempotencyClaim, IdempotencyClaimStatus
from intelligence.connectors.identifiers import OperationId
from intelligence.connectors.observations import CandidateObservation
from intelligence.domain.money import CurrencyCode, Money
from tests.connectors.execution.doubles import (
    TEST_CURRENCY,
    ControlledConnector,
    ControlledSleeper,
    ManualClock,
    connector_context,
    connector_usage,
    failed_outcome,
    operation_runner,
    run_async,
    search_request,
    search_success,
)
from tests.connectors.synthetic_fixtures import synthetic_query

pytestmark = pytest.mark.allow_hosts(["127.0.0.1"])


def test_sufficient_and_insufficient_budget_are_checked_before_each_attempt() -> None:
    successful_connector = ControlledConnector()
    success = run_async(operation_runner().execute(search_request(successful_connector)))

    blocked_connector = ControlledConnector()
    blocked_sleeper = ControlledSleeper()
    blocked = run_async(
        operation_runner(sleeper=blocked_sleeper).execute(
            search_request(
                blocked_connector,
                context=connector_context(budget=Money(Decimal("0.50"), TEST_CURRENCY)),
            )
        )
    )

    assert success.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert success.total_usage.cost == Money(Decimal("1.00"), TEST_CURRENCY)
    assert blocked.outcome.error is not None
    assert blocked.outcome.error.code is ConnectorErrorCode.BUDGET_EXCEEDED
    assert blocked.control_code is ConnectorExecutionControlCode.BUDGET_BLOCKED
    assert blocked.attempts_started == 0
    assert blocked_connector.operation_calls == 0
    assert blocked_sleeper.delays == []


def test_budget_that_funds_one_attempt_blocks_retry_without_sleep() -> None:
    connector = ControlledConnector(
        search_values=(failed_outcome(ConnectorErrorCode.UNAVAILABLE), search_success())
    )
    sleeper = ControlledSleeper()
    context = connector_context(budget=Money(Decimal("1.50"), TEST_CURRENCY))

    result = run_async(
        operation_runner(sleeper=sleeper).execute(search_request(connector, context=context))
    )

    assert result.outcome.error is not None
    assert result.outcome.error.code is ConnectorErrorCode.BUDGET_EXCEEDED
    assert result.total_usage.cost == Money(Decimal("1.00"), TEST_CURRENCY)
    assert result.attempts_started == 1
    assert connector.operation_calls == 1
    assert sleeper.delays == []


@pytest.mark.parametrize(
    ("reported", "expected_total"),
    [
        (Decimal("0.25"), Decimal("0.25")),
        (Decimal("2.00"), Decimal("2.00")),
    ],
)
def test_actual_cost_reconciles_below_or_above_estimate(
    reported: Decimal,
    expected_total: Decimal,
) -> None:
    usage = connector_usage(cost=Money(reported, TEST_CURRENCY))
    connector = ControlledConnector(search_values=(search_success(usage=usage),))

    result = run_async(operation_runner().execute(search_request(connector)))

    assert result.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert result.total_usage.cost == Money(expected_total, TEST_CURRENCY)


def test_real_cost_overrun_is_explicit_and_never_exposes_negative_balance() -> None:
    usage = connector_usage(cost=Money(Decimal("2.00"), TEST_CURRENCY))
    connector = ControlledConnector(search_values=(search_success(usage=usage),))
    context = connector_context(budget=Money(Decimal("1.50"), TEST_CURRENCY))

    result = run_async(operation_runner().execute(search_request(connector, context=context)))

    assert result.outcome.error is not None
    assert result.outcome.error.code is ConnectorErrorCode.BUDGET_EXCEEDED
    assert result.total_usage.cost == Money(Decimal("2.00"), TEST_CURRENCY)
    assert result.total_usage.cost.amount >= 0


def test_missing_real_cost_uses_conservative_estimate() -> None:
    connector = ControlledConnector(
        search_values=(search_success(usage=connector_usage(cost=None)),)
    )

    result = run_async(operation_runner().execute(search_request(connector)))

    assert result.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert result.total_usage.cost == Money(Decimal("1.00"), TEST_CURRENCY)


def test_incompatible_reported_currency_becomes_invalid_without_conversion() -> None:
    eur = CurrencyCode("EUR")
    usage = connector_usage(cost=Money(Decimal("1.00"), eur))
    connector = ControlledConnector(search_values=(search_success(usage=usage),))

    result = run_async(operation_runner().execute(search_request(connector)))

    assert result.outcome.error is not None
    assert result.outcome.error.code is ConnectorErrorCode.INVALID_RESPONSE
    assert result.control_code is ConnectorExecutionControlCode.INVALID_CONNECTOR_RESPONSE
    assert result.total_usage.cost == Money(Decimal("1.00"), TEST_CURRENCY)


def test_usage_and_cost_accumulate_across_attempts() -> None:
    first_usage = connector_usage(cost=Money(Decimal("0.40"), TEST_CURRENCY))
    second_usage = connector_usage(cost=Money(Decimal("0.60"), TEST_CURRENCY))
    connector = ControlledConnector(
        search_values=(
            failed_outcome(ConnectorErrorCode.UNAVAILABLE, usage=first_usage),
            search_success(usage=second_usage),
        )
    )

    result = run_async(operation_runner().execute(search_request(connector)))

    assert result.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert result.total_usage.calls == 2
    assert result.total_usage.bytes_received == 256
    assert result.total_usage.cost == Money(Decimal("1.00"), TEST_CURRENCY)
    assert connector.contexts[1].budget_remaining == Money(Decimal("9.60"), TEST_CURRENCY)


def test_completed_success_and_failure_replay_without_new_call_or_charge() -> None:
    async def scenario() -> tuple[
        ConnectorExecutionResult[CandidateObservation],
        ConnectorExecutionResult[CandidateObservation],
        ConnectorExecutionResult[CandidateObservation],
        ConnectorExecutionResult[CandidateObservation],
        ControlledConnector,
        ControlledConnector,
    ]:
        success_store = InMemoryIdempotencyStore()
        success_connector = ControlledConnector()
        success_runner = operation_runner(store=success_store)
        first_success = await success_runner.execute(search_request(success_connector))
        replay_success = await success_runner.execute(search_request(success_connector))

        failure_store = InMemoryIdempotencyStore()
        failure_connector = ControlledConnector(
            search_values=(failed_outcome(ConnectorErrorCode.AUTH_REQUIRED),)
        )
        failure_runner = operation_runner(store=failure_store)
        first_failure = await failure_runner.execute(search_request(failure_connector))
        replay_failure = await failure_runner.execute(search_request(failure_connector))
        return (
            first_success,
            replay_success,
            first_failure,
            replay_failure,
            success_connector,
            failure_connector,
        )

    first_success, replay_success, first_failure, replay_failure, success, failure = run_async(
        scenario()
    )

    assert not first_success.replayed
    assert replay_success.replayed
    assert replay_success.digest == first_success.digest
    assert replay_success.total_usage == first_success.total_usage
    assert not first_failure.replayed
    assert replay_failure.replayed
    assert replay_failure.outcome == first_failure.outcome
    assert success.operation_calls == 1
    assert failure.operation_calls == 1


class ObservedIdempotencyStore(InMemoryIdempotencyStore):
    def __init__(self) -> None:
        super().__init__()
        self.waiting = asyncio.Event()

    async def reserve(self, operation_id: OperationId, fingerprint: str) -> IdempotencyClaim:
        claim = await super().reserve(operation_id, fingerprint)
        if claim.status is IdempotencyClaimStatus.WAIT:
            self.waiting.set()
        return claim


def test_concurrent_identical_calls_execute_once_and_share_logical_result() -> None:
    async def scenario() -> tuple[
        ConnectorExecutionResult[CandidateObservation],
        ConnectorExecutionResult[CandidateObservation],
        ControlledConnector,
    ]:
        store = ObservedIdempotencyStore()
        connector = ControlledConnector(block_operations=True)
        runner = operation_runner(store=store)
        request = search_request(connector)
        owner = asyncio.create_task(runner.execute(request))
        await connector.started.wait()
        follower = asyncio.create_task(runner.execute(request))
        await store.waiting.wait()
        connector.release.set()
        first, second = await asyncio.gather(owner, follower)
        return first, second, connector

    first, second, connector = run_async(scenario())

    assert connector.operation_calls == 1
    assert first.outcome == second.outcome
    assert first.digest == second.digest
    assert first.total_usage == second.total_usage
    assert {first.idempotency_status, second.idempotency_status} == {
        ConnectorExecutionIdempotencyStatus.EXECUTED,
        ConnectorExecutionIdempotencyStatus.REPLAYED,
    }


def test_idempotency_follower_observes_its_own_deadline_without_duplicate_call() -> None:
    async def scenario() -> tuple[
        ConnectorExecutionResult[CandidateObservation],
        ConnectorExecutionResult[CandidateObservation],
        ControlledConnector,
    ]:
        store = ObservedIdempotencyStore()
        connector = ControlledConnector(block_operations=True)
        owner_sleeper = ControlledSleeper()
        owner = asyncio.create_task(
            operation_runner(store=store, sleeper=owner_sleeper).execute(search_request(connector))
        )
        await connector.started.wait()

        follower_clock = ManualClock()
        follower_sleeper = ControlledSleeper()
        follower = asyncio.create_task(
            operation_runner(
                store=store,
                clock=follower_clock,
                sleeper=follower_sleeper,
            ).execute(
                search_request(
                    connector,
                    context=connector_context(deadline=200.0),
                )
            )
        )
        await store.waiting.wait()
        await follower_sleeper.deadline_started.wait()
        follower_clock.value = 200.0
        follower_sleeper.deadline_release.set()
        timed_out = await follower

        connector.release.set()
        completed = await owner
        return completed, timed_out, connector

    completed, timed_out, connector = run_async(scenario())

    assert completed.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert timed_out.outcome.status is ConnectorOutcomeStatus.FAILED
    assert timed_out.outcome.error is not None
    assert timed_out.outcome.error.code is ConnectorErrorCode.TIMEOUT
    assert timed_out.attempts_started == 0
    assert connector.operation_calls == 1


def test_cancelled_idempotency_follower_does_not_release_owner_reservation() -> None:
    async def scenario() -> tuple[
        ConnectorExecutionResult[CandidateObservation], ControlledConnector
    ]:
        store = ObservedIdempotencyStore()
        connector = ControlledConnector(block_operations=True)
        runner = operation_runner(store=store)
        request = search_request(connector)
        owner = asyncio.create_task(runner.execute(request))
        await connector.started.wait()
        follower = asyncio.create_task(runner.execute(request))
        await store.waiting.wait()

        follower.cancel()
        with pytest.raises(asyncio.CancelledError):
            await follower
        connector.release.set()
        return await owner, connector

    completed, connector = run_async(scenario())

    assert completed.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert connector.operation_calls == 1


def test_idempotency_wait_rejects_sleeper_that_returns_before_deadline() -> None:
    async def scenario() -> ConnectorExecutionResult[CandidateObservation]:
        store = ObservedIdempotencyStore()
        connector = ControlledConnector(block_operations=True)
        owner = asyncio.create_task(
            operation_runner(store=store).execute(search_request(connector))
        )
        await connector.started.wait()

        follower_sleeper = ControlledSleeper()
        follower = asyncio.create_task(
            operation_runner(store=store, sleeper=follower_sleeper).execute(
                search_request(connector)
            )
        )
        await store.waiting.wait()
        await follower_sleeper.deadline_started.wait()
        follower_sleeper.deadline_release.set()
        with pytest.raises(RuntimeError, match="sleeper returned before"):
            await follower

        connector.release.set()
        return await owner

    completed = run_async(scenario())

    assert completed.outcome.status is ConnectorOutcomeStatus.SUCCEEDED


def test_same_operation_id_with_different_fingerprint_is_typed_conflict() -> None:
    async def scenario() -> tuple[
        ConnectorExecutionResult[CandidateObservation],
        ConnectorExecutionResult[CandidateObservation],
        ControlledConnector,
    ]:
        store = InMemoryIdempotencyStore()
        connector = ControlledConnector()
        runner = operation_runner(store=store)
        first = await runner.execute(search_request(connector))
        changed_query = replace(
            synthetic_query(),
            normalized_name="different synthetic execution request",
        )
        conflict = await runner.execute(search_request(connector, query=changed_query))
        return first, conflict, connector

    first, conflict, connector = run_async(scenario())

    assert first.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert conflict.idempotency_status is ConnectorExecutionIdempotencyStatus.CONFLICT
    assert conflict.control_code is ConnectorExecutionControlCode.IDEMPOTENCY_CONFLICT
    assert conflict.outcome.error is not None
    assert conflict.outcome.error.code is ConnectorErrorCode.INVALID_REQUEST
    assert conflict.attempts_started == 0
    assert connector.operation_calls == 1


def test_independent_stores_never_share_global_state() -> None:
    connector = ControlledConnector()
    first = run_async(operation_runner().execute(search_request(connector)))
    changed_query = replace(
        synthetic_query(),
        normalized_name="independent synthetic request",
    )
    second = run_async(operation_runner().execute(search_request(connector, query=changed_query)))

    assert first.outcome.status is second.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert connector.operation_calls == 2


def test_external_owner_cancellation_releases_reservation_for_next_caller() -> None:
    async def scenario() -> tuple[
        ConnectorExecutionResult[CandidateObservation], ControlledConnector
    ]:
        store = ObservedIdempotencyStore()
        blocked = ControlledConnector(block_operations=True)
        owner = asyncio.create_task(operation_runner(store=store).execute(search_request(blocked)))
        await blocked.started.wait()
        replacement = ControlledConnector()
        follower = asyncio.create_task(
            operation_runner(store=store).execute(search_request(replacement))
        )
        await store.waiting.wait()
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner

        completed = await follower
        return completed, replacement

    completed, replacement = run_async(scenario())

    assert completed.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert replacement.operation_calls == 1
