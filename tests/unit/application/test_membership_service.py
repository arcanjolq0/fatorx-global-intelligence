"""Unit tests for authorized membership administration and audit coordination."""

from datetime import UTC, datetime, timedelta

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import AuditActionCode, AuditReasonCode
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import (
    AuthorizationDeniedError,
    InvalidOperationError,
    LastOwnerProtectionError,
    MembershipConflictError,
    PersistenceError,
    ResourceNotFoundError,
)
from intelligence.application.services.memberships import MembershipService
from intelligence.domain.audit import AuditOutcome
from intelligence.domain.identifiers import CorrelationId, MembershipId, UserId, WorkspaceId
from intelligence.domain.identities import (
    EmailAddress,
    MembershipRole,
    MembershipStatus,
    UserAccount,
    UserAccountStatus,
    WorkspaceMembership,
)
from tests.unit.application.fakes import FakeClock, FakeDatabase, FakeUnitOfWorkFactory

NOW = datetime(2026, 7, 28, 15, tzinfo=UTC)


def _actor() -> ActorContext:
    return ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )


def _user(
    user_id: UserId,
    *,
    status: UserAccountStatus = UserAccountStatus.ACTIVE,
) -> UserAccount:
    return UserAccount(
        id=user_id,
        email=EmailAddress(f"{user_id.value}@example.test"),
        display_name="Internal user",
        status=status,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )


