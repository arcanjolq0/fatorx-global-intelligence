"""Proof that the reusable suite accepts valid connectors and detects violations."""

from dataclasses import replace
from typing import cast

import pytest

from intelligence.connectors.artifacts import ArtifactPayload, ArtifactReference
from intelligence.connectors.context import ConnectorContext
from intelligence.connectors.descriptor import ConnectorDescriptor
from intelligence.connectors.enums import (
    ConnectorErrorCode,
    ConnectorOperation,
    ConnectorOutcomeStatus,
)
from intelligence.connectors.identifiers import ConnectorId, SourceId
from intelligence.connectors.observations import CandidateObservation, Observation
from intelligence.connectors.outcomes import ConnectorOutcome, SourceSnapshot
from intelligence.connectors.queries import CandidateRef, CompanyQuery
from intelligence.connectors.simulated import (
    BusinessRegistryScenario,
    SimulatedBusinessRegistryConnector,
)
from intelligence.connectors.versions import SemanticVersion
from tests.connectors.contract_suite import (
    ConnectorContractCase,
    ConnectorContractViolation,
    OperationExpectation,
    validate_connector_contract,
)
from tests.connectors.synthetic_fixtures import (
    run_immediate,
    synthetic_candidate,
    synthetic_context,
    synthetic_query,
)

_EXPECTED_RESULTS = (
    (
        BusinessRegistryScenario.SUCCESS,
        ConnectorOutcomeStatus.SUCCEEDED,
        None,
    ),
    (
        BusinessRegistryScenario.NO_RESULTS,
        ConnectorOutcomeStatus.NO_RESULTS,
        None,
    ),
    (
        BusinessRegistryScenario.MULTIPLE_CANDIDATES,
        ConnectorOutcomeStatus.SUCCEEDED,
        None,
    ),
    (
        BusinessRegistryScenario.PARTIAL,
        ConnectorOutcomeStatus.PARTIAL,
        None,
    ),
    (
        BusinessRegistryScenario.RATE_LIMITED,
        ConnectorOutcomeStatus.FAILED,
        ConnectorErrorCode.RATE_LIMITED,
    ),
    (
        BusinessRegistryScenario.TIMEOUT,
        ConnectorOutcomeStatus.FAILED,
        ConnectorErrorCode.TIMEOUT,
    ),
    (
        BusinessRegistryScenario.UNAVAILABLE,
        ConnectorOutcomeStatus.FAILED,
        ConnectorErrorCode.UNAVAILABLE,
    ),
    (
        BusinessRegistryScenario.INVALID_RESPONSE,
        ConnectorOutcomeStatus.FAILED,
        ConnectorErrorCode.INVALID_RESPONSE,
    ),
    (
        BusinessRegistryScenario.CANCELLED,
        ConnectorOutcomeStatus.CANCELLED,
        ConnectorErrorCode.CANCELLED,
    ),
    (
        BusinessRegistryScenario.POLICY_BLOCKED,
        ConnectorOutcomeStatus.FAILED,
        ConnectorErrorCode.POLICY_BLOCKED,
    ),
    (
        BusinessRegistryScenario.BUDGET_EXCEEDED,
        ConnectorOutcomeStatus.FAILED,
        ConnectorErrorCode.BUDGET_EXCEEDED,
    ),
)


def _valid_connector() -> SimulatedBusinessRegistryConnector:
    return SimulatedBusinessRegistryConnector(BusinessRegistryScenario.SUCCESS)


def _case(
    factory: type[DelegatingConnector],
    *,
    expectations: tuple[OperationExpectation, ...] | None = None,
) -> ConnectorContractCase:
    expected_descriptor = factory().describe()
    return ConnectorContractCase(
        connector_factory=factory,
        expected_descriptor=expected_descriptor,
        query=synthetic_query(),
        context=synthetic_context(),
        details_candidate=synthetic_candidate(expected_descriptor.connector_id),
        expectations=expectations
        or (
            OperationExpectation(
                ConnectorOperation.SEARCH,
                ConnectorOutcomeStatus.SUCCEEDED,
            ),
            OperationExpectation(
                ConnectorOperation.FETCH_DETAILS,
                ConnectorOutcomeStatus.SUCCEEDED,
            ),
        ),
    )


