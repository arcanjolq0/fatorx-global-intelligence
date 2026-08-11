"""F4.4 planning service authorization, replay, conflict, and atomicity tests."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import (
    AuthorizationDeniedError,
    ConcurrentInvestigationUpdateError,
    InvalidInvestigationPlanningError,
    InvestigationCommandCollisionError,
    InvestigationPlanAlreadyExistsError,
    InvestigationPlanningDeadlineError,
    PersistenceError,
    RequiredPlanningCapabilityUnavailableError,
)
from intelligence.application.investigation_planning import (
    CreateInvestigationPlan,
    digest_create_investigation_plan_command,
)
from intelligence.application.services.investigation_planning import (
    InvestigationPlanningService,
)
from intelligence.connectors.registry import ConnectorRegistry
from intelligence.connectors.simulated.business_registry import (
    SimulatedBusinessRegistryConnector,
)
from intelligence.connectors.simulated.scenarios import BusinessRegistryScenario
from intelligence.domain.audit import AuditOutcome
from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CompanyId,
    CorrelationId,
    InvestigationCommandId,
    InvestigationId,
    InvestigationPlanId,
    MembershipId,
    PlannedCapabilityId,
    PlannedConnectorOptionId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.identities import (
    EmailAddress,
    MembershipRole,
    MembershipStatus,
    UserAccount,
    UserAccountStatus,
    WorkspaceMembership,
)
from intelligence.domain.investigation_inputs import IdentificationInput, OriginalAndNormalizedText
from intelligence.domain.investigations import Investigation, InvestigationState
from intelligence.orchestration.planning import INVESTIGATION_PLANNING_V1
from tests.unit.application.fakes import FakeDatabase, FakeUnitOfWorkFactory

NOW = datetime(2026, 8, 1, 19, tzinfo=UTC)


@dataclass(slots=True)
class CountingClock:
    instant: datetime
    calls: list[datetime] = field(default_factory=list)

    def now(self) -> datetime:
        self.calls.append(self.instant)
        return self.instant


@dataclass(slots=True)
class FailingClock:
    def now(self) -> datetime:
        raise AssertionError("Replay must not read the clock.")


def _registry(*, populated: bool = True) -> ConnectorRegistry:
    registry = ConnectorRegistry()
    if populated:
        registry.register(SimulatedBusinessRegistryConnector(BusinessRegistryScenario.SUCCESS))
    return registry


def _setup(
    *,
    role: MembershipRole = MembershipRole.ANALYST,
    state: InvestigationState = InvestigationState.PLANNING,
    confirmed: bool = True,
    company_persisted: bool = True,
    deadline_at: datetime | None = NOW + timedelta(hours=3),
    registry: ConnectorRegistry | None = None,
    **factory_options: bool,
) -> tuple[
    ActorContext,
    Investigation,
    Company,
    FakeDatabase,
    FakeUnitOfWorkFactory,
    CountingClock,
    InvestigationPlanningService,
]:
    actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )
    company = Company(
        id=CompanyId.new(),
        workspace_id=actor.workspace_id,
        legal_name="Empresa Exemplo S.A.",
        country_code=CountryCode("BR"),
        status=CompanyStatus.ACTIVE,
        created_at=NOW - timedelta(minutes=10),
        updated_at=NOW - timedelta(minutes=10),
    )
    identification_input = IdentificationInput(
        legal_name=OriginalAndNormalizedText(
            original_value="Empresa Exemplo S.A.",
            normalized_value="empresa exemplo s.a.",
        )
    )
    investigation = Investigation.reconstitute(
        id=InvestigationId.new(),
        workspace_id=actor.workspace_id,
        requested_by=actor.user_id,
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        created_at=NOW - timedelta(hours=1),
        state=state,
        state_version=4,
        confirmed_company_id=company.id if confirmed else None,
        deadline_at=deadline_at,
        started_at=NOW - timedelta(minutes=30),
        completed_at=NOW if state is InvestigationState.CANCELLED else None,
        identification_input=identification_input,
    )
    user = UserAccount(
        id=actor.user_id,
        email=EmailAddress(f"{actor.user_id.value}@example.test"),
        display_name="Planner",
        status=UserAccountStatus.ACTIVE,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )
    membership = WorkspaceMembership(
        id=MembershipId.new(),
        workspace_id=actor.workspace_id,
        user_id=actor.user_id,
        role=role,
        status=MembershipStatus.ACTIVE,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )
    database = FakeDatabase(
        companies=({(actor.workspace_id, company.id): company} if company_persisted else {}),
        investigations={(actor.workspace_id, investigation.id): investigation},
        users={actor.user_id: user},
        memberships={(actor.workspace_id, actor.user_id): membership},
    )
    factory = FakeUnitOfWorkFactory(database, **factory_options)
    clock = CountingClock(NOW)
    service = InvestigationPlanningService(
        factory,
        ContextualAuthorizer(),
        clock,
        registry or _registry(),
    )
    return actor, investigation, company, database, factory, clock, service


def _command(
    investigation: Investigation,
    *,
    command_id: InvestigationCommandId | None = None,
    expected_state_version: int | None = None,
) -> CreateInvestigationPlan:
    return CreateInvestigationPlan(
        command_id=command_id or InvestigationCommandId.new(),
        investigation_id=investigation.id,
        expected_state_version=expected_state_version or investigation.state_version,
        planning_policy=INVESTIGATION_PLANNING_V1,
    )


def test_success_persists_ready_plan_audit_and_never_changes_investigation() -> None:
    actor, investigation, _, database, factory, clock, service = _setup()
    command = _command(investigation)
    result = service.create_investigation_plan(actor, command)

    assert not result.replayed
    assert len(result.plan.capabilities) == 10
    assert sum(len(item.connector_options) for item in result.plan.capabilities) == 2
    assert result.plan.investigation_state_version == investigation.state_version
    assert database.investigations[(actor.workspace_id, investigation.id)] == investigation
    assert len(database.investigation_plans) == 1
    assert database.investigation_transitions == {}
    assert len(database.audit_events) == 1
    audit = database.audit_events[0]
    assert audit.outcome is AuditOutcome.SUCCESS
    assert audit.investigation_plan_id == result.plan.id
    assert audit.planned_capability_count == 10
    assert audit.planned_connector_option_count == 2
    assert audit.planning_maximum_estimated_cost_kind_code == "UNKNOWN"
    assert audit.planning_maximum_estimated_cost is None
    assert clock.calls == [NOW]
    assert factory.created[0].investigations.cas_calls == []


def test_command_digest_is_stable_and_closed() -> None:
    actor, investigation, _, _, _, _, _ = _setup()
    command = _command(investigation)
    assert digest_create_investigation_plan_command(
        actor, command
    ) == digest_create_investigation_plan_command(actor, command)


def test_replay_in_new_uow_uses_no_clock_ids_writes_or_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, investigation, _, database, factory, _, service = _setup()
    command = _command(investigation)
    first = service.create_investigation_plan(actor, command)
    counts = (len(database.investigation_plans), len(database.audit_events))

    def fail_new() -> None:
        raise AssertionError("Replay must not generate IDs.")

    monkeypatch.setattr(InvestigationPlanId, "new", fail_new)
    monkeypatch.setattr(PlannedCapabilityId, "new", fail_new)
    monkeypatch.setattr(PlannedConnectorOptionId, "new", fail_new)
    replay_service = InvestigationPlanningService(
        factory,
        ContextualAuthorizer(),
        FailingClock(),
        _registry(),
    )
    replay = replay_service.create_investigation_plan(actor, command)
    assert replay.replayed
    assert replay.plan == first.plan
    assert (len(database.investigation_plans), len(database.audit_events)) == counts
    assert factory.created[-1].investigations.get_for_update_calls == []
    assert factory.created[-1].investigations.cas_calls == []


def test_same_command_with_different_content_is_collision() -> None:
    actor, investigation, _, _, _, _, service = _setup()
    command = _command(investigation)
    service.create_investigation_plan(actor, command)
    with pytest.raises(InvestigationCommandCollisionError):
        service.create_investigation_plan(
            actor,
            _command(
                investigation,
                command_id=command.command_id,
                expected_state_version=investigation.state_version + 1,
            ),
        )


def test_distinct_command_for_same_investigation_is_typed_conflict() -> None:
    actor, investigation, _, database, _, _, service = _setup()
    service.create_investigation_plan(actor, _command(investigation))
    with pytest.raises(InvestigationPlanAlreadyExistsError):
        service.create_investigation_plan(actor, _command(investigation))
    assert len(database.investigation_plans) == 1


@pytest.mark.parametrize(
    ("state", "confirmed"),
    [
        (InvestigationState.IDENTIFYING, False),
        (InvestigationState.CANCELLED, True),
    ],
)
def test_invalid_state_or_missing_confirmed_company_is_rejected(
    state: InvestigationState,
    confirmed: bool,
) -> None:
    actor, investigation, _, database, _, _, service = _setup(
        state=state,
        confirmed=confirmed,
    )
    with pytest.raises(InvalidInvestigationPlanningError):
        service.create_investigation_plan(actor, _command(investigation))
    assert database.investigation_plans == {}


def test_stale_version_and_missing_company_row_fail_closed() -> None:
    actor, investigation, _, _, _, _, service = _setup()
    with pytest.raises(ConcurrentInvestigationUpdateError):
        service.create_investigation_plan(
            actor,
            _command(investigation, expected_state_version=investigation.state_version + 1),
        )

    actor, investigation, _, _, _, _, service = _setup(company_persisted=False)
    with pytest.raises(PersistenceError):
        service.create_investigation_plan(actor, _command(investigation))


def test_required_capability_and_deadline_failures_are_typed() -> None:
    actor, investigation, _, _, _, _, service = _setup(registry=_registry(populated=False))
    with pytest.raises(RequiredPlanningCapabilityUnavailableError):
        service.create_investigation_plan(actor, _command(investigation))

    actor, investigation, _, _, _, _, service = _setup(deadline_at=NOW + timedelta(minutes=30))
    with pytest.raises(InvestigationPlanningDeadlineError):
        service.create_investigation_plan(actor, _command(investigation))


def test_viewer_is_denied_without_loading_investigation() -> None:
    actor, investigation, _, database, factory, _, service = _setup(role=MembershipRole.VIEWER)
    with pytest.raises(AuthorizationDeniedError):
        service.create_investigation_plan(actor, _command(investigation))
    assert database.investigation_plans == {}
    assert factory.created[0].investigations.get_for_update_calls == []


@pytest.mark.parametrize(
    "failure",
    ["fail_plan_add", "fail_capability_add", "fail_option_add", "fail_audit", "fail_commit"],
)
def test_every_persistence_failure_rolls_back_complete_plan(failure: str) -> None:
    actor, investigation, _, database, _, _, service = _setup(
        fail_plan_add=failure == "fail_plan_add",
        fail_capability_add=failure == "fail_capability_add",
        fail_option_add=failure == "fail_option_add",
        fail_audit=failure == "fail_audit",
        fail_commit=failure == "fail_commit",
    )
    with pytest.raises(PersistenceError):
        service.create_investigation_plan(actor, _command(investigation))
    assert database.investigation_plans == {}
    assert database.audit_events == []
    assert database.investigations[(actor.workspace_id, investigation.id)] == investigation
