"""Deterministic entity-resolution policy, contracts, and matching tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime
from typing import cast

import pytest

from intelligence.domain.geography import CountryCode
from intelligence.domain.investigation_inputs import (
    IDENTIFICATION_INPUT_EXTENDED_SCHEMA_VERSION,
    BusinessIdentifierInput,
    BusinessIdentifierType,
    CorporateDomainInput,
    IdentificationAddressInput,
    IdentificationInput,
    OriginalAndNormalizedText,
)
from intelligence.entity_resolution.contracts import (
    MAX_CANDIDATES_PER_BATCH,
    CandidateIdentitySnapshot,
    CandidateOriginSnapshot,
    CandidateSubmissionBatch,
    EntityCandidateInput,
    SourceRegistrationStatus,
)
from intelligence.entity_resolution.errors import (
    InvalidCandidateBatchError,
    InvalidCandidateError,
    InvalidMatchEvaluationError,
    InvalidMatchingPolicyError,
)
from intelligence.entity_resolution.matching import (
    CandidateBatchEvaluation,
    CandidateEvaluation,
    DimensionScore,
    evaluate_candidate_batch,
    normalize_matching_name,
    rank_candidate_evaluations,
    reconstitute_candidate_batch_evaluation,
    reconstitute_candidate_evaluation,
)
from intelligence.entity_resolution.policy import (
    INITIAL_MATCH_POLICY,
    DimensionWeight,
    HardConflictRule,
    MatchClassification,
    MatchDimension,
    MatchExplanationCode,
    MatchPolicy,
)


def _text(value: str) -> OriginalAndNormalizedText:
    return OriginalAndNormalizedText(original_value=value, normalized_value=value)


def _identifier(value: str = "123", country: str = "BR") -> BusinessIdentifierInput:
    return BusinessIdentifierInput(
        identifier_type=BusinessIdentifierType.TAX_IDENTIFIER,
        original_value=value,
        normalized_value=value,
        jurisdiction_country_code=CountryCode(country),
    )


def _address(locality: str = "São Paulo", postal: str = "01000") -> IdentificationAddressInput:
    return IdentificationAddressInput(
        country_code=CountryCode("BR"),
        locality=_text(locality),
        postal_code=_text(postal),
    )


def _input(**changes: object) -> IdentificationInput:
    values: dict[str, object] = {
        "schema_version": IDENTIFICATION_INPUT_EXTENDED_SCHEMA_VERSION,
        "legal_name": _text("Acme S.A."),
        "trade_name": _text("Acme"),
        "identifiers": (_identifier(),),
        "corporate_domain": CorporateDomainInput(
            original_value="acme.example", normalized_value="acme.example"
        ),
        "address": _address(),
        "administrators": (_text("Ana Silva"), _text("Bob Costa")),
        "incorporated_on": date(2001, 2, 3),
        "original_language": "pt-BR",
    }
    values.update(changes)
    return IdentificationInput(**values)  # type: ignore[arg-type]


def _candidate(key: str = "candidate-a", **identity_changes: object) -> EntityCandidateInput:
    values: dict[str, object] = {
        "legal_name": _text("Acme S.A."),
        "trade_name": _text("Acme"),
        "country_code": CountryCode("BR"),
        "identifiers": (_identifier(),),
        "corporate_domain": CorporateDomainInput(
            original_value="acme.example", normalized_value="acme.example"
        ),
        "address": _address(),
        "administrators": (_text("Ana Silva"), _text("Bob Costa")),
        "incorporated_on": date(2001, 2, 3),
        "registry_status": SourceRegistrationStatus.ACTIVE,
    }
    values.update(identity_changes)
    return EntityCandidateInput(
        candidate_key=key,
        identity=CandidateIdentitySnapshot(**values),  # type: ignore[arg-type]
        origin=CandidateOriginSnapshot(
            source_id="SYNTHETIC_REGISTRY",
            connector_id="synthetic.registry",
            connector_version="1.0.0",
            source_candidate_reference=f"opaque-{key}",
            collection_operation_reference="operation-1",
            collected_at=datetime(2026, 7, 29, 12, tzinfo=UTC),
            original_result_digest="a" * 64,
        ),
    )


def _evaluate(
    candidate: EntityCandidateInput | None = None,
    *,
    identification_input: IdentificationInput | None = None,
) -> CandidateEvaluation:
    source = identification_input or _input()
    batch = CandidateSubmissionBatch(
        input_digest=source.digest,
        candidates=(candidate or _candidate(),),
    )
    return evaluate_candidate_batch(
        investigation_country_code=CountryCode("BR"),
        identification_input=source,
        batch=batch,
        policy=INITIAL_MATCH_POLICY,
    ).candidates[0]


def _dimension(
    evaluation: CandidateEvaluation,
    dimension: MatchDimension,
) -> DimensionScore:
    return next(item for item in evaluation.dimensions if item.dimension is dimension)


def test_policy_is_canonical_versioned_integer_only_and_reconstitutable() -> None:
    policy = INITIAL_MATCH_POLICY

    assert sum(item.basis_points for item in policy.weights) == 10_000
    assert policy.high_threshold == 8_500
    assert policy.medium_threshold == 6_000
    assert policy.from_canonical_json(policy.to_canonical_json()) == policy
    assert len(policy.digest) == 64
    assert "Acme" not in repr(policy)

    with pytest.raises(InvalidMatchingPolicyError):
        replace(policy, high_threshold=8_500.0)  # type: ignore[arg-type]
    with pytest.raises(InvalidMatchingPolicyError):
        replace(
            policy,
            weights=(DimensionWeight(dimension=MatchDimension.IDENTIFIER, basis_points=10_000),),
        )
    with pytest.raises(InvalidMatchingPolicyError):
        policy.from_canonical_json(policy.to_canonical_json() + " ")


def test_candidate_contracts_are_closed_immutable_canonical_and_redacted() -> None:
    candidate = _candidate()
    identity_json = candidate.identity.to_canonical_json()
    origin_json = candidate.origin.to_canonical_json()

    assert CandidateIdentitySnapshot.from_canonical_json(identity_json) == candidate.identity
    assert CandidateOriginSnapshot.from_canonical_json(origin_json) == candidate.origin
    assert EntityCandidateInput.from_canonical_json(candidate.to_canonical_json()) == candidate
    assert "Acme" not in repr(candidate)
    assert "opaque-candidate-a" not in repr(candidate.origin)
    assert candidate.identity.to_public_redacted().identifier_count == 1
    with pytest.raises(FrozenInstanceError):
        candidate.candidate_key = "changed"  # type: ignore[misc]
    with pytest.raises(InvalidCandidateError):
        CandidateOriginSnapshot(
            source_id="source",
            connector_id="connector",
            connector_version="1.0.0",
            source_candidate_reference="https://secret.example",
            collected_at=datetime.now(UTC),
        )
    with pytest.raises(InvalidCandidateError):
        CandidateIdentitySnapshot.from_canonical_json(identity_json + " ")


def test_candidate_batch_rejects_empty_duplicate_and_more_than_one_hundred() -> None:
    digest = _input().digest
    with pytest.raises(InvalidCandidateBatchError):
        CandidateSubmissionBatch(input_digest=digest, candidates=())
    with pytest.raises(InvalidCandidateBatchError):
        CandidateSubmissionBatch(
            input_digest=digest,
            candidates=(_candidate(), _candidate()),
        )


def test_candidate_batch_digest_uses_canonical_candidate_key_order() -> None:
    digest = _input().digest
    first = _candidate("candidate-a")
    second = _candidate("candidate-b")

    forward = CandidateSubmissionBatch(input_digest=digest, candidates=(first, second))
    reversed_batch = CandidateSubmissionBatch(input_digest=digest, candidates=(second, first))

    assert forward.digest == reversed_batch.digest
    assert forward.to_canonical_json() == reversed_batch.to_canonical_json()
    with pytest.raises(InvalidCandidateBatchError):
        CandidateSubmissionBatch(
            input_digest=digest,
            candidates=tuple(
                _candidate(f"candidate-{index}") for index in range(MAX_CANDIDATES_PER_BATCH + 1)
            ),
        )


def test_exact_candidate_has_maximum_score_coverage_and_high_classification() -> None:
    result = _evaluate()

    assert result.total_score == 10_000
    assert result.coverage == 10_000
    assert result.classification is MatchClassification.HIGH
    assert result.hard_conflict is False
    assert _dimension(result, MatchDimension.IDENTIFIER).explanation is (
        MatchExplanationCode.IDENTIFIER_EXACT
    )


@pytest.mark.parametrize(
    ("candidate", "dimension", "explanation", "available", "conflict"),
    [
        (
            _candidate(identifiers=(_identifier("999"),)),
            MatchDimension.IDENTIFIER,
            MatchExplanationCode.IDENTIFIER_CONFLICT,
            True,
            True,
        ),
        (
            _candidate(identifiers=()),
            MatchDimension.IDENTIFIER,
            MatchExplanationCode.IDENTIFIER_UNAVAILABLE,
            False,
            False,
        ),
        (
            _candidate(country_code=CountryCode("US"), identifiers=(), address=None),
            MatchDimension.GEOGRAPHY,
            MatchExplanationCode.GEOGRAPHY_CONFLICT,
            True,
            True,
        ),
        (
            _candidate(
                corporate_domain=CorporateDomainInput(
                    original_value="other.example", normalized_value="other.example"
                )
            ),
            MatchDimension.DOMAIN,
            MatchExplanationCode.DOMAIN_DIFFERENT,
            True,
            False,
        ),
        (
            _candidate(corporate_domain=None),
            MatchDimension.DOMAIN,
            MatchExplanationCode.DOMAIN_UNAVAILABLE,
            False,
            False,
        ),
        (
            _candidate(address=None),
            MatchDimension.ADDRESS,
            MatchExplanationCode.ADDRESS_UNAVAILABLE,
            False,
            False,
        ),
        (
            _candidate(administrators=()),
            MatchDimension.ADMINISTRATORS,
            MatchExplanationCode.ADMINISTRATORS_UNAVAILABLE,
            False,
            False,
        ),
        (
            _candidate(incorporated_on=date(2002, 1, 1)),
            MatchDimension.TEMPORAL,
            MatchExplanationCode.TEMPORAL_DIFFERENT,
            True,
            False,
        ),
    ],
)
def test_dimensional_mismatch_absence_and_conflict_rules(
    candidate: EntityCandidateInput,
    dimension: MatchDimension,
    explanation: MatchExplanationCode,
    available: bool,
    conflict: bool,
) -> None:
    result = _evaluate(candidate)
    score = _dimension(result, dimension)

    assert score.explanation is explanation
    assert score.available is available
    assert score.hard_conflict is conflict
    assert result.classification is MatchClassification.EXCLUDED if conflict else True


@pytest.mark.parametrize(
    ("source_changes", "candidate_changes", "explanation"),
    [
        ({}, {}, MatchExplanationCode.NAME_LEGAL_EXACT),
        (
            {"legal_name": _text("Different Legal")},
            {"legal_name": _text("Other Legal")},
            MatchExplanationCode.NAME_TRADE_EXACT,
        ),
        (
            {"legal_name": _text("Acme Trading"), "trade_name": _text("Cross Name")},
            {"legal_name": _text("Cross Name"), "trade_name": _text("Other")},
            MatchExplanationCode.NAME_CROSS_EXACT,
        ),
        (
            {"legal_name": _text("Global Acme Holdings"), "trade_name": None},
            {"legal_name": _text("Holdings, Acme Global"), "trade_name": None},
            MatchExplanationCode.NAME_TOKENS_EQUIVALENT,
        ),
        (
            {"legal_name": _text("First"), "trade_name": None},
            {"legal_name": _text("Second"), "trade_name": None},
            MatchExplanationCode.NAME_DIFFERENT,
        ),
    ],
)
def test_name_rules_are_distinct_and_deterministic(
    source_changes: dict[str, object],
    candidate_changes: dict[str, object],
    explanation: MatchExplanationCode,
) -> None:
    source = _input(**source_changes)
    result = _evaluate(
        _candidate(**candidate_changes),  # type: ignore[arg-type]
        identification_input=source,
    )

    assert _dimension(result, MatchDimension.NAME).explanation is explanation


def test_partial_address_and_administrators_use_only_comparable_values() -> None:
    result = _evaluate(
        _candidate(
            address=_address(locality="São Paulo", postal="99999"),
            administrators=(_text("Ana Silva"), _text("Other Person")),
        )
    )

    assert _dimension(result, MatchDimension.ADDRESS).score == 5_000
    assert _dimension(result, MatchDimension.ADDRESS).explanation is (
        MatchExplanationCode.ADDRESS_PARTIAL
    )
    assert _dimension(result, MatchDimension.ADMINISTRATORS).score == 3_333
    assert _dimension(result, MatchDimension.ADMINISTRATORS).explanation is (
        MatchExplanationCode.ADMINISTRATORS_PARTIAL
    )


def test_name_normalization_uses_nfkc_casefold_symbols_and_collapsed_spaces() -> None:
    assert normalize_matching_name("  ACME—S.A.  ") == "acme s a"
    assert normalize_matching_name("\uff21\uff23\uff2d\uff25") == "acme"
    with pytest.raises(InvalidMatchEvaluationError):
        normalize_matching_name(123)  # type: ignore[arg-type]


def test_ranking_is_stable_and_ties_are_broken_by_candidate_key() -> None:
    source = _input()
    batch = CandidateSubmissionBatch(
        input_digest=source.digest,
        candidates=(
            _candidate("z-tied"),
            _candidate("excluded", identifiers=(_identifier("999"),)),
            _candidate("a-tied"),
        ),
    )

    first = evaluate_candidate_batch(
        investigation_country_code=CountryCode("BR"),
        identification_input=source,
        batch=batch,
        policy=INITIAL_MATCH_POLICY,
    )
    second = evaluate_candidate_batch(
        investigation_country_code=CountryCode("BR"),
        identification_input=source,
        batch=batch,
        policy=INITIAL_MATCH_POLICY,
    )

    assert [item.candidate_key for item in first.candidates] == [
        "a-tied",
        "z-tied",
        "excluded",
    ]
    assert first.digest == second.digest
    changed = _evaluate(_candidate(legal_name=_text("Other")))
    assert changed.digest != first.candidates[0].digest


def test_batch_input_digest_must_match_persisted_input() -> None:
    source = _input()
    batch = CandidateSubmissionBatch(input_digest="0" * 64, candidates=(_candidate(),))

    with pytest.raises(InvalidMatchEvaluationError, match="input digest"):
        evaluate_candidate_batch(
            investigation_country_code=CountryCode("BR"),
            identification_input=source,
            batch=batch,
            policy=INITIAL_MATCH_POLICY,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"legal_name": "name"},
        {"country_code": "BR"},
        {"trade_name": "trade"},
        {"identifiers": []},
        {"corporate_domain": "domain"},
        {"address": "address"},
        {"incorporated_on": datetime(2026, 1, 1, tzinfo=UTC)},
        {"administrators": []},
        {"registry_status": "ACTIVE"},
    ],
)
def test_candidate_identity_rejects_every_untyped_or_unsupported_field(
    changes: dict[str, object],
) -> None:
    identity = _candidate().identity
    with pytest.raises(InvalidCandidateError):
        replace(identity, **changes)  # type: ignore[arg-type]


def test_candidate_identity_rejects_cross_country_nested_values_and_limits() -> None:
    with pytest.raises(InvalidCandidateError, match="address country"):
        CandidateIdentitySnapshot(
            legal_name=_text("Name"),
            country_code=CountryCode("US"),
            address=_address(),
        )
    with pytest.raises(InvalidCandidateError, match="jurisdiction"):
        CandidateIdentitySnapshot(
            legal_name=_text("Name"),
            country_code=CountryCode("US"),
            identifiers=(_identifier(),),
        )
    with pytest.raises(InvalidCandidateError, match="identifiers"):
        replace(_candidate().identity, identifiers=(_identifier(),) * 21)
    with pytest.raises(InvalidCandidateError, match="administrators"):
        replace(_candidate().identity, administrators=(_text("A"),) * 51)


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"source_id": "invalid source"},
        {"connector_id": "invalid connector"},
        {"connector_version": "v1"},
        {"source_candidate_reference": ""},
        {"source_candidate_reference": "x" * 257},
        {"source_candidate_reference": "https://example.test"},
        {"collection_operation_reference": "bad\nreference"},
        {"original_result_digest": "A" * 64},
    ],
)
def test_candidate_origin_rejects_unsupported_or_unsafe_values(
    changes: dict[str, object],
) -> None:
    with pytest.raises(InvalidCandidateError):
        replace(_candidate().origin, **changes)  # type: ignore[arg-type]


def test_candidate_and_batch_reject_untyped_fields_versions_and_noncanonical_json() -> None:
    candidate = _candidate()
    source = _input()
    batch = CandidateSubmissionBatch(input_digest=source.digest, candidates=(candidate,))
    for changes in (
        {"candidate_key": "invalid key"},
        {"identity": "identity"},
        {"origin": "origin"},
    ):
        with pytest.raises(InvalidCandidateError):
            replace(candidate, **changes)  # type: ignore[arg-type]
    with pytest.raises(InvalidCandidateBatchError):
        replace(batch, batch_version=True)
    with pytest.raises(InvalidCandidateBatchError):
        replace(batch, candidates=cast(tuple[EntityCandidateInput, ...], [candidate]))
    assert CandidateSubmissionBatch.from_canonical_json(batch.to_canonical_json()) == batch
    with pytest.raises(InvalidCandidateError):
        EntityCandidateInput.from_canonical_json(candidate.to_canonical_json() + " ")
    with pytest.raises(InvalidCandidateBatchError):
        CandidateSubmissionBatch(input_digest="bad", candidates=(candidate,))


@pytest.mark.parametrize(
    ("kind", "mutator"),
    [
        ("identity", lambda value: value.update({"country_code": "BRA"})),
        ("identity", lambda value: value.update({"registry_status": "INVALID"})),
        ("identity", lambda value: value.update({"incorporated_on": "2026-1-1"})),
        ("identity", lambda value: value.update({"administrators": "invalid"})),
        ("origin", lambda value: value.update({"collected_at": "2026-01-01"})),
        ("origin", lambda value: value.update({"schema_version": True})),
        ("candidate", lambda value: value.update({"candidate_key": 1})),
        ("batch", lambda value: value.update({"candidates": "invalid"})),
    ],
)
def test_reconstitution_rejects_malformed_closed_snapshots(
    kind: str,
    mutator: Callable[[dict[str, object]], object],
) -> None:
    candidate = _candidate()
    source = _input()
    batch = CandidateSubmissionBatch(input_digest=source.digest, candidates=(candidate,))
    serialized = {
        "identity": candidate.identity.to_canonical_json(),
        "origin": candidate.origin.to_canonical_json(),
        "candidate": candidate.to_canonical_json(),
        "batch": batch.to_canonical_json(),
    }[kind]
    value = cast(dict[str, object], json.loads(serialized))
    mutator(value)
    malformed = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with pytest.raises((InvalidCandidateError, InvalidCandidateBatchError)):
        if kind == "identity":
            CandidateIdentitySnapshot.from_canonical_json(malformed)
        elif kind == "origin":
            CandidateOriginSnapshot.from_canonical_json(malformed)
        elif kind == "candidate":
            EntityCandidateInput.from_canonical_json(malformed)
        else:
            CandidateSubmissionBatch.from_canonical_json(malformed)


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"policy_id": "invalid"},
        {"version": 0},
        {"normalization_version": "invalid"},
        {"weights": cast(tuple[DimensionWeight, ...], [])},
        {"weights": INITIAL_MATCH_POLICY.weights[:-1]},
        {
            "weights": tuple(
                replace(value, basis_points=value.basis_points + 1)
                if value.dimension is MatchDimension.NAME
                else value
                for value in INITIAL_MATCH_POLICY.weights
            )
        },
        {"high_threshold": 5_000, "medium_threshold": 6_000},
        {"hard_conflict_rules": cast(frozenset[HardConflictRule], set())},
        {"hard_conflict_rules": frozenset({HardConflictRule.COUNTRY_MISMATCH})},
    ],
)
def test_policy_rejects_invalid_shapes_and_values(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidMatchingPolicyError):
        replace(INITIAL_MATCH_POLICY, **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "normalization_version",
    ["", "NAME_NORMALIZATION_V2", "NAME_NORMALIZATION_V99", "OTHER"],
)
def test_policy_rejects_unknown_normalization_versions(normalization_version: str) -> None:
    with pytest.raises(InvalidMatchingPolicyError, match=r"unsupported|invalid format"):
        replace(INITIAL_MATCH_POLICY, normalization_version=normalization_version)


@pytest.mark.parametrize(
    "normalization_version",
    ["NAME_NORMALIZATION_V2", "NAME_NORMALIZATION_V99", "OTHER"],
)
def test_policy_reconstitution_rejects_unknown_normalization_versions(
    normalization_version: str,
) -> None:
    value = cast(dict[str, object], json.loads(INITIAL_MATCH_POLICY.to_canonical_json()))
    value["normalization_version"] = normalization_version
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))

    with pytest.raises(InvalidMatchingPolicyError, match="unsupported"):
        MatchPolicy.from_canonical_json(serialized)


def test_policy_classification_and_public_argument_validation() -> None:
    policy = INITIAL_MATCH_POLICY
    assert policy.classify(8_500, has_hard_conflict=False) is MatchClassification.HIGH
    assert policy.classify(6_000, has_hard_conflict=False) is MatchClassification.MEDIUM
    assert policy.classify(5_999, has_hard_conflict=False) is MatchClassification.LOW
    assert policy.classify(10_000, has_hard_conflict=True) is MatchClassification.EXCLUDED
    with pytest.raises(InvalidMatchingPolicyError):
        policy.classify(1, has_hard_conflict=cast(bool, 1))
    with pytest.raises(InvalidMatchingPolicyError):
        policy.weight_for(cast(MatchDimension, "NAME"))
    with pytest.raises(InvalidMatchingPolicyError):
        DimensionWeight(dimension=cast(MatchDimension, "NAME"), basis_points=1)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "{",
        "[]",
        '{"unsupported":true}',
    ],
)
def test_policy_reconstitution_rejects_non_json_or_unsupported_roots(value: object) -> None:
    with pytest.raises(InvalidMatchingPolicyError):
        INITIAL_MATCH_POLICY.from_canonical_json(cast(str, value))


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.update({"weights": "invalid"}),
        lambda value: value["weights"].append("invalid"),
        lambda value: value["weights"][0].update({"dimension": 1}),
        lambda value: value["weights"][0].update({"basis_points": True}),
        lambda value: value.update({"policy_id": 1}),
        lambda value: value.update({"version": True}),
        lambda value: value.update({"hard_conflict_rules": [1]}),
        lambda value: value.update({"hard_conflict_rules": ["INVALID"]}),
    ],
)
def test_policy_reconstitution_rejects_invalid_nested_types(
    mutator: Callable[[dict[str, object]], object],
) -> None:
    value = cast(dict[str, object], json.loads(INITIAL_MATCH_POLICY.to_canonical_json()))
    mutator(value)
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
    with pytest.raises(InvalidMatchingPolicyError):
        INITIAL_MATCH_POLICY.from_canonical_json(serialized)


@pytest.mark.parametrize(
    "changes",
    [
        {"dimension": cast(MatchDimension, "NAME")},
        {"score": True},
        {"contribution": 1},
        {"available": cast(bool, 1)},
        {"explanation": cast(MatchExplanationCode, "INVALID")},
        {"available": False, "score": 1, "contribution": 0},
        {"available": False, "hard_conflict": True},
    ],
)
def test_dimension_score_rejects_inconsistent_or_untyped_values(
    changes: dict[str, object],
) -> None:
    score = _dimension(_evaluate(), MatchDimension.NAME)
    with pytest.raises(InvalidMatchEvaluationError):
        replace(score, **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"explanation": MatchExplanationCode.DOMAIN_EXACT},
        {"explanation": MatchExplanationCode.NAME_UNAVAILABLE},
        {"score": 9_999, "contribution": 2_499},
        {"hard_conflict": True},
    ],
)
def test_dimension_score_rejects_semantically_incompatible_explanations(
    changes: dict[str, object],
) -> None:
    score = _dimension(_evaluate(), MatchDimension.NAME)

    with pytest.raises(InvalidMatchEvaluationError, match="semantically"):
        replace(score, **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"candidate_key": ""},
        {"candidate_digest": "bad"},
        {"dimensions": ()},
        {"total_score": 0},
        {"coverage": 0},
        {"hard_conflict": True},
        {"classification": cast(MatchClassification, "HIGH")},
        {"classification": MatchClassification.EXCLUDED},
        {"rank": 0},
    ],
)
def test_candidate_evaluation_rejects_inconsistent_or_untyped_values(
    changes: dict[str, object],
) -> None:
    evaluation = _evaluate()
    with pytest.raises(InvalidMatchEvaluationError):
        replace(evaluation, **changes)  # type: ignore[arg-type]


def test_batch_evaluation_and_evaluator_validate_public_boundary() -> None:
    source = _input()
    submission = CandidateSubmissionBatch(
        input_digest=source.digest,
        candidates=(_candidate(),),
    )
    result = evaluate_candidate_batch(
        investigation_country_code=CountryCode("BR"),
        identification_input=source,
        batch=submission,
        policy=INITIAL_MATCH_POLICY,
    )
    assert result.top_classification is MatchClassification.HIGH
    assert "Acme" not in repr(result)
    for changes in (
        {"batch_digest": "bad"},
        {"schema_version": 2},
        {"candidates": ()},
        {"candidates": (replace(result.candidates[0], rank=2),)},
    ):
        with pytest.raises(InvalidMatchEvaluationError):
            replace(result, **changes)
    with pytest.raises(InvalidMatchEvaluationError):
        evaluate_candidate_batch(
            investigation_country_code=cast(CountryCode, "BR"),
            identification_input=source,
            batch=submission,
            policy=INITIAL_MATCH_POLICY,
        )
    with pytest.raises(InvalidMatchEvaluationError):
        evaluate_candidate_batch(
            investigation_country_code=CountryCode("BR"),
            identification_input=cast(IdentificationInput, "input"),
            batch=submission,
            policy=INITIAL_MATCH_POLICY,
        )
    with pytest.raises(InvalidMatchEvaluationError):
        evaluate_candidate_batch(
            investigation_country_code=CountryCode("BR"),
            identification_input=source,
            batch=cast(CandidateSubmissionBatch, "batch"),
            policy=INITIAL_MATCH_POLICY,
        )
    with pytest.raises(InvalidMatchEvaluationError):
        evaluate_candidate_batch(
            investigation_country_code=CountryCode("BR"),
            identification_input=source,
            batch=submission,
            policy=cast(MatchPolicy, "policy"),
        )


def test_unavailable_name_disjoint_address_and_different_administrators_are_explained() -> None:
    extended = _input()
    no_name = IdentificationInput(
        schema_version=IDENTIFICATION_INPUT_EXTENDED_SCHEMA_VERSION,
        identifiers=(_identifier(),),
        administrators=extended.administrators,
    )
    candidate = _candidate(
        address=IdentificationAddressInput(
            country_code=CountryCode("BR"),
            address_line_1=_text("Street"),
        ),
        administrators=(_text("Completely Different"),),
    )
    result = _evaluate(candidate, identification_input=no_name)
    assert _dimension(result, MatchDimension.NAME).explanation is (
        MatchExplanationCode.NAME_UNAVAILABLE
    )
    assert _dimension(result, MatchDimension.ADDRESS).explanation is (
        MatchExplanationCode.ADDRESS_UNAVAILABLE
    )
    assert _dimension(result, MatchDimension.ADMINISTRATORS).explanation is (
        MatchExplanationCode.ADMINISTRATORS_DIFFERENT
    )


def test_address_with_no_comparable_fields_and_fully_different_fields_is_explained() -> None:
    source = _input(address=_address(locality="Source", postal="11111"))
    no_common = _candidate(
        address=IdentificationAddressInput(
            country_code=CountryCode("BR"),
            address_line_1=_text("Only candidate line"),
        )
    )
    different = _candidate(address=_address(locality="Other", postal="99999"))

    assert (
        _dimension(
            _evaluate(no_common, identification_input=source), MatchDimension.ADDRESS
        ).explanation
        is MatchExplanationCode.ADDRESS_UNAVAILABLE
    )
    assert (
        _dimension(
            _evaluate(different, identification_input=source), MatchDimension.ADDRESS
        ).explanation
        is MatchExplanationCode.ADDRESS_DIFFERENT
    )


def test_reconstitution_helpers_reject_invalid_context_and_tampering() -> None:
    source = _input()
    candidate = _candidate()
    batch = CandidateSubmissionBatch(input_digest=source.digest, candidates=(candidate,))
    result = evaluate_candidate_batch(
        investigation_country_code=CountryCode("BR"),
        identification_input=source,
        batch=batch,
        policy=INITIAL_MATCH_POLICY,
    )
    evaluation = result.candidates[0]
    arguments: dict[str, object] = {
        "candidate": candidate,
        "dimensions": evaluation.dimensions,
        "total_score": evaluation.total_score,
        "coverage": evaluation.coverage,
        "classification": evaluation.classification,
        "hard_conflict": evaluation.hard_conflict,
        "rank": evaluation.rank,
        "policy": INITIAL_MATCH_POLICY,
        "input_digest": source.digest,
        "evaluation_digest": evaluation.digest,
    }

    for changes in (
        {"candidate": "candidate"},
        {"policy": "policy"},
        {"evaluation_digest": "0" * 64},
    ):
        with pytest.raises(InvalidMatchEvaluationError):
            reconstitute_candidate_evaluation(**(arguments | changes))  # type: ignore[arg-type]

    unavailable = next(
        item
        for item in _evaluate(_candidate(corporate_domain=None)).dimensions
        if item.dimension is MatchDimension.DOMAIN
    )
    wrong_weight = replace(unavailable, weight=unavailable.weight + 1)
    weight_arguments = arguments | {
        "dimensions": tuple(
            wrong_weight if item.dimension is MatchDimension.DOMAIN else item
            for item in evaluation.dimensions
        )
    }
    with pytest.raises(InvalidMatchEvaluationError, match="weight"):
        reconstitute_candidate_evaluation(**weight_arguments)  # type: ignore[arg-type]

    batch_arguments: dict[str, object] = {
        "batch": batch,
        "policy": INITIAL_MATCH_POLICY,
        "candidates": result.candidates,
        "evaluation_digest": result.digest,
    }
    batch_changes: tuple[dict[str, object], ...] = (
        {"batch": "batch"},
        {"policy": "policy"},
        {"candidates": ()},
        {"candidates": (replace(evaluation, candidate_digest="0" * 64),)},
        {"candidates": (replace(evaluation, input_digest="0" * 64),)},
        {"candidates": (replace(evaluation, policy_digest="0" * 64),)},
        {"evaluation_digest": "0" * 64},
    )
    for batch_change in batch_changes:
        with pytest.raises(InvalidMatchEvaluationError):
            reconstitute_candidate_batch_evaluation(
                **(batch_arguments | batch_change)  # type: ignore[arg-type]
            )


def test_batch_evaluation_rejects_duplicate_context_and_wrong_official_ranking() -> None:
    source = _input()
    batch = CandidateSubmissionBatch(
        input_digest=source.digest,
        candidates=(_candidate("candidate-b"), _candidate("candidate-a")),
    )
    result = evaluate_candidate_batch(
        investigation_country_code=CountryCode("BR"),
        identification_input=source,
        batch=batch,
        policy=INITIAL_MATCH_POLICY,
    )
    first, second = result.candidates

    invalid_candidates = (
        (first, replace(second, candidate_key=first.candidate_key)),
        (first, replace(second, input_digest="0" * 64)),
        (first, replace(second, policy_digest="0" * 64)),
        (replace(second, rank=1), replace(first, rank=2)),
    )
    for candidates in invalid_candidates:
        with pytest.raises(InvalidMatchEvaluationError):
            CandidateBatchEvaluation(
                batch_digest=result.batch_digest,
                input_digest=result.input_digest,
                policy_digest=result.policy_digest,
                candidates=candidates,
            )

    with pytest.raises(InvalidMatchEvaluationError):
        rank_candidate_evaluations(cast(tuple[CandidateEvaluation, ...], []))
    assert "candidate=<redacted>" in repr(first)


def test_dimension_semantics_reject_unavailable_conflict_and_invalid_partial() -> None:
    name = _dimension(_evaluate(), MatchDimension.NAME)
    with pytest.raises(InvalidMatchEvaluationError, match="comparable"):
        replace(
            name,
            score=0,
            contribution=0,
            available=False,
            hard_conflict=True,
            explanation=MatchExplanationCode.NAME_UNAVAILABLE,
        )
    with pytest.raises(InvalidMatchEvaluationError, match="semantically"):
        replace(
            name,
            dimension=MatchDimension.ADDRESS,
            score=0,
            contribution=0,
            explanation=MatchExplanationCode.ADDRESS_PARTIAL,
        )
    with pytest.raises(InvalidMatchEvaluationError):
        replace(_evaluate(), dimensions=cast(tuple[DimensionScore, ...], []))
