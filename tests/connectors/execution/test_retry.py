"""Deterministic retry, backoff, jitter, and precedence tests."""

from datetime import timedelta

import pytest

from intelligence.connectors.enums import ConnectorErrorCode, ConnectorOutcomeStatus
from intelligence.connectors.execution import ConnectorExecutionControlCode
from tests.connectors.execution.doubles import (
    ControlledConnector,
    ControlledSleeper,
    FixedJitter,
    ManualClock,
    MutableCancellationSignal,
    connector_context,
    execution_policy,
    failed_outcome,
    operation_runner,
    run_async,
    search_request,
    search_success,
)

pytestmark = pytest.mark.allow_hosts(["127.0.0.1"])


def test_unavailable_retries_then_succeeds_with_attempts_one_and_two() -> None:
    connector = ControlledConnector(
        search_values=(failed_outcome(ConnectorErrorCode.UNAVAILABLE), search_success())
    )
    sleeper = ControlledSleeper()

    result = run_async(operation_runner(sleeper=sleeper).execute(search_request(connector)))

    assert result.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert result.attempts_started == 2
    assert [context.attempt for context in connector.contexts] == [1, 2]
    assert sleeper.delays == [timedelta(seconds=1)]
    assert result.total_usage.calls == 2


def test_typed_timeout_can_retry_without_confusing_deadline_timeout() -> None:
    connector = ControlledConnector(
        search_values=(failed_outcome(ConnectorErrorCode.TIMEOUT), search_success())
    )
    sleeper = ControlledSleeper()

    result = run_async(operation_runner(sleeper=sleeper).execute(search_request(connector)))

    assert result.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert connector.operation_calls == 2
    assert sleeper.delays == [timedelta(seconds=1)]


def test_rate_limit_respects_retry_after_above_bounded_backoff() -> None:
    connector = ControlledConnector(
        search_values=(
            failed_outcome(
                ConnectorErrorCode.RATE_LIMITED,
                retry_after=timedelta(seconds=30),
            ),
            search_success(),
        )
    )
    sleeper = ControlledSleeper()
    policy = execution_policy(max_backoff=timedelta(seconds=5))

    result = run_async(
        operation_runner(sleeper=sleeper).execute(search_request(connector, policy=policy))
    )

    assert result.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert sleeper.delays == [timedelta(seconds=30)]


def test_bounded_injected_jitter_is_added_deterministically() -> None:
    connector = ControlledConnector(
        search_values=(failed_outcome(ConnectorErrorCode.UNAVAILABLE), search_success())
    )
    sleeper = ControlledSleeper()
    policy = execution_policy(max_jitter=timedelta(milliseconds=250))

    result = run_async(
        operation_runner(
            sleeper=sleeper,
            jitter=FixedJitter(timedelta(milliseconds=250)),
        ).execute(search_request(connector, policy=policy))
    )

    assert result.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert sleeper.delays == [timedelta(milliseconds=1250)]


@pytest.mark.parametrize(
    "first_outcome",
    [
        failed_outcome(ConnectorErrorCode.AUTH_REQUIRED),
        search_success(warning_message="Synthetic partial response"),
        failed_outcome(ConnectorErrorCode.INVALID_RESPONSE),
    ],
)
def test_non_retriable_or_partial_results_never_sleep(
    first_outcome: object,
) -> None:
    connector = ControlledConnector(search_values=(first_outcome, search_success()))
    sleeper = ControlledSleeper()

    result = run_async(operation_runner(sleeper=sleeper).execute(search_request(connector)))

    assert result.attempts_started == 1
    assert connector.operation_calls == 1
    assert sleeper.delays == []


def test_retry_limit_counts_first_attempt_and_stops_exactly_at_maximum() -> None:
    connector = ControlledConnector(search_values=(failed_outcome(ConnectorErrorCode.UNAVAILABLE),))
    sleeper = ControlledSleeper()
    policy = execution_policy(max_attempts=3)

    result = run_async(
        operation_runner(sleeper=sleeper).execute(search_request(connector, policy=policy))
    )

    assert result.outcome.status is ConnectorOutcomeStatus.FAILED
    assert result.attempts_started == 3
    assert connector.operation_calls == 3
    assert sleeper.delays == [timedelta(seconds=1), timedelta(seconds=2)]


def test_deadline_prevents_retry_without_backoff_sleep() -> None:
    connector = ControlledConnector(
        search_values=(failed_outcome(ConnectorErrorCode.UNAVAILABLE), search_success())
    )
    sleeper = ControlledSleeper()
    context = connector_context(deadline=100.5)

    result = run_async(
        operation_runner(clock=ManualClock(100.0), sleeper=sleeper).execute(
            search_request(connector, context=context)
        )
    )

    assert result.outcome.error is not None
    assert result.outcome.error.code is ConnectorErrorCode.TIMEOUT
    assert result.control_code is ConnectorExecutionControlCode.DEADLINE_EXPIRED
    assert connector.operation_calls == 1
    assert sleeper.delays == []


def test_cancellation_observed_after_failed_call_prevents_retry() -> None:
    signal = MutableCancellationSignal()
    connector = ControlledConnector(
        search_values=(failed_outcome(ConnectorErrorCode.UNAVAILABLE), search_success()),
        cancel_signal_after_call=signal,
    )
    sleeper = ControlledSleeper()

    result = run_async(
        operation_runner(sleeper=sleeper).execute(
            search_request(connector, context=connector_context(signal=signal))
        )
    )

    assert result.outcome.status is ConnectorOutcomeStatus.CANCELLED
    assert result.control_code is ConnectorExecutionControlCode.CANCELLATION_OBSERVED
    assert connector.operation_calls == 1
    assert sleeper.delays == []


def test_internal_error_retries_only_when_explicitly_authorized() -> None:
    unapproved = ControlledConnector(
        search_values=(RuntimeError("external exception text"), search_success())
    )
    unapproved_sleeper = ControlledSleeper()
    first = run_async(
        operation_runner(sleeper=unapproved_sleeper).execute(search_request(unapproved))
    )

    approved = ControlledConnector(
        search_values=(RuntimeError("external exception text"), search_success())
    )
    approved_sleeper = ControlledSleeper()
    approved_policy = execution_policy(retriable_codes=(ConnectorErrorCode.INTERNAL_ERROR,))
    second = run_async(
        operation_runner(sleeper=approved_sleeper).execute(
            search_request(approved, policy=approved_policy)
        )
    )

    assert first.outcome.error is not None
    assert first.outcome.error.code is ConnectorErrorCode.INTERNAL_ERROR
    assert "external exception text" not in first.outcome.error.message
    assert unapproved.operation_calls == 1
    assert unapproved_sleeper.delays == []
    assert second.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert approved.operation_calls == 2
    assert approved_sleeper.delays == [timedelta(seconds=1)]


def test_invalid_response_retries_only_when_explicitly_authorized() -> None:
    connector = ControlledConnector(
        search_values=(failed_outcome(ConnectorErrorCode.INVALID_RESPONSE), search_success())
    )
    sleeper = ControlledSleeper()
    policy = execution_policy(retriable_codes=(ConnectorErrorCode.INVALID_RESPONSE,))

    result = run_async(
        operation_runner(sleeper=sleeper).execute(search_request(connector, policy=policy))
    )

    assert result.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert connector.operation_calls == 2
    assert sleeper.delays == [timedelta(seconds=1)]
