"""F5.3 decision-chain, temporal integrity, and pure projection tests."""

from dataclasses import replace
from datetime import datetime, timedelta
from hashlib import sha256
from typing import cast

import pytest

from intelligence.application.evidence_admissibility_policy import (
    F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    EvidenceAdmissibilityCommandId,
    EvidenceAdmissibilityDecisionId,
    EvidenceCommandId,
    EvidenceId,
    EvidenceLifecycleEventId,
    UserId,
)
from intelligence.evidence.admissibility import (
    EffectiveEvidenceAdmissibilityStatus,
    EvidenceAdmissibilityDecision,
    EvidenceAdmissibilityDecisionOutcome,
    EvidenceAdmissibilityHistory,
    EvidenceAdmissibilityPurpose,
    EvidenceAdmissibilityReason,
    EvidenceAdmissionBasis,
    build_evidence_admissibility_decision,
    project_effective_evidence_admissibility,
)
from intelligence.evidence.errors import (
    EvidenceAdmissibilityHistoryError,
    EvidenceAdmissibilityIntegrityError,
    EvidenceNotExistingAtCutoffError,
)
from intelligence.evidence.models import (
    EvidenceHistory,
    EvidenceLifecycleEventType,
    EvidenceLifecycleReason,
    build_evidence,
    build_lifecycle_event,
)
from tests.claims.synthetic_fixtures import FIXED_TIME, synthetic_history

DECIDER = UserId.from_value("40000000-0000-4000-8000-000000000001")


def _decision(
    *,
    outcome: EvidenceAdmissibilityDecisionOutcome = (
        EvidenceAdmissibilityDecisionOutcome.ADMISSIBLE
    ),
    reason: EvidenceAdmissibilityReason = (
        EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED
    ),
    decided_at: datetime = FIXED_TIME,
    valid_until: datetime | None = None,
    sequence: int = 1,
    predecessor: EvidenceAdmissibilityDecisionId | None = None,
    policy_id: str = "F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1",
) -> EvidenceAdmissibilityDecision:
    evidence = synthetic_history().latest
    return build_evidence_admissibility_decision(
        decision_id=EvidenceAdmissibilityDecisionId.new(),
        evidence=evidence,
        decision_sequence=sequence,
        supersedes_decision_id=predecessor,
        outcome=outcome,
        reason_code=reason,
        policy_id=policy_id,
        policy_version=1,
        purpose=EvidenceAdmissibilityPurpose.INTERNAL_FACTUAL_EVIDENCE_USE,
        admission_basis=EvidenceAdmissionBasis.CONTROLLED_TEST_EVIDENCE,
        controlled_trust_root_id=F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.manifest_id,
        controlled_trust_root_version=1,
        controlled_trust_root_digest=F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.digest,
        valid_until=valid_until,
        command_id=EvidenceAdmissibilityCommandId.new(),
        command_digest=sha256(f"command-{sequence}".encode()).hexdigest(),
        decided_by=DECIDER,
        decided_at=decided_at,
    )


def test_projection_before_existence_is_typed_and_existing_without_decision_is_pending() -> None:
    evidence = synthetic_history()
    with pytest.raises(EvidenceNotExistingAtCutoffError):
        project_effective_evidence_admissibility(
            evidence_history=evidence,
            decision_histories=(),
            as_of=FIXED_TIME - timedelta(microseconds=1),
        )
    result = project_effective_evidence_admissibility(
        evidence_history=evidence, decision_histories=(), as_of=FIXED_TIME
    )
    assert result.status is EffectiveEvidenceAdmissibilityStatus.PENDING


@pytest.mark.parametrize(
    ("outcome", "reason", "expected"),
    [
        (
            EvidenceAdmissibilityDecisionOutcome.ADMISSIBLE,
            EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED,
            EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE,
        ),
        (
            EvidenceAdmissibilityDecisionOutcome.RESTRICTED,
            EvidenceAdmissibilityReason.POLICY_OR_VERIFIABILITY_RESTRICTED,
            EffectiveEvidenceAdmissibilityStatus.RESTRICTED,
        ),
        (
            EvidenceAdmissibilityDecisionOutcome.REJECTED,
            EvidenceAdmissibilityReason.CONTENT_OR_CONTEXT_REJECTED,
            EffectiveEvidenceAdmissibilityStatus.REJECTED,
        ),
    ],
)
def test_projection_maps_all_persisted_outcomes(
    outcome: EvidenceAdmissibilityDecisionOutcome,
    reason: EvidenceAdmissibilityReason,
    expected: EffectiveEvidenceAdmissibilityStatus,
) -> None:
    evidence = synthetic_history()
    decision = _decision(outcome=outcome, reason=reason)
    result = project_effective_evidence_admissibility(
        evidence_history=evidence,
        decision_histories=(EvidenceAdmissibilityHistory(decisions=(decision,)),),
        as_of=FIXED_TIME,
    )
    assert result.status is expected


