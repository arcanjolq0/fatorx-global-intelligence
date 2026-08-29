"""Commands and redacted results for F5.4 Claim review."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from intelligence.application.actor_context import ActorContext
from intelligence.claims.review import (
    ClaimReviewHistory,
    ClaimReviewReason,
    ClaimReviewRequestedAction,
    EffectiveClaimReview,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import ClaimId, ClaimReviewCommandId, InvestigationId

CLAIM_REVIEW_COMMAND_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DecideClaimReview:
    command_id: ClaimReviewCommandId
    investigation_id: InvestigationId
    claim_id: ClaimId
    expected_claim_digest: str
    expected_previous_decision_digest: str | None
    requested_action: ClaimReviewRequestedAction
    reason_code: ClaimReviewReason
    schema_version: int = CLAIM_REVIEW_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not all(
            (
                isinstance(self.command_id, ClaimReviewCommandId),
                isinstance(self.investigation_id, InvestigationId),
                isinstance(self.claim_id, ClaimId),
                isinstance(self.requested_action, ClaimReviewRequestedAction),
                isinstance(self.reason_code, ClaimReviewReason),
                self.schema_version == CLAIM_REVIEW_COMMAND_SCHEMA_VERSION,
            )
        ):
            raise InvariantViolationError("Claim-review command is invalid.")
        for digest in (self.expected_claim_digest, self.expected_previous_decision_digest):
            if digest is not None and (
                not isinstance(digest, str)
                or len(digest) != 64
                or bytes.fromhex(digest).hex() != digest
            ):
                raise InvariantViolationError("Claim-review digest is invalid.")


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimReviewOperationResult:
    history: ClaimReviewHistory
    effective: EffectiveClaimReview
    replayed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimReviewReadResult:
    history: ClaimReviewHistory | None
    effective: EffectiveClaimReview


def digest_decide_claim_review(actor: ActorContext, command: DecideClaimReview) -> str:
    value = {
        "actor_user_id": str(actor.user_id),
        "workspace_id": str(actor.workspace_id),
        "command_id": str(command.command_id),
        "command_type": "DECIDE_CLAIM_REVIEW",
        "payload": {
            "investigation_id": str(command.investigation_id),
            "claim_id": str(command.claim_id),
            "expected_claim_digest": command.expected_claim_digest,
            "expected_previous_decision_digest": command.expected_previous_decision_digest,
            "requested_action": command.requested_action.value,
            "reason_code": command.reason_code.value,
            "schema_version": command.schema_version,
        },
    }
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
