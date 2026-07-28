"""Closed audit vocabulary and explicit application-level event coordination."""

from datetime import datetime
from enum import StrEnum

from intelligence.application.actor_context import ActorContext
from intelligence.application.errors import PersistenceError
from intelligence.application.ports.unit_of_work import UnitOfWork
from intelligence.domain.audit import (
    AuditEvent,
    AuditOutcome,
    AuditResourceId,
    AuditResourceType,
)
from intelligence.domain.identifiers import AuditEventId


class AuditActionCode(StrEnum):
    """Closed actions recorded by the F2.4.2 application services."""

    MEMBERSHIP_ADDED = "MEMBERSHIP_ADDED"
    MEMBERSHIP_ROLE_CHANGED = "MEMBERSHIP_ROLE_CHANGED"
    MEMBERSHIP_DEACTIVATED = "MEMBERSHIP_DEACTIVATED"
    MEMBERSHIP_REACTIVATED = "MEMBERSHIP_REACTIVATED"
    COMPANY_CREATED = "COMPANY_CREATED"
    INVESTIGATION_CREATED = "INVESTIGATION_CREATED"
    COMPANY_READ_DENIED = "COMPANY_READ_DENIED"
    INVESTIGATION_READ_DENIED = "INVESTIGATION_READ_DENIED"


class AuditReasonCode(StrEnum):
    """Closed, redacted explanations for denied and failed actions."""

    ACTOR_USER_NOT_FOUND = "ACTOR_USER_NOT_FOUND"
    ACTOR_USER_DISABLED = "ACTOR_USER_DISABLED"
    ACTOR_MEMBERSHIP_NOT_FOUND = "ACTOR_MEMBERSHIP_NOT_FOUND"
    ACTOR_MEMBERSHIP_INACTIVE = "ACTOR_MEMBERSHIP_INACTIVE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TARGET_USER_NOT_FOUND = "TARGET_USER_NOT_FOUND"
    TARGET_USER_DISABLED = "TARGET_USER_DISABLED"
    TARGET_MEMBERSHIP_NOT_FOUND = "TARGET_MEMBERSHIP_NOT_FOUND"
    TARGET_MEMBERSHIP_ALREADY_EXISTS = "TARGET_MEMBERSHIP_ALREADY_EXISTS"
    TARGET_ROLE_NOT_ALLOWED = "TARGET_ROLE_NOT_ALLOWED"
    SELF_MANAGEMENT_NOT_ALLOWED = "SELF_MANAGEMENT_NOT_ALLOWED"
    LAST_OWNER_PROTECTED = "LAST_OWNER_PROTECTED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    WORKSPACE_SCOPE_VIOLATION = "WORKSPACE_SCOPE_VIOLATION"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    PERSISTENCE_CONFLICT = "PERSISTENCE_CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


def build_audit_event(
    *,
    actor: ActorContext,
    action: AuditActionCode,
    resource_type: AuditResourceType,
    resource_id: AuditResourceId | None,
    outcome: AuditOutcome,
    reason: AuditReasonCode | None,
    occurred_at: datetime,
) -> AuditEvent:
    """Build one minimal event using only trusted context and closed codes."""

    if not isinstance(action, AuditActionCode):
        raise TypeError("action must be an AuditActionCode")
    if reason is not None and not isinstance(reason, AuditReasonCode):
        raise TypeError("reason must be an AuditReasonCode or None")
    if outcome is not AuditOutcome.SUCCESS and reason is None:
        raise ValueError("Denied and failed audit events require a reason code.")
    return AuditEvent(
        id=AuditEventId.new(),
        workspace_id=actor.workspace_id,
        actor_user_id=actor.user_id,
        action_code=action.value,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        reason_code=reason.value if reason is not None else None,
        correlation_id=actor.correlation_id,
        occurred_at=occurred_at,
    )


def append_audit_event(
    unit_of_work: UnitOfWork,
    *,
    actor: ActorContext,
    action: AuditActionCode,
    resource_type: AuditResourceType,
    resource_id: AuditResourceId | None,
    outcome: AuditOutcome,
    reason: AuditReasonCode | None,
    occurred_at: datetime,
) -> AuditEvent:
    """Append an event to the caller's active transaction without committing it."""

    event = build_audit_event(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        reason=reason,
        occurred_at=occurred_at,
    )
    unit_of_work.audit_events.add(event)
    return event


def commit_standalone_outcome(
    unit_of_work: UnitOfWork,
    *,
    actor: ActorContext,
    action: AuditActionCode,
    resource_type: AuditResourceType,
    resource_id: AuditResourceId | None,
    outcome: AuditOutcome,
    reason: AuditReasonCode,
    occurred_at: datetime,
) -> bool:
    """Persist a denial/failure without replacing the original application error."""

    try:
        append_audit_event(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            reason=reason,
            occurred_at=occurred_at,
        )
        unit_of_work.commit()
    except PersistenceError:
        return False
    return True


__all__ = [
    "AuditActionCode",
    "AuditReasonCode",
    "append_audit_event",
    "build_audit_event",
    "commit_standalone_outcome",
]
