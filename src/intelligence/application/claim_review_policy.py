"""Pure F5.4 factual Claim-review policy."""

from dataclasses import dataclass

from intelligence.application.claim_review import DecideClaimReview
from intelligence.claims.models import (
    Claim,
    ClaimEvidenceLink,
    ClaimEvidenceRole,
    ClaimEvidenceUseOutcome,
)
from intelligence.claims.review import (
    ClaimReviewBasisEntry,
    ClaimReviewOutcome,
    ClaimReviewPurpose,
    ClaimReviewReason,
    ClaimReviewRequestedAction,
)
from intelligence.domain.identifiers import UserId
from intelligence.evidence.admissibility import EffectiveEvidenceAdmissibilityStatus

CLAIM_REVIEW_POLICY_ID = "F5_4_INTERNAL_FACTUAL_CLAIM_REVIEW_V1"
CLAIM_REVIEW_POLICY_VERSION = 1


class ClaimReviewPolicyError(Exception):
    pass


class ClaimReviewSelfApprovalPolicyError(ClaimReviewPolicyError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimReviewPolicyEvaluation:
    outcome: ClaimReviewOutcome
    reason_code: ClaimReviewReason
    policy_id: str
    policy_version: int
    purpose: ClaimReviewPurpose


class ClaimReviewPolicyV1:
    def evaluate(
        self,
        *,
        claim: Claim,
        links: tuple[ClaimEvidenceLink, ...],
        entries: tuple[ClaimReviewBasisEntry, ...],
        command: DecideClaimReview,
        decided_by: UserId,
    ) -> ClaimReviewPolicyEvaluation:
        if (
            command.claim_id != claim.id
            or command.expected_claim_digest != claim.claim_digest
            or len(links) != len(entries)
        ):
            raise ClaimReviewPolicyError("Claim review target is stale.")
        mapped = {
            ClaimReviewRequestedAction.ACCEPT: (
                ClaimReviewOutcome.ACCEPTED_FOR_INTERNAL_FACTUAL_USE,
                ClaimReviewReason.FACTUAL_BASIS_ACCEPTED,
            ),
            ClaimReviewRequestedAction.REJECT: (
                ClaimReviewOutcome.REJECTED_FOR_INTERNAL_FACTUAL_USE,
                ClaimReviewReason.INTERNAL_FACTUAL_USE_REJECTED,
            ),
            ClaimReviewRequestedAction.RETURN_FOR_CORRECTION: (
                ClaimReviewOutcome.NEEDS_CORRECTION,
                ClaimReviewReason.CLAIM_CORRECTION_REQUIRED,
            ),
        }[command.requested_action]
        if command.reason_code is not mapped[1]:
            raise ClaimReviewPolicyError("Action and reason are incompatible.")
        if command.requested_action is ClaimReviewRequestedAction.ACCEPT:
            if decided_by == claim.created_by:
                raise ClaimReviewSelfApprovalPolicyError("Claim creator cannot self-accept.")
            valid = {
                e.evidence_id
                for e in entries
                if e.contextual_outcome == ClaimEvidenceUseOutcome.ELIGIBLE.value
                and e.effective_status is EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE
            }
            if not any(
                link.role is ClaimEvidenceRole.SUPPORTS and link.evidence_id in valid
                for link in links
            ) or any(
                link.role is ClaimEvidenceRole.CONTRADICTS and link.evidence_id in valid
                for link in links
            ):
                raise ClaimReviewPolicyError("Factual Claim gate is not satisfied.")
        return ClaimReviewPolicyEvaluation(
            outcome=mapped[0],
            reason_code=mapped[1],
            policy_id=CLAIM_REVIEW_POLICY_ID,
            policy_version=CLAIM_REVIEW_POLICY_VERSION,
            purpose=ClaimReviewPurpose.INTERNAL_FACTUAL_CLAIM_USE,
        )


F5_4_INTERNAL_FACTUAL_CLAIM_REVIEW_V1 = ClaimReviewPolicyV1()