def _membership(
    actor: ActorContext,
    user_id: UserId,
    role: MembershipRole,
    *,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> WorkspaceMembership:
    timestamp = NOW - timedelta(hours=1)
    return WorkspaceMembership(
        id=MembershipId.new(),
        workspace_id=actor.workspace_id,
        user_id=user_id,
        role=role,
        status=status,
        created_at=timestamp,
        updated_at=timestamp,
        deactivated_at=timestamp if status is MembershipStatus.INACTIVE else None,
    )


def _setup(
    actor_role: MembershipRole,
    *,
    target_role: MembershipRole | None = None,
    target_status: MembershipStatus = MembershipStatus.ACTIVE,
    target_user_status: UserAccountStatus = UserAccountStatus.ACTIVE,
    target_is_actor: bool = False,
) -> tuple[
    ActorContext,
    UserId,
    FakeDatabase,
    FakeUnitOfWorkFactory,
    MembershipService,
]:
    actor = _actor()
    target_user_id = actor.user_id if target_is_actor else UserId.new()
    database = FakeDatabase(users={actor.user_id: _user(actor.user_id)})
    database.memberships[(actor.workspace_id, actor.user_id)] = _membership(
        actor,
        actor.user_id,
        actor_role,
    )
    if not target_is_actor:
        database.users[target_user_id] = _user(target_user_id, status=target_user_status)
    if target_role is not None and not target_is_actor:
        database.memberships[(actor.workspace_id, target_user_id)] = _membership(
            actor,
            target_user_id,
            target_role,
            status=target_status,
        )
    factory = FakeUnitOfWorkFactory(database)
    service = MembershipService(factory, ContextualAuthorizer(), FakeClock(NOW))
    return actor, target_user_id, database, factory, service


@pytest.mark.parametrize(
    ("actor_role", "target_role"),
    [
        (MembershipRole.OWNER, MembershipRole.OWNER),
        (MembershipRole.OWNER, MembershipRole.ADMIN),
        (MembershipRole.ADMIN, MembershipRole.ANALYST),
        (MembershipRole.ADMIN, MembershipRole.VIEWER),
    ],
)
def test_allowed_roles_add_membership_and_success_audit_atomically(
    actor_role: MembershipRole,
    target_role: MembershipRole,
) -> None:
    actor, target_user_id, database, factory, service = _setup(actor_role)

    membership = service.add_member(actor, user_id=target_user_id, role=target_role)

    assert membership.workspace_id == actor.workspace_id
    assert membership.user_id == target_user_id
    assert membership.role is target_role
    assert membership.status is MembershipStatus.ACTIVE
    assert database.memberships[(actor.workspace_id, target_user_id)] == membership
    event = database.audit_events[-1]
    assert event.action_code == AuditActionCode.MEMBERSHIP_ADDED.value
    assert event.outcome is AuditOutcome.SUCCESS
    assert event.resource_id == membership.id
    assert event.correlation_id == actor.correlation_id
    assert factory.created[0].commit_calls == 1


@pytest.mark.parametrize("target_role", [MembershipRole.OWNER, MembershipRole.ADMIN])
def test_admin_cannot_add_owner_or_admin_and_denial_is_audited(
    target_role: MembershipRole,
) -> None:
    actor, target_user_id, database, _, service = _setup(MembershipRole.ADMIN)

    with pytest.raises(AuthorizationDeniedError, match="not authorized"):
        service.add_member(actor, user_id=target_user_id, role=target_role)

    assert (actor.workspace_id, target_user_id) not in database.memberships
    event = database.audit_events[-1]
    assert event.outcome is AuditOutcome.DENIED
    assert event.reason_code == AuditReasonCode.TARGET_ROLE_NOT_ALLOWED.value


@pytest.mark.parametrize("actor_role", [MembershipRole.ANALYST, MembershipRole.VIEWER])
def test_non_administrative_roles_cannot_manage_memberships(
    actor_role: MembershipRole,
) -> None:
    actor, target_user_id, database, _, service = _setup(actor_role)

    with pytest.raises(AuthorizationDeniedError):
        service.add_member(actor, user_id=target_user_id, role=MembershipRole.VIEWER)

    assert database.audit_events[-1].reason_code == AuditReasonCode.PERMISSION_DENIED.value
    assert (actor.workspace_id, target_user_id) not in database.memberships


def test_add_rejects_missing_disabled_and_duplicate_targets_with_failure_audit() -> None:
    actor, target_user_id, database, _, service = _setup(MembershipRole.OWNER)
    del database.users[target_user_id]

    with pytest.raises(ResourceNotFoundError):
        service.add_member(actor, user_id=target_user_id, role=MembershipRole.VIEWER)
    assert database.audit_events[-1].reason_code == AuditReasonCode.TARGET_USER_NOT_FOUND.value

    database.users[target_user_id] = _user(
        target_user_id,
        status=UserAccountStatus.DISABLED,
    )
    with pytest.raises(InvalidOperationError):
        service.add_member(actor, user_id=target_user_id, role=MembershipRole.VIEWER)
    assert database.audit_events[-1].reason_code == AuditReasonCode.TARGET_USER_DISABLED.value

    database.users[target_user_id] = _user(target_user_id)
    existing = _membership(actor, target_user_id, MembershipRole.VIEWER)
    database.memberships[(actor.workspace_id, target_user_id)] = existing
    with pytest.raises(MembershipConflictError):
        service.add_member(actor, user_id=target_user_id, role=MembershipRole.ANALYST)
    assert (
        database.audit_events[-1].reason_code
        == AuditReasonCode.TARGET_MEMBERSHIP_ALREADY_EXISTS.value
    )
    assert database.memberships[(actor.workspace_id, target_user_id)] == existing


def test_owner_changes_role_after_locking_owners_and_target() -> None:
    actor, target_user_id, database, factory, service = _setup(
        MembershipRole.OWNER,
        target_role=MembershipRole.ANALYST,
    )

    changed = service.change_role(
        actor,
        user_id=target_user_id,
        new_role=MembershipRole.VIEWER,
    )

    assert changed.role is MembershipRole.VIEWER
    assert changed.updated_at == NOW
    repository = factory.created[0].memberships
    assert repository.owner_lock_calls == [actor.workspace_id]
    assert repository.get_for_update_calls == [(actor.workspace_id, target_user_id)]
    assert database.audit_events[-1].action_code == AuditActionCode.MEMBERSHIP_ROLE_CHANGED.value


def test_admin_cannot_change_self_or_owner_admin_targets() -> None:
    actor, _, database, _, service = _setup(
        MembershipRole.ADMIN,
        target_is_actor=True,
    )

    with pytest.raises(AuthorizationDeniedError):
        service.change_role(actor, user_id=actor.user_id, new_role=MembershipRole.VIEWER)
    assert (
        database.audit_events[-1].reason_code == AuditReasonCode.SELF_MANAGEMENT_NOT_ALLOWED.value
    )

    actor, target_user_id, database, _, service = _setup(
        MembershipRole.ADMIN,
        target_role=MembershipRole.OWNER,
    )
    with pytest.raises(AuthorizationDeniedError):
        service.change_role(actor, user_id=target_user_id, new_role=MembershipRole.VIEWER)
    assert database.audit_events[-1].reason_code == AuditReasonCode.TARGET_ROLE_NOT_ALLOWED.value


def test_change_role_rejects_missing_target_and_noop() -> None:
    actor, target_user_id, database, _, service = _setup(MembershipRole.OWNER)

    with pytest.raises(ResourceNotFoundError):
        service.change_role(
            actor,
            user_id=target_user_id,
            new_role=MembershipRole.VIEWER,
        )
    assert (
        database.audit_events[-1].reason_code == AuditReasonCode.TARGET_MEMBERSHIP_NOT_FOUND.value
    )

    membership = _membership(actor, target_user_id, MembershipRole.VIEWER)
    database.memberships[(actor.workspace_id, target_user_id)] = membership
    with pytest.raises(InvalidOperationError):
        service.change_role(
            actor,
            user_id=target_user_id,
            new_role=MembershipRole.VIEWER,
        )
    assert database.memberships[(actor.workspace_id, target_user_id)] == membership
    assert database.audit_events[-1].reason_code == AuditReasonCode.VALIDATION_FAILURE.value


def test_last_owner_is_protected_for_self_demotion_and_deactivation() -> None:
    actor, _, database, _, service = _setup(MembershipRole.OWNER, target_is_actor=True)

    with pytest.raises(LastOwnerProtectionError):
        service.change_role(
            actor,
            user_id=actor.user_id,
            new_role=MembershipRole.ADMIN,
        )
    assert database.audit_events[-1].reason_code == AuditReasonCode.LAST_OWNER_PROTECTED.value

    with pytest.raises(LastOwnerProtectionError):
        service.deactivate_member(actor, user_id=actor.user_id)
    assert (
        database.memberships[(actor.workspace_id, actor.user_id)].status is MembershipStatus.ACTIVE
    )


def test_owner_can_demote_self_when_another_active_owner_remains() -> None:
    actor, _, database, _, service = _setup(MembershipRole.OWNER, target_is_actor=True)
    other_owner_id = UserId.new()
    database.users[other_owner_id] = _user(other_owner_id)
    database.memberships[(actor.workspace_id, other_owner_id)] = _membership(
        actor,
        other_owner_id,
        MembershipRole.OWNER,
    )

    changed = service.change_role(
        actor,
        user_id=actor.user_id,
        new_role=MembershipRole.ADMIN,
    )

    assert changed.role is MembershipRole.ADMIN
    assert database.memberships[(actor.workspace_id, other_owner_id)].role is MembershipRole.OWNER


def test_deactivate_and_reactivate_valid_membership() -> None:
    actor, target_user_id, database, _, service = _setup(
        MembershipRole.OWNER,
        target_role=MembershipRole.ANALYST,
    )

    inactive = service.deactivate_member(actor, user_id=target_user_id)
    active = service.reactivate_member(actor, user_id=target_user_id)

    assert inactive.status is MembershipStatus.INACTIVE
    assert inactive.deactivated_at == NOW
    assert active.status is MembershipStatus.ACTIVE
    assert active.deactivated_at is None
    assert database.memberships[(actor.workspace_id, target_user_id)] == active
    assert [event.action_code for event in database.audit_events[-2:]] == [
        AuditActionCode.MEMBERSHIP_DEACTIVATED.value,
        AuditActionCode.MEMBERSHIP_REACTIVATED.value,
    ]


def test_invalid_deactivate_and_reactivate_states_do_not_mutate_membership() -> None:
    actor, target_user_id, database, _, service = _setup(
        MembershipRole.OWNER,
        target_role=MembershipRole.ANALYST,
        target_status=MembershipStatus.INACTIVE,
    )

    with pytest.raises(InvalidOperationError):
        service.deactivate_member(actor, user_id=target_user_id)
    assert (
        database.memberships[(actor.workspace_id, target_user_id)].status
        is MembershipStatus.INACTIVE
    )

    current = database.memberships[(actor.workspace_id, target_user_id)].reactivate(updated_at=NOW)
    database.memberships[(actor.workspace_id, target_user_id)] = current
    with pytest.raises(InvalidOperationError):
        service.reactivate_member(actor, user_id=target_user_id)
    assert (
        database.memberships[(actor.workspace_id, target_user_id)].status is MembershipStatus.ACTIVE
    )


def test_success_commit_failure_rolls_back_membership_and_success_event() -> None:
    actor, target_user_id, database, _, _ = _setup(MembershipRole.OWNER)
    factory = FakeUnitOfWorkFactory(database, fail_commit=True)
    service = MembershipService(factory, ContextualAuthorizer(), FakeClock(NOW))

    with pytest.raises(PersistenceError, match="Unable to commit"):
        service.add_member(actor, user_id=target_user_id, role=MembershipRole.VIEWER)

    assert (actor.workspace_id, target_user_id) not in database.memberships
    assert database.audit_events == []
    assert factory.created[0].rollback_calls == 1
