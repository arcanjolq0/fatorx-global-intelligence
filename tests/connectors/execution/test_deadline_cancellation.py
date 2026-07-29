"""Event-synchronized deadline and cooperative cancellation races."""

import asyncio

import pytest

from intelligence.connectors.context import ConnectorContext
from intelligence.connectors.enums import ConnectorErrorCode, ConnectorOutcomeStatus
from intelligence.connectors.execution import (
    ConnectorExecutionControlCode,
    ConnectorExecutionResult,
)
from intelligence.connectors.observations import CandidateObservation
from intelligence.connectors.outcomes import ConnectorOutcome
from intelligence.connectors.queries import CompanyQuery
from tests.connectors.execution.doubles import (
    ControlledConnector,
    ControlledSleeper,
    ManualClock,
    MutableCancellationSignal,
    connector_context,
    failed_outcome,
    operation_runner,
    run_async,
    search_request,
    search_success,
)

pytestmark = pytest.mark.allow_hosts(["127.0.0.1"])


def test_deadline_cancels_and_awaits_blocked_connector_task() -> None:
    async def scenario() -> tuple[
        ConnectorExecutionResult[CandidateObservation], ControlledConnector
    ]:
        clock = ManualClock(100.0)
        sleeper = ControlledSleeper()
        connector = ControlledConnector(block_operations=True)
        task = asyncio.create_task(
            operation_runner(clock=clock, sleeper=sleeper).execute(
                search_request(connector, context=connector_context(deadline=150.0))
            )
        )
        await connector.started.wait()
        await sleeper.deadline_started.wait()
        clock.value = 150.0
        sleeper.deadline_release.set()
        result = await task
        return result, connector

    result, connector = run_async(scenario())

    assert result.outcome.status is ConnectorOutcomeStatus.FAILED
    assert result.outcome.error is not None
    assert result.outcome.error.code is ConnectorErrorCode.TIMEOUT
    assert result.control_code is ConnectorExecutionControlCode.DEADLINE_EXPIRED
    assert result.attempts_started == 1
    assert connector.task_cancelled.is_set()
    assert connector.operation_calls == 1


class LateSuccessConnector(ControlledConnector):
    """Ignore task cancellation once to prove late content is discarded."""

    async def search(
        self,
        query: CompanyQuery,
        context: ConnectorContext,
    ) -> ConnectorOutcome[CandidateObservation]:
        del query
        self.search_calls += 1
        self.operation_calls += 1
        self.contexts.append(context)
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.task_cancelled.set()
            return search_success()
        return search_success()


def test_late_success_after_deadline_is_never_published() -> None:
    async def scenario() -> tuple[
        ConnectorExecutionResult[CandidateObservation], LateSuccessConnector
    ]:
        clock = ManualClock(100.0)
        sleeper = ControlledSleeper()
        connector = LateSuccessConnector(block_operations=True)
        task = asyncio.create_task(
            operation_runner(clock=clock, sleeper=sleeper).execute(
                search_request(connector, context=connector_context(deadline=150.0))
            )
        )
        await connector.started.wait()
        await sleeper.deadline_started.wait()
        clock.value = 150.0
        sleeper.deadline_release.set()
        result = await task
        return result, connector

    result, connector = run_async(scenario())

    assert result.outcome.status is ConnectorOutcomeStatus.FAILED
    assert result.outcome.items == ()
    assert result.outcome.error is not None
    assert result.outcome.error.code is ConnectorErrorCode.TIMEOUT
    assert connector.task_cancelled.is_set()


def test_cancellation_during_call_discards_success_without_retry() -> None:
    async def scenario() -> tuple[
        ConnectorExecutionResult[CandidateObservation],
        ControlledConnector,
        ControlledSleeper,
    ]:
        signal = MutableCancellationSignal()
        sleeper = ControlledSleeper()
        connector = ControlledConnector(block_operations=True)
        task = asyncio.create_task(
            operation_runner(sleeper=sleeper).execute(
                search_request(
                    connector,
                    context=connector_context(signal=signal),
                )
            )
        )
        await connector.started.wait()
        signal.cancel()
        connector.release.set()
        result = await task
        return result, connector, sleeper

    result, connector, sleeper = run_async(scenario())

    assert result.outcome.status is ConnectorOutcomeStatus.CANCELLED
    assert result.outcome.items == ()
    assert result.outcome.artifacts == ()
    assert result.outcome.error is not None
    assert result.outcome.error.code is ConnectorErrorCode.CANCELLED
    assert result.control_code is ConnectorExecutionControlCode.CANCELLATION_OBSERVED
    assert connector.operation_calls == 1
    assert sleeper.delays == []


def test_cancellation_during_backoff_stops_before_second_attempt() -> None:
    async def scenario() -> tuple[
        ConnectorExecutionResult[CandidateObservation],
        ControlledConnector,
        ControlledSleeper,
    ]:
        signal = MutableCancellationSignal()
        sleeper = ControlledSleeper(block_backoff=True)
        connector = ControlledConnector(
            search_values=(failed_outcome(ConnectorErrorCode.UNAVAILABLE), search_success())
        )
        task = asyncio.create_task(
            operation_runner(sleeper=sleeper).execute(
                search_request(connector, context=connector_context(signal=signal))
            )
        )
        await sleeper.backoff_started.wait()
        signal.cancel()
        sleeper.backoff_release.set()
        result = await task
        return result, connector, sleeper

    result, connector, sleeper = run_async(scenario())

    assert result.outcome.status is ConnectorOutcomeStatus.CANCELLED
    assert connector.operation_calls == 1
    assert len(sleeper.delays) == 1


def test_deadline_expiring_during_backoff_stops_before_second_attempt() -> None:
    async def scenario() -> tuple[
        ConnectorExecutionResult[CandidateObservation], ControlledConnector
    ]:
        clock = ManualClock(100.0)
        sleeper = ControlledSleeper(block_backoff=True)
        connector = ControlledConnector(
            search_values=(failed_outcome(ConnectorErrorCode.UNAVAILABLE), search_success())
        )
        task = asyncio.create_task(
            operation_runner(clock=clock, sleeper=sleeper).execute(
                search_request(connector, context=connector_context(deadline=200.0))
            )
        )
        await sleeper.backoff_started.wait()
        clock.value = 200.0
        sleeper.backoff_release.set()
        result = await task
        return result, connector

    result, connector = run_async(scenario())

    assert result.outcome.error is not None
    assert result.outcome.error.code is ConnectorErrorCode.TIMEOUT
    assert result.control_code is ConnectorExecutionControlCode.DEADLINE_EXPIRED
    assert connector.operation_calls == 1
