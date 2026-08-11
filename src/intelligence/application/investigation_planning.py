"""Typed F4.4 command, durable digest, and stable planning result."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256

from intelligence.application.actor_context import ActorContext
from intelligence.application.investigation_lifecycle import InvestigationCommandDigest
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import InvestigationCommandId, InvestigationId
from intelligence.orchestration.planning import InvestigationPlan, PlanningPolicy

CREATE_INVESTIGATION_PLAN_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CreateInvestigationPlan:
    """Request pure plan generation from persisted context and a versioned policy."""

    command_id: InvestigationCommandId
    investigation_id: InvestigationId
    expected_state_version: int
    planning_policy: PlanningPolicy = field(repr=False)
    schema_version: int = CREATE_INVESTIGATION_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.command_id, InvestigationCommandId) or not isinstance(
            self.investigation_id, InvestigationId
        ):
            raise InvariantViolationError("Investigation planning identifiers must be typed.")
        if (
            isinstance(self.expected_state_version, bool)
            or not isinstance(self.expected_state_version, int)
            or self.expected_state_version < 1
        ):
            raise InvariantViolationError(
                "Investigation planning expected_state_version must be positive."
            )
        if not isinstance(self.planning_policy, PlanningPolicy):
            raise InvariantViolationError("Investigation planning policy must be typed.")
        if self.schema_version != CREATE_INVESTIGATION_PLAN_SCHEMA_VERSION:
            raise InvariantViolationError("Investigation planning command schema is unsupported.")

    def __repr__(self) -> str:
        return (
            "CreateInvestigationPlan("
            f"command_id={self.command_id!r}, investigation_id={self.investigation_id!r}, "
            f"expected_state_version={self.expected_state_version}, "
            f"planning_policy_id={self.planning_policy.policy_id!r})"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class InvestigationPlanningResult:
    """Return the immutable persisted plan and whether it was replayed."""

    plan: InvestigationPlan
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.plan, InvestigationPlan):
            raise InvariantViolationError("Investigation planning result plan must be typed.")
        if not isinstance(self.replayed, bool):
            raise InvariantViolationError("Investigation planning replay flag must be boolean.")


def digest_create_investigation_plan_command(
    actor: ActorContext,
    command: CreateInvestigationPlan,
) -> InvestigationCommandDigest:
    """Digest the closed command semantics without generated plan data or time."""

    if not isinstance(actor, ActorContext) or not isinstance(command, CreateInvestigationPlan):
        raise TypeError("Investigation planning digest requires typed inputs.")
    serialized = json.dumps(
        {
            "actor_user_id": str(actor.user_id),
            "command_schema_version": command.schema_version,
            "expected_state_version": command.expected_state_version,
            "investigation_id": str(command.investigation_id),
            "planning_policy": command.planning_policy.to_canonical_json(),
            "workspace_id": str(actor.workspace_id),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return InvestigationCommandDigest(sha256(serialized.encode("utf-8")).hexdigest())


__all__ = [
    "CREATE_INVESTIGATION_PLAN_SCHEMA_VERSION",
    "CreateInvestigationPlan",
    "InvestigationPlanningResult",
    "digest_create_investigation_plan_command",
]
