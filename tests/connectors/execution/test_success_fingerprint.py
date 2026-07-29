"""Successful operations, canonical fingerprints, digests, and safe events."""

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from intelligence.connectors.artifacts import ArtifactPayload
from intelligence.connectors.enums import ConnectorOutcomeStatus
from intelligence.connectors.execution import ConnectorExecutionEventKind
from intelligence.connectors.execution.fingerprint import connector_request_fingerprint
from intelligence.connectors.identifiers import OperationId
from intelligence.connectors.observations import CandidateObservation, Observation
from intelligence.domain.money import Money
from tests.connectors.execution.doubles import (
    TEST_CURRENCY,
    ControlledConnector,
    CredentialDouble,
    MutableCancellationSignal,
    connector_context,
    connector_descriptor,
    details_request,
    document_request,
    operation_runner,
    run_async,
    search_request,
)
from tests.connectors.synthetic_fixtures import synthetic_query

pytestmark = pytest.mark.allow_hosts(["127.0.0.1"])


def test_runner_executes_each_typed_operation_exactly_once() -> None:
    search_connector = ControlledConnector()
    details_connector = ControlledConnector()
    document_connector = ControlledConnector()

    search = run_async(operation_runner().execute(search_request(search_connector)))
    details = run_async(operation_runner().execute(details_request(details_connector)))
    document = run_async(operation_runner().execute(document_request(document_connector)))

    assert search.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert isinstance(search.outcome.items[0], CandidateObservation)
    assert details.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert isinstance(details.outcome.items[0], Observation)
    assert document.outcome.status is ConnectorOutcomeStatus.SUCCEEDED
    assert isinstance(document.outcome.items[0], ArtifactPayload)
    assert search_connector.search_calls == 1
    assert details_connector.details_calls == 1
    assert document_connector.document_calls == 1
    assert all(result.attempts_started == 1 for result in (search, details, document))
    assert all(result.total_usage.calls == 1 for result in (search, details, document))


def test_fingerprint_is_stable_and_excludes_dynamic_context_and_secret_handle() -> None:
    descriptor = connector_descriptor(credential_ref_name="CONTROLLED_CREDENTIAL")
    first_context = connector_context(
        deadline=500.0,
        budget=Money(Decimal("10.00"), TEST_CURRENCY),
        credential=CredentialDouble("first-secret", "CONTROLLED_CREDENTIAL"),
    )
    second_signal = MutableCancellationSignal(cancelled=True)
    second_context = connector_context(
        deadline=900.0,
        budget=Money(Decimal("2.00"), TEST_CURRENCY),
        signal=second_signal,
        attempt=2,
        credential=CredentialDouble("second-secret", "CONTROLLED_CREDENTIAL"),
    )
    first = search_request(ControlledConnector(descriptor=descriptor), context=first_context)
    second = search_request(ControlledConnector(descriptor=descriptor), context=second_context)

    first_fingerprint = connector_request_fingerprint(
        first,
        descriptor,
        credential_reference="CONTROLLED_CREDENTIAL",
    )
    second_fingerprint = connector_request_fingerprint(
        second,
        descriptor,
        credential_reference="CONTROLLED_CREDENTIAL",
    )

    assert first_fingerprint == second_fingerprint
    assert len(first_fingerprint) == 64
    assert "first-secret" not in first_fingerprint
    assert "second-secret" not in second_fingerprint


def test_fingerprint_changes_for_public_request_semantics() -> None:
    descriptor = connector_descriptor()
    original = search_request(ControlledConnector())
    changed_query = replace(synthetic_query(), normalized_name="different synthetic name")
    changed = replace(original, query=changed_query)

    original_fingerprint = connector_request_fingerprint(
        original,
        descriptor,
        credential_reference=None,
    )
    changed_fingerprint = connector_request_fingerprint(
        changed,
        descriptor,
        credential_reference=None,
    )

    assert original_fingerprint != changed_fingerprint


def test_same_logical_result_has_stable_fingerprint_and_digest() -> None:
    first = run_async(operation_runner().execute(search_request(ControlledConnector())))
    second_context = connector_context(
        operation_id=OperationId.from_value("40000000-0000-4000-8000-000000000099")
    )
    second = run_async(
        operation_runner().execute(search_request(ControlledConnector(), context=second_context))
    )

    assert first.fingerprint == second.fingerprint
    assert first.digest == second.digest
    assert first.digest == first.events[-1].digest


def test_events_and_public_repr_contain_only_structural_allowlist() -> None:
    result = run_async(operation_runner().execute(search_request(ControlledConnector())))
    representation = repr(result)
    event_representation = repr(result.events)

    assert [event.kind for event in result.events] == [
        ConnectorExecutionEventKind.RESERVED,
        ConnectorExecutionEventKind.ATTEMPT_STARTED,
        ConnectorExecutionEventKind.ATTEMPT_COMPLETED,
        ConnectorExecutionEventKind.COMPLETED,
    ]
    for forbidden in (
        "Synthetic Alpha Registry Test",
        "synthetic-alpha.test",
        "TEST-REG-0001",
        "synthetic-secret-cursor",
        "token",
        "password",
        "https://",
    ):
        assert forbidden.casefold() not in representation.casefold()
        assert forbidden.casefold() not in event_representation.casefold()


def test_public_result_and_events_are_immutable() -> None:
    result = run_async(operation_runner().execute(search_request(ControlledConnector())))

    with pytest.raises(FrozenInstanceError):
        result.attempts_started = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.events[0].attempt = 2  # type: ignore[misc]
