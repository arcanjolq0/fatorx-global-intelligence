"""Policy invariants and no-I/O preflight tests for F3.3."""

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
from typing import cast

import pytest

from intelligence.connectors.enums import (
    ConnectorCapability,
    ConnectorErrorCode,
    ConnectorOperation,
    ConnectorOutcomeStatus,
)
from intelligence.connectors.execution import (
    ConnectorExecutionControlCode,
    ConnectorExecutionPolicy,
    ConnectorExecutionPolicyVersion,
    ConnectorExecutionPreflightError,
    InvalidConnectorExecutionPolicyError,
)
from intelligence.connectors.execution.contracts import ConnectorOperationRequest
from intelligence.connectors.queries import CompanyQuery
from intelligence.domain.geography import CountryCode
from intelligence.domain.money import CurrencyCode, Money
from tests.connectors.execution.doubles import (
    ControlledConnector,
    ControlledSleeper,
    CredentialDouble,
    FixedJitter,
    ManualClock,
    MutableCancellationSignal,
    connector_context,
    connector_descriptor,
    details_request,
    execution_policy,
    operation_runner,
    run_async,
    search_request,
)
from tests.connectors.execution.doubles import (
    test_candidate as make_candidate,
)

pytestmark = pytest.mark.allow_hosts(["127.0.0.1"])


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_attempts": 0},
        {"max_attempts": 6},
        {"retriable_codes": (ConnectorErrorCode.AUTH_REQUIRED,)},
        {"base_backoff": timedelta(seconds=-1)},
        {
            "base_backoff": timedelta(seconds=2),
            "max_backoff": timedelta(seconds=1),
        },
        {"max_jitter": timedelta(minutes=6)},
        {"max_items": 0},
        {"max_artifacts": 101},
    ],
)
def test_policy_rejects_unbounded_or_forbidden_values(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "version": ConnectorExecutionPolicyVersion("policy-1"),
        "max_attempts": 3,
        "retriable_codes": (ConnectorErrorCode.UNAVAILABLE,),
        "base_backoff": timedelta(seconds=1),
        "max_backoff": timedelta(seconds=30),
        "max_jitter": timedelta(0),
        "estimated_attempt_cost": Money(Decimal("1.00"), CurrencyCode("USD")),
        "max_items": 10,
        "max_artifacts": 10,
    }
    values.update(overrides)

    with pytest.raises(InvalidConnectorExecutionPolicyError):
        ConnectorExecutionPolicy(**values)  # type: ignore[arg-type]


def test_policy_and_operation_requests_are_immutable_and_hide_input() -> None:
    policy = execution_policy()
    request = search_request(ControlledConnector(), policy=policy)

    with pytest.raises(FrozenInstanceError):
        policy.max_attempts = 4  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        request.country = CountryCode("US")  # type: ignore[misc]
    assert "Synthetic Alpha Registry Test" not in repr(request)


def test_unsupported_country_capability_operation_and_mode_fail_before_io() -> None:
    cases: tuple[ConnectorOperationRequest, ...] = (
        search_request(ControlledConnector(), country=CountryCode("US")),
        search_request(
            ControlledConnector(),
            capability=ConnectorCapability.OWNERSHIP,
        ),
        details_request(
            ControlledConnector(
                descriptor=connector_descriptor(operations=(ConnectorOperation.SEARCH,))
            )
        ),
        search_request(
            ControlledConnector(descriptor=connector_descriptor(supports_test_mode=False))
        ),
    )
    expected_codes = (
        ConnectorErrorCode.UNSUPPORTED_COUNTRY,
        ConnectorErrorCode.UNSUPPORTED_CAPABILITY,
        ConnectorErrorCode.UNSUPPORTED_OPERATION,
        ConnectorErrorCode.POLICY_BLOCKED,
    )

    for request, expected_code in zip(cases, expected_codes, strict=True):
        sleeper = ControlledSleeper()
        with pytest.raises(ConnectorExecutionPreflightError) as raised:
            run_async(operation_runner(sleeper=sleeper).execute(request))
        assert raised.value.code is expected_code
        assert cast(ControlledConnector, request.connector).operation_calls == 0
        assert sleeper.delays == []
        assert sleeper.deadline_waits == []


