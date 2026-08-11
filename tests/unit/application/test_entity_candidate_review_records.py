"""Validation and redaction tests for F4.2 append-only application records."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from intelligence.application.entity_candidate_review import (
    CandidateReviewDecision,
    EntityCandidateBatchRecord,
    EntityCandidateDimensionRecord,
    EntityCandidateRecord,
    build_candidate_batch_record,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    EntityCandidateBatchId,
    EntityCandidateId,
    InvestigationCommandId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.investigation_inputs import (
    IdentificationInput,
    OriginalAndNormalizedText,
)
from intelligence.entity_resolution.contracts import (
    CandidateIdentitySnapshot,
    CandidateOriginSnapshot,
    CandidateSubmissionBatch,
    EntityCandidateInput,
)
from intelligence.entity_resolution.errors import InvalidMatchEvaluationError
from intelligence.entity_resolution.matching import (
    CandidateEvaluation,
    evaluate_candidate_batch,
)
from intelligence.entity_resolution.policy import (
    INITIAL_MATCH_POLICY,
    MatchClassification,
    MatchDimension,
    MatchExplanationCode,
    MatchPolicy,
)

NOW = datetime(2026, 7, 29, 20, tzinfo=UTC)


def _text(value: str) -> OriginalAndNormalizedText:
    return OriginalAndNormalizedText(original_value=value, normalized_value=value.casefold())


def _record(*candidate_keys: str) -> EntityCandidateBatchRecord:
    source = IdentificationInput(legal_name=_text("Example Company"))
    keys = candidate_keys or ("candidate-1",)
    submission = CandidateSubmissionBatch(
        input_digest=source.digest,
        candidates=tuple(
            EntityCandidateInput(
                candidate_key=candidate_key,
                identity=CandidateIdentitySnapshot(
                    legal_name=_text("Example Company"),
                    country_code=CountryCode("BR"),
                ),
                origin=CandidateOriginSnapshot(
                    source_id="SYNTHETIC_SOURCE",
                    connector_id="synthetic.source",
                    connector_version="1.0.0",
                    source_candidate_reference=f"opaque-{candidate_key}",
                    collected_at=NOW,
                ),
            )
            for candidate_key in keys
        ),
    )
    evaluation = evaluate_candidate_batch(
        investigation_country_code=CountryCode("BR"),
        identification_input=source,
        batch=submission,
        policy=INITIAL_MATCH_POLICY,
    )
    return build_candidate_batch_record(
        batch_id=EntityCandidateBatchId.new(),
        workspace_id=WorkspaceId.new(),
        investigation_id=InvestigationId.new(),
        command_id=InvestigationCommandId.new(),
        created_by=UserId.new(),
        created_at=NOW,
        submission=submission,
        policy=INITIAL_MATCH_POLICY,
        evaluation=evaluation,
    )


def _consistent_candidate(
    candidate: EntityCandidateRecord,
    **changes: object,
) -> EntityCandidateRecord:
    candidate_key = str(changes.get("candidate_key", candidate.candidate_key))
    identity = changes.get("identity", candidate.identity)
    origin = changes.get("origin", candidate.origin)
    dimensions = changes.get("dimensions", candidate.dimensions)
    policy = changes.get("matching_policy", candidate.matching_policy)
    input_digest = str(changes.get("input_digest", candidate.input_digest))
    assert isinstance(identity, CandidateIdentitySnapshot)
    assert isinstance(origin, CandidateOriginSnapshot)
    assert isinstance(dimensions, tuple)
    assert isinstance(policy, MatchPolicy)
    total_score = changes.get("total_score", candidate.total_score)
    coverage = changes.get("coverage", candidate.coverage)
    classification = changes.get("classification", candidate.classification)
    hard_conflict = changes.get("hard_conflict", candidate.hard_conflict)
    rank = changes.get("rank", candidate.rank)
    assert isinstance(total_score, int)
    assert isinstance(coverage, int)
    assert isinstance(classification, MatchClassification)
    assert isinstance(hard_conflict, bool)
    assert isinstance(rank, int)
    candidate_input = EntityCandidateInput(
        candidate_key=candidate_key,
        identity=identity,
        origin=origin,
    )
    evaluation = CandidateEvaluation(
        candidate_key=candidate_key,
        candidate_digest=candidate_input.digest,
        dimensions=tuple(item.score for item in dimensions),
        total_score=total_score,
        coverage=coverage,
        classification=classification,
        hard_conflict=hard_conflict,
        rank=rank,
        policy_digest=policy.digest,
        input_digest=input_digest,
    )
    return replace(candidate, evaluation_digest=evaluation.digest, **changes)  # type: ignore[arg-type]


def test_builder_creates_scoped_pending_records_and_safe_representations() -> None:
    batch = _record()
    candidate = batch.candidates[0]

    assert batch.top_classification is MatchClassification.LOW
    assert candidate.decision is CandidateReviewDecision.PENDING_REVIEW
    assert candidate.decision_by is None and candidate.decided_at is None
    assert len(candidate.dimensions) == 7
    assert all(item.batch_id == batch.id for item in candidate.dimensions)
    assert "Example Company" not in repr(batch)
    assert "Example Company" not in repr(candidate)


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "id"},
        {"workspace_id": "workspace"},
        {"investigation_id": "investigation"},
        {"batch_id": "batch"},
        {"identity": "identity"},
        {"origin": "origin"},
        {"classification": "LOW"},
        {"hard_conflict": 0},
        {"rank": 0},
        {"total_score": 10_001},
        {"coverage": True},
        {"evaluation_digest": "bad"},
        {"decision": "PENDING_REVIEW"},
        {"decision_by": UserId.new()},
        {"decided_at": NOW},
        {"dimensions": ()},
    ],
)
def test_candidate_record_rejects_invalid_fields(changes: dict[str, object]) -> None:
    candidate = _record().candidates[0]
    with pytest.raises(InvariantViolationError):
        replace(candidate, **changes)  # type: ignore[arg-type]


def test_candidate_record_rejects_dimension_scope_mismatch() -> None:
    candidate = _record().candidates[0]
    wrong = replace(
        candidate.dimensions[0],
        candidate_id=EntityCandidateId.new(),
    )
    with pytest.raises(InvariantViolationError, match="scope"):
        replace(candidate, dimensions=(wrong, *candidate.dimensions[1:]))


@pytest.mark.parametrize(
    "changes",
    [
        {"total_score": 3_501},
        {"coverage": 3_499},
        {"classification": MatchClassification.MEDIUM},
        {"hard_conflict": True},
        {"evaluation_digest": "0" * 64},
        {"rank": 2},
    ],
)
def test_candidate_record_rejects_semantically_tampered_evaluation_fields(
    changes: dict[str, object],
) -> None:
    candidate = _record().candidates[0]

    with pytest.raises(InvariantViolationError, match="evaluation"):
        replace(candidate, **changes)  # type: ignore[arg-type]


def test_candidate_record_rejects_tampered_dimension_content() -> None:
    candidate = _record().candidates[0]
    by_dimension = {item.score.dimension: item for item in candidate.dimensions}
    unavailable = by_dimension[MatchDimension.DOMAIN]

    wrong_weight_score = replace(unavailable.score, weight=unavailable.score.weight + 1)
    wrong_weight = replace(unavailable, score=wrong_weight_score)
    with pytest.raises(InvariantViolationError, match="evaluation"):
        replace(
            candidate,
            dimensions=tuple(
                wrong_weight if item.score.dimension is MatchDimension.DOMAIN else item
                for item in candidate.dimensions
            ),
        )

    duplicate = replace(
        by_dimension[MatchDimension.NAME],
        score=by_dimension[MatchDimension.IDENTIFIER].score,
    )
    with pytest.raises(InvariantViolationError, match="evaluation"):
        replace(
            candidate,
            dimensions=tuple(
                duplicate if item.score.dimension is MatchDimension.NAME else item
                for item in candidate.dimensions
            ),
        )

    with pytest.raises(InvariantViolationError, match="seven"):
        replace(candidate, dimensions=candidate.dimensions[:-1])


def test_dimension_score_rejects_tampered_score_contribution_availability_and_explanation() -> None:
    candidate = _record().candidates[0]
    domain = next(
        item.score for item in candidate.dimensions if item.score.dimension is MatchDimension.DOMAIN
    )

    for changes in (
        {"score": 1},
        {"contribution": 1},
        {"available": True},
        {"explanation": MatchExplanationCode.NAME_UNAVAILABLE},
    ):
        with pytest.raises(InvalidMatchEvaluationError):
            replace(domain, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "id"},
        {"workspace_id": "workspace"},
        {"investigation_id": "investigation"},
        {"command_id": "command"},
        {"created_by": "user"},
        {"batch_version": True},
        {"policy_id": ""},
        {"policy_id": "different-policy"},
        {"policy_version": 0},
        {"input_digest": "bad"},
        {"policy_digest": "bad"},
        {"submission_digest": "bad"},
        {"evaluation_digest": "bad"},
        {"policy_snapshot": "{}"},
        {"candidates": ()},
    ],
)
def test_batch_record_rejects_invalid_fields(changes: dict[str, object]) -> None:
    batch = _record()
    with pytest.raises(InvariantViolationError):
        replace(batch, **changes)  # type: ignore[arg-type]


def test_batch_record_rejects_rank_and_child_scope_inconsistency() -> None:
    batch = _record()
    candidate = batch.candidates[0]
    with pytest.raises(InvariantViolationError, match="evaluation"):
        replace(batch, candidates=(replace(candidate, rank=2),))

    wrong_workspace = WorkspaceId.new()
    wrong_scope_candidate = replace(
        candidate,
        workspace_id=wrong_workspace,
        dimensions=tuple(
            replace(item, workspace_id=wrong_workspace) for item in candidate.dimensions
        ),
    )
    with pytest.raises(InvariantViolationError, match="scope"):
        replace(batch, candidates=(wrong_scope_candidate,))


def test_batch_record_rejects_semantic_digest_context_and_ranking_tampering() -> None:
    batch = _record("candidate-b", "candidate-a")
    first, second = batch.candidates

    for changes in (
        {"submission_digest": "0" * 64},
        {"evaluation_digest": "0" * 64},
        {"input_digest": "0" * 64},
        {"candidates": tuple(reversed(batch.candidates))},
    ):
        with pytest.raises(InvariantViolationError):
            replace(batch, **changes)

    duplicate_rank = _consistent_candidate(second, rank=first.rank)
    with pytest.raises(InvariantViolationError, match="ranks"):
        replace(batch, candidates=(first, duplicate_rank))

    noncontiguous_rank = _consistent_candidate(second, rank=3)
    with pytest.raises(InvariantViolationError, match="ranks"):
        replace(batch, candidates=(first, noncontiguous_rank))

    duplicate_key = _consistent_candidate(second, candidate_key=first.candidate_key)
    with pytest.raises(InvariantViolationError, match="evaluation"):
        replace(batch, candidates=(first, duplicate_key))


def test_batch_record_rejects_valid_but_incompatible_policy_snapshot() -> None:
    batch = _record()
    incompatible = replace(INITIAL_MATCH_POLICY, version=2)

    with pytest.raises(InvariantViolationError, match="context"):
        replace(
            batch,
            policy_version=incompatible.version,
            policy_digest=incompatible.digest,
            policy_snapshot=incompatible.to_canonical_json(),
        )


def test_batch_record_rejects_candidate_with_other_batch_investigation_or_workspace() -> None:
    batch = _record()
    candidate = batch.candidates[0]

    wrong_workspace = WorkspaceId.new()
    wrong_investigation = InvestigationId.new()
    wrong_batch = EntityCandidateBatchId.new()
    aliens = (
        replace(
            candidate,
            workspace_id=wrong_workspace,
            dimensions=tuple(
                replace(item, workspace_id=wrong_workspace) for item in candidate.dimensions
            ),
        ),
        replace(
            candidate,
            investigation_id=wrong_investigation,
            dimensions=tuple(
                replace(item, investigation_id=wrong_investigation) for item in candidate.dimensions
            ),
        ),
        replace(
            candidate,
            batch_id=wrong_batch,
            dimensions=tuple(replace(item, batch_id=wrong_batch) for item in candidate.dimensions),
        ),
    )
    for alien in aliens:
        with pytest.raises(InvariantViolationError, match="scope"):
            replace(batch, candidates=(alien,))


def test_dimension_record_is_immutable_and_typed_by_composition() -> None:
    dimension = _record().candidates[0].dimensions[0]
    assert isinstance(dimension, EntityCandidateDimensionRecord)
    assert isinstance(dimension.score.score, int)

    with pytest.raises(InvariantViolationError):
        replace(dimension, candidate_id="candidate")  # type: ignore[arg-type]
    with pytest.raises(InvariantViolationError):
        replace(dimension, score="score")  # type: ignore[arg-type]
