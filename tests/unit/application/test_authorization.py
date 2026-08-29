"""Exhaustive role matrix and contextual authorization tests."""

from datetime import UTC, datetime
from typing import cast

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import AuditReasonCode
from intelligence.application.authorization import (
    ContextualAuthorizer,
    Permission,
    RolePermissionPolicy,
)
from intelligence.application.ports.unit_of_work import UnitOfWork
from intelligence.domain.identifiers import CorrelationId, MembershipId, UserId, WorkspaceId
from intelligence.domain.identities import (
    EmailAddress,
    MembershipRole,
    MembershipStatus,
    UserAccount,
    UserAccountStatus,
    WorkspaceMembership,
)
from tests.unit.application.fakes import FakeDatabase, FakeUnitOfWorkFactory

NOW = datetime(2026, 7, 28, 15, tzinfo=UTC)
CREATE_AND_READ = {
    Permission.COMPANY_CREATE,
    Permission.COMPANY_READ,
    Permission.INVESTIGATION_CREATE,
    Permission.INVESTIGATION_CANCEL,
    Permission.INVESTIGATION_READ,
    Permission.INVESTIGATION_START_IDENTIFICATION,
    Permission.INVESTIGATION_REQUEST_ENTITY_CONFIRMATION,
    Permission.INVESTIGATION_ENTITY_CONFIRM,
    Permission.INVESTIGATION_PLAN_CREATE,
    Permission.INVESTIGATION_COLLECTION_START,
    Permission.COLLECTION_OPERATION_EXECUTE,
    Permission.EVIDENCE_REGISTER,
    Permission.EVIDENCE_CORRECT,
    Permission.EVIDENCE_READ,
    Permission.EVIDENCE_ADMISSIBILITY_READ,
    Permission.CLAIM_READ,
    Permission.CLAIM_REVIEW_READ,
}
EXPECTED: dict[MembershipRole, set[Permission]] = {
    MembershipRole.OWNER: set(Permission),
    MembershipRole.ADMIN: set(Permission),
    MembershipRole.ANALYST: CREATE_AND_READ,
    MembershipRole.VIEWER: {
        Permission.COMPANY_READ,
        Permission.INVESTIGATION_READ,
        Permission.EVIDENCE_READ,
        Permission.EVIDENCE_ADMISSIBILITY_READ,
        Permission.CLAIM_READ,
        Permission.CLAIM_REVIEW_READ,
    },
}


def _user(user_id: UserId, status: UserAccountStatus = UserAccountStatus.ACTIVE) -> UserAccount:
    return UserAccount(
        id=user_id,
        email=EmailAddress(f"{user_id.value}@example.test"),
        display_name="Actor",
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def _membership(
    actor: ActorContext,
    role: MembershipRole,
    status: MembershipStatus = MembershipStatus.ACTIVE,
    *,
    workspace_id: WorkspaceId | None = None,
) -> WorkspaceMembership:
    return WorkspaceMembership(
        id=MembershipId.new(),
        workspace_id=workspace_id or actor.workspace_id,
        user_id=actor.user_id,
        role=role,
        status=status,
        created_at=NOW,
        updated_at=NOW,
        deactivated_at=NOW if status is MembershipStatus.INACTIVE else None,
    )


def _actor() -> ActorContext:
    return ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )


@pytest.mark.parametrize("role", list(MembershipRole))
@pytest.mark.parametrize("permission", list(Permission))
def test_role_permission_matrix_is_exhaustive(
    role: MembershipRole,
    permission: Permission,
) -> None:
    assert RolePermissionPolicy.allows(role, permission) is (permission in EXPECTED[role])


def test_role_policy_rejects_untyped_roles_and_permissions() -> None:
    with pytest.raises(TypeError, match="role"):
        RolePermissionPolicy.allows(cast(MembershipRole, "OWNER"), Permission.COMPANY_READ)
    with pytest.raises(TypeError, match="permission"):
        RolePermissionPolicy.allows(
            MembershipRole.OWNER,
            cast(Permission, "IMPLICIT_PERMISSION"),
        )


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("missing-user", AuditReasonCode.ACTOR_USER_NOT_FOUND),
        ("disabled-user", AuditReasonCode.ACTOR_USER_DISABLED),
        ("missing-membership", AuditReasonCode.ACTOR_MEMBERSHIP_NOT_FOUND),
        ("inactive-membership", AuditReasonCode.ACTOR_MEMBERSHIP_INACTIVE),
        ("wrong-workspace-membership", AuditReasonCode.WORKSPACE_SCOPE_VIOLATION),
        ("denied-role", AuditReasonCode.PERMISSION_DENIED),
    ],
)
def test_contextual_authorizer_returns_closed_denial_reasons(
    setup: str,
    reason: AuditReasonCode,
) -> None:
    actor = _actor()
    database = FakeDatabase()
    if setup != "missing-user":
        status = (
            UserAccountStatus.DISABLED if setup == "disabled-user" else UserAccountStatus.ACTIVE
        )
        database.users[actor.user_id] = _user(actor.user_id, status)
    if setup not in {"missing-user", "disabled-user", "missing-membership"}:
        membership = _membership(
            actor,
            MembershipRole.VIEWER if setup == "denied-role" else MembershipRole.OWNER,
            MembershipStatus.INACTIVE
            if setup == "inactive-membership"
            else MembershipStatus.ACTIVE,
        )
        database.memberships[(actor.workspace_id, actor.user_id)] = membership

    factory = FakeUnitOfWorkFactory(database)
    with factory() as concrete:
        if setup == "wrong-workspace-membership":
            concrete.memberships._database.memberships[(actor.workspace_id, actor.user_id)] = (
                _membership(actor, MembershipRole.OWNER, workspace_id=WorkspaceId.new())
            )
        decision = ContextualAuthorizer().authorize(
            cast(UnitOfWork, concrete),
            actor,
            Permission.COMPANY_CREATE,
        )

    assert not decision.is_allowed
    assert decision.authorized_actor is None
    assert decision.denial_reason is reason


def test_contextual_authorizer_returns_minimal_authorized_actor() -> None:
    actor = _actor()
    database = FakeDatabase(
        users={actor.user_id: _user(actor.user_id)},
        memberships={
            (actor.workspace_id, actor.user_id): _membership(actor, MembershipRole.ANALYST)
        },
    )
    factory = FakeUnitOfWorkFactory(database)

    with factory() as concrete:
        decision = ContextualAuthorizer().authorize(
            cast(UnitOfWork, concrete),
            actor,
            Permission.INVESTIGATION_CREATE,
        )

    assert decision.is_allowed
    assert decision.denial_reason is None
    assert decision.authorized_actor is not None
    assert decision.authorized_actor.user_id == actor.user_id
    assert decision.authorized_actor.workspace_id == actor.workspace_id
    assert decision.authorized_actor.correlation_id == actor.correlation_id
    assert decision.authorized_actor.role is MembershipRole.ANALYST


def test_resource_repositories_are_not_consulted_before_authorization() -> None:
    actor = _actor()
    factory = FakeUnitOfWorkFactory()

    with factory() as concrete:
        decision = ContextualAuthorizer().authorize(
            cast(UnitOfWork, concrete),
            actor,
            Permission.COMPANY_READ,
        )

        assert not decision.is_allowed
        assert concrete.companies.get_calls == []
        assert concrete.investigations.get_calls == []