@pytest.mark.parametrize(("scenario", "status", "error_code"), _EXPECTED_RESULTS)
def test_reusable_suite_accepts_every_deterministic_simulator_scenario(
    scenario: BusinessRegistryScenario,
    status: ConnectorOutcomeStatus,
    error_code: ConnectorErrorCode | None,
) -> None:
    expected = SimulatedBusinessRegistryConnector(scenario).describe()
    case = ConnectorContractCase(
        connector_factory=lambda: SimulatedBusinessRegistryConnector(scenario),
        expected_descriptor=expected,
        query=synthetic_query(),
        context=synthetic_context(),
        details_candidate=synthetic_candidate(expected.connector_id),
        expectations=(
            OperationExpectation(ConnectorOperation.SEARCH, status, error_code),
            OperationExpectation(ConnectorOperation.FETCH_DETAILS, status, error_code),
        ),
    )

    run_immediate(validate_connector_contract(case))


class DelegatingConnector:
    """Valid test double base used only to isolate one violation at a time."""

    def __init__(self) -> None:
        self.delegate = _valid_connector()

    def describe(self) -> ConnectorDescriptor:
        return self.delegate.describe()

    async def search(
        self,
        query: CompanyQuery,
        context: ConnectorContext,
    ) -> ConnectorOutcome[CandidateObservation]:
        return await self.delegate.search(query, context)

    async def fetch_details(
        self,
        candidate_ref: CandidateRef,
        context: ConnectorContext,
    ) -> ConnectorOutcome[Observation]:
        return await self.delegate.fetch_details(candidate_ref, context)

    async def fetch_document(
        self,
        document_ref: ArtifactReference,
        context: ConnectorContext,
    ) -> ConnectorOutcome[ArtifactPayload]:
        return await self.delegate.fetch_document(document_ref, context)


class WrongSearchItemConnector(DelegatingConnector):
    async def search(
        self,
        query: CompanyQuery,
        context: ConnectorContext,
    ) -> ConnectorOutcome[CandidateObservation]:
        candidate = synthetic_candidate(self.describe().connector_id)
        details = await self.delegate.fetch_details(candidate, context)
        del query
        return cast(ConnectorOutcome[CandidateObservation], details)


class WrongDetailsItemConnector(DelegatingConnector):
    async def fetch_details(
        self,
        candidate_ref: CandidateRef,
        context: ConnectorContext,
    ) -> ConnectorOutcome[Observation]:
        search = await self.delegate.search(synthetic_query(), context)
        del candidate_ref
        return cast(ConnectorOutcome[Observation], search)


class WrongCandidateConnectorIdConnector(DelegatingConnector):
    async def search(
        self,
        query: CompanyQuery,
        context: ConnectorContext,
    ) -> ConnectorOutcome[CandidateObservation]:
        outcome = await self.delegate.search(query, context)
        item = outcome.items[0]
        wrong_candidate = replace(
            item.candidate,
            connector_id=ConnectorId("simulated.wrong"),
        )
        return _copy_outcome(outcome, (replace(item, candidate=wrong_candidate),))


class WrongSourceIdConnector(DelegatingConnector):
    async def search(
        self,
        query: CompanyQuery,
        context: ConnectorContext,
    ) -> ConnectorOutcome[CandidateObservation]:
        outcome = await self.delegate.search(query, context)
        source = outcome.source_snapshot
        assert source is not None
        wrong_source = SourceSnapshot(
            source_id=SourceId("source.synthetic.wrong"),
            origin_reference=source.origin_reference,
            retrieved_at=source.retrieved_at,
            published_at=source.published_at,
        )
        return ConnectorOutcome(
            status=outcome.status,
            items=outcome.items,
            artifacts=outcome.artifacts,
            source_snapshot=wrong_source,
            pagination=outcome.pagination,
            usage=outcome.usage,
            warnings=outcome.warnings,
            error=outcome.error,
            response_digest=outcome.response_digest,
        )