def test_expiration_boundary_and_unbounded_admission_are_deterministic() -> None:
    evidence = synthetic_history()
    expiry = FIXED_TIME + timedelta(hours=1)
    history = EvidenceAdmissibilityHistory(decisions=(_decision(valid_until=expiry),))
    before = project_effective_evidence_admissibility(
        evidence_history=evidence,
        decision_histories=(history,),
        as_of=expiry - timedelta(microseconds=1),
    )
    at = project_effective_evidence_admissibility(
        evidence_history=evidence, decision_histories=(history,), as_of=expiry
    )
    unbounded = EvidenceAdmissibilityHistory(decisions=(_decision(),))
    later = project_effective_evidence_admissibility(
        evidence_history=evidence,
        decision_histories=(unbounded,),
        as_of=expiry + timedelta(days=999),
    )
    assert before.status is EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE
    assert at.status is EffectiveEvidenceAdmissibilityStatus.EXPIRED
    assert later.status is EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE


def test_revocation_is_terminal_but_not_retroactive() -> None:
    original = synthetic_history()
    revoked_at = FIXED_TIME + timedelta(hours=1)
    event = build_lifecycle_event(
        event_id=EvidenceLifecycleEventId.new(),
        workspace_id=original.latest.workspace_id,
        investigation_id=original.latest.investigation_id,
        evidence_id=original.latest.id,
        command_id=EvidenceCommandId.new(),
        command_digest=sha256(b"revoke-command").hexdigest(),
        event_type=EvidenceLifecycleEventType.REVOKED,
        reason=EvidenceLifecycleReason.CONTENT_INVALID,
        actor_user_id=DECIDER,
        related_evidence_id=None,
        occurred_at=revoked_at,
    )
    evidence = EvidenceHistory(
        artifact=original.artifact, versions=original.versions, events=(event,)
    )
    decisions = (EvidenceAdmissibilityHistory(decisions=(_decision(),)),)
    before = project_effective_evidence_admissibility(
        evidence_history=evidence,
        decision_histories=decisions,
        as_of=revoked_at - timedelta(microseconds=1),
    )
    at = project_effective_evidence_admissibility(
        evidence_history=evidence, decision_histories=decisions, as_of=revoked_at
    )
    assert before.status is EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE
    assert at.status is EffectiveEvidenceAdmissibilityStatus.REVOKED


def test_correction_selects_historical_version_and_starts_new_pending() -> None:
    original = synthetic_history()
    corrected_at = FIXED_TIME + timedelta(hours=1)
    prior = original.latest
    correction_command = EvidenceCommandId.new()
    command_digest = sha256(b"correction-command").hexdigest()
    corrected = build_evidence(
        evidence_id=EvidenceId.new(),
        series_id=prior.series_id,
        version=2,
        supersedes_evidence_id=prior.id,
        workspace_id=prior.workspace_id,
        investigation_id=prior.investigation_id,
        subject_company_id=prior.subject_company_id,
        entity_resolution_decision_id=prior.entity_resolution_decision_id,
        artifact_id=prior.artifact_id,
        command_id=correction_command,
        command_digest=command_digest,
        kind=prior.kind,
        language=prior.language,
        locator=prior.locator,
        located_content=b"Synthetic Alpha Registry Corrected Ltd.",
        content_original="Synthetic Alpha Registry Corrected Ltd.",
        extraction_method=prior.extraction_method,
        extraction_method_version=prior.extraction_method_version,
        matching_policy_id=prior.matching_policy_id,
        matching_policy_version=prior.matching_policy_version,
        created_by=DECIDER,
        created_at=corrected_at,
    )
    superseded = build_lifecycle_event(
        event_id=EvidenceLifecycleEventId.new(),
        workspace_id=prior.workspace_id,
        investigation_id=prior.investigation_id,
        evidence_id=prior.id,
        command_id=correction_command,
        command_digest=command_digest,
        event_type=EvidenceLifecycleEventType.SUPERSEDED,
        reason=EvidenceLifecycleReason.CORRECTION,
        actor_user_id=DECIDER,
        related_evidence_id=corrected.id,
        occurred_at=corrected_at,
    )
    evidence = EvidenceHistory(
        artifact=original.artifact,
        versions=(prior, corrected),
        events=(superseded,),
    )
    old_decisions = EvidenceAdmissibilityHistory(decisions=(_decision(),))
    historical = project_effective_evidence_admissibility(
        evidence_history=evidence,
        decision_histories=(old_decisions,),
        as_of=corrected_at - timedelta(microseconds=1),
    )
    current = project_effective_evidence_admissibility(
        evidence_history=evidence,
        decision_histories=(old_decisions,),
        as_of=corrected_at,
    )
    assert historical.evidence_id == prior.id
    assert historical.status is EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE
    assert current.evidence_id == corrected.id
    assert current.status is EffectiveEvidenceAdmissibilityStatus.PENDING

    invalid_boundary = EvidenceAdmissibilityHistory(decisions=(_decision(decided_at=corrected_at),))
    with pytest.raises(EvidenceAdmissibilityHistoryError):
        invalid_boundary.validate_against(evidence)


