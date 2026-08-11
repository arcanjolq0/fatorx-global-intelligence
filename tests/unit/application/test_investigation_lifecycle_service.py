"""Application tests for atomic F4.1 investigation lifecycle commands."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import AuditActionCode, AuditReasonCode
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import (
    AuthorizationDeniedError,
    ConcurrentInvestigationUpdateError,
    InvestigationCommandCollisionError,
    InvestigationTransitionError,
    PersistenceError,
    ResourceNotFoundError,
)
from intelligence.application.investigation_lifecycle import (
    CancelInvestigation,
    InvestigationCancellationReason,
    InvestigationCommandType,
    StartIdentification,
)
from intelligence.application.services.investigations import InvestigationService
from intelligence.domain.audit import AuditOutcome
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CorrelationId,
    InvestigationCommandId,
    InvestigationId,
    MembershipId,
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
from intelligence.domain.investigation_inputs import (
    IdentificationInput,
    OriginalAndNormalizedText,
)
from intelligence.domain.investigations import Investigation, InvestigationState
from tests.unit.application.fakes import FakeClock, FakeDatabase, FakeUnitOfWorkFactory

NOW = datetime(2026, 7, 29, 16, tzinfo=UTC)


def _input(name: str = "Empresa Exemplo S.A.") -> IdentificationInput:
    return IdentificationInput(
        legal_name=OriginalAndNormalizedText(
            original_value=name,
            normalized_value=name.lower(),
        )
    )


def _setup(
    role: MembershipRole = MembershipRole.OWNER,
    **factory_options: bool,
) -> tuple[
    ActorContext,
    FakeDatabase,
    FakeUnitOfWorkFactory,
    InvestigationService,
    Investigation,
]:
    actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )
    investigation = Investigation(
        id=InvestigationId.new(),
        workspace_id=actor.workspace_id,
        requested_by=actor.user_id,
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        created_at=NOW - timedelta(minutes=1),
    )
    database = FakeDatabase(
        investigations={(actor.workspace_id, investigation.id): investigation},
        users={
            actor.user_id: UserAccount(
                id=actor.user_id,
                email=EmailAddress(f"{actor.user_id.value}@example.test"),
                display_name="Actor",
                status=UserAccountStatus.ACTIVE,
                created_at=NOW - timedelta(days=1),
                updated_at=NOW - timedelta(days=1),
            )
        },
        memberships={
            (actor.workspace_id, actor.user_id): WorkspaceMembership(
                id=MembershipId.new(),
                workspace_id=actor.workspace_id,
                user_id=actor.user_id,
                role=role,
                status=MembershipStatus.ACTIVE,
                created_at=NOW - timedelta(days=1),
                updated_at=NOW - timedelta(days=1),
            )
        },
    )
    factory = FakeUnitOfWorkFactory(database, **factory_options)
    service = InvestigationService(factory, ContextualAuthorizer(), FakeClock(NOW))
    return actor, database, factory, service, investigation


def _start_command(
    investigation: Investigation,
    *,
    command_id: InvestigationCommandId | None = None,
    expected_state_version: int = 1,
    name: str = "Empresa Exemplo S.A.",
) -> StartIdentification:
    return StartIdentification(
        command_id=command_id or InvestigationCommandId.new(),
        investigation_id=investigation.id,
        expected_state_version=expected_state_version,
        identification_input=_input(name),
    )


@pytest.mark.parametrize(
    "role",
    [MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.ANALYST],
)
def test_authorized_roles_start_identification_atomically(role: MembershipRole) -> None:
    actor, database, factory, service, investigation = _setup(role)
    command = _start_command(investigation)

    result = service.start_identification(actor, command)

    assert result.state is InvestigationState.IDENTIFYING
    assert result.state_version == 2
    assert result.occurred_at == NOW
    assert not result.replayed
    persisted = database.investigations[(actor.workspace_id, investigation.id)]
    assert persisted.state is InvestigationState.IDENTIFYING
    assert persisted.identification_input == command.identification_input
    assert len(database.investigation_transitions) == 1
    record = next(iter(database.investigation_transitions.values()))
    assert record.command_type is InvestigationCommandType.START_IDENTIFICATION
    assert record.actor_user_id == actor.user_id
    assert database.audit_events[-1].action_code == (
        AuditActionCode.INVESTIGATION_IDENTIFICATION_STARTED.value
    )
    assert database.audit_events[-1].outcome is AuditOutcome.SUCCESS
    assert factory.created[0].commit_calls == 1


def test_viewer_is_denied_before_resource_or_command_lookup() -> None:
    actor, database, factory, service, investigation = _setup(MembershipRole.VIEWER)

    with pytest.raises(AuthorizationDeniedError):
        service.start_identification(actor, _start_command(investigation))

    assert database.investigations[(actor.workspace_id, investigation.id)] == investigation
    assert database.investigation_transitions == {}
    unit_of_work = factory.created[0]
    assert unit_of_work.investigations.get_calls == []
    assert unit_of_work.investigation_transitions.get_calls == []
    assert database.audit_events[-1].reason_code == AuditReasonCode.PERMISSION_DENIED.value


def test_cross_workspace_and_missing_investigation_are_safe_absence() -> None:
    actor, database, factory, service, investigation = _setup()
    other_investigation = Investigation(
        id=InvestigationId.new(),
        workspace_id=WorkspaceId.new(),
        requested_by=UserId.new(),
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        created_at=NOW - timedelta(minutes=1),
    )
    database.investigations[(other_investigation.workspace_id, other_investigation.id)] = (
        other_investigation
    )
    command = StartIdentification(
        command_id=InvestigationCommandId.new(),
        investigation_id=other_investigation.id,
        expected_state_version=1,
        identification_input=_input(),
    )

    with pytest.raises(ResourceNotFoundError):
        service.start_identification(actor, command)

    assert factory.created[0].investigations.get_calls == [
        (actor.workspace_id, other_investigation.id)
    ]
    assert database.investigations[(actor.workspace_id, investigation.id)] == investigation
    assert database.audit_events[-1].resource_id is None
    assert database.audit_events[-1].outcome is AuditOutcome.DENIED


def test_exact_command_replay_is_durable_and_has_no_second_effect_or_success_audit() -> None:
    actor, database, factory, service, investigation = _setup()
    command = _start_command(investigation)

    first = service.start_identification(actor, command)
    second = service.start_identification(actor, command)

    assert not first.replayed
    assert second.replayed
    assert second.investigation_id == first.investigation_id
    assert second.state == first.state
    assert second.state_version == first.state_version
    assert second.occurred_at == first.occurred_at
    assert len(database.investigation_transitions) == 1
    assert len(database.audit_events) == 1
    replay_unit_of_work = factory.created[1]
    assert replay_unit_of_work.investigations.get_calls == []
    assert replay_unit_of_work.investigations.cas_calls == []


def test_same_command_id_with_different_content_is_collision_without_transition() -> None:
    actor, database, _, service, investigation = _setup()
    command_id = InvestigationCommandId.new()
    service.start_identification(
        actor,
        _start_command(investigation, command_id=command_id),
    )

    with pytest.raises(InvestigationCommandCollisionError):
        service.start_identification(
            actor,
            _start_command(
                investigation,
                command_id=command_id,
                name="Conteúdo Diferente",
            ),
        )

    assert len(database.investigation_transitions) == 1
    assert database.investigations[(actor.workspace_id, investigation.id)].state_version == 2
    assert database.audit_events[-1].reason_code == AuditReasonCode.COMMAND_ID_COLLISION.value
    assert database.audit_events[-1].outcome is AuditOutcome.FAILURE


def test_stale_expected_version_is_typed_and_does_not_attempt_cas() -> None:
    actor, database, factory, service, investigation = _setup()

    with pytest.raises(ConcurrentInvestigationUpdateError):
        service.start_identification(
            actor,
            _start_command(investigation, expected_state_version=2),
        )

    assert factory.created[0].investigations.cas_calls == []
    assert database.investigations[(actor.workspace_id, investigation.id)] == investigation
    assert database.investigation_transitions == {}
    assert database.audit_events[-1].reason_code == AuditReasonCode.STATE_VERSION_CONFLICT.value


def test_compare_and_swap_conflict_preserves_state_and_records_failure_only() -> None:
    actor, database, factory, service, investigation = _setup(force_cas_conflict=True)

    with pytest.raises(ConcurrentInvestigationUpdateError):
        service.start_identification(actor, _start_command(investigation))

    assert len(factory.created[0].investigations.cas_calls) == 1
    assert database.investigations[(actor.workspace_id, investigation.id)] == investigation
    assert database.investigation_transitions == {}
    assert len(database.audit_events) == 1
    assert database.audit_events[0].outcome is AuditOutcome.FAILURE


@pytest.mark.parametrize(
    "failure",
    ["ledger", "audit", "commit"],
)
def test_ledger_audit_or_commit_failure_rolls_back_entire_success(
    failure: str,
) -> None:
    actor, database, _, service, investigation = _setup(
        fail_transition_add=failure == "ledger",
        fail_audit=failure == "audit",
        fail_commit=failure == "commit",
    )

    with pytest.raises(PersistenceError):
        service.start_identification(actor, _start_command(investigation))

    assert database.investigations[(actor.workspace_id, investigation.id)] == investigation
    assert database.investigation_transitions == {}
    assert database.audit_events == []


def test_cancel_created_is_atomic_and_audits_only_closed_reason() -> None:
    actor, database, _, service, investigation = _setup()
    command = CancelInvestigation(
        command_id=InvestigationCommandId.new(),
        investigation_id=investigation.id,
        expected_state_version=1,
        reason=InvestigationCancellationReason.NO_LONGER_REQUIRED,
    )

    result = service.cancel_investigation(actor, command)

    assert result.state is InvestigationState.CANCELLED
    assert result.state_version == 2
    cancelled = database.investigations[(actor.workspace_id, investigation.id)]
    assert cancelled.started_at == cancelled.completed_at == NOW
    record = next(iter(database.investigation_transitions.values()))
    assert record.reason is InvestigationCancellationReason.NO_LONGER_REQUIRED
    event = database.audit_events[-1]
    assert event.action_code == AuditActionCode.INVESTIGATION_CANCELLED.value
    assert event.reason_code == AuditReasonCode.CANCELLATION_NO_LONGER_REQUIRED.value


def test_cancel_terminal_is_invalid_but_exact_replay_remains_successful() -> None:
    actor, database, _, service, investigation = _setup()
    command = CancelInvestigation(
        command_id=InvestigationCommandId.new(),
        investigation_id=investigation.id,
        expected_state_version=1,
        reason=InvestigationCancellationReason.USER_REQUESTED,
    )
    first = service.cancel_investigation(actor, command)
    replay = service.cancel_investigation(actor, command)
    another = CancelInvestigation(
        command_id=InvestigationCommandId.new(),
        investigation_id=investigation.id,
        expected_state_version=2,
        reason=InvestigationCancellationReason.POLICY_REQUIRED,
    )

    with pytest.raises(InvestigationTransitionError):
        service.cancel_investigation(actor, another)

    assert not first.replayed and replay.replayed
    assert len(database.investigation_transitions) == 1
    assert database.audit_events[-1].reason_code == AuditReasonCode.INVALID_TRANSITION.value


@dataclass(slots=True)
class CountingClock:
    instant: datetime
    calls: list[datetime] = field(default_factory=list)

    def now(self) -> datetime:
        self.calls.append(self.instant)
        return self.instant


def test_clock_is_read_once_for_effective_transition_and_not_for_replay() -> None:
    actor, database, factory, _, investigation = _setup()
    clock = CountingClock(NOW)
    service = InvestigationService(factory, ContextualAuthorizer(), clock)
    command = _start_command(investigation)

    service.start_identification(actor, command)
    service.start_identification(actor, command)

    assert clock.calls == [NOW]
    assert "Empresa Exemplo" not in repr(database.audit_events[0])
