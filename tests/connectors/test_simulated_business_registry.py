"""Scenario-specific tests for the deterministic synthetic business registry."""

from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest

from intelligence.connectors.artifacts import ArtifactReference
from intelligence.connectors.enums import (
    ArtifactRetentionMode,
    ConnectorCapability,
    ConnectorErrorCode,
    ConnectorOperation,
    ConnectorOutcomeStatus,
)
from intelligence.connectors.identifiers import ArtifactRefId, OriginReferenceId
from intelligence.connectors.observations import CandidateObservation, Observation
from intelligence.connectors.protocol import Connector
from intelligence.connectors.simulated import (
    SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID,
    SIMULATED_BUSINESS_REGISTRY_SOURCE_ID,
    BusinessRegistryScenario,
    SimulatedBusinessRegistryConnector,
)
from tests.connectors.synthetic_fixtures import (
    run_immediate,
    synthetic_candidate,
    synthetic_context,
    synthetic_query,
)

_FAILURE_SCENARIOS = (
    (BusinessRegistryScenario.RATE_LIMITED, ConnectorErrorCode.RATE_LIMITED),
    (BusinessRegistryScenario.TIMEOUT, ConnectorErrorCode.TIMEOUT),
    (BusinessRegistryScenario.UNAVAILABLE, ConnectorErrorCode.UNAVAILABLE),
    (BusinessRegistryScenario.INVALID_RESPONSE, ConnectorErrorCode.INVALID_RESPONSE),
    (BusinessRegistryScenario.POLICY_BLOCKED, ConnectorErrorCode.POLICY_BLOCKED),
    (BusinessRegistryScenario.BUDGET_EXCEEDED, ConnectorErrorCode.BUDGET_EXCEEDED),
)


def test_descriptor_is_stable_explicit_and_does_not_declare_documents() -> None:
    connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.SUCCESS)
    descriptor = connector.describe()

    assert isinstance(connector, Connector)
    assert descriptor is connector.describe()
    assert descriptor.connector_id == SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID
    assert descriptor.source_id == SIMULATED_BUSINESS_REGISTRY_SOURCE_ID
    assert descriptor.capabilities == frozenset(
        {
            ConnectorCapability.COMPANY_IDENTITY,
            ConnectorCapability.COMPANY_REGISTRY,
        }
    )
    assert descriptor.operations == frozenset(
        {ConnectorOperation.SEARCH, ConnectorOperation.FETCH_DETAILS}
    )
    assert descriptor.supports_test_mode
    assert ConnectorOperation.FETCH_DOCUMENT not in descriptor.operations


def test_connector_and_scenario_configuration_are_immutable_and_typed() -> None:
    connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.SUCCESS)

    with pytest.raises(FrozenInstanceError):
        connector.scenario = BusinessRegistryScenario.NO_RESULTS  # type: ignore[misc]
    with pytest.raises(TypeError):
        SimulatedBusinessRegistryConnector("SUCCESS")  # type: ignore[arg-type]


def test_success_search_and_details_return_only_neutral_typed_items() -> None:
    connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.SUCCESS)
    search = run_immediate(connector.search(synthetic_query(), synthetic_context()))

    assert search.status is ConnectorOutcomeStatus.SUCCEEDED
    assert len(search.items) == 1
    assert all(isinstance(item, CandidateObservation) for item in search.items)
    candidate = search.items[0].candidate
    assert candidate.connector_id == connector.describe().connector_id
    assert candidate.display_name.startswith("Synthetic ")
    assert candidate.domain is not None and candidate.domain.value.endswith(".test")
    assert candidate.primary_identifier is not None
    assert candidate.primary_identifier.original_value.startswith("TEST-")

    details = run_immediate(connector.fetch_details(candidate, synthetic_context()))

    assert details.status is ConnectorOutcomeStatus.SUCCEEDED
    assert len(details.items) == 6
    assert all(isinstance(item, Observation) for item in details.items)
    assert all(item.subject_candidate_ref == candidate for item in details.items)
    assert {item.observation_type.code for item in details.items} == {
        "COMPANY.REGISTERED_NAME",
        "COMPANY.BUSINESS_IDENTIFIER",
        "COMPANY.REGISTRY_STATUS",
        "COMPANY.INCORPORATION_DATE",
        "COMPANY.LOCALITY",
        "COMPANY.ECONOMIC_ACTIVITY",
    }


def test_no_results_is_valid_and_not_a_failure_for_both_declared_operations() -> None:
    connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.NO_RESULTS)

    search = run_immediate(connector.search(synthetic_query(), synthetic_context()))
    details = run_immediate(
        connector.fetch_details(
            synthetic_candidate(connector.describe().connector_id),
            synthetic_context(),
        )
    )

    for outcome in (search, details):
        assert outcome.status is ConnectorOutcomeStatus.NO_RESULTS
        assert outcome.items == ()
        assert outcome.artifacts == ()
        assert outcome.error is None
        assert outcome.source_snapshot is not None


