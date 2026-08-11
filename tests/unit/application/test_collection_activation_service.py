"""F4.5 activation authorization, replay, lifecycle, and atomicity tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.collection_activation import StartInvestigationCollection
from intelligence.application.errors import (
    AuthorizationDeniedError,
    CollectionActivationDeadlineError,
    CollectionRunAlreadyExistsError,
    ConcurrentInvestigationUpdateError,
    InvestigationCommandCollisionError,
    PersistenceDataError,
    PersistenceError,
)
from intelligence.application.investigation_lifecycle import (
    InvestigationCommandDigest,
    InvestigationCommandType,
    InvestigationTransitionRecord,
)
from intelligence.application.services.collection_activation import CollectionActivationService
from intelligence.domain.audit import AuditOutcome
from intelligence.domain.companies import Company
from intelligence.domain.identifiers import (
    CollectionOperationId,
    CollectionRunId,
    InvestigationCommandId,
    InvestigationPlanId,
    InvestigationTransitionId,
)
from intelligence.domain.identities import MembershipRole
from intelligence.domain.investigations import Investigation, InvestigationState
from intelligence.orchestration.collection_activation import (
    COLLECTION_ACTIVATION_V1,
    ready_operation_critical_path_seconds,
)
from intelligence.orchestration.planning import InvestigationPlan
from tests.unit.application.fakes import FakeDatabase, FakeUnitOfWorkFactory
from tests.unit.application.test_investigation_planning_service import (
    CountingClock,
)
from tests.unit.application.test_investigation_planning_service import (
    _setup as planning_setup,
)
from tests.unit.orchestration.test_planning import _descriptor, _plan

NOW = datetime(2026, 8, 1, 19, tzinfo=UTC)


def _setup(
    *, role: MembershipRole = MembershipRole.ANALYST
) -> tuple[
    ActorContext,
    Investigation,
    Company,
    InvestigationPlan,
    FakeDatabase,
    FakeUnitOfWorkFactory,
    CountingClock,
    CollectionActivationService,
]:
    actor, investigation, company, database, factory, _, _ = planning_setup(role=role)
    plan = _plan(
        investigation=investigation,
        company=company,
        descriptors=(_descriptor("collection.country"),),
    )
    database.investigation_plans[(actor.workspace_id, plan.id)] = plan
    database.audit_events.clear()
    factory.created.clear()
    clock = CountingClock(NOW)
    service = CollectionActivationService(factory, ContextualAuthorizer(), clock)
    return actor, investigation, company, plan, database, factory, clock, service


def _command(
    investigation: Investigation,
    plan: InvestigationPlan,
    *,
    command_id: InvestigationCommandId | None = None,
    plan_id: InvestigationPlanId | None = None,
) -> StartInvestigationCollection:
    return StartInvestigationCollection(
        command_id=command_id or InvestigationCommandId.new(),
        investigation_id=investigation.id,
        plan_id=plan_id or plan.id,
        expected_state_version=investigation.state_version,
        activation_policy=COLLECTION_ACTIVATION_V1,
    )


def test_success_persists_manifest_transition_audit_and_collecting_state() -> None:
    actor, investigation, _, plan, database, factory, clock, service = _setup()
    result = service.start_investigation_collection(actor, _command(investigation, plan))

    assert not result.replayed
    assert result.collection_run.plan_id == plan.id
    assert database.investigations[(actor.workspace_id, investigation.id)].state is (
        InvestigationState.COLLECTING
    )
    assert database.investigations[(actor.workspace_id, investigation.id)].state_version == (
        investigation.state_version + 1
    )
    assert len(database.collection_runs) == 1
    assert len(database.investigation_transitions) == 1
    assert len(database.audit_events) == 1
    audit = database.audit_events[0]
    assert audit.outcome is AuditOutcome.SUCCESS
    assert audit.collection_run_id == result.collection_run.id
    assert audit.collection_operation_count == len(result.collection_run.operations)
    assert clock.calls == [NOW]
    assert len(factory.created[0].investigations.cas_calls) == 1


def test_activation_revalidates_sufficient_and_exact_deadline() -> None:
    for offset_seconds in (1, 0):
        actor, investigation, _, plan, _, factory, _, _ = _setup()
        assert investigation.deadline_at is not None
        critical_seconds = ready_operation_critical_path_seconds(plan)
        activated_at = investigation.deadline_at - timedelta(
            seconds=critical_seconds + offset_seconds
        )
        service = CollectionActivationService(
            factory, ContextualAuthorizer(), CountingClock(activated_at)
        )

        result = service.start_investigation_collection(actor, _command(investigation, plan))

        assert result.collection_run.created_at == activated_at


def test_insufficient_remaining_time_fails_before_manifest_transition_or_success_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, investigation, _, plan, database, factory, _, _ = _setup()
    assert investigation.deadline_at is not None
    critical_seconds = ready_operation_critical_path_seconds(plan)
    activated_at = investigation.deadline_at - timedelta(seconds=critical_seconds - 1)

    def fail_new() -> None:
        raise AssertionError("Deadline rejection must precede manifest and transition IDs.")

    monkeypatch.setattr(CollectionRunId, "new", fail_new)
    monkeypatch.setattr(CollectionOperationId, "new", fail_new)
    monkeypatch.setattr(InvestigationTransitionId, "new", fail_new)
    service = CollectionActivationService(
        factory, ContextualAuthorizer(), CountingClock(activated_at)
    )

    with pytest.raises(CollectionActivationDeadlineError):
        service.start_investigation_collection(actor, _command(investigation, plan))

    assert database.collection_runs == {}
    assert database.investigation_transitions == {}
    assert database.investigations[(actor.workspace_id, investigation.id)] == investigation
    assert len(database.audit_events) == 1
    assert database.audit_events[0].outcome is AuditOutcome.FAILURE


def test_replay_in_new_uow_reads_no_clock_generates_no_ids_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, investigation, _, plan, database, factory, _, service = _setup()
    command = _command(investigation, plan)
    first = service.start_investigation_collection(actor, command)
    counts = (
        len(database.collection_runs),
        len(database.investigation_transitions),
        len(database.audit_events),
    )

    def fail_new() -> None:
        raise AssertionError("Replay must not generate IDs.")

    monkeypatch.setattr(CollectionRunId, "new", fail_new)
    monkeypatch.setattr(CollectionOperationId, "new", fail_new)
    monkeypatch.setattr(InvestigationTransitionId, "new", fail_new)
    replay_service = CollectionActivationService(
        factory,
        ContextualAuthorizer(),
        type("FailingClock", (), {"now": lambda self: fail_new()})(),
    )
    replay = replay_service.start_investigation_collection(actor, command)

    assert replay.replayed
    assert replay.collection_run == first.collection_run
    assert counts == (
        len(database.collection_runs),
        len(database.investigation_transitions),
        len(database.audit_events),
    )
    assert factory.created[-1].investigations.cas_calls == []


def test_same_command_id_with_changed_plan_is_collision() -> None:
    actor, investigation, _, plan, _, _, _, service = _setup()
    command = _command(investigation, plan)
    service.start_investigation_collection(actor, command)

    with pytest.raises(InvestigationCommandCollisionError):
        service.start_investigation_collection(
            actor,
            _command(
                investigation,
                plan,
                command_id=command.command_id,
                plan_id=InvestigationPlanId.new(),
            ),
        )


def test_command_id_owned_by_another_command_type_is_a_true_collision() -> None:
    actor, investigation, _, plan, database, _, _, service = _setup()
    command = _command(investigation, plan)
    database.investigation_transitions[(actor.workspace_id, command.command_id)] = (
        InvestigationTransitionRecord(
            id=InvestigationTransitionId.new(),
            workspace_id=actor.workspace_id,
            investigation_id=investigation.id,
            command_id=command.command_id,
            command_type=InvestigationCommandType.START_IDENTIFICATION,
            state_before=InvestigationState.CREATED,
            version_before=1,
            state_after=InvestigationState.IDENTIFYING,
            version_after=2,
            actor_user_id=actor.user_id,
            reason=None,
            occurred_at=NOW,
            command_digest=InvestigationCommandDigest("e" * 64),
            correlation_id=actor.correlation_id,
        )
    )

    with pytest.raises(InvestigationCommandCollisionError):
        service.start_investigation_collection(actor, command)


def test_run_or_transition_without_its_historical_counterpart_fails_closed() -> None:
    for missing in ("run", "transition"):
        actor, investigation, _, plan, database, _, _, service = _setup()
        command = _command(investigation, plan)
        result = service.start_investigation_collection(actor, command)
        if missing == "run":
            database.collection_runs.pop((actor.workspace_id, result.collection_run.id))
        else:
            database.investigation_transitions.pop((actor.workspace_id, command.command_id))

        with pytest.raises(PersistenceDataError):
            service.start_investigation_collection(actor, command)


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("actor_user_id", lambda _run: type(_run.created_by).new()),
        ("occurred_at", lambda run: run.created_at + timedelta(seconds=1)),
        ("collection_run_id", lambda _run: CollectionRunId.new()),
        ("collection_company_id", lambda run: type(run.company_id).new()),
        ("collection_plan_id", lambda _run: InvestigationPlanId.new()),
        ("collection_operation_count", lambda run: len(run.operations) - 1),
        ("collection_activation_policy_id", lambda _run: "COLLECTION_ACTIVATION_V2"),
        ("collection_activation_policy_version", lambda _run: 2),
    ],
)
def test_replay_rejects_divergent_historical_activation_fields(
    field_name: str,
    replacement: object,
) -> None:
    actor, investigation, _, plan, database, _, _, service = _setup()
    command = _command(investigation, plan)
    run = service.start_investigation_collection(actor, command).collection_run
    key = (actor.workspace_id, command.command_id)
    transition = database.investigation_transitions[key]
    value_factory = replacement
    assert callable(value_factory)
    database.investigation_transitions[key] = replace(
        transition, **{field_name: value_factory(run)}
    )

    with pytest.raises(PersistenceDataError):
        service.start_investigation_collection(actor, command)


def test_distinct_command_rejects_existing_run() -> None:
    actor, investigation, _, plan, database, _, _, service = _setup()
    service.start_investigation_collection(actor, _command(investigation, plan))
    database.investigations[(actor.workspace_id, investigation.id)] = investigation

    with pytest.raises(CollectionRunAlreadyExistsError):
        service.start_investigation_collection(actor, _command(investigation, plan))


@pytest.mark.parametrize(
    "failure_option",
    [
        "fail_run_add",
        "fail_operation_add",
        "fail_dependency_add",
        "fail_transition_add",
        "fail_audit",
        "fail_commit",
    ],
)
def test_failures_roll_back_manifest_transition_investigation_and_audit(
    failure_option: str,
) -> None:
    actor, investigation, _, plan, database, factory, _, _ = _setup()
    setattr(factory, failure_option, True)
    service = CollectionActivationService(factory, ContextualAuthorizer(), CountingClock(NOW))

    with pytest.raises(PersistenceError):
        service.start_investigation_collection(actor, _command(investigation, plan))

    assert database.collection_runs == {}
    assert database.investigation_transitions == {}
    assert database.audit_events == []
    assert database.investigations[(actor.workspace_id, investigation.id)] == investigation


def test_cas_conflict_rolls_back_the_manifest_before_returning_conflict() -> None:
    actor, investigation, _, plan, database, factory, _, _ = _setup()
    factory.force_cas_conflict = True
    service = CollectionActivationService(factory, ContextualAuthorizer(), CountingClock(NOW))

    with pytest.raises(ConcurrentInvestigationUpdateError):
        service.start_investigation_collection(actor, _command(investigation, plan))
    assert database.collection_runs == {}
    assert database.audit_events == []


def test_viewer_is_denied_without_manifest_or_transition() -> None:
    actor, investigation, _, plan, database, _, _, service = _setup(role=MembershipRole.VIEWER)
    with pytest.raises(AuthorizationDeniedError):
        service.start_investigation_collection(actor, _command(investigation, plan))
    assert database.collection_runs == {}
    assert database.investigation_transitions == {}
    assert len(database.audit_events) == 1