class NondeterministicConnector(DelegatingConnector):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def search(
        self,
        query: CompanyQuery,
        context: ConnectorContext,
    ) -> ConnectorOutcome[CandidateObservation]:
        self.calls += 1
        scenario = (
            BusinessRegistryScenario.SUCCESS
            if self.calls == 1
            else BusinessRegistryScenario.MULTIPLE_CANDIDATES
        )
        return await SimulatedBusinessRegistryConnector(scenario).search(query, context)


class ChangingDescriptorConnector(DelegatingConnector):
    def __init__(self) -> None:
        super().__init__()
        self.describe_calls = 0

    def describe(self) -> ConnectorDescriptor:
        self.describe_calls += 1
        descriptor = self.delegate.describe()
        if self.describe_calls == 1:
            return descriptor
        return replace(descriptor, version=SemanticVersion(1, 0, 1))


class UndeclaredDetailsConnector(DelegatingConnector):
    def describe(self) -> ConnectorDescriptor:
        return replace(
            self.delegate.describe(),
            operations=frozenset({ConnectorOperation.SEARCH}),
        )


def _copy_outcome(
    outcome: ConnectorOutcome[CandidateObservation],
    items: tuple[CandidateObservation, ...],
) -> ConnectorOutcome[CandidateObservation]:
    return ConnectorOutcome(
        status=outcome.status,
        items=items,
        artifacts=outcome.artifacts,
        source_snapshot=outcome.source_snapshot,
        pagination=replace(outcome.pagination, returned_count=len(items))
        if outcome.pagination is not None
        else None,
        usage=outcome.usage,
        warnings=outcome.warnings,
        error=outcome.error,
        response_digest=outcome.response_digest,
    )


@pytest.mark.parametrize(
    ("factory", "expectations", "message"),
    (
        (
            WrongSearchItemConnector,
            (
                OperationExpectation(
                    ConnectorOperation.SEARCH,
                    ConnectorOutcomeStatus.SUCCEEDED,
                ),
            ),
            "CandidateObservation",
        ),
        (
            WrongDetailsItemConnector,
            (
                OperationExpectation(
                    ConnectorOperation.FETCH_DETAILS,
                    ConnectorOutcomeStatus.SUCCEEDED,
                ),
            ),
            "Observation",
        ),
        (
            WrongCandidateConnectorIdConnector,
            (
                OperationExpectation(
                    ConnectorOperation.SEARCH,
                    ConnectorOutcomeStatus.SUCCEEDED,
                ),
            ),
            "connector_id",
        ),
        (
            WrongSourceIdConnector,
            (
                OperationExpectation(
                    ConnectorOperation.SEARCH,
                    ConnectorOutcomeStatus.SUCCEEDED,
                ),
            ),
            "source_id",
        ),
        (
            NondeterministicConnector,
            (
                OperationExpectation(
                    ConnectorOperation.SEARCH,
                    ConnectorOutcomeStatus.SUCCEEDED,
                ),
            ),
            "deterministic",
        ),
        (
            ChangingDescriptorConnector,
            (
                OperationExpectation(
                    ConnectorOperation.SEARCH,
                    ConnectorOutcomeStatus.SUCCEEDED,
                ),
            ),
            "descriptor changed",
        ),
        (
            UndeclaredDetailsConnector,
            (
                OperationExpectation(
                    ConnectorOperation.FETCH_DETAILS,
                    ConnectorOutcomeStatus.SUCCEEDED,
                ),
            ),
            "not declared",
        ),
    ),
)
def test_reusable_suite_rejects_deliberately_invalid_test_connectors(
    factory: type[DelegatingConnector],
    expectations: tuple[OperationExpectation, ...],
    message: str,
) -> None:
    case = _case(factory, expectations=expectations)

    with pytest.raises(ConnectorContractViolation, match=message):
        run_immediate(validate_connector_contract(case))
