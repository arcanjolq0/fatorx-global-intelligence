"""Immutable application records for one F4.2 entity-candidate review batch."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    EntityCandidateBatchId,
    EntityCandidateId,
    InvestigationCommandId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.time import normalize_utc
from intelligence.entity_resolution.contracts import (
    CANDIDATE_BATCH_SCHEMA_VERSION,
    CandidateIdentitySnapshot,
    CandidateOriginSnapshot,
    CandidateSubmissionBatch,
    EntityCandidateInput,
)
from intelligence.entity_resolution.errors import EntityResolutionError
from intelligence.entity_resolution.matching import (
    CandidateBatchEvaluation,
    CandidateEvaluation,
    DimensionScore,
    reconstitute_candidate_batch_evaluation,
    reconstitute_candidate_evaluation,
)
from intelligence.entity_resolution.policy import MatchClassification, MatchPolicy

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


class CandidateReviewDecision(StrEnum):
    """Only candidate decision authorized in F4.2."""

    PENDING_REVIEW = "PENDING_REVIEW"


@dataclass(frozen=True, slots=True, kw_only=True)
class EntityCandidateDimensionRecord:
    """Immutable persistence record for one evaluated dimension."""

    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    batch_id: EntityCandidateBatchId
    candidate_id: EntityCandidateId
    score: DimensionScore

    def __post_init__(self) -> None:
        typed_ids = (
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.batch_id, EntityCandidateBatchId),
            (self.candidate_id, EntityCandidateId),
        )
        if any(not isinstance(value, expected) for value, expected in typed_ids):
            raise InvariantViolationError("Candidate dimension identifiers must be strongly typed.")
        if not isinstance(self.score, DimensionScore):
            raise InvariantViolationError("Candidate dimension score must be typed.")


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class EntityCandidateRecord:
    """Neutral candidate snapshot and its reproducible ranked evaluation."""

    id: EntityCandidateId
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    batch_id: EntityCandidateBatchId
    candidate_key: str = field(repr=False)
    rank: int
    total_score: int
    coverage: int
    classification: MatchClassification
    hard_conflict: bool
    identity: CandidateIdentitySnapshot = field(repr=False)
    origin: CandidateOriginSnapshot = field(repr=False)
    evaluation_digest: str
    matching_policy: MatchPolicy = field(repr=False)
    input_digest: str = field(repr=False)
    decision: CandidateReviewDecision = CandidateReviewDecision.PENDING_REVIEW
    decision_by: UserId | None = None
    decided_at: datetime | None = None
    dimensions: tuple[EntityCandidateDimensionRecord, ...] = field(repr=False)

    def __post_init__(self) -> None:
        typed_ids = (
            (self.id, EntityCandidateId),
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.batch_id, EntityCandidateBatchId),
        )
        if any(not isinstance(value, expected) for value, expected in typed_ids):
            raise InvariantViolationError("Candidate record identifiers must be strongly typed.")
        if not isinstance(self.identity, CandidateIdentitySnapshot) or not isinstance(
            self.origin, CandidateOriginSnapshot
        ):
            raise InvariantViolationError("Candidate record snapshots must be typed.")
        if not isinstance(self.matching_policy, MatchPolicy):
            raise InvariantViolationError("Candidate record matching policy must be typed.")
        _digest(self.input_digest, "candidate input digest")
        if not isinstance(self.classification, MatchClassification) or not isinstance(
            self.hard_conflict, bool
        ):
            raise InvariantViolationError("Candidate record evaluation metadata is invalid.")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise InvariantViolationError("Candidate record rank must be positive.")
        for value, name in ((self.total_score, "score"), (self.coverage, "coverage")):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
                raise InvariantViolationError(f"Candidate record {name} must use basis points.")
        _digest(self.evaluation_digest, "candidate evaluation digest")
        if self.decision is not CandidateReviewDecision.PENDING_REVIEW:
            raise InvariantViolationError("F4.2 candidates must remain pending human review.")
        if self.decision_by is not None or self.decided_at is not None:
            raise InvariantViolationError("F4.2 cannot record a candidate decision.")
        if not isinstance(self.dimensions, tuple) or len(self.dimensions) != 7:
            raise InvariantViolationError("Candidate record requires seven dimensional scores.")
        if any(
            item.workspace_id != self.workspace_id
            or item.investigation_id != self.investigation_id
            or item.batch_id != self.batch_id
            or item.candidate_id != self.id
            for item in self.dimensions
        ):
            raise InvariantViolationError("Candidate dimension scope is inconsistent.")
        try:
            self.to_candidate_evaluation()
        except EntityResolutionError as error:
            raise InvariantViolationError("Candidate record evaluation is inconsistent.") from error

    def to_candidate_input(self) -> EntityCandidateInput:
        """Rebuild the official candidate input from the closed persisted snapshots."""

        return EntityCandidateInput(
            candidate_key=self.candidate_key,
            identity=self.identity,
            origin=self.origin,
        )

    def to_candidate_evaluation(self) -> CandidateEvaluation:
        """Rebuild and validate the official evaluation using required batch context."""

        return reconstitute_candidate_evaluation(
            candidate=self.to_candidate_input(),
            dimensions=tuple(item.score for item in self.dimensions),
            total_score=self.total_score,
            coverage=self.coverage,
            classification=self.classification,
            hard_conflict=self.hard_conflict,
            rank=self.rank,
            policy=self.matching_policy,
            input_digest=self.input_digest,
            evaluation_digest=self.evaluation_digest,
        )

    def __repr__(self) -> str:
        return (
            "EntityCandidateRecord("
            f"id={self.id!r}, rank={self.rank}, classification={self.classification.value!r}, "
            f"total_score={self.total_score}, coverage={self.coverage}, payload=<redacted>)"
        )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class EntityCandidateBatchRecord:
    """Append-only batch persisted with policy and evaluation snapshots."""

    id: EntityCandidateBatchId
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    batch_version: int
    input_digest: str
    policy_id: str
    policy_version: int
    policy_digest: str
    policy_snapshot: str = field(repr=False)
    command_id: InvestigationCommandId
    created_by: UserId
    created_at: datetime
    submission_digest: str
    evaluation_digest: str
    candidates: tuple[EntityCandidateRecord, ...] = field(repr=False)

    def __post_init__(self) -> None:
        typed_ids = (
            (self.id, EntityCandidateBatchId),
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.command_id, InvestigationCommandId),
            (self.created_by, UserId),
        )
        if any(not isinstance(value, expected) for value, expected in typed_ids):
            raise InvariantViolationError("Candidate batch record identifiers must be typed.")
        if self.batch_version != CANDIDATE_BATCH_SCHEMA_VERSION or isinstance(
            self.batch_version, bool
        ):
            raise InvariantViolationError("Candidate batch record version is unsupported.")
        if not isinstance(self.policy_id, str) or not self.policy_id:
            raise InvariantViolationError("Candidate batch policy ID is invalid.")
        if (
            isinstance(self.policy_version, bool)
            or not isinstance(self.policy_version, int)
            or self.policy_version < 1
        ):
            raise InvariantViolationError("Candidate batch policy version is invalid.")
        _digest(self.input_digest, "candidate batch input digest")
        _digest(self.policy_digest, "candidate batch policy digest")
        _digest(self.submission_digest, "candidate batch submission digest")
        _digest(self.evaluation_digest, "candidate batch evaluation digest")
        try:
            policy = MatchPolicy.from_canonical_json(self.policy_snapshot)
        except EntityResolutionError as error:
            raise InvariantViolationError("Candidate batch policy snapshot is invalid.") from error
        if (
            policy.policy_id != self.policy_id
            or policy.version != self.policy_version
            or policy.digest != self.policy_digest
        ):
            raise InvariantViolationError("Candidate batch policy snapshot is inconsistent.")
        if not isinstance(self.candidates, tuple) or not 1 <= len(self.candidates) <= 100:
            raise InvariantViolationError("Candidate batch record requires one to 100 candidates.")
        if tuple(candidate.rank for candidate in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise InvariantViolationError("Candidate batch ranks must be contiguous.")
        if any(
            candidate.workspace_id != self.workspace_id
            or candidate.investigation_id != self.investigation_id
            or candidate.batch_id != self.id
            for candidate in self.candidates
        ):
            raise InvariantViolationError("Candidate batch child scope is inconsistent.")
        if any(
            candidate.matching_policy != policy or candidate.input_digest != self.input_digest
            for candidate in self.candidates
        ):
            raise InvariantViolationError("Candidate batch evaluation context is inconsistent.")
        try:
            submission = CandidateSubmissionBatch(
                input_digest=self.input_digest,
                candidates=tuple(candidate.to_candidate_input() for candidate in self.candidates),
                batch_version=self.batch_version,
            )
            if submission.digest != self.submission_digest:
                raise InvariantViolationError("Candidate batch submission digest is inconsistent.")
            reconstitute_candidate_batch_evaluation(
                batch=submission,
                policy=policy,
                candidates=tuple(
                    candidate.to_candidate_evaluation() for candidate in self.candidates
                ),
                evaluation_digest=self.evaluation_digest,
            )
        except EntityResolutionError as error:
            raise InvariantViolationError("Candidate batch evaluation is inconsistent.") from error
        object.__setattr__(self, "created_at", normalize_utc(self.created_at))

    @property
    def top_classification(self) -> MatchClassification:
        return self.candidates[0].classification

    def __repr__(self) -> str:
        return (
            "EntityCandidateBatchRecord("
            f"id={self.id!r}, policy_id={self.policy_id!r}, "
            f"policy_version={self.policy_version}, candidate_count={len(self.candidates)}, "
            f"top_classification={self.top_classification.value!r}, payload=<redacted>)"
        )


def build_candidate_batch_record(
    *,
    batch_id: EntityCandidateBatchId,
    workspace_id: WorkspaceId,
    investigation_id: InvestigationId,
    command_id: InvestigationCommandId,
    created_by: UserId,
    created_at: datetime,
    submission: CandidateSubmissionBatch,
    policy: MatchPolicy,
    evaluation: CandidateBatchEvaluation,
) -> EntityCandidateBatchRecord:
    """Build persistence records after matching and before the single commit."""

    candidates_by_key = {item.candidate_key: item for item in submission.candidates}
    records: list[EntityCandidateRecord] = []
    for evaluated in evaluation.candidates:
        candidate_id = EntityCandidateId.new()
        candidate = candidates_by_key[evaluated.candidate_key]
        dimensions = tuple(
            EntityCandidateDimensionRecord(
                workspace_id=workspace_id,
                investigation_id=investigation_id,
                batch_id=batch_id,
                candidate_id=candidate_id,
                score=score,
            )
            for score in evaluated.dimensions
        )
        records.append(
            EntityCandidateRecord(
                id=candidate_id,
                workspace_id=workspace_id,
                investigation_id=investigation_id,
                batch_id=batch_id,
                candidate_key=candidate.candidate_key,
                rank=evaluated.rank,
                total_score=evaluated.total_score,
                coverage=evaluated.coverage,
                classification=evaluated.classification,
                hard_conflict=evaluated.hard_conflict,
                identity=candidate.identity,
                origin=candidate.origin,
                evaluation_digest=evaluated.digest,
                matching_policy=policy,
                input_digest=submission.input_digest,
                dimensions=dimensions,
            )
        )
    return EntityCandidateBatchRecord(
        id=batch_id,
        workspace_id=workspace_id,
        investigation_id=investigation_id,
        batch_version=submission.batch_version,
        input_digest=submission.input_digest,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        policy_digest=policy.digest,
        policy_snapshot=policy.to_canonical_json(),
        command_id=command_id,
        created_by=created_by,
        created_at=created_at,
        submission_digest=submission.digest,
        evaluation_digest=evaluation.digest,
        candidates=tuple(records),
    )


def _digest(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise InvariantViolationError(f"{field_name} must be a lowercase SHA-256 value.")


__all__ = [
    "CandidateReviewDecision",
    "EntityCandidateBatchRecord",
    "EntityCandidateDimensionRecord",
    "EntityCandidateRecord",
    "build_candidate_batch_record",
]
