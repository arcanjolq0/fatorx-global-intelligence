"""Pure deterministic candidate evaluation and stable ranking."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from unicodedata import category, normalize

from intelligence.domain.geography import CountryCode
from intelligence.domain.investigation_inputs import (
    BusinessIdentifierInput,
    IdentificationAddressInput,
    IdentificationInput,
    OriginalAndNormalizedText,
)
from intelligence.entity_resolution.contracts import (
    CandidateSubmissionBatch,
    EntityCandidateInput,
)
from intelligence.entity_resolution.errors import InvalidMatchEvaluationError
from intelligence.entity_resolution.policy import (
    BASIS_POINTS_MAX,
    MatchClassification,
    MatchDimension,
    MatchExplanationCode,
    MatchPolicy,
)

MATCH_EVALUATION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True, kw_only=True)
class DimensionScore:
    """One independently reproducible weighted matching dimension."""

    dimension: MatchDimension
    score: int
    weight: int
    contribution: int
    available: bool
    hard_conflict: bool
    explanation: MatchExplanationCode

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, MatchDimension):
            raise InvalidMatchEvaluationError("Dimension score uses an invalid dimension.")
        _basis_points(self.score, "dimension score")
        _basis_points(self.weight, "dimension weight")
        _basis_points(self.contribution, "weighted contribution")
        if not isinstance(self.available, bool) or not isinstance(self.hard_conflict, bool):
            raise InvalidMatchEvaluationError("Dimension indicators must be boolean.")
        if not isinstance(self.explanation, MatchExplanationCode):
            raise InvalidMatchEvaluationError("Dimension explanation uses an invalid code.")
        expected_contribution = self.score * self.weight // BASIS_POINTS_MAX
        if self.contribution != expected_contribution:
            raise InvalidMatchEvaluationError("Weighted contribution is inconsistent.")
        if not self.available and (self.score != 0 or self.contribution != 0):
            raise InvalidMatchEvaluationError("Unavailable dimensions cannot contribute.")
        if self.hard_conflict and not self.available:
            raise InvalidMatchEvaluationError("A hard conflict requires comparable data.")
        _validate_dimension_semantics(self)

    def to_canonical_object(self) -> dict[str, object]:
        return {
            "available": self.available,
            "contribution": self.contribution,
            "dimension": self.dimension.value,
            "explanation": self.explanation.value,
            "hard_conflict": self.hard_conflict,
            "score": self.score,
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CandidateEvaluation:
    """Ranked evaluation containing no canonical-company decision."""

    candidate_key: str = field(repr=False)
    candidate_digest: str
    dimensions: tuple[DimensionScore, ...]
    total_score: int
    coverage: int
    classification: MatchClassification
    hard_conflict: bool
    rank: int
    policy_digest: str
    input_digest: str
    schema_version: int = MATCH_EVALUATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MATCH_EVALUATION_SCHEMA_VERSION or isinstance(
            self.schema_version, bool
        ):
            raise InvalidMatchEvaluationError("Evaluation schema version is unsupported.")
        if not isinstance(self.candidate_key, str) or not self.candidate_key:
            raise InvalidMatchEvaluationError("Evaluation candidate key is invalid.")
        _digest(self.candidate_digest, "candidate digest")
        _digest(self.policy_digest, "policy digest")
        _digest(self.input_digest, "input digest")
        if not isinstance(self.dimensions, tuple) or any(
            not isinstance(item, DimensionScore) for item in self.dimensions
        ):
            raise InvalidMatchEvaluationError("Evaluation dimensions must be an immutable tuple.")
        dimensions = tuple(item.dimension for item in self.dimensions)
        if len(dimensions) != len(MatchDimension) or set(dimensions) != set(MatchDimension):
            raise InvalidMatchEvaluationError("Evaluation must contain every dimension once.")
        _basis_points(self.total_score, "total score")
        _basis_points(self.coverage, "coverage")
        if self.total_score != sum(item.contribution for item in self.dimensions):
            raise InvalidMatchEvaluationError("Evaluation total score is inconsistent.")
        if self.coverage != sum(item.weight for item in self.dimensions if item.available):
            raise InvalidMatchEvaluationError("Evaluation coverage is inconsistent.")
        if not isinstance(self.hard_conflict, bool) or self.hard_conflict != any(
            item.hard_conflict for item in self.dimensions
        ):
            raise InvalidMatchEvaluationError("Evaluation hard-conflict indicator is inconsistent.")
        if not isinstance(self.classification, MatchClassification):
            raise InvalidMatchEvaluationError("Evaluation classification is invalid.")
        if self.hard_conflict != (self.classification is MatchClassification.EXCLUDED):
            raise InvalidMatchEvaluationError("Excluded classification and conflict must agree.")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise InvalidMatchEvaluationError("Evaluation rank must be positive.")

    @property
    def identifier_score(self) -> int:
        return next(
            item.score for item in self.dimensions if item.dimension is MatchDimension.IDENTIFIER
        )

    @property
    def digest(self) -> str:
        return sha256(self.to_canonical_json().encode("utf-8")).hexdigest()

    def to_canonical_json(self) -> str:
        return _canonical_json(self.to_canonical_object())

    def to_canonical_object(self) -> dict[str, object]:
        return {
            "candidate_digest": self.candidate_digest,
            "candidate_key": self.candidate_key,
            "classification": self.classification.value,
            "coverage": self.coverage,
            "dimensions": [
                item.to_canonical_object()
                for item in sorted(self.dimensions, key=lambda value: value.dimension.value)
            ],
            "hard_conflict": self.hard_conflict,
            "input_digest": self.input_digest,
            "policy_digest": self.policy_digest,
            "rank": self.rank,
            "schema_version": self.schema_version,
            "total_score": self.total_score,
        }

    def __repr__(self) -> str:
        return (
            "CandidateEvaluation("
            f"rank={self.rank}, classification={self.classification.value!r}, "
            f"total_score={self.total_score}, coverage={self.coverage}, "
            f"hard_conflict={self.hard_conflict}, candidate=<redacted>)"
        )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CandidateBatchEvaluation:
    """Deterministically ranked evaluations for one submitted batch."""

    batch_digest: str
    input_digest: str
    policy_digest: str
    candidates: tuple[CandidateEvaluation, ...] = field(repr=False)
    schema_version: int = MATCH_EVALUATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _digest(self.batch_digest, "batch digest")
        _digest(self.input_digest, "input digest")
        _digest(self.policy_digest, "policy digest")
        if self.schema_version != MATCH_EVALUATION_SCHEMA_VERSION or isinstance(
            self.schema_version, bool
        ):
            raise InvalidMatchEvaluationError("Batch evaluation schema is unsupported.")
        if not isinstance(self.candidates, tuple) or not self.candidates:
            raise InvalidMatchEvaluationError("Batch evaluation requires candidates.")
        if tuple(item.rank for item in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise InvalidMatchEvaluationError("Batch evaluation ranks must be contiguous.")
        candidate_keys = tuple(item.candidate_key for item in self.candidates)
        if len(set(candidate_keys)) != len(candidate_keys):
            raise InvalidMatchEvaluationError("Batch evaluation candidate keys cannot repeat.")
        if any(item.input_digest != self.input_digest for item in self.candidates):
            raise InvalidMatchEvaluationError("Batch evaluation input digest is inconsistent.")
        if any(item.policy_digest != self.policy_digest for item in self.candidates):
            raise InvalidMatchEvaluationError("Batch evaluation policy digest is inconsistent.")
        if self.candidates != rank_candidate_evaluations(self.candidates):
            raise InvalidMatchEvaluationError("Batch evaluation ranking is inconsistent.")

    @property
    def digest(self) -> str:
        return sha256(self.to_canonical_json().encode("utf-8")).hexdigest()

    @property
    def top_classification(self) -> MatchClassification:
        return self.candidates[0].classification

    def to_canonical_json(self) -> str:
        return _canonical_json(
            {
                "batch_digest": self.batch_digest,
                "candidates": [item.to_canonical_object() for item in self.candidates],
                "input_digest": self.input_digest,
                "policy_digest": self.policy_digest,
                "schema_version": self.schema_version,
            }
        )

    def __repr__(self) -> str:
        return (
            "CandidateBatchEvaluation("
            f"candidate_count={len(self.candidates)}, "
            f"top_classification={self.top_classification.value!r}, candidates=<redacted>)"
        )


def normalize_matching_name(value: str) -> str:
    """Apply policy V1 NFKC/casefold/punctuation/whitespace normalization."""

    if not isinstance(value, str):
        raise InvalidMatchEvaluationError("Matching name must be text.")
    folded = normalize("NFKC", value).casefold()
    separated = "".join(
        " " if category(character)[0] in {"P", "S"} else character for character in folded
    )
    return " ".join(separated.split())


def evaluate_candidate_batch(
    *,
    investigation_country_code: CountryCode,
    identification_input: IdentificationInput,
    batch: CandidateSubmissionBatch,
    policy: MatchPolicy,
) -> CandidateBatchEvaluation:
    """Evaluate and rank a bounded batch without I/O, clock, or randomness."""

    if not isinstance(investigation_country_code, CountryCode):
        raise InvalidMatchEvaluationError("Investigation country must be typed.")
    if not isinstance(identification_input, IdentificationInput):
        raise InvalidMatchEvaluationError("Identification input must be typed.")
    if not isinstance(batch, CandidateSubmissionBatch):
        raise InvalidMatchEvaluationError("Candidate batch must be typed.")
    if not isinstance(policy, MatchPolicy):
        raise InvalidMatchEvaluationError("Matching policy must be typed.")
    if batch.input_digest != identification_input.digest:
        raise InvalidMatchEvaluationError("Candidate batch input digest does not match.")

    preliminary = tuple(
        _evaluate_candidate(
            investigation_country_code=investigation_country_code,
            identification_input=identification_input,
            candidate=candidate,
            policy=policy,
        )
        for candidate in batch.candidates
    )
    ordered = rank_candidate_evaluations(preliminary)
    ranked = tuple(
        _candidate_evaluation(
            candidate_key=item.candidate_key,
            candidate_digest=item.candidate_digest,
            dimensions=item.dimensions,
            policy=policy,
            input_digest=identification_input.digest,
            rank=rank,
        )
        for rank, item in enumerate(ordered, start=1)
    )
    return CandidateBatchEvaluation(
        batch_digest=batch.digest,
        input_digest=identification_input.digest,
        policy_digest=policy.digest,
        candidates=ranked,
    )


def _evaluate_candidate(
    *,
    investigation_country_code: CountryCode,
    identification_input: IdentificationInput,
    candidate: EntityCandidateInput,
    policy: MatchPolicy,
) -> CandidateEvaluation:
    dimensions = (
        _identifier_dimension(identification_input, candidate, policy),
        _name_dimension(identification_input, candidate, policy),
        _domain_dimension(identification_input, candidate, policy),
        _geography_dimension(investigation_country_code, candidate, policy),
        _address_dimension(identification_input, candidate, policy),
        _administrators_dimension(identification_input, candidate, policy),
        _temporal_dimension(identification_input, candidate, policy),
    )
    return _candidate_evaluation(
        candidate_key=candidate.candidate_key,
        candidate_digest=candidate.digest,
        dimensions=dimensions,
        policy=policy,
        input_digest=identification_input.digest,
        rank=1,
    )


def _candidate_evaluation(
    *,
    candidate_key: str,
    candidate_digest: str,
    dimensions: tuple[DimensionScore, ...],
    policy: MatchPolicy,
    input_digest: str,
    rank: int,
) -> CandidateEvaluation:
    total = sum(item.contribution for item in dimensions)
    coverage = sum(item.weight for item in dimensions if item.available)
    conflict = any(item.hard_conflict for item in dimensions)
    return CandidateEvaluation(
        candidate_key=candidate_key,
        candidate_digest=candidate_digest,
        dimensions=dimensions,
        total_score=total,
        coverage=coverage,
        classification=policy.classify(total, has_hard_conflict=conflict),
        hard_conflict=conflict,
        rank=rank,
        policy_digest=policy.digest,
        input_digest=input_digest,
    )


def reconstitute_candidate_evaluation(
    *,
    candidate: EntityCandidateInput,
    dimensions: tuple[DimensionScore, ...],
    total_score: int,
    coverage: int,
    classification: MatchClassification,
    hard_conflict: bool,
    rank: int,
    policy: MatchPolicy,
    input_digest: str,
    evaluation_digest: str,
) -> CandidateEvaluation:
    """Rebuild and validate one persisted evaluation against its full context."""

    if not isinstance(candidate, EntityCandidateInput):
        raise InvalidMatchEvaluationError("Persisted evaluation candidate is invalid.")
    if not isinstance(policy, MatchPolicy):
        raise InvalidMatchEvaluationError("Persisted evaluation policy is invalid.")
    for item in dimensions:
        if item.weight != policy.weight_for(item.dimension):
            raise InvalidMatchEvaluationError("Persisted dimension weight is inconsistent.")
    evaluation = CandidateEvaluation(
        candidate_key=candidate.candidate_key,
        candidate_digest=candidate.digest,
        dimensions=dimensions,
        total_score=total_score,
        coverage=coverage,
        classification=classification,
        hard_conflict=hard_conflict,
        rank=rank,
        policy_digest=policy.digest,
        input_digest=input_digest,
    )
    expected_classification = policy.classify(
        evaluation.total_score,
        has_hard_conflict=evaluation.hard_conflict,
    )
    if evaluation.classification is not expected_classification:
        raise InvalidMatchEvaluationError("Persisted evaluation classification is inconsistent.")
    _digest(evaluation_digest, "persisted evaluation digest")
    if evaluation.digest != evaluation_digest:
        raise InvalidMatchEvaluationError("Persisted evaluation digest is inconsistent.")
    return evaluation


def reconstitute_candidate_batch_evaluation(
    *,
    batch: CandidateSubmissionBatch,
    policy: MatchPolicy,
    candidates: tuple[CandidateEvaluation, ...],
    evaluation_digest: str,
) -> CandidateBatchEvaluation:
    """Rebuild and validate a persisted aggregate, candidate set, and official ranking."""

    if not isinstance(batch, CandidateSubmissionBatch):
        raise InvalidMatchEvaluationError("Persisted evaluation batch is invalid.")
    if not isinstance(policy, MatchPolicy):
        raise InvalidMatchEvaluationError("Persisted evaluation policy is invalid.")
    submitted_by_key = {item.candidate_key: item for item in batch.candidates}
    if len(candidates) != len(submitted_by_key):
        raise InvalidMatchEvaluationError("Persisted evaluation candidate count is inconsistent.")
    for evaluation in candidates:
        candidate = submitted_by_key.get(evaluation.candidate_key)
        if candidate is None or candidate.digest != evaluation.candidate_digest:
            raise InvalidMatchEvaluationError("Persisted evaluation candidate is inconsistent.")
        if evaluation.input_digest != batch.input_digest:
            raise InvalidMatchEvaluationError("Persisted evaluation input digest is inconsistent.")
        if evaluation.policy_digest != policy.digest:
            raise InvalidMatchEvaluationError("Persisted evaluation policy digest is inconsistent.")
    result = CandidateBatchEvaluation(
        batch_digest=batch.digest,
        input_digest=batch.input_digest,
        policy_digest=policy.digest,
        candidates=candidates,
    )
    _digest(evaluation_digest, "persisted batch evaluation digest")
    if result.digest != evaluation_digest:
        raise InvalidMatchEvaluationError("Persisted batch evaluation digest is inconsistent.")
    return result


def rank_candidate_evaluations(
    values: tuple[CandidateEvaluation, ...],
) -> tuple[CandidateEvaluation, ...]:
    """Return evaluations in the single official deterministic ranking order."""

    if not isinstance(values, tuple) or any(
        not isinstance(value, CandidateEvaluation) for value in values
    ):
        raise InvalidMatchEvaluationError("Candidate evaluations must be an immutable tuple.")
    return tuple(sorted(values, key=_ranking_key))


def _identifier_dimension(
    source: IdentificationInput,
    candidate: EntityCandidateInput,
    policy: MatchPolicy,
) -> DimensionScore:
    source_groups = _identifier_groups(source.identifiers)
    candidate_groups = _identifier_groups(candidate.identity.identifiers)
    comparable = set(source_groups) & set(candidate_groups)
    if not comparable:
        return _dimension(
            MatchDimension.IDENTIFIER,
            policy,
            score=0,
            available=False,
            explanation=MatchExplanationCode.IDENTIFIER_UNAVAILABLE,
        )
    exact = any(source_groups[group] & candidate_groups[group] for group in comparable)
    return _dimension(
        MatchDimension.IDENTIFIER,
        policy,
        score=BASIS_POINTS_MAX if exact else 0,
        available=True,
        hard_conflict=not exact,
        explanation=(
            MatchExplanationCode.IDENTIFIER_EXACT
            if exact
            else MatchExplanationCode.IDENTIFIER_CONFLICT
        ),
    )


def _identifier_groups(
    identifiers: tuple[BusinessIdentifierInput, ...],
) -> dict[tuple[str, str | None], set[str]]:
    result: dict[tuple[str, str | None], set[str]] = {}
    for identifier in identifiers:
        group = (
            identifier.identifier_type.value,
            (
                identifier.jurisdiction_country_code.value
                if identifier.jurisdiction_country_code is not None
                else None
            ),
        )
        result.setdefault(group, set()).add(identifier.normalized_value)
    return result


def _name_dimension(
    source: IdentificationInput,
    candidate: EntityCandidateInput,
    policy: MatchPolicy,
) -> DimensionScore:
    source_legal = _normalized_optional(source.legal_name)
    source_trade = _normalized_optional(source.trade_name)
    candidate_legal = _normalized_optional(candidate.identity.legal_name)
    candidate_trade = _normalized_optional(candidate.identity.trade_name)
    source_names = {value for value in (source_legal, source_trade) if value}
    candidate_names = {value for value in (candidate_legal, candidate_trade) if value}
    if not source_names or not candidate_names:
        return _dimension(
            MatchDimension.NAME,
            policy,
            score=0,
            available=False,
            explanation=MatchExplanationCode.NAME_UNAVAILABLE,
        )
    if source_legal and source_legal == candidate_legal:
        score, explanation = BASIS_POINTS_MAX, MatchExplanationCode.NAME_LEGAL_EXACT
    elif source_trade and source_trade == candidate_trade:
        score, explanation = 9_500, MatchExplanationCode.NAME_TRADE_EXACT
    elif (source_legal and source_legal == candidate_trade) or (
        source_trade and source_trade == candidate_legal
    ):
        score, explanation = 9_000, MatchExplanationCode.NAME_CROSS_EXACT
    elif any(
        tuple(sorted(source_name.split())) == tuple(sorted(candidate_name.split()))
        for source_name in source_names
        for candidate_name in candidate_names
    ):
        score, explanation = 8_000, MatchExplanationCode.NAME_TOKENS_EQUIVALENT
    else:
        score, explanation = 0, MatchExplanationCode.NAME_DIFFERENT
    return _dimension(
        MatchDimension.NAME,
        policy,
        score=score,
        available=True,
        explanation=explanation,
    )


def _domain_dimension(
    source: IdentificationInput,
    candidate: EntityCandidateInput,
    policy: MatchPolicy,
) -> DimensionScore:
    source_domain = source.corporate_domain
    candidate_domain = candidate.identity.corporate_domain
    if source_domain is None or candidate_domain is None:
        return _dimension(
            MatchDimension.DOMAIN,
            policy,
            score=0,
            available=False,
            explanation=MatchExplanationCode.DOMAIN_UNAVAILABLE,
        )
    exact = source_domain.normalized_value == candidate_domain.normalized_value
    return _dimension(
        MatchDimension.DOMAIN,
        policy,
        score=BASIS_POINTS_MAX if exact else 0,
        available=True,
        explanation=(
            MatchExplanationCode.DOMAIN_EXACT if exact else MatchExplanationCode.DOMAIN_DIFFERENT
        ),
    )


def _geography_dimension(
    investigation_country_code: CountryCode,
    candidate: EntityCandidateInput,
    policy: MatchPolicy,
) -> DimensionScore:
    exact = investigation_country_code == candidate.identity.country_code
    return _dimension(
        MatchDimension.GEOGRAPHY,
        policy,
        score=BASIS_POINTS_MAX if exact else 0,
        available=True,
        hard_conflict=not exact,
        explanation=(
            MatchExplanationCode.GEOGRAPHY_EXACT
            if exact
            else MatchExplanationCode.GEOGRAPHY_CONFLICT
        ),
    )


def _address_dimension(
    source: IdentificationInput,
    candidate: EntityCandidateInput,
    policy: MatchPolicy,
) -> DimensionScore:
    source_address = source.address
    candidate_address = candidate.identity.address
    if source_address is None or candidate_address is None:
        return _dimension(
            MatchDimension.ADDRESS,
            policy,
            score=0,
            available=False,
            explanation=MatchExplanationCode.ADDRESS_UNAVAILABLE,
        )
    source_fields = _address_fields(source_address)
    candidate_fields = _address_fields(candidate_address)
    common_fields = tuple(sorted(set(source_fields) & set(candidate_fields)))
    if not common_fields:
        return _dimension(
            MatchDimension.ADDRESS,
            policy,
            score=0,
            available=False,
            explanation=MatchExplanationCode.ADDRESS_UNAVAILABLE,
        )
    matches = sum(source_fields[field] == candidate_fields[field] for field in common_fields)
    score = matches * BASIS_POINTS_MAX // len(common_fields)
    if matches == len(common_fields):
        explanation = MatchExplanationCode.ADDRESS_EXACT
    elif matches:
        explanation = MatchExplanationCode.ADDRESS_PARTIAL
    else:
        explanation = MatchExplanationCode.ADDRESS_DIFFERENT
    return _dimension(
        MatchDimension.ADDRESS,
        policy,
        score=score,
        available=True,
        explanation=explanation,
    )


def _address_fields(value: IdentificationAddressInput) -> dict[str, str]:
    fields = {
        "address_line_1": value.address_line_1,
        "address_line_2": value.address_line_2,
        "administrative_area": value.administrative_area,
        "locality": value.locality,
        "postal_code": value.postal_code,
    }
    return {
        name: normalize_matching_name(item.normalized_value)
        for name, item in fields.items()
        if item is not None
    }


def _administrators_dimension(
    source: IdentificationInput,
    candidate: EntityCandidateInput,
    policy: MatchPolicy,
) -> DimensionScore:
    source_values = {_normalized_text(value) for value in source.administrators}
    candidate_values = {_normalized_text(value) for value in candidate.identity.administrators}
    if not source_values or not candidate_values:
        return _dimension(
            MatchDimension.ADMINISTRATORS,
            policy,
            score=0,
            available=False,
            explanation=MatchExplanationCode.ADMINISTRATORS_UNAVAILABLE,
        )
    intersection = source_values & candidate_values
    union = source_values | candidate_values
    score = len(intersection) * BASIS_POINTS_MAX // len(union)
    if source_values == candidate_values:
        explanation = MatchExplanationCode.ADMINISTRATORS_EXACT
    elif intersection:
        explanation = MatchExplanationCode.ADMINISTRATORS_PARTIAL
    else:
        explanation = MatchExplanationCode.ADMINISTRATORS_DIFFERENT
    return _dimension(
        MatchDimension.ADMINISTRATORS,
        policy,
        score=score,
        available=True,
        explanation=explanation,
    )


def _temporal_dimension(
    source: IdentificationInput,
    candidate: EntityCandidateInput,
    policy: MatchPolicy,
) -> DimensionScore:
    source_date = source.incorporated_on
    candidate_date = candidate.identity.incorporated_on
    if source_date is None or candidate_date is None:
        return _dimension(
            MatchDimension.TEMPORAL,
            policy,
            score=0,
            available=False,
            explanation=MatchExplanationCode.TEMPORAL_UNAVAILABLE,
        )
    exact = source_date == candidate_date
    return _dimension(
        MatchDimension.TEMPORAL,
        policy,
        score=BASIS_POINTS_MAX if exact else 0,
        available=True,
        explanation=(
            MatchExplanationCode.TEMPORAL_EXACT
            if exact
            else MatchExplanationCode.TEMPORAL_DIFFERENT
        ),
    )


def _dimension(
    dimension: MatchDimension,
    policy: MatchPolicy,
    *,
    score: int,
    available: bool,
    explanation: MatchExplanationCode,
    hard_conflict: bool = False,
) -> DimensionScore:
    weight = policy.weight_for(dimension)
    return DimensionScore(
        dimension=dimension,
        score=score,
        weight=weight,
        contribution=score * weight // BASIS_POINTS_MAX,
        available=available,
        hard_conflict=hard_conflict,
        explanation=explanation,
    )


def _normalized_optional(value: OriginalAndNormalizedText | None) -> str | None:
    return None if value is None else _normalized_text(value)


def _normalized_text(value: OriginalAndNormalizedText) -> str:
    return normalize_matching_name(value.normalized_value)


def _ranking_key(value: CandidateEvaluation) -> tuple[int, int, int, int, int, str]:
    class_order = {
        MatchClassification.HIGH: 0,
        MatchClassification.MEDIUM: 1,
        MatchClassification.LOW: 2,
        MatchClassification.EXCLUDED: 3,
    }
    return (
        1 if value.hard_conflict else 0,
        class_order[value.classification],
        -value.total_score,
        -value.coverage,
        -value.identifier_score,
        value.candidate_key,
    )


_FIXED_EXPLANATION_SEMANTICS: dict[
    MatchExplanationCode,
    tuple[MatchDimension, int, bool, bool],
] = {
    MatchExplanationCode.IDENTIFIER_EXACT: (MatchDimension.IDENTIFIER, 10_000, True, False),
    MatchExplanationCode.IDENTIFIER_CONFLICT: (MatchDimension.IDENTIFIER, 0, True, True),
    MatchExplanationCode.IDENTIFIER_UNAVAILABLE: (MatchDimension.IDENTIFIER, 0, False, False),
    MatchExplanationCode.NAME_LEGAL_EXACT: (MatchDimension.NAME, 10_000, True, False),
    MatchExplanationCode.NAME_TRADE_EXACT: (MatchDimension.NAME, 9_500, True, False),
    MatchExplanationCode.NAME_CROSS_EXACT: (MatchDimension.NAME, 9_000, True, False),
    MatchExplanationCode.NAME_TOKENS_EQUIVALENT: (MatchDimension.NAME, 8_000, True, False),
    MatchExplanationCode.NAME_DIFFERENT: (MatchDimension.NAME, 0, True, False),
    MatchExplanationCode.NAME_UNAVAILABLE: (MatchDimension.NAME, 0, False, False),
    MatchExplanationCode.DOMAIN_EXACT: (MatchDimension.DOMAIN, 10_000, True, False),
    MatchExplanationCode.DOMAIN_DIFFERENT: (MatchDimension.DOMAIN, 0, True, False),
    MatchExplanationCode.DOMAIN_UNAVAILABLE: (MatchDimension.DOMAIN, 0, False, False),
    MatchExplanationCode.GEOGRAPHY_EXACT: (MatchDimension.GEOGRAPHY, 10_000, True, False),
    MatchExplanationCode.GEOGRAPHY_CONFLICT: (MatchDimension.GEOGRAPHY, 0, True, True),
    MatchExplanationCode.ADDRESS_EXACT: (MatchDimension.ADDRESS, 10_000, True, False),
    MatchExplanationCode.ADDRESS_DIFFERENT: (MatchDimension.ADDRESS, 0, True, False),
    MatchExplanationCode.ADDRESS_UNAVAILABLE: (MatchDimension.ADDRESS, 0, False, False),
    MatchExplanationCode.ADMINISTRATORS_EXACT: (
        MatchDimension.ADMINISTRATORS,
        10_000,
        True,
        False,
    ),
    MatchExplanationCode.ADMINISTRATORS_DIFFERENT: (
        MatchDimension.ADMINISTRATORS,
        0,
        True,
        False,
    ),
    MatchExplanationCode.ADMINISTRATORS_UNAVAILABLE: (
        MatchDimension.ADMINISTRATORS,
        0,
        False,
        False,
    ),
    MatchExplanationCode.TEMPORAL_EXACT: (MatchDimension.TEMPORAL, 10_000, True, False),
    MatchExplanationCode.TEMPORAL_DIFFERENT: (MatchDimension.TEMPORAL, 0, True, False),
    MatchExplanationCode.TEMPORAL_UNAVAILABLE: (MatchDimension.TEMPORAL, 0, False, False),
}

_PARTIAL_EXPLANATION_DIMENSIONS = {
    MatchExplanationCode.ADDRESS_PARTIAL: MatchDimension.ADDRESS,
    MatchExplanationCode.ADMINISTRATORS_PARTIAL: MatchDimension.ADMINISTRATORS,
}


def _validate_dimension_semantics(value: DimensionScore) -> None:
    fixed = _FIXED_EXPLANATION_SEMANTICS.get(value.explanation)
    if fixed is not None:
        expected_dimension, expected_score, expected_available, expected_conflict = fixed
        if (
            value.dimension is not expected_dimension
            or value.score != expected_score
            or value.available is not expected_available
            or value.hard_conflict is not expected_conflict
        ):
            raise InvalidMatchEvaluationError("Dimension explanation is semantically inconsistent.")
        return
    partial_dimension = _PARTIAL_EXPLANATION_DIMENSIONS.get(value.explanation)
    if (
        partial_dimension is None
        or value.dimension is not partial_dimension
        or not 0 < value.score < BASIS_POINTS_MAX
        or not value.available
        or value.hard_conflict
    ):
        raise InvalidMatchEvaluationError("Dimension explanation is semantically inconsistent.")


def _basis_points(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= BASIS_POINTS_MAX:
        raise InvalidMatchEvaluationError(f"{field_name} must be integer basis points.")


def _digest(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise InvalidMatchEvaluationError(f"{field_name} must be a lowercase SHA-256 digest.")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = [
    "MATCH_EVALUATION_SCHEMA_VERSION",
    "CandidateBatchEvaluation",
    "CandidateEvaluation",
    "DimensionScore",
    "evaluate_candidate_batch",
    "normalize_matching_name",
    "rank_candidate_evaluations",
    "reconstitute_candidate_batch_evaluation",
    "reconstitute_candidate_evaluation",
]
