"""Trusted actor context consumed by tenant-scoped application services."""

from dataclasses import dataclass

from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import CorrelationId, UserId, WorkspaceId


@dataclass(frozen=True, slots=True, kw_only=True)
class ActorContext:
    """Already-authenticated identity and tenant scope supplied by a future boundary."""

    user_id: UserId
    workspace_id: WorkspaceId
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserId):
            raise InvariantViolationError("ActorContext user_id must be a UserId.")
        if not isinstance(self.workspace_id, WorkspaceId):
            raise InvariantViolationError("ActorContext workspace_id must be a WorkspaceId.")
        if not isinstance(self.correlation_id, CorrelationId):
            raise InvariantViolationError("ActorContext correlation_id must be a CorrelationId.")


__all__ = ["ActorContext"]
