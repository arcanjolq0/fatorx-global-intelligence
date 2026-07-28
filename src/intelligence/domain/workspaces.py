"""Workspace entity and invariants."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import WorkspaceId
from intelligence.domain.time import normalize_utc


class WorkspaceStatus(StrEnum):
    """Lifecycle status of a tenant workspace."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True, slots=True, kw_only=True)
class Workspace:
    """Immutable tenant boundary for all business records."""

    id: WorkspaceId
    name: str
    status: WorkspaceStatus
    retention_policy_version: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, WorkspaceId):
            raise InvariantViolationError("Workspace id must be a WorkspaceId.")
        if not isinstance(self.status, WorkspaceStatus):
            raise InvariantViolationError("Workspace status must be a WorkspaceStatus.")

        name = _required_text(self.name, field_name="Workspace name")
        retention_policy_version = _required_text(
            self.retention_policy_version,
            field_name="Retention policy version",
        )
        created_at = normalize_utc(self.created_at)
        updated_at = normalize_utc(self.updated_at)
        if updated_at < created_at:
            raise InvariantViolationError("Workspace updated_at cannot precede created_at.")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "retention_policy_version", retention_policy_version)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)


def _required_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvariantViolationError(f"{field_name} must be a non-empty string.")
    return value.strip()


__all__ = ["Workspace", "WorkspaceStatus"]