def test_history_rejects_decision_before_creation_and_at_revocation() -> None:
    evidence = synthetic_history()
    before = EvidenceAdmissibilityHistory(
        decisions=(_decision(decided_at=FIXED_TIME - timedelta(microseconds=1)),)
    )
    with pytest.raises(EvidenceAdmissibilityHistoryError):
        before.validate_against(evidence)

    revoked_at = FIXED_TIME + timedelta(hours=1)
    event = build_lifecycle_event(
        event_id=EvidenceLifecycleEventId.new(),
        workspace_id=evidence.latest.workspace_id,
        investigation_id=evidence.latest.investigation_id,
        evidence_id=evidence.latest.id,
        command_id=EvidenceCommandId.new(),
        command_digest=sha256(b"revoke-command-at-boundary").hexdigest(),
        event_type=EvidenceLifecycleEventType.REVOKED,
        reason=EvidenceLifecycleReason.CONTENT_INVALID,
        actor_user_id=DECIDER,
        related_evidence_id=None,
        occurred_at=revoked_at,
    )
    revoked = EvidenceHistory(
        artifact=evidence.artifact, versions=evidence.versions, events=(event,)
    )
    at_revocation = EvidenceAdmissibilityHistory(decisions=(_decision(decided_at=revoked_at),))
    with pytest.raises(EvidenceAdmissibilityHistoryError):
        at_revocation.validate_against(revoked)


def test_chain_digest_and_expiration_invariants_fail_closed() -> None:
    first = _decision()
    with pytest.raises(EvidenceAdmissibilityIntegrityError):
        replace(first, decision_digest="0" * 64)
    with pytest.raises(InvariantViolationError):
        _decision(
            outcome=EvidenceAdmissibilityDecisionOutcome.RESTRICTED,
            reason=EvidenceAdmissibilityReason.POLICY_OR_VERIFIABILITY_RESTRICTED,
            valid_until=FIXED_TIME + timedelta(hours=1),
        )
    with pytest.raises(InvariantViolationError):
        _decision(valid_until=FIXED_TIME)
    second = _decision(sequence=2, predecessor=EvidenceAdmissibilityDecisionId.new())
    with pytest.raises(EvidenceAdmissibilityHistoryError):
        EvidenceAdmissibilityHistory(decisions=(first, second))


def test_closed_record_and_history_validation_edges_fail_closed() -> None:
    first = _decision()
    with pytest.raises(InvariantViolationError):
        replace(first, id=cast(EvidenceAdmissibilityDecisionId, EvidenceId.new()))
    with pytest.raises(InvariantViolationError):
        replace(first, evidence_version=0)
    with pytest.raises(InvariantViolationError):
        replace(first, decision_sequence=2)
    with pytest.raises(InvariantViolationError):
        replace(first, evidence_digest="A" * 64)
    with pytest.raises(InvariantViolationError):
        replace(first, policy_id="lowercase-not-allowed")
    with pytest.raises(InvariantViolationError):
        replace(
            first,
            outcome=EvidenceAdmissibilityDecisionOutcome.REJECTED,
        )
    with pytest.raises(InvariantViolationError):
        replace(
            first,
            purpose=cast(EvidenceAdmissibilityPurpose, "INTERNAL_FACTUAL_EVIDENCE_USE"),
        )
    with pytest.raises(InvariantViolationError):
        replace(first, schema_version=2)
    with pytest.raises(EvidenceAdmissibilityHistoryError):
        EvidenceAdmissibilityHistory(decisions=())
    history = EvidenceAdmissibilityHistory(decisions=(first,))
    with pytest.raises(EvidenceAdmissibilityHistoryError):
        history.through(EvidenceAdmissibilityDecisionId.new())
    with pytest.raises(EvidenceAdmissibilityHistoryError):
        project_effective_evidence_admissibility(
            evidence_history=synthetic_history(),
            decision_histories=(history, history),
            as_of=FIXED_TIME,
        )


def test_history_rejects_policy_drift_and_regressive_timestamp() -> None:
    first = _decision()
    drift = _decision(
        sequence=2,
        predecessor=first.id,
        policy_id="F5_3_OTHER_POLICY_V1",
    )
    with pytest.raises(EvidenceAdmissibilityHistoryError):
        EvidenceAdmissibilityHistory(decisions=(first, drift))
    regressive = _decision(
        sequence=2,
        predecessor=first.id,
        decided_at=FIXED_TIME - timedelta(microseconds=1),
    )
    with pytest.raises(EvidenceAdmissibilityHistoryError):
        EvidenceAdmissibilityHistory(decisions=(first, regressive))
