"""Pure F5.2 Claim invariants, histories, links, and assessments."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256

import pytest

from intelligence.claims.errors import ClaimHistoryError, ClaimIntegrityError
from intelligence.claims.models import (
    Claim,
    ClaimAssessmentOutcome,
    ClaimAssessmentReason,
    ClaimCorrectionReason,
    ClaimCreationMethod,
    ClaimCriticality,
    ClaimEvidenceLink,
    ClaimEvidencePurpose,
    ClaimEvidenceRole,
    ClaimEvidenceUseDecision,
    ClaimEvidenceUseOutcome,
    ClaimEvidenceUseReason,
    ClaimHistory,
    ClaimPredicate,
    ClaimTemporal,
    ClaimValue,
    CountryCodeClaimValue,
    DateClaimValue,
    PeriodClaimTemporal,
    PointClaimTemporal,
    RegistrationIdentifierClaimValue,
    RegistrationStatus,
    RegistrationStatusClaimValue,
    TemporalAbsenceReason,
    TextClaimValue,
    UndatedClaimTemporal,
    assess_links,
    build_claim,
    build_claim_link,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import ClaimCommandId, ClaimId, EvidenceId
from tests.claims.synthetic_fixtures import (
    COMPANY_ID,
    DECISION_ID,
    FIXED_TIME,
    INVESTIGATION_ID,
    USER_ID,
    WORKSPACE_ID,
    synthetic_history,
)


def _claim(
    *,
    version: int = 1,
    previous: Claim | None = None,
    predicate: ClaimPredicate = ClaimPredicate.LEGAL_NAME,
    value: ClaimValue | None = None,
    temporal: ClaimTemporal | None = None,
) -> Claim:
    claim_id = ClaimId.from_value(f"40000000-0000-4000-8000-{version:012d}")
    first_id = claim_id if previous is None else previous.series_id
    return build_claim(
        claim_id=claim_id,
        series_id=first_id,
        version=version,
        supersedes_claim_id=None if previous is None else previous.id,
        workspace_id=WORKSPACE_ID,
        investigation_id=INVESTIGATION_ID,
        subject_company_id=COMPANY_ID,
        entity_resolution_decision_id=DECISION_ID,
        command_id=ClaimCommandId.from_value(f"41000000-0000-4000-8000-{version:012d}"),
        command_digest=sha256(f"claim-command-{version}".encode()).hexdigest(),
        predicate_code=predicate,
        predicate_version=1,
        value=value if value is not None else TextClaimValue("Synthetic Alpha Ltd."),
        temporal=temporal or UndatedClaimTemporal(TemporalAbsenceReason.NOT_APPLICABLE),
        criticality=ClaimCriticality.STANDARD,
        creation_method=ClaimCreationMethod.MANUAL,
        creation_method_version=1,
        created_by=USER_ID,
        created_at=FIXED_TIME,
        correction_reason=(None if previous is None else ClaimCorrectionReason.VALUE_CORRECTION),
    )


def _decision(outcome: ClaimEvidenceUseOutcome) -> ClaimEvidenceUseDecision:
    return ClaimEvidenceUseDecision(
        outcome=outcome,
        reason_code=(
            ClaimEvidenceUseReason.CONTROLLED_EVIDENCE_ELIGIBLE
            if outcome is ClaimEvidenceUseOutcome.ELIGIBLE
            else ClaimEvidenceUseReason.CONTROLLED_EVIDENCE_NOT_PROVEN
        ),
        policy_id="F5_2_CONTROLLED_CORPUS_V1",
        policy_version=1,
        purpose=ClaimEvidencePurpose.INTERNAL_CLAIM_VERIFICATION,
        controlled_corpus_manifest_version=1,
        controlled_corpus_manifest_digest=sha256(b"manifest").hexdigest(),
        requested_by=USER_ID,
        evaluated_at=FIXED_TIME,
    )


def _link(
    claim: Claim, role: ClaimEvidenceRole, outcome: ClaimEvidenceUseOutcome
) -> ClaimEvidenceLink:
    evidence = synthetic_history().latest
    return build_claim_link(
        claim=claim,
        evidence_id=evidence.id,
        evidence_digest=evidence.evidence_digest,
        role=role,
        use_decision=_decision(outcome),
    )


def test_all_predicate_value_pairs_are_closed() -> None:
    values: dict[ClaimPredicate, ClaimValue] = {
        ClaimPredicate.LEGAL_NAME: TextClaimValue("Synthetic Alpha Ltd."),
        ClaimPredicate.REGISTRATION_STATUS: RegistrationStatusClaimValue(RegistrationStatus.ACTIVE),
        ClaimPredicate.INCORPORATION_DATE: DateClaimValue(date(2020, 1, 15)),
        ClaimPredicate.COUNTRY_OF_REGISTRATION: CountryCodeClaimValue(CountryCode("BR")),
        ClaimPredicate.REGISTRATION_IDENTIFIER: RegistrationIdentifierClaimValue(
            "SYNTHETIC_REGISTRY_ID", "TEST-REG-0001", CountryCode("BR")
        ),
    }
    base = _claim()
    for predicate, value in values.items():
        built = build_claim(
            claim_id=ClaimId.new(),
            series_id=base.series_id,
            version=2,
            supersedes_claim_id=base.id,
            workspace_id=WORKSPACE_ID,
            investigation_id=INVESTIGATION_ID,
            subject_company_id=COMPANY_ID,
            entity_resolution_decision_id=DECISION_ID,
            command_id=ClaimCommandId.new(),
            command_digest=sha256(predicate.value.encode()).hexdigest(),
            predicate_code=predicate,
            predicate_version=1,
            value=value,
            temporal=UndatedClaimTemporal(TemporalAbsenceReason.NOT_APPLICABLE),
            criticality=ClaimCriticality.STANDARD,
            creation_method=ClaimCreationMethod.MANUAL,
            creation_method_version=1,
            created_by=USER_ID,
            created_at=FIXED_TIME,
            correction_reason=ClaimCorrectionReason.VALUE_CORRECTION,
        )
        assert built.value == value
    with pytest.raises(InvariantViolationError, match="incompatible"):
        replace(base, value=DateClaimValue(date(2020, 1, 15)))

    for predicate, expected_value in values.items():
        for candidate in values.values():
            if candidate is expected_value:
                continue
            with pytest.raises(InvariantViolationError, match="incompatible"):
                _claim(predicate=predicate, value=candidate)


def test_all_temporal_shapes_are_closed_and_normalized() -> None:
    instant = datetime(2026, 8, 21, 12, tzinfo=UTC)
    point = PointClaimTemporal(instant)
    assert _claim(temporal=point).temporal == point
    period = PeriodClaimTemporal(instant, instant + timedelta(days=1))
    assert _claim(temporal=period).temporal == period
    undated = UndatedClaimTemporal(TemporalAbsenceReason.NOT_PROVIDED)
    assert _claim(temporal=undated).temporal == undated
    with pytest.raises(InvariantViolationError, match="precede"):
        PeriodClaimTemporal(instant, instant - timedelta(seconds=1))


def test_history_requires_support_and_preserves_predicate() -> None:
    first = _claim()
    support = _link(first, ClaimEvidenceRole.SUPPORTS, ClaimEvidenceUseOutcome.RESTRICTED)
    history = ClaimHistory((first,), (support,))
    second = _claim(version=2, previous=first, value=TextClaimValue("Corrected Alpha Ltd."))
    second_support = _link(second, ClaimEvidenceRole.SUPPORTS, ClaimEvidenceUseOutcome.ELIGIBLE)
    corrected = ClaimHistory((first, second), (support, second_support))
    assert corrected.latest is second
    with pytest.raises(ClaimHistoryError, match="predicate"):
        changed_predicate = _claim(
            version=2,
            previous=first,
            predicate=ClaimPredicate.REGISTRATION_STATUS,
            value=RegistrationStatusClaimValue(RegistrationStatus.ACTIVE),
        )
        changed_link = _link(
            changed_predicate,
            ClaimEvidenceRole.SUPPORTS,
            ClaimEvidenceUseOutcome.ELIGIBLE,
        )
        ClaimHistory((first, changed_predicate), (support, changed_link))
    with pytest.raises(ClaimHistoryError, match="support"):
        ClaimHistory(
            (first,),
            (
                _link(
                    first,
                    ClaimEvidenceRole.CONTRADICTS,
                    ClaimEvidenceUseOutcome.ELIGIBLE,
                ),
            ),
        )
    with pytest.raises(ClaimHistoryError, match="contiguous"):
        third = _claim(version=3, previous=first)
        ClaimHistory(
            (first, third),
            (
                support,
                _link(
                    third,
                    ClaimEvidenceRole.SUPPORTS,
                    ClaimEvidenceUseOutcome.ELIGIBLE,
                ),
            ),
        )
    with pytest.raises(ClaimHistoryError, match="duplicated"):
        ClaimHistory(
            (first,),
            (
                support,
                _link(first, ClaimEvidenceRole.QUALIFIES, ClaimEvidenceUseOutcome.ELIGIBLE),
            ),
        )
    assert history.latest_links == (support,)


@pytest.mark.parametrize("field", ["requested_by", "evaluated_at"])
def test_history_binds_link_decision_provenance_to_claim_version(field: str) -> None:
    claim = _claim()
    decision = _decision(ClaimEvidenceUseOutcome.ELIGIBLE)
    if field == "requested_by":
        decision = replace(decision, requested_by=USER_ID.new())
    else:
        decision = replace(decision, evaluated_at=FIXED_TIME + timedelta(seconds=1))
    evidence = synthetic_history().latest
    link = build_claim_link(
        claim=claim,
        evidence_id=evidence.id,
        evidence_digest=evidence.evidence_digest,
        role=ClaimEvidenceRole.SUPPORTS,
        use_decision=decision,
    )

    with pytest.raises(ClaimHistoryError, match="provenance"):
        ClaimHistory((claim,), (link,))


def test_tampered_digests_fail_closed() -> None:
    claim = _claim()
    with pytest.raises(ClaimIntegrityError, match="digest"):
        replace(claim, claim_digest=sha256(b"tampered").hexdigest())
    link = _link(claim, ClaimEvidenceRole.SUPPORTS, ClaimEvidenceUseOutcome.ELIGIBLE)
    with pytest.raises(ClaimIntegrityError, match="digest"):
        replace(link, link_digest=sha256(b"tampered").hexdigest())
    assert "Synthetic Alpha" not in repr(claim)


def test_assessment_matrix_and_qualifiers() -> None:
    claim = _claim()
    evidence_id = synthetic_history().latest.id
    support = _link(claim, ClaimEvidenceRole.SUPPORTS, ClaimEvidenceUseOutcome.ELIGIBLE)
    contradicts = build_claim_link(
        claim=claim,
        evidence_id=evidence_id,
        evidence_digest=synthetic_history().latest.evidence_digest,
        role=ClaimEvidenceRole.CONTRADICTS,
        use_decision=_decision(ClaimEvidenceUseOutcome.ELIGIBLE),
    )
    insufficient = assess_links((support,), frozenset())
    assert insufficient.outcome is ClaimAssessmentOutcome.INSUFFICIENT
    assert insufficient.reason is ClaimAssessmentReason.NO_ELIGIBLE_SUPPORT
    supported = assess_links((support,), frozenset({evidence_id}))
    assert supported.outcome is ClaimAssessmentOutcome.SUPPORTED
    conflicted = assess_links((support, contradicts), frozenset({evidence_id}))
    assert conflicted.outcome is ClaimAssessmentOutcome.CONFLICTED
    only_contradiction = assess_links((contradicts,), frozenset({evidence_id}))
    assert only_contradiction.reason is ClaimAssessmentReason.ELIGIBLE_CONTRADICTION_WITHOUT_SUPPORT
    qualifier_id = EvidenceId.new()
    qualifier = build_claim_link(
        claim=claim,
        evidence_id=qualifier_id,
        evidence_digest=synthetic_history().latest.evidence_digest,
        role=ClaimEvidenceRole.QUALIFIES,
        use_decision=_decision(ClaimEvidenceUseOutcome.ELIGIBLE),
    )
    qualified = assess_links((support, qualifier), frozenset({evidence_id, qualifier_id}))
    assert qualified.outcome is ClaimAssessmentOutcome.SUPPORTED
    assert qualified.qualifications == (qualifier_id,)
