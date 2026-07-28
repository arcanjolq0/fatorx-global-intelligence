"""Authorized workspace membership administration with coordinated audit."""

from typing import Never

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import (
    AuditActionCode,
    AuditReasonCode,
    append_audit_event,
    commit_standalone_outcome,
)
from intelligence.application.authorization import (
    AuthorizedActor,
    ContextualAuthorizer,
    Permission,
)
from intelligence.application.errors import (
    AuthorizationDeniedError,
    InvalidOperationError,
    LastOwnerProtectionError,
    MembershipConflictError,
    PersistenceConflictError,
    ResourceNotFoundError,
)
from intelligence.application.ports.clock import Clock
from intelligence.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from intelligence.domain.audit import AuditOutcome, AuditResourceType
from intelligence.domain.identifiers import MembershipId, UserId
from intelligence.domain.identities import (
    MembershipRole,
    MembershipStatus,
    UserAccountStatus,
    WorkspaceMembership,
)

_ADMIN_TARGET_ROLES = frozenset({MembershipRole.ANALYST, MembershipRole.VIEWER})


class MembershipService:
    """Administer memberships within the workspace carried by the actor context."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        authorizer: ContextualAuthorizer,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authorizer = authorizer
        self._clock = clock

    def add_member(
        self,
        actor: ActorContext,
        *,
        user_id: UserId,
        role: MembershipRole,
    ) -> WorkspaceMembership:
        action = AuditActionCode.MEMBERSHIP_ADDED
        try:
            with self._unit_of_work_factory() as unit_of_work:
                authorized = self._authorize(
                    unit_of_work,
                    actor,
                    Permission.MEMBERSHIP_ADD,
                    action,
                )
                self._require_target_role(
                    unit_of_work,
                    actor,
                    authorized,
                    action,
                    role,
                )
                target_user = unit_of_work.users.get(user_id)
                if target_user is None:
                    self._fail(
                        unit_of_work,
                        actor,
                        action,
                        AuditReasonCode.TARGET_USER_NOT_FOUND,
                        ResourceNotFoundError(),
                    )
                if target_user.status is not UserAccountStatus.ACTIVE:
                    self._fail(
                        unit_of_work,
                        actor,
                        action,
                        AuditReasonCode.TARGET_USER_DISABLED,
                        InvalidOperationError(),
                    )
                if unit_of_work.memberships.get(actor.workspace_id, user_id) is not None:
                    self._fail(
                        unit_of_work,
                        actor,
                        action,
                        AuditReasonCode.TARGET_MEMBERSHIP_ALREADY_EXISTS,
                        MembershipConflictError(),
                    )

                occurred_at = self._clock.now()
                membership = WorkspaceMembership(
                    id=MembershipId.new(),
                    workspace_id=actor.workspace_id,
                    user_id=user_id,
                    role=role,
                    status=MembershipStatus.ACTIVE,
                    created_at=occurred_at,
                    updated_at=occurred_at,
                )
                unit_of_work.memberships.add(membership)
                append_audit_event(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    resource_type=AuditResourceType.MEMBERSHIP,
                    resource_id=membership.id,
                    outcome=AuditOutcome.SUCCESS,
                    reason=None,
                    occurred_at=occurred_at,
                )
                unit_of_work.commit()
                return membership
        except PersistenceConflictError as error:
            raise MembershipConflictError() from error

    def change_role(
        self,
        actor: ActorContext,
        *,
        user_id: UserId,
        new_role: MembershipRole,
    ) -> WorkspaceMembership:
        action = AuditActionCode.MEMBERSHIP_ROLE_CHANGED
        try:
            with self._unit_of_work_factory() as unit_of_work:
                authorized = self._authorize(
                    unit_of_work,
                    actor,
                    Permission.MEMBERSHIP_CHANGE_ROLE,
                    action,
                )
                active_owners = unit_of_work.memberships.list_active_owners_for_update(
                    actor.workspace_id
                )
                membership = self._target_for_update(unit_of_work, actor, action, user_id)
                self._require_membership_management(
                    unit_of_work,
                    actor,
                    authorized,
                    action,
                    membership,
                    new_role=new_role,
                )
                if membership.role is new_role:
                    self._fail(
                        unit_of_work,
                        actor,
                        action,
                        AuditReasonCode.VALIDATION_FAILURE,
                        InvalidOperationError(),
                        membership_id=membership.id,
                    )
                if (
                    membership.status is MembershipStatus.ACTIVE
                    and membership.role is MembershipRole.OWNER
                    and new_role is not MembershipRole.OWNER
                ):
                    self._protect_last_owner(
                        unit_of_work,
                        actor,
                        action,
                        membership,
                        active_owners,
                    )

                occurred_at = self._clock.now()
                changed = membership.change_role(new_role, updated_at=occurred_at)
                unit_of_work.memberships.update(changed)
                append_audit_event(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    resource_type=AuditResourceType.MEMBERSHIP,
                    resource_id=changed.id,
                    outcome=AuditOutcome.SUCCESS,
                    reason=None,
                    occurred_at=occurred_at,
                )
                unit_of_work.commit()
                return changed
        except PersistenceConflictError as error:
            raise MembershipConflictError() from error

    def deactivate_member(
        self,
        actor: ActorContext,
        *,
        user_id: UserId,
    ) -> WorkspaceMembership:
        action = AuditActionCode.MEMBERSHIP_DEACTIVATED
        try:
            with self._unit_of_work_factory() as unit_of_work:
                authorized = self._authorize(
                    unit_of_work,
                    actor,
                    Permission.MEMBERSHIP_DEACTIVATE,
                    action,
                )
                active_owners = unit_of_work.memberships.list_active_owners_for_update(
                    actor.workspace_id
                )
                membership = self._target_for_update(unit_of_work, actor, action, user_id)
                self._require_membership_management(
                    unit_of_work,
                    actor,
                    authorized,
                    action,
                    membership,
                )
                if membership.status is not MembershipStatus.ACTIVE:
                    self._fail(
                        unit_of_work,
                        actor,
                        action,
                        AuditReasonCode.VALIDATION_FAILURE,
                        InvalidOperationError(),
                        membership_id=membership.id,
                    )
                if membership.role is MembershipRole.OWNER:
                    self._protect_last_owner(
                        unit_of_work,
                        actor,
                        action,
                        membership,
                        active_owners,
                    )

                occurred_at = self._clock.now()
                deactivated = membership.deactivate(updated_at=occurred_at)
                unit_of_work.memberships.update(deactivated)
                append_audit_event(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    resource_type=AuditResourceType.MEMBERSHIP,
                    resource_id=deactivated.id,
                    outcome=AuditOutcome.SUCCESS,
                    reason=None,
                    occurred_at=occurred_at,
                )
                unit_of_work.commit()
                return deactivated
        except PersistenceConflictError as error:
            raise MembershipConflictError() from error

    def reactivate_member(
        self,
        actor: ActorContext,
        *,
        user_id: UserId,
    ) -> WorkspaceMembership:
        action = AuditActionCode.MEMBERSHIP_REACTIVATED
        try:
            with self._unit_of_work_factory() as unit_of_work:
                authorized = self._authorize(
                    unit_of_work,
                    actor,
                    Permission.MEMBERSHIP_REACTIVATE,
                    action,
                )
                membership = self._target_for_update(unit_of_work, actor, action, user_id)
                self._require_membership_management(
                    unit_of_work,
                    actor,
                    authorized,
                    action,
                    membership,
                )
                if membership.status is not MembershipStatus.INACTIVE:
                    self._fail(
                        unit_of_work,
                        actor,
                        action,
                        AuditReasonCode.VALIDATION_FAILURE,
                        InvalidOperationError(),
                        membership_id=membership.id,
                    )

                occurred_at = self._clock.now()
                reactivated = membership.reactivate(updated_at=occurred_at)
                unit_of_work.memberships.update(reactivated)
                append_audit_event(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    resource_type=AuditResourceType.MEMBERSHIP,
                    resource_id=reactivated.id,
                    outcome=AuditOutcome.SUCCESS,
                    reason=None,
                    occurred_at=occurred_at,
                )
                unit_of_work.commit()
                return reactivated
        except PersistenceConflictError as error:
            raise MembershipConflictError() from error

    def _authorize(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        permission: Permission,
        action: AuditActionCode,
    ) -> AuthorizedActor:
        decision = self._authorizer.authorize(unit_of_work, actor, permission)
        if decision.authorized_actor is not None:
            return decision.authorized_actor
        reason = decision.denial_reason
        if reason is None:
            raise RuntimeError("A denied authorization decision requires a reason.")
        commit_standalone_outcome(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=AuditResourceType.MEMBERSHIP,
            resource_id=None,
            outcome=AuditOutcome.DENIED,
            reason=reason,
            occurred_at=self._clock.now(),
        )
        raise AuthorizationDeniedError()

    def _require_target_role(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        authorized: AuthorizedActor,
        action: AuditActionCode,
        role: MembershipRole,
    ) -> None:
        if not isinstance(role, MembershipRole) or (
            authorized.role is MembershipRole.ADMIN and role not in _ADMIN_TARGET_ROLES
        ):
            self._deny(
                unit_of_work,
                actor,
                action,
                AuditReasonCode.TARGET_ROLE_NOT_ALLOWED,
            )

    def _require_membership_management(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        authorized: AuthorizedActor,
        action: AuditActionCode,
        membership: WorkspaceMembership,
        *,
        new_role: MembershipRole | None = None,
    ) -> None:
        if authorized.role is MembershipRole.ADMIN:
            if membership.user_id == actor.user_id:
                self._deny(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.SELF_MANAGEMENT_NOT_ALLOWED,
                    membership.id,
                )
            if membership.role not in _ADMIN_TARGET_ROLES or (
                new_role is not None and new_role not in _ADMIN_TARGET_ROLES
            ):
                self._deny(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.TARGET_ROLE_NOT_ALLOWED,
                    membership.id,
                )

    def _target_for_update(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        action: AuditActionCode,
        user_id: UserId,
    ) -> WorkspaceMembership:
        membership = unit_of_work.memberships.get_for_update(actor.workspace_id, user_id)
        if membership is None:
            self._fail(
                unit_of_work,
                actor,
                action,
                AuditReasonCode.TARGET_MEMBERSHIP_NOT_FOUND,
                ResourceNotFoundError(),
            )
        return membership

    def _protect_last_owner(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        action: AuditActionCode,
        membership: WorkspaceMembership,
        active_owners: list[WorkspaceMembership],
    ) -> None:
        if len(active_owners) <= 1:
            self._deny(
                unit_of_work,
                actor,
                action,
                AuditReasonCode.LAST_OWNER_PROTECTED,
                membership.id,
                LastOwnerProtectionError(),
            )

    def _deny(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        action: AuditActionCode,
        reason: AuditReasonCode,
        membership_id: MembershipId | None = None,
        error: Exception | None = None,
    ) -> Never:
        commit_standalone_outcome(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=AuditResourceType.MEMBERSHIP,
            resource_id=membership_id,
            outcome=AuditOutcome.DENIED,
            reason=reason,
            occurred_at=self._clock.now(),
        )
        raise error or AuthorizationDeniedError()

    def _fail(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        action: AuditActionCode,
        reason: AuditReasonCode,
        error: Exception,
        *,
        membership_id: MembershipId | None = None,
    ) -> Never:
        commit_standalone_outcome(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=AuditResourceType.MEMBERSHIP,
            resource_id=membership_id,
            outcome=AuditOutcome.FAILURE,
            reason=reason,
            occurred_at=self._clock.now(),
        )
        raise error


__all__ = ["MembershipService"]
