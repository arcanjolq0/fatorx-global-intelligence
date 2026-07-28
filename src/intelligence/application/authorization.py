"""Pure role policy and contextual authorization for application services."""

from dataclasses import dataclass
from enum import StrEnum

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import AuditReasonCode
from intelligence.application.ports.unit_of_work import UnitOfWork
from intelligence.domain.identifiers import CorrelationId, UserId, WorkspaceId
from intelligence.domain.identities import (
    MembershipRole,
    MembershipStatus,
    UserAccountStatus,
)


class Permission(StrEnum):
    """Closed permission vocabulary for the F2.4.2 services."""

    COMPANY_CREATE = "COMPANY_CREATE"
    COMPANY_READ = "COMPANY_READ"
    INVESTIGATION_CREATE = "INVESTIGATION_CREATE"
    INVESTIGATION_READ = "INVESTIGATION_READ"
    MEMBERSHIP_ADD = "MEMBERSHIP_ADD"
    MEMBERSHIP_CHANGE_ROLE = "MEMBERSHIP_CHANGE_ROLE"
    MEMBERSHIP_DEACTIVATE = "MEMBERSHIP_DEACTIVATE"
    MEMBERSHIP_REACTIVATE = "MEMBERSHIP_REACTIVATE"


_ALL_PERMISSIONS = frozenset(Permission)
_CREATE_AND_READ = frozenset(
    {
        Permission.COMPANY_CREATE,
        Permission.COMPANY_READ,
        Permission.INVESTIGATION_CREATE,
        Permission.INVESTIGATION_READ,
    }
)
_READ_ONLY = frozenset({Permission.COMPANY_READ, Permission.INVESTIGATION_READ})
_ROLE_PERMISSIONS: dict[MembershipRole, frozenset[Permission]] = {
    MembershipRole.OWNER: _ALL_PERMISSIONS,
    MembershipRole.ADMIN: _ALL_PERMISSIONS,
    MembershipRole.ANALYST: _CREATE_AND_READ,
    MembershipRole.VIEWER: _READ_ONLY,
}


class RolePermissionPolicy:
    """Deterministic role-to-permission matrix without IO or mutable state."""

    @staticmethod
    def allows(role: MembershipRole, permission: Permission) -> bool:
        if not isinstance(role, MembershipRole):
            raise TypeError("role must be a MembershipRole")
        if not isinstance(permission, Permission):
            raise TypeError("permission must be a Permission")
        return permission in _ROLE_PERMISSIONS[role]


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizedActor:
    """Minimal authorization result, never a database row or credential."""

    user_id: UserId
    workspace_id: WorkspaceId
    correlation_id: CorrelationId
    role: MembershipRole


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizationDecision:
    """Explicit allowed actor or closed denial reason."""

    authorized_actor: AuthorizedActor | None
    denial_reason: AuditReasonCode | None

    @property
    def is_allowed(self) -> bool:
        return self.authorized_actor is not None

    @classmethod
    def allow(cls, actor: AuthorizedActor) -> AuthorizationDecision:
        return cls(authorized_actor=actor, denial_reason=None)

    @classmethod
    def deny(cls, reason: AuditReasonCode) -> AuthorizationDecision:
        return cls(authorized_actor=None, denial_reason=reason)


class ContextualAuthorizer:
    """Validate actor identity, tenant membership, state, and role in one UoW."""

    def __init__(self, policy: RolePermissionPolicy | None = None) -> None:
        self._policy = policy or RolePermissionPolicy()

    def authorize(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        permission: Permission,
    ) -> AuthorizationDecision:
        user = unit_of_work.users.get(actor.user_id)
        if user is None:
            return AuthorizationDecision.deny(AuditReasonCode.ACTOR_USER_NOT_FOUND)
        if user.status is not UserAccountStatus.ACTIVE:
            return AuthorizationDecision.deny(AuditReasonCode.ACTOR_USER_DISABLED)

        membership = unit_of_work.memberships.get(actor.workspace_id, actor.user_id)
        if membership is None:
            return AuthorizationDecision.deny(AuditReasonCode.ACTOR_MEMBERSHIP_NOT_FOUND)
        if membership.workspace_id != actor.workspace_id or membership.user_id != actor.user_id:
            return AuthorizationDecision.deny(AuditReasonCode.WORKSPACE_SCOPE_VIOLATION)
        if membership.status is not MembershipStatus.ACTIVE:
            return AuthorizationDecision.deny(AuditReasonCode.ACTOR_MEMBERSHIP_INACTIVE)
        if not self._policy.allows(membership.role, permission):
            return AuthorizationDecision.deny(AuditReasonCode.PERMISSION_DENIED)

        return AuthorizationDecision.allow(
            AuthorizedActor(
                user_id=actor.user_id,
                workspace_id=actor.workspace_id,
                correlation_id=actor.correlation_id,
                role=membership.role,
            )
        )


__all__ = [
    "AuthorizationDecision",
    "AuthorizedActor",
    "ContextualAuthorizer",
    "Permission",
    "RolePermissionPolicy",
]
