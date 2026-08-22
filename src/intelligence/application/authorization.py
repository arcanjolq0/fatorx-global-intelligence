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
    INVESTIGATION_CANCEL = "INVESTIGATION_CANCEL"
    INVESTIGATION_READ = "INVESTIGATION_READ"
    INVESTIGATION_START_IDENTIFICATION = "INVESTIGATION_START_IDENTIFICATION"
    INVESTIGATION_REQUEST_ENTITY_CONFIRMATION = "INVESTIGATION_REQUEST_ENTITY_CONFIRMATION"
    INVESTIGATION_ENTITY_CONFIRM = "INVESTIGATION_ENTITY_CONFIRM"
    INVESTIGATION_PLAN_CREATE = "INVESTIGATION_PLAN_CREATE"
    INVESTIGATION_COLLECTION_START = "INVESTIGATION_COLLECTION_START"
    COLLECTION_OPERATION_EXECUTE = "COLLECTION_OPERATION_EXECUTE"
    EVIDENCE_REGISTER = "EVIDENCE_REGISTER"
    EVIDENCE_CORRECT = "EVIDENCE_CORRECT"
    EVIDENCE_REVOKE = "EVIDENCE_REVOKE"
    EVIDENCE_READ = "EVIDENCE_READ"
    EVIDENCE_ADMISSIBILITY_READ = "EVIDENCE_ADMISSIBILITY_READ"
    EVIDENCE_ADMISSIBILITY_ADMIT = "EVIDENCE_ADMISSIBILITY_ADMIT"
    EVIDENCE_ADMISSIBILITY_RESTRICT = "EVIDENCE_ADMISSIBILITY_RESTRICT"
    EVIDENCE_ADMISSIBILITY_REJECT = "EVIDENCE_ADMISSIBILITY_REJECT"
    EVIDENCE_ADMISSIBILITY_SUPERSEDE = "EVIDENCE_ADMISSIBILITY_SUPERSEDE"
    CLAIM_READ = "CLAIM_READ"
    CLAIM_REGISTER = "CLAIM_REGISTER"
    CLAIM_CORRECT = "CLAIM_CORRECT"
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
    }
)
_READ_ONLY = frozenset(
    {
        Permission.CLAIM_READ,
        Permission.COMPANY_READ,
        Permission.INVESTIGATION_READ,
        Permission.EVIDENCE_READ,
        Permission.EVIDENCE_ADMISSIBILITY_READ,
    }
)
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
