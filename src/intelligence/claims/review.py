"""Immutable exact-version internal factual Claim-review records."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from intelligence.claims.errors import ClaimHistoryError, ClaimIntegrityError
from intelligence.claims.models import Claim, ClaimEvidenceRole, ClaimHistory
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    ClaimId,
    ClaimReviewCommandId,
    ClaimReviewDecisionId,
    CompanyId,
    EntityResolutionDecisionId,
    EvidenceAdmissibilityDecisionId,
    EvidenceId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.time import normalize_utc
from intelligence.evidence.admissibility import EffectiveEvidenceAdmissibilityStatus

CLAIM_REVIEW_DECISION_SCHEMA_VERSION = 1
CLAIM_REVIEW_BASIS_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)
_POLICY_ID = re.compile(r"[A-Z][A-Z0-9_.:-]{0,127}", flags=re.ASCII)


class ClaimReviewRequestedAction(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    RETURN_FOR_CORRECTION = "RETURN_FOR_CORRECTION"


class ClaimReviewOutcome(StrEnum):
    ACCEPTED_FOR_INTERNAL_FACTUAL_USE = "ACCEPTED_FOR_INTERNAL_FACTUAL_USE"
    REJECTED_FOR_INTERNAL_FACTUAL_USE = "REJECTED_FOR_INTERNAL_FACTUAL_USE"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"


class EffectiveClaimReviewStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"
    INVALIDATED = "INVALIDATED"


class ClaimReviewPurpose(StrEnum):
    INTERNAL_FACTUAL_CLAIM_USE = "INTERNAL_FACTUAL_CLAIM_USE"


class ClaimReviewReason(StrEnum):
    FACTUAL_BASIS_ACCEPTED = "FACTUAL_BASIS_ACCEPTED"
    INTERNAL_FACTUAL_USE_REJECTED = "INTERNAL_FACTUAL_USE_REJECTED"
    CLAIM_CORRECTION_REQUIRED = "CLAIM_CORRECTION_REQUIRED"


_OUTCOME_REASON: Mapping[ClaimReviewOutcome, ClaimReviewReason] = {
    ClaimReviewOutcome.ACCEPTED_FOR_INTERNAL_FACTUAL_USE: ClaimReviewReason.FACTUAL_BASIS_ACCEPTED,
    ClaimReviewOutcome.REJECTED_FOR_INTERNAL_FACTUAL_USE: (
        ClaimReviewReason.INTERNAL_FACTUAL_USE_REJECTED
    ),
    ClaimReviewOutcome.NEEDS_CORRECTION: ClaimReviewReason.CLAIM_CORRECTION_REQUIRED,
}


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimReviewBasisEntry:
    link_digest: str
    role: ClaimEvidenceRole
    evidence_id: EvidenceId
    evidence_digest: str
    contextual_outcome: str
    effective_status: EffectiveEvidenceAdmissibilityStatus
    admissibility_decision_id: EvidenceAdmissibilityDecisionId | None
    admissibility_decision_digest: str | None

    def __post_init__(self) -> None:
        for value, name in ((self.link_digest, "link"), (self.evidence_digest, "Evidence")):
            _digest(value, name)
        if (
            not isinstance(self.role, ClaimEvidenceRole)
            or not isinstance(self.evidence_id, EvidenceId)
            or not isinstance(self.effective_status, EffectiveEvidenceAdmissibilityStatus)
        ):
            raise InvariantViolationError("Review-basis vocabulary is invalid.")
        if (self.admissibility_decision_id is None) != (self.admissibility_decision_digest is None):
            raise InvariantViolationError("Review-basis decision shape is invalid.")
        if self.admissibility_decision_digest is not None:
            _digest(self.admissibility_decision_digest, "admissibility")


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ClaimReviewDecision:
    id: ClaimReviewDecisionId
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    subject_company_id: CompanyId
    entity_resolution_decision_id: EntityResolutionDecisionId
    claim_id: ClaimId
    claim_series_id: ClaimId
    claim_version: int
    claim_digest: str
    decision_sequence: int
    supersedes_decision_id: ClaimReviewDecisionId | None
    outcome: ClaimReviewOutcome
    reason_code: ClaimReviewReason
    policy_id: str
    policy_version: int
    purpose: ClaimReviewPurpose
    review_basis_digest: str
    command_id: ClaimReviewCommandId
    command_digest: str
    decided_by: UserId
    decided_at: datetime
    decision_digest: str
    schema_version: int = CLAIM_REVIEW_DECISION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, kind in (
            (self.id, ClaimReviewDecisionId),
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.subject_company_id, CompanyId),
            (self.entity_resolution_decision_id, EntityResolutionDecisionId),
            (self.claim_id, ClaimId),
            (self.claim_series_id, ClaimId),
            (self.command_id, ClaimReviewCommandId),
            (self.decided_by, UserId),
        ):
            if not isinstance(value, kind):
                raise InvariantViolationError("Claim-review identifier type is invalid.")
        if not all(
            isinstance(v, int) and not isinstance(v, bool) and v >= 1
            for v in (self.claim_version, self.decision_sequence, self.policy_version)
        ):
            raise InvariantViolationError("Claim-review version is invalid.")
        if (self.decision_sequence == 1) != (self.supersedes_decision_id is None):
            raise InvariantViolationError("Claim-review predecessor shape is invalid.")
        if self.supersedes_decision_id is not None and not isinstance(
            self.supersedes_decision_id, ClaimReviewDecisionId
        ):
            raise InvariantViolationError("Claim-review predecessor is invalid.")
        for digest_value, digest_name in (
            (self.claim_digest, "Claim"),
            (self.review_basis_digest, "basis"),
            (self.command_digest, "command"),
            (self.decision_digest, "decision"),
        ):
            _digest(digest_value, digest_name)
        if (
            _POLICY_ID.fullmatch(self.policy_id) is None
            or not isinstance(self.outcome, ClaimReviewOutcome)
            or not isinstance(self.reason_code, ClaimReviewReason)
            or not isinstance(self.purpose, ClaimReviewPurpose)
        ):
            raise InvariantViolationError("Claim-review vocabulary is invalid.")
        if (
            _OUTCOME_REASON[self.outcome] is not self.reason_code
            or self.schema_version != CLAIM_REVIEW_DECISION_SCHEMA_VERSION
        ):
            raise InvariantViolationError("Claim-review decision is invalid.")
        object.__setattr__(self, "decided_at", normalize_utc(self.decided_at))
        if self.decision_digest != claim_review_decision_digest(self):
            raise ClaimIntegrityError("Claim-review decision digest verification failed.")

    def __repr__(self) -> str:
        return (
            "ClaimReviewDecision("
            f"id={self.id!r}, claim_id={self.claim_id!r}, outcome={self.outcome.value!r}"
            ")"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimReviewHistory:
    decisions: tuple[ClaimReviewDecision, ...]

    def __post_init__(self) -> None:
        if not self.decisions:
            raise ClaimHistoryError("Claim-review history cannot be empty.")
        first = self.decisions[0]
        for index, item in enumerate(self.decisions):
            previous = self.decisions[index - 1] if index else None
            if item.decision_sequence != index + 1 or item.supersedes_decision_id != (
                previous.id if previous else None
            ):
                raise ClaimHistoryError("Claim-review chain is not contiguous.")
            if any(
                (
                    item.workspace_id != first.workspace_id,
                    item.investigation_id != first.investigation_id,
                    item.subject_company_id != first.subject_company_id,
                    item.entity_resolution_decision_id != first.entity_resolution_decision_id,
                    item.claim_id != first.claim_id,
                    item.claim_series_id != first.claim_series_id,
                    item.claim_version != first.claim_version,
                    item.claim_digest != first.claim_digest,
                    item.policy_id != first.policy_id,
                    item.policy_version != first.policy_version,
                    item.purpose is not first.purpose,
                )
            ):
                raise ClaimHistoryError("Claim-review history scope changed.")

    @property
    def latest(self) -> ClaimReviewDecision:
        return self.decisions[-1]

    def validate_against(self, history: ClaimHistory) -> None:
        claim = next((v for v in history.versions if v.id == self.latest.claim_id), None)
        if claim is None or any(
            (
                claim.series_id != self.latest.claim_series_id,
                claim.version != self.latest.claim_version,
                claim.claim_digest != self.latest.claim_digest,
            )
        ):
            raise ClaimHistoryError("Claim-review exact version is invalid.")
        upper = next(
            (v.created_at for v in history.versions if v.version == claim.version + 1), None
        )
        if any(
            d.decided_at < claim.created_at or (upper is not None and d.decided_at >= upper)
            for d in self.decisions
        ):
            raise ClaimHistoryError("Claim-review lies outside Claim interval.")


@dataclass(frozen=True, slots=True, kw_only=True)
class EffectiveClaimReview:
    status: EffectiveClaimReviewStatus
    claim_id: ClaimId
    claim_series_id: ClaimId
    claim_version: int
    claim_digest: str
    decision_id: ClaimReviewDecisionId | None
    as_of: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", normalize_utc(self.as_of))


def claim_review_basis_digest(*, claim: Claim, entries: tuple[ClaimReviewBasisEntry, ...]) -> str:
    if len({e.evidence_id for e in entries}) != len(entries):
        raise ClaimHistoryError("Review basis duplicates Evidence.")
    payload = {
        "schema_version": CLAIM_REVIEW_BASIS_SCHEMA_VERSION,
        "claim": {
            "id": str(claim.id),
            "series_id": str(claim.series_id),
            "version": claim.version,
            "digest": claim.claim_digest,
        },
        "links": [
            {
                "link_digest": e.link_digest,
                "role": e.role.value,
                "evidence_id": str(e.evidence_id),
                "evidence_digest": e.evidence_digest,
                "contextual_outcome": e.contextual_outcome,
                "effective_status": e.effective_status.value,
                "decision_id": str(e.admissibility_decision_id)
                if e.admissibility_decision_id
                else None,
                "decision_digest": e.admissibility_decision_digest,
            }
            for e in sorted(entries, key=lambda e: (str(e.evidence_id), e.role.value))
        ],
    }
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _values(d: ClaimReviewDecision) -> dict[str, object]:
    return {
        k: getattr(d, k)
        for k in (
            "id",
            "workspace_id",
            "investigation_id",
            "subject_company_id",
            "entity_resolution_decision_id",
            "claim_id",
            "claim_series_id",
            "claim_version",
            "claim_digest",
            "decision_sequence",
            "supersedes_decision_id",
            "outcome",
            "reason_code",
            "policy_id",
            "policy_version",
            "purpose",
            "review_basis_digest",
            "command_id",
            "command_digest",
            "decided_by",
            "decided_at",
            "schema_version",
        )
    }


def claim_review_decision_digest(d: ClaimReviewDecision) -> str:
    def scalar(value: object) -> object:
        if hasattr(value, "value"):
            return str(value.value)
        if isinstance(value, datetime):
            return normalize_utc(value).isoformat().replace("+00:00", "Z")
        return value

    data = {k: scalar(v) for k, v in _values(d).items()}
    return sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_claim_review_decision(
    *,
    decision_id: ClaimReviewDecisionId,
    claim: Claim,
    decision_sequence: int,
    supersedes_decision_id: ClaimReviewDecisionId | None,
    outcome: ClaimReviewOutcome,
    reason_code: ClaimReviewReason,
    policy_id: str,
    policy_version: int,
    purpose: ClaimReviewPurpose,
    review_basis_digest: str,
    command_id: ClaimReviewCommandId,
    command_digest: str,
    decided_by: UserId,
    decided_at: datetime,
) -> ClaimReviewDecision:
    normalized_decided_at = normalize_utc(decided_at)
    shadow = object.__new__(ClaimReviewDecision)
    object.__setattr__(shadow, "id", decision_id)
    object.__setattr__(shadow, "workspace_id", claim.workspace_id)
    object.__setattr__(shadow, "investigation_id", claim.investigation_id)
    object.__setattr__(shadow, "subject_company_id", claim.subject_company_id)
    object.__setattr__(shadow, "entity_resolution_decision_id", claim.entity_resolution_decision_id)
    object.__setattr__(shadow, "claim_id", claim.id)
    object.__setattr__(shadow, "claim_series_id", claim.series_id)
    object.__setattr__(shadow, "claim_version", claim.version)
    object.__setattr__(shadow, "claim_digest", claim.claim_digest)
    object.__setattr__(shadow, "decision_sequence", decision_sequence)
    object.__setattr__(shadow, "supersedes_decision_id", supersedes_decision_id)
    object.__setattr__(shadow, "outcome", outcome)
    object.__setattr__(shadow, "reason_code", reason_code)
    object.__setattr__(shadow, "policy_id", policy_id)
    object.__setattr__(shadow, "policy_version", policy_version)
    object.__setattr__(shadow, "purpose", purpose)
    object.__setattr__(shadow, "review_basis_digest", review_basis_digest)
    object.__setattr__(shadow, "command_id", command_id)
    object.__setattr__(shadow, "command_digest", command_digest)
    object.__setattr__(shadow, "decided_by", decided_by)
    object.__setattr__(shadow, "decided_at", normalized_decided_at)
    object.__setattr__(shadow, "schema_version", CLAIM_REVIEW_DECISION_SCHEMA_VERSION)
    return ClaimReviewDecision(
        id=decision_id,
        workspace_id=claim.workspace_id,
        investigation_id=claim.investigation_id,
        subject_company_id=claim.subject_company_id,
        entity_resolution_decision_id=claim.entity_resolution_decision_id,
        claim_id=claim.id,
        claim_series_id=claim.series_id,
        claim_version=claim.version,
        claim_digest=claim.claim_digest,
        decision_sequence=decision_sequence,
        supersedes_decision_id=supersedes_decision_id,
        outcome=outcome,
        reason_code=reason_code,
        policy_id=policy_id,
        policy_version=policy_version,
        purpose=purpose,
        review_basis_digest=review_basis_digest,
        command_id=command_id,
        command_digest=command_digest,
        decided_by=decided_by,
        decided_at=normalized_decided_at,
        decision_digest=claim_review_decision_digest(shadow),
        schema_version=CLAIM_REVIEW_DECISION_SCHEMA_VERSION,
    )


def _digest(value: object, name: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise InvariantViolationError(f"{name} digest is invalid.")
