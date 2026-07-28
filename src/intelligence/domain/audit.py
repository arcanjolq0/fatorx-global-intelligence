"""Immutable minimal audit events without arbitrary payloads."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    AuditEventId,
    CompanyId,
    CorrelationId,
    InvestigationId,
    MembershipId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.time import normalize_utc

ACTION_CODE_MAX_LENGTH = 64
REASON_CODE_MAX_LENGTH = 64
_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_.:-]*", flags=re.ASCII)

type AuditResourceId = WorkspaceId | UserId | MembershipId | CompanyId | InvestigationId


class AuditOutcome(StrEnum):
    """Result recorded for one attempted action."""

    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    FAILURE = "FAILURE"


class AuditResourceType(StrEnum):
    """Initial closed resource vocabulary for audit events."""

    WORKSPACE = "WORKSPACE"
    USER = "USER"
    MEMBERSHIP = "MEMBERSHIP"
    COMPANY = "COMPANY"
    INVESTIGATION = "INVESTIGATION"


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditEvent:
    """Append-only audit snapshot with a minimal redacted shape."""

    id: AuditEventId
    workspace_id: WorkspaceId
    actor_user_id: UserId
    action_code: str
    resource_type: AuditResourceType
    resource_id: AuditResourceId | None
    outcome: AuditOutcome
    reason_code: str | None
    correlation_id: CorrelationId
    occurred_at: datetime

    def __post_init__(self) -> None:
        _validate_types(self)
        action_code = _code(
            self.action_code,
            field_name="AuditEvent action_code",
            maximum_length=ACTION_CODE_MAX_LENGTH,
        )
        reason_code = (
            _code(
                self.reason_code,
                field_name="AuditEvent reason_code",
                maximum_length=REASON_CODE_MAX_LENGTH,
            )
            if self.reason_code is not None
            else None
        )
        occurred_at = normalize_utc(self.occurred_at)

        object.__setattr__(self, "action_code", action_code)
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "occurred_at", occurred_at)


def _validate_types(event: AuditEvent) -> None:
    if not isinstance(event.id, AuditEventId):
        raise InvariantViolationError("AuditEvent id must be an AuditEventId.")
    if not isinstance(event.workspace_id, WorkspaceId):
        raise InvariantViolationError("AuditEvent workspace_id must be a WorkspaceId.")
    if not isinstance(event.actor_user_id, UserId):
        raise InvariantViolationError("AuditEvent actor_user_id must be a UserId.")
    if not isinstance(event.resource_type, AuditResourceType):
        raise InvariantViolationError("AuditEvent resource_type must be an AuditResourceType.")
    if event.resource_id is not None and not isinstance(
        event.resource_id,
        (WorkspaceId, UserId, MembershipId, CompanyId, InvestigationId),
    ):
        raise InvariantViolationError("AuditEvent resource_id must be a typed resource ID.")
    expected_identifier_types: dict[AuditResourceType, type[AuditResourceId]] = {
        AuditResourceType.WORKSPACE: WorkspaceId,
        AuditResourceType.USER: UserId,
        AuditResourceType.MEMBERSHIP: MembershipId,
        AuditResourceType.COMPANY: CompanyId,
        AuditResourceType.INVESTIGATION: InvestigationId,
    }
    if event.resource_id is not None and not isinstance(
        event.resource_id, expected_identifier_types[event.resource_type]
    ):
        raise InvariantViolationError("AuditEvent resource_id must match its resource_type.")
    if not isinstance(event.outcome, AuditOutcome):
        raise InvariantViolationError("AuditEvent outcome must be an AuditOutcome.")
    if not isinstance(event.correlation_id, CorrelationId):
        raise InvariantViolationError("AuditEvent correlation_id must be a CorrelationId.")


def _code(value: str, *, field_name: str, maximum_length: int) -> str:
    if not isinstance(value, str):
        raise InvariantViolationError(f"{field_name} must be text.")
    canonical = value.strip().upper()
    if not canonical:
        raise InvariantViolationError(f"{field_name} cannot be empty.")
    if len(canonical) > maximum_length:
        raise InvariantViolationError(f"{field_name} cannot exceed {maximum_length} characters.")
    if _CODE_PATTERN.fullmatch(canonical) is None:
        raise InvariantViolationError(f"{field_name} has an invalid format.")
    return canonical


__all__ = [
    "ACTION_CODE_MAX_LENGTH",
    "REASON_CODE_MAX_LENGTH",
    "AuditEvent",
    "AuditOutcome",
    "AuditResourceId",
    "AuditResourceType",
]