def test_wrong_input_and_foreign_candidate_fail_before_io() -> None:
    wrong_input_connector = ControlledConnector()
    wrong_input = replace(
        search_request(wrong_input_connector),
        query=cast(CompanyQuery, make_candidate()),
    )
    foreign_connector = ControlledConnector()
    foreign_candidate = make_candidate(
        connector_id=type(foreign_connector.descriptor.connector_id)("controlled.other")
    )
    requests: tuple[ConnectorOperationRequest, ...] = (
        wrong_input,
        details_request(foreign_connector, candidate=foreign_candidate),
    )

    for request in requests:
        sleeper = ControlledSleeper()
        with pytest.raises(ConnectorExecutionPreflightError) as raised:
            run_async(operation_runner(sleeper=sleeper).execute(request))
        assert raised.value.code is ConnectorErrorCode.INVALID_REQUEST
        assert cast(ControlledConnector, request.connector).operation_calls == 0
        assert sleeper.delays == []
        assert sleeper.deadline_waits == []


def test_credential_is_required_only_for_declared_matching_reference() -> None:
    required_descriptor = connector_descriptor(credential_ref_name="CONTROLLED_CREDENTIAL")
    missing = ControlledConnector(descriptor=required_descriptor)
    wrong = ControlledConnector(descriptor=required_descriptor)
    undeclared = ControlledConnector()
    cases: tuple[ConnectorOperationRequest, ...] = (
        search_request(missing),
        search_request(
            wrong,
            context=connector_context(
                credential=CredentialDouble("secret-value", "WRONG_CREDENTIAL")
            ),
        ),
        search_request(
            undeclared,
            context=connector_context(
                credential=CredentialDouble("secret-value", "CONTROLLED_CREDENTIAL")
            ),
        ),
    )
    expected = (
        ConnectorErrorCode.AUTH_REQUIRED,
        ConnectorErrorCode.AUTH_REQUIRED,
        ConnectorErrorCode.INVALID_REQUEST,
    )

    for request, code in zip(cases, expected, strict=True):
        sleeper = ControlledSleeper()
        with pytest.raises(ConnectorExecutionPreflightError) as raised:
            run_async(operation_runner(sleeper=sleeper).execute(request))
        assert raised.value.code is code
        assert "secret-value" not in str(raised.value)
        assert cast(ControlledConnector, request.connector).operation_calls == 0
        assert sleeper.delays == []


def test_budget_policy_and_currency_mismatch_fail_before_io() -> None:
    connector_without_estimate = ControlledConnector()
    connector_wrong_currency = ControlledConnector()
    requests: tuple[ConnectorOperationRequest, ...] = (
        search_request(
            connector_without_estimate,
            policy=execution_policy(estimated_attempt_cost=None),
        ),
        search_request(
            connector_wrong_currency,
            policy=execution_policy(
                estimated_attempt_cost=Money(Decimal("1.00"), CurrencyCode("EUR"))
            ),
        ),
    )

    for request in requests:
        sleeper = ControlledSleeper()
        with pytest.raises(ConnectorExecutionPreflightError) as raised:
            run_async(operation_runner(sleeper=sleeper).execute(request))
        assert raised.value.code is ConnectorErrorCode.INVALID_REQUEST
        assert cast(ControlledConnector, request.connector).operation_calls == 0
        assert sleeper.delays == []


def test_expired_deadline_and_precancelled_signal_publish_no_content_or_io() -> None:
    expired_connector = ControlledConnector()
    expired_sleeper = ControlledSleeper()
    expired = run_async(
        operation_runner(clock=ManualClock(100.0), sleeper=expired_sleeper).execute(
            search_request(expired_connector, context=connector_context(deadline=100.0))
        )
    )
    signal = MutableCancellationSignal(cancelled=True)
    cancelled_connector = ControlledConnector()
    cancelled_sleeper = ControlledSleeper()
    cancelled = run_async(
        operation_runner(sleeper=cancelled_sleeper).execute(
            search_request(cancelled_connector, context=connector_context(signal=signal))
        )
    )

    assert expired.outcome.status is ConnectorOutcomeStatus.FAILED
    assert expired.outcome.error is not None
    assert expired.outcome.error.code is ConnectorErrorCode.TIMEOUT
    assert expired.control_code is ConnectorExecutionControlCode.DEADLINE_EXPIRED
    assert cancelled.outcome.status is ConnectorOutcomeStatus.CANCELLED
    assert cancelled.control_code is ConnectorExecutionControlCode.CANCELLATION_OBSERVED
    assert expired_connector.operation_calls == cancelled_connector.operation_calls == 0
    assert expired_sleeper.delays == cancelled_sleeper.delays == []
    assert expired_sleeper.deadline_waits == cancelled_sleeper.deadline_waits == []


def test_jitter_port_is_structurally_required_without_global_randomness() -> None:
    connector = ControlledConnector()
    runner = operation_runner(jitter=FixedJitter(timedelta(milliseconds=25)))

    result = run_async(runner.execute(search_request(connector)))

    assert result.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
