"""F4.6 direct TEST-mode collection execution boundary tests."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.collection_execution import (
    CollectionExecutionResultRecord,
    ExecuteCollectionSearchOperation,
    build_collection_execution_ownership,
)
from intelligence.application.errors import (
    AuthorizationDeniedError,
    CollectionExecutionAlreadyOwnedError,
    CollectionExecutionInProgressError,
    InvalidCollectionExecutionError,
    InvestigationCommandCollisionError,
)
from intelligence.application.services.collection_activation import CollectionActivationService
from intelligence.application.services.collection_execution import CollectionExecutionService
from intelligence.connectors.artifacts import ArtifactPayload, ArtifactReference
from intelligence.connectors.context import ConnectorContext, LocaleTag, MonotonicDeadline
from intelligence.connectors.descriptor import ConnectorDescriptor
from intelligence.connectors.enums import (
    ConnectorCapability,
    ConnectorErrorCode,
    ConnectorOutcomeStatus,
)
from intelligence.connectors.execution.errors import ConnectorExecutionPreflightError
from intelligence.connectors.execution.policies import ConnectorExecutionPolicy
from intelligence.connectors.identifiers import ConnectorId
from intelligence.connectors.observations import CandidateObservation, Observation
from intelligence.connectors.outcomes import ConnectorOutcome
from intelligence.connectors.protocol import Connector
from intelligence.connectors.queries import CandidateRef, CompanyQuery
from intelligence.connectors.simulated import (
    SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID,
    BusinessRegistryScenario,
    SimulatedBusinessRegistryConnector,
)
from intelligence.connectors.versions import SourcePolicyVersion
from intelligence.domain.audit import AuditOutcome
from intelligence.domain.identifiers import InvestigationCommandId
from intelligence.domain.identities import MembershipRole
from intelligence.orchestration.planning import InvestigationPlan
from tests.connectors.execution.doubles import (
    MutableCancellationSignal,
    execution_policy,
    operation_runner,
    run_async,
)
from tests.unit.application.fakes import FakeDatabase, FakeUnitOfWorkFactory
from tests.unit.application.test_collection_activation_service import _command as activation_command
from tests.unit.application.test_investigation_planning_service import (
    CountingClock,
    FailingClock,
)
from tests.unit.application.test_investigation_planning_service import (
    _setup as planning_setup,
)
from tests.unit.orchestration.test_planning import _plan

NOW = datetime(2026, 8, 1, 19, tzinfo=UTC)
pytestmark = pytest.mark.allow_hosts(["127.0.0.1"])


class _DescriptorChangingConnector:
    """Expose one stable descriptor before commit and another after commit."""

    def __init__(
        self,
        base: SimulatedBusinessRegistryConnector,
        *,
        mutate_at: int = 3,
    ) -> None:
        self._base = base
        self._expected = base.describe()
        self._changed = replace(
            self._expected,
            connector_id=ConnectorId("synthetic.changed_registry"),
        )
        self.describe_calls = 0
        self.search_calls = 0
        self._mutate_at = mutate_at

    @property
    def expected_descriptor(self) -> ConnectorDescriptor:
        return self._expected

    def describe(self) -> ConnectorDescriptor:
        self.describe_calls += 1
        return self._changed if self.describe_calls >= self._mutate_at else self._expected

    async def search(
        self, query: CompanyQuery, context: ConnectorContext
    ) -> ConnectorOutcome[CandidateObservation]:
        self.search_calls += 1
        return await self._base.search(query, context)

    async def fetch_details(
        self, candidate_ref: CandidateRef, context: ConnectorContext
    ) -> ConnectorOutcome[Observation]:
        return await self._base.fetch_details(candidate_ref, context)

    async def fetch_document(
        self, document_ref: ArtifactReference, context: ConnectorContext
    ) -> ConnectorOutcome[ArtifactPayload]:
        return await self._base.fetch_document(document_ref, context)


def _setup() -> tuple[
    ActorContext,
    InvestigationPlan,
    FakeDatabase,
    FakeUnitOfWorkFactory,
    SimulatedBusinessRegistryConnector,
    ExecuteCollectionSearchOperation,
    CollectionExecutionService,
]:
    actor, investigation, company, database, factory, _, _ = planning_setup()
    connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.SUCCESS)
    plan = _plan(
        investigation=investigation,
        company=company,
        descriptors=(connector.describe(),),
    )
    database.investigation_plans[(actor.workspace_id, plan.id)] = plan
    activation = CollectionActivationService(factory, ContextualAuthorizer(), CountingClock(NOW))
    run = activation.start_investigation_collection(
        actor, activation_command(investigation, plan)
    ).collection_run
    operation = next(
        item for item in run.operations if item.capability is ConnectorCapability.COMPANY_REGISTRY
    )
    command = ExecuteCollectionSearchOperation(
        command_id=InvestigationCommandId.new(),
        collection_run_id=run.id,
        collection_operation_id=operation.id,
        expected_run_digest=run.run_digest,
        expected_operation_digest=operation.operation_digest,
        source_policy_version=SourcePolicyVersion("synthetic-source-policy-1"),
        accepted_locales=(LocaleTag("pt-BR"),),
        execution_policy=execution_policy(estimated_attempt_cost=None),
    )
    database.audit_events.clear()
    factory.created.clear()
    service = CollectionExecutionService(
        unit_of_work_factory=factory,
        authorizer=ContextualAuthorizer(),
        clock=CountingClock(NOW),
        runner=operation_runner(),
        admitted_connector_ids=frozenset({SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID}),
    )
    return actor, plan, database, factory, connector, command, service


def _execute(
    service: CollectionExecutionService,
    actor: ActorContext,
    command: ExecuteCollectionSearchOperation,
    connector: Connector,
) -> CollectionExecutionResultRecord:
    return run_async(
        service.execute_search(
            actor,
            command,
            connector=connector,
            monotonic_deadline=MonotonicDeadline(1_000.0),
            cancellation_signal=MutableCancellationSignal(),
        )
    )


def test_success_records_ownership_before_io_and_persists_only_redacted_completion() -> None:
    actor, _, database, _, connector, command, service = _setup()

    result = _execute(service, actor, command, connector)

    ownership = database.collection_execution_ownership[(actor.workspace_id, command.command_id)]
    persisted = database.collection_execution_results[(actor.workspace_id, command.command_id)]
    run = database.collection_runs[(actor.workspace_id, command.collection_run_id)]
    operation = next(item for item in run.operations if item.id == command.collection_operation_id)
    assert ownership.started_at == NOW
    assert persisted == result
    assert result.outcome_status is ConnectorOutcomeStatus.SUCCEEDED
    assert result.completed_at >= ownership.started_at
    assert not hasattr(result, "items")
    assert operation.attempt == 0
    assert operation.status.value == "PENDING"
    assert len(database.audit_events) == 1
    assert database.audit_events[0].outcome is AuditOutcome.SUCCESS


def test_completed_command_replays_without_clock_connector_or_new_writes() -> None:
    actor, _, database, factory, connector, command, service = _setup()
    first = _execute(service, actor, command, connector)
    counts = (
        len(database.collection_execution_ownership),
        len(database.collection_execution_results),
        len(database.audit_events),
    )
    replay_service = CollectionExecutionService(
        unit_of_work_factory=factory,
        authorizer=ContextualAuthorizer(),
        clock=FailingClock(),
        runner=operation_runner(),
        admitted_connector_ids=frozenset({SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID}),
    )

    replay = _execute(replay_service, actor, command, connector)

    assert replay == first
    assert counts == (
        len(database.collection_execution_ownership),
        len(database.collection_execution_results),
        len(database.audit_events),
    )


def test_reused_command_id_with_changed_payload_is_a_collision() -> None:
    actor, _, _, _, connector, command, service = _setup()
    _execute(service, actor, command, connector)
    changed = replace(command, expected_operation_digest="f" * 64)

    with pytest.raises(InvestigationCommandCollisionError):
        _execute(service, actor, changed, connector)


def test_wall_deadline_is_revalidated_before_ownership_or_connector_io() -> None:
    actor, plan, database, factory, connector, command, _ = _setup()
    assert plan.deadline_at is not None
    expired_service = CollectionExecutionService(
        unit_of_work_factory=factory,
        authorizer=ContextualAuthorizer(),
        clock=CountingClock(plan.deadline_at),
        runner=operation_runner(),
        admitted_connector_ids=frozenset({SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID}),
    )

    with pytest.raises(InvalidCollectionExecutionError):
        _execute(expired_service, actor, command, connector)

    assert database.collection_execution_ownership == {}
    assert database.collection_execution_results == {}
    assert database.audit_events[-1].outcome is AuditOutcome.FAILURE


def test_viewer_is_denied_before_ownership_or_connector_io() -> None:
    actor, _, database, _, connector, command, service = _setup()
    key = (actor.workspace_id, actor.user_id)
    database.memberships[key] = replace(database.memberships[key], role=MembershipRole.VIEWER)

    with pytest.raises(AuthorizationDeniedError):
        _execute(service, actor, command, connector)

    assert database.collection_execution_ownership == {}
    assert database.collection_execution_results == {}
    assert database.audit_events[-1].outcome is AuditOutcome.DENIED


def test_policy_argument_remains_strictly_typed() -> None:
    _, _, _, _, _, command, _ = _setup()
    assert isinstance(command.execution_policy, ConnectorExecutionPolicy)


@pytest.mark.parametrize(
    ("mutate_at", "ownership_expected", "completion_expected"),
    (
        (1, False, False),
        (2, False, False),
        (3, True, False),
        (4, True, False),
        (5, True, True),
    ),
)
def test_descriptor_divergence_is_terminal_at_every_boundary(
    mutate_at: int,
    ownership_expected: bool,
    completion_expected: bool,
) -> None:
    actor, _, database, _, connector, command, service = _setup()
    command = replace(
        command,
        execution_policy=execution_policy(
            estimated_attempt_cost=None,
            retriable_codes=(ConnectorErrorCode.INVALID_RESPONSE,),
        ),
    )
    changing = _DescriptorChangingConnector(connector, mutate_at=mutate_at)

    if completion_expected:
        result = _execute(service, actor, command, changing)
        assert result.outcome_status is ConnectorOutcomeStatus.FAILED
    else:
        with pytest.raises((InvalidCollectionExecutionError, ConnectorExecutionPreflightError)):
            _execute(service, actor, command, changing)

    ownership = database.collection_execution_ownership.get(
        (actor.workspace_id, command.command_id)
    )
    assert (ownership is not None) is ownership_expected
    if ownership is not None:
        assert ownership.connector_id == changing.expected_descriptor.connector_id
    assert changing.search_calls == (1 if completion_expected else 0)
    assert bool(database.collection_execution_results) is completion_expected


def test_existing_ownership_without_completion_is_reported_as_in_progress() -> None:
    actor, _, database, _, connector, command, service = _setup()
    run = database.collection_runs[(actor.workspace_id, command.collection_run_id)]
    descriptor = connector.describe()
    ownership = build_collection_execution_ownership(
        actor=actor,
        investigation_id=run.investigation_id,
        command=command,
        connector_id=descriptor.connector_id,
        connector_version=descriptor.version,
        contract_version=descriptor.contract_version,
        source_id=descriptor.source_id,
        started_at=NOW,
    )
    database.collection_execution_ownership[(actor.workspace_id, command.command_id)] = ownership

    with pytest.raises(CollectionExecutionInProgressError):
        _execute(service, actor, command, connector)

    assert database.collection_execution_results == {}
    assert database.audit_events[-1].outcome is AuditOutcome.FAILURE


def test_distinct_command_cannot_take_an_already_owned_operation() -> None:
    actor, _, database, _, connector, command, service = _setup()
    run = database.collection_runs[(actor.workspace_id, command.collection_run_id)]
    descriptor = connector.describe()
    other_command = replace(command, command_id=InvestigationCommandId.new())
    ownership = build_collection_execution_ownership(
        actor=actor,
        investigation_id=run.investigation_id,
        command=other_command,
        connector_id=descriptor.connector_id,
        connector_version=descriptor.version,
        contract_version=descriptor.contract_version,
        source_id=descriptor.source_id,
        started_at=NOW,
    )
    database.collection_execution_ownership[(actor.workspace_id, other_command.command_id)] = (
        ownership
    )

    with pytest.raises(CollectionExecutionAlreadyOwnedError):
        _execute(service, actor, command, connector)

    assert database.collection_execution_results == {}
    assert database.audit_events[-1].outcome is AuditOutcome.FAILURE