def test_multiple_candidates_have_distinct_ids_and_stable_documented_order() -> None:
    connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.MULTIPLE_CANDIDATES)

    first = run_immediate(connector.search(synthetic_query(), synthetic_context()))
    second = run_immediate(connector.search(synthetic_query(), synthetic_context()))

    names = tuple(item.candidate.display_name for item in first.items)
    identifiers = tuple(item.candidate.candidate_ref_id for item in first.items)
    assert names == (
        "Synthetic Alpha Registry Test Ltd.",
        "Synthetic Beta Registry Test Ltd.",
    )
    assert len(set(identifiers)) == 2
    assert first == second


def test_partial_search_and_details_declare_their_gap() -> None:
    connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.PARTIAL)
    candidate = synthetic_candidate(connector.describe().connector_id)

    search = run_immediate(connector.search(synthetic_query(), synthetic_context()))
    details = run_immediate(connector.fetch_details(candidate, synthetic_context()))

    for outcome in (search, details):
        assert outcome.status is ConnectorOutcomeStatus.PARTIAL
        assert outcome.items
        assert outcome.warnings
        assert outcome.error is None


@pytest.mark.parametrize(("scenario", "error_code"), _FAILURE_SCENARIOS)
def test_failure_scenarios_are_typed_for_search_and_details(
    scenario: BusinessRegistryScenario,
    error_code: ConnectorErrorCode,
) -> None:
    connector = SimulatedBusinessRegistryConnector(scenario)
    candidate = synthetic_candidate(connector.describe().connector_id)

    search = run_immediate(connector.search(synthetic_query(), synthetic_context()))
    details = run_immediate(connector.fetch_details(candidate, synthetic_context()))

    for outcome in (search, details):
        assert outcome.status is ConnectorOutcomeStatus.FAILED
        assert outcome.error is not None
        assert outcome.error.code is error_code
        assert outcome.items == ()
    if scenario is BusinessRegistryScenario.RATE_LIMITED:
        assert search.error is not None
        assert search.error.retry_after == timedelta(seconds=30)


def test_cancelled_has_no_late_content_for_search_or_details() -> None:
    connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.CANCELLED)
    candidate = synthetic_candidate(connector.describe().connector_id)

    outcomes = (
        run_immediate(connector.search(synthetic_query(), synthetic_context())),
        run_immediate(connector.fetch_details(candidate, synthetic_context())),
    )

    for outcome in outcomes:
        assert outcome.status is ConnectorOutcomeStatus.CANCELLED
        assert outcome.items == ()
        assert outcome.artifacts == ()
        assert outcome.pagination is None
        assert outcome.error is not None
        assert outcome.error.code is ConnectorErrorCode.CANCELLED


def test_invalid_response_is_redacted_and_never_constructs_invalid_outcome() -> None:
    connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.INVALID_RESPONSE)

    outcome = run_immediate(connector.search(synthetic_query(), synthetic_context()))

    assert outcome.status is ConnectorOutcomeStatus.FAILED
    assert outcome.error is not None
    assert outcome.error.code is ConnectorErrorCode.INVALID_RESPONSE
    assert outcome.error.message == "Synthetic source response could not be translated"
    assert outcome.items == ()


def test_usage_snapshots_digests_and_repetition_are_fixed() -> None:
    first_connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.SUCCESS)
    second_connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.SUCCESS)

    first = run_immediate(first_connector.search(synthetic_query(), synthetic_context()))
    repeated = run_immediate(first_connector.search(synthetic_query(), synthetic_context()))
    fresh = run_immediate(second_connector.search(synthetic_query(), synthetic_context()))

    assert first == repeated == fresh
    assert first.source_snapshot is not None
    assert first.source_snapshot.source_id == SIMULATED_BUSINESS_REGISTRY_SOURCE_ID
    assert first.usage.calls == 1
    assert first.usage.bytes_received == 512
    assert first.usage.duration == timedelta(milliseconds=12)
    assert first.response_digest == (
        "0000000000000000000000000000000000000000000000000000000000000001"
    )


def test_foreign_candidate_is_rejected_without_external_exception() -> None:
    connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.SUCCESS)
    foreign = synthetic_candidate(type(connector.describe().connector_id)("simulated.other"))

    outcome = run_immediate(connector.fetch_details(foreign, synthetic_context()))

    assert outcome.status is ConnectorOutcomeStatus.FAILED
    assert outcome.error is not None
    assert outcome.error.code is ConnectorErrorCode.INVALID_REQUEST


def test_undeclared_document_surface_returns_typed_rejection_without_io() -> None:
    connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.SUCCESS)
    reference = ArtifactReference(
        artifact_ref_id=ArtifactRefId.from_value("30000000-0000-4000-8000-000000000001"),
        media_type="application/pdf",
        retention=ArtifactRetentionMode.REFERENCE_ONLY,
        origin_reference=OriginReferenceId("synthetic-document-reference"),
    )

    outcome = run_immediate(connector.fetch_document(reference, synthetic_context()))

    assert ConnectorOperation.FETCH_DOCUMENT not in connector.describe().operations
    assert outcome.status is ConnectorOutcomeStatus.FAILED
    assert outcome.error is not None
    assert outcome.error.code is ConnectorErrorCode.UNSUPPORTED_OPERATION
    assert outcome.usage.calls == 0
