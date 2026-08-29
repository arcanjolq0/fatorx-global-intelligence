"""Strict relational mapping for immutable F5.4 Claim-review decisions."""

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from intelligence.claims.review import (
    ClaimReviewDecision,
    ClaimReviewOutcome,
    ClaimReviewPurpose,
    ClaimReviewReason,
)
from intelligence.domain.identifiers import (
    ClaimId,
    ClaimReviewCommandId,
    ClaimReviewDecisionId,
    CompanyId,
    EntityResolutionDecisionId,
    InvestigationId,
    UserId,
    WorkspaceId,
)

type RelationalValues = Mapping[str, object]


def claim_review_decision_to_values(decision: ClaimReviewDecision) -> dict[str, object]:
    return {
        "id": decision.id.value,
        "workspace_id": decision.workspace_id.value,
        "investigation_id": decision.investigation_id.value,
        "subject_company_id": decision.subject_company_id.value,
        "entity_resolution_decision_id": decision.entity_resolution_decision_id.value,
        "claim_id": decision.claim_id.value,
        "claim_series_id": decision.claim_series_id.value,
        "claim_version": decision.claim_version,
        "claim_digest": decision.claim_digest,
        "decision_sequence": decision.decision_sequence,
        "supersedes_decision_id": (
            decision.supersedes_decision_id.value if decision.supersedes_decision_id else None
        ),
        "outcome": decision.outcome.value,
        "reason_code": decision.reason_code.value,
        "policy_id": decision.policy_id,
        "policy_version": decision.policy_version,
        "purpose": decision.purpose.value,
        "review_basis_digest": decision.review_basis_digest,
        "command_id": decision.command_id.value,
        "command_digest": decision.command_digest,
        "decided_by": decision.decided_by.value,
        "decided_at": decision.decided_at,
        "decision_digest": decision.decision_digest,
        "schema_version": decision.schema_version,
    }


def claim_review_decision_from_values(values: RelationalValues) -> ClaimReviewDecision:
    predecessor = _optional(values, "supersedes_decision_id", UUID)
    return ClaimReviewDecision(
        id=ClaimReviewDecisionId(_required(values, "id", UUID)),
        workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
        investigation_id=InvestigationId(_required(values, "investigation_id", UUID)),
        subject_company_id=CompanyId(_required(values, "subject_company_id", UUID)),
        entity_resolution_decision_id=EntityResolutionDecisionId(
            _required(values, "entity_resolution_decision_id", UUID)
        ),
        claim_id=ClaimId(_required(values, "claim_id", UUID)),
        claim_series_id=ClaimId(_required(values, "claim_series_id", UUID)),
        claim_version=_required_int(values, "claim_version"),
        claim_digest=_required(values, "claim_digest", str),
        decision_sequence=_required_int(values, "decision_sequence"),
        supersedes_decision_id=ClaimReviewDecisionId(predecessor) if predecessor else None,
        outcome=ClaimReviewOutcome(_required(values, "outcome", str)),
        reason_code=ClaimReviewReason(_required(values, "reason_code", str)),
        policy_id=_required(values, "policy_id", str),
        policy_version=_required_int(values, "policy_version"),
        purpose=ClaimReviewPurpose(_required(values, "purpose", str)),
        review_basis_digest=_required(values, "review_basis_digest", str),
        command_id=ClaimReviewCommandId(_required(values, "command_id", UUID)),
        command_digest=_required(values, "command_digest", str),
        decided_by=UserId(_required(values, "decided_by", UUID)),
        decided_at=_required(values, "decided_at", datetime),
        decision_digest=_required(values, "decision_digest", str),
        schema_version=_required_int(values, "schema_version"),
    )


def _required[T](values: RelationalValues, key: str, expected: type[T]) -> T:
    value = values.get(key)
    if not isinstance(value, expected):
        raise ValueError(f"Persisted Claim-review field {key} is invalid.")
    return value


def _optional[T](values: RelationalValues, key: str, expected: type[T]) -> T | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, expected):
        raise ValueError(f"Persisted Claim-review field {key} is invalid.")
    return value


def _required_int(values: RelationalValues, key: str) -> int:
    value = _required(values, key, int)
    if isinstance(value, bool):
        raise ValueError(f"Persisted Claim-review field {key} is invalid.")
    return value


__all__ = ["claim_review_decision_from_values", "claim_review_decision_to_values"]
