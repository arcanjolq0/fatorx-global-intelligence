"""Typed F4.5 activation command, durable digest, and stable result."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256

from intelligence.application.actor_context import ActorContext
from intelligence.application.investigation_lifecycle import (
    InvestigationCommandDigest,
    InvestigationCommandType,
    InvestigationTransitionRecord,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    InvestigationCommandId,
    InvestigationId,
    InvestigationPlanId,
)
from intelligence.domain.investigations import InvestigationState
from intelligence.orchestration.collection_activation import (
    CollectionActivationPolicy,
    CollectionRun,
)

START_COLLECTION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class StartInvestigationCollection:
    """Activate one persisted READY plan without accepting generated manifest data."""

    command_id: InvestigationCommandId
    investigation_id: InvestigationId
    plan_id: InvestigationPlanId
    expected_state_version: int
    activation_policy: CollectionActivationPolicy = field(repr=False)
    schema_version: int = START_COLLECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        typed = (
            (self.command_id, InvestigationCommandId),
            (self.investigation_id, InvestigationId),
            (self.plan_id, InvestigationPlanId),
            (self.activation_policy, CollectionActivationPolicy),
        )
        if any(not isinstance(value, expected) for value, expected in typed):
            raise InvariantViolationError("Collection activation command metadata is invalid.")
        if (
            isinstance(self.expected_state_version, bool)
            or not isinstance(self.expected_state_version, int)
            or self.expected_state_version < 1
        ):
            raise InvariantViolationError(
                "Collection activation expected_state_version must be positive."
            )
        if self.schema_version != START_COLLECTION_SCHEMA_VERSION:
            raise InvariantViolationError("Collection activation command schema is unsupported.")

    def __repr__(self) -> str:
        return (
            "StartInvestigationCollection("
            f"command_id={self.command_id!r}, investigation_id={self.investigation_id!r}, "
            f"plan_id={self.plan_id!r}, expected_state_version={self.expected_state_version}, "
            f"activation_policy_id={self.activation_policy.policy_id!r})"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectionActivationResult:
    """Return the durable manifest and whether this call replayed it."""

    collection_run: CollectionRun
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.collection_run, CollectionRun):
            raise InvariantViolationError("Collection activation result run must be typed.")
        if not isinstance(self.replayed, bool):
            raise InvariantViolationError("Collection activation replay flag must be boolean.")


def digest_start_collection_command(
    actor: ActorContext,
    command: StartInvestigationCollection,
) -> InvestigationCommandDigest:
    """Hash only client-controlled activation semantics and actor scope."""

    if not isinstance(actor, ActorContext) or not isinstance(command, StartInvestigationCollection):
        raise TypeError("Collection activation digest requires typed inputs.")
    serialized = json.dumps(
        {
            "activation_policy": command.activation_policy.to_canonical_json(),
            "actor_user_id": str(actor.user_id),
            "command_schema_version": command.schema_version,
            "expected_state_version": command.expected_state_version,
            "investigation_id": str(command.investigation_id),
            "plan_id": str(command.plan_id),
            "workspace_id": str(actor.workspace_id),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return InvestigationCommandDigest(sha256(serialized.encode("utf-8")).hexdigest())


def validate_collection_activation_history(
    run: CollectionRun,
    transition: InvestigationTransitionRecord,
) -> None:
    """Require an exact immutable PLANNING-to-COLLECTING transition for one run."""

    if not isinstance(run, CollectionRun) or not isinstance(
        transition, InvestigationTransitionRecord
    ):
        raise InvariantViolationError("Collection activation history must be typed.")
    if (
        transition.command_type is not InvestigationCommandType.START_COLLECTION
        or transition.workspace_id != run.workspace_id
        or transition.investigation_id != run.investigation_id
        or transition.command_id != run.command_id
        or transition.command_digest.value != run.command_digest
        or transition.state_before is not InvestigationState.PLANNING
        or transition.state_after is not InvestigationState.COLLECTING
        or transition.version_after != transition.version_before + 1
        or transition.version_after != run.investigation_state_version
        or transition.actor_user_id != run.created_by
        or transition.occurred_at != run.created_at
        or transition.collection_run_id != run.id
        or transition.collection_company_id != run.company_id
        or transition.collection_plan_id != run.plan_id
        or transition.collection_operation_count != len(run.operations)
        or transition.collection_activation_policy_id != run.activation_policy_id
        or transition.collection_activation_policy_version != run.activation_policy_version
    ):
        raise InvariantViolationError("Collection activation history is inconsistent.")


__all__ = [
    "START_COLLECTION_SCHEMA_VERSION",
    "CollectionActivationResult",
    "StartInvestigationCollection",
    "digest_start_collection_command",
    "validate_collection_activation_history",
]
