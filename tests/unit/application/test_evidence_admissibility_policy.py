"""F5.3 trust-root integrity, policy gates, and self-approval tests."""

from datetime import timedelta
from hashlib import sha256

import pytest

from intelligence.application.claim_evidence_policy import F5_2_CONTROLLED_CORPUS_MANIFEST_V1
from intelligence.application.evidence_admissibility_policy import (
    CONTROLLED_TEST_EVIDENCE_MANIFEST_ID,
    F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1,
    F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1,
    ControlledTestEvidenceAnchorV1,
    ControlledTestEvidenceManifestV1,
    EvidenceAdmissibilityPolicyError,
    EvidenceAdmissibilityPolicyEvaluation,
    EvidenceAdmissibilityPolicyV1,
    build_manifest,
    locator_digest,
    manifest_digest,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    EvidenceAdmissibilityCommandId,
    EvidenceAdmissibilityDecisionId,
    EvidenceId,
    UserId,
)
from intelligence.evidence.admissibility import (
    EvidenceAdmissibilityDecision,
    EvidenceAdmissibilityDecisionOutcome,
    EvidenceAdmissibilityPurpose,
    EvidenceAdmissibilityReason,
    EvidenceAdmissibilityRequestedAction,
    EvidenceAdmissionBasis,
    build_evidence_admissibility_decision,
)
from intelligence.evidence.models import (
    ArtifactOriginType,
    ArtifactStorageMode,
    EvidenceDisplayMode,
    EvidenceHistory,
    EvidenceKind,
    RetentionMode,
)
from tests.claims.synthetic_fixtures import (
    FIXED_TIME,
    SYNTHETIC_ARTIFACT_BYTES,
    SYNTHETIC_LOCATED_BYTES,
    USER_ID,
    artifact_hash,
    content_hash,
    synthetic_history,
    synthetic_locator,
)

DECIDER = UserId.from_value("40000000-0000-4000-8000-000000000001")


def _persisted_decision(
    history: EvidenceHistory,
    *,
    actor: UserId = DECIDER,
    outcome: EvidenceAdmissibilityDecisionOutcome = (
        EvidenceAdmissibilityDecisionOutcome.ADMISSIBLE
    ),
) -> EvidenceAdmissibilityDecision:
    reason = {
        EvidenceAdmissibilityDecisionOutcome.ADMISSIBLE: (
            EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED
        ),
        EvidenceAdmissibilityDecisionOutcome.RESTRICTED: (
            EvidenceAdmissibilityReason.POLICY_OR_VERIFIABILITY_RESTRICTED
        ),
        EvidenceAdmissibilityDecisionOutcome.REJECTED: (
            EvidenceAdmissibilityReason.CONTENT_OR_CONTEXT_REJECTED
        ),
    }[outcome]
    return build_evidence_admissibility_decision(
        decision_id=EvidenceAdmissibilityDecisionId.new(),
        evidence=history.latest,
        decision_sequence=1,
        supersedes_decision_id=None,
        outcome=outcome,
        reason_code=reason,
        policy_id="F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1",
        policy_version=1,
        purpose=EvidenceAdmissibilityPurpose.INTERNAL_FACTUAL_EVIDENCE_USE,
        admission_basis=EvidenceAdmissionBasis.CONTROLLED_TEST_EVIDENCE,
        controlled_trust_root_id=F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.manifest_id,
        controlled_trust_root_version=F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.version,
        controlled_trust_root_digest=F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.digest,
        valid_until=None,
        command_id=EvidenceAdmissibilityCommandId.new(),
        command_digest=sha256(b"persisted-decision-command").hexdigest(),
        decided_by=actor,
        decided_at=FIXED_TIME,
    )


def _evaluate(
    *,
    history: EvidenceHistory | None = None,
    action: EvidenceAdmissibilityRequestedAction = EvidenceAdmissibilityRequestedAction.ADMIT,
    actor: UserId = DECIDER,
) -> EvidenceAdmissibilityPolicyEvaluation:
    chosen = history or synthetic_history()
    reason = {
        EvidenceAdmissibilityRequestedAction.ADMIT: (
            EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED
        ),
        EvidenceAdmissibilityRequestedAction.RESTRICT: (
            EvidenceAdmissibilityReason.POLICY_OR_VERIFIABILITY_RESTRICTED
        ),
        EvidenceAdmissibilityRequestedAction.REJECT: (
            EvidenceAdmissibilityReason.CONTENT_OR_CONTEXT_REJECTED
        ),
    }[action]
    return F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1.evaluate(
        history=chosen,
        expected_evidence_id=chosen.latest.id,
        expected_evidence_digest=chosen.latest.evidence_digest,
        requested_action=action,
        reason_code=reason,
        requested_valid_until=None,
        decided_by=actor,
        decided_at=FIXED_TIME,
    )


def test_fixture_and_manifest_are_independently_recomputable() -> None:
    anchor = ControlledTestEvidenceAnchorV1(
        artifact_original_sha256=sha256(SYNTHETIC_ARTIFACT_BYTES).hexdigest(),
        evidence_content_sha256=sha256(SYNTHETIC_LOCATED_BYTES).hexdigest(),
        evidence_kind=EvidenceKind.STRUCTURED_DATA,
        locator_type=synthetic_locator().type,
        locator_digest=sha256(
            (
                '{"pointer":"/company/legal_name","response_sha256":"'
                + artifact_hash()
                + '","type":"JSON_POINTER"}'
            ).encode()
        ).hexdigest(),
    )
    rebuilt = build_manifest((anchor,))
    assert artifact_hash() == anchor.artifact_original_sha256
    assert content_hash() == anchor.evidence_content_sha256
    assert locator_digest(synthetic_locator()) == anchor.locator_digest
    assert rebuilt == F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1
    assert rebuilt.digest == manifest_digest(rebuilt.manifest_id, rebuilt.version, (anchor,))
    assert rebuilt.manifest_id == CONTROLLED_TEST_EVIDENCE_MANIFEST_ID
    assert rebuilt.digest != F5_2_CONTROLLED_CORPUS_MANIFEST_V1.digest


def test_exact_anchor_allows_admit_and_self_approval_is_denied() -> None:
    evaluation = _evaluate()
    assert evaluation.outcome is EvidenceAdmissibilityDecisionOutcome.ADMISSIBLE
    assert evaluation.controlled_trust_root_digest == (
        F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.digest
    )
    with pytest.raises(EvidenceAdmissibilityPolicyError):
        _evaluate(actor=USER_ID)


@pytest.mark.parametrize(
    ("history", "actor"),
    [
        (synthetic_history(), USER_ID),
        (synthetic_history(located=b"Different controlled text"), DECIDER),
        (synthetic_history(storage_mode=ArtifactStorageMode.OBJECT), DECIDER),
    ],
)
def test_persisted_admissible_semantic_forgery_fails_closed(
    history: EvidenceHistory,
    actor: UserId,
) -> None:
    decision = _persisted_decision(history, actor=actor)
    with pytest.raises(EvidenceAdmissibilityPolicyError):
        F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1.validate_persisted_decision(
            history=history,
            decision=decision,
        )


@pytest.mark.parametrize(
    "outcome",
    [
        EvidenceAdmissibilityDecisionOutcome.RESTRICTED,
        EvidenceAdmissibilityDecisionOutcome.REJECTED,
    ],
)
def test_persisted_negative_decisions_do_not_require_positive_anchor_match(
    outcome: EvidenceAdmissibilityDecisionOutcome,
) -> None:
    history = synthetic_history(located=b"Not present in the positive trust root")
    F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1.validate_persisted_decision(
        history=history,
        decision=_persisted_decision(history, actor=USER_ID, outcome=outcome),
    )


@pytest.mark.parametrize(
    "history",
    [
        synthetic_history(located=b"Different controlled text"),
        synthetic_history(kind=EvidenceKind.TEXT),
        synthetic_history(pointer="/company/registration_status"),
        synthetic_history(storage_mode=ArtifactStorageMode.OBJECT),
        synthetic_history(retention_mode=RetentionMode.UNTIL),
        synthetic_history(display_mode=EvidenceDisplayMode.REDACTED),
        synthetic_history(retain_content=False),
    ],
)
def test_artifact_only_or_partial_policy_match_never_admits(
    history: EvidenceHistory,
) -> None:
    with pytest.raises(EvidenceAdmissibilityPolicyError):
        _evaluate(history=history)


def test_labels_source_and_origin_do_not_grant_or_remove_trust() -> None:
    changed = synthetic_history(
        source_id="looks.real.but.is.untrusted",
        origin_type=ArtifactOriginType.MANUAL_REFERENCE,
    )
    assert _evaluate(history=changed).outcome is EvidenceAdmissibilityDecisionOutcome.ADMISSIBLE


@pytest.mark.parametrize(
    "action",
    [EvidenceAdmissibilityRequestedAction.RESTRICT, EvidenceAdmissibilityRequestedAction.REJECT],
)
def test_negative_decisions_allow_creator_and_always_snapshot_trust_root(
    action: EvidenceAdmissibilityRequestedAction,
) -> None:
    evaluation = _evaluate(action=action, actor=USER_ID)
    assert evaluation.controlled_trust_root_id == CONTROLLED_TEST_EVIDENCE_MANIFEST_ID
    assert evaluation.controlled_trust_root_digest == (
        F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.digest
    )


def test_manifest_duplicates_invalid_hashes_tamper_and_f52_laundering_fail() -> None:
    anchor = F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.anchors[0]
    with pytest.raises(InvariantViolationError):
        build_manifest((anchor, anchor))
    with pytest.raises(InvariantViolationError):
        ControlledTestEvidenceAnchorV1(
            artifact_original_sha256="A" * 64,
            evidence_content_sha256=anchor.evidence_content_sha256,
            evidence_kind=anchor.evidence_kind,
            locator_type=anchor.locator_type,
            locator_digest=anchor.locator_digest,
        )
    manifest = ControlledTestEvidenceManifestV1(
        manifest_id=CONTROLLED_TEST_EVIDENCE_MANIFEST_ID,
        version=1,
        anchors=(anchor,),
    )
    object.__setattr__(manifest, "digest", "0" * 64)
    with pytest.raises(InvariantViolationError):
        EvidenceAdmissibilityPolicyV1(manifest)
    with pytest.raises(TypeError):
        EvidenceAdmissibilityPolicyV1(F5_2_CONTROLLED_CORPUS_MANIFEST_V1)  # type: ignore[arg-type]


def test_manifest_empty_and_noncanonical_order_fail_closed() -> None:
    first = F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.anchors[0]
    second = ControlledTestEvidenceAnchorV1(
        artifact_original_sha256="0" * 64,
        evidence_content_sha256=first.evidence_content_sha256,
        evidence_kind=first.evidence_kind,
        locator_type=first.locator_type,
        locator_digest=first.locator_digest,
    )
    with pytest.raises(InvariantViolationError):
        ControlledTestEvidenceManifestV1(
            manifest_id=CONTROLLED_TEST_EVIDENCE_MANIFEST_ID,
            version=1,
            anchors=(),
        )
    ordered = tuple(sorted((first, second), key=ControlledTestEvidenceAnchorV1.canonical_json))
    with pytest.raises(InvariantViolationError):
        ControlledTestEvidenceManifestV1(
            manifest_id=CONTROLLED_TEST_EVIDENCE_MANIFEST_ID,
            version=1,
            anchors=tuple(reversed(ordered)),
        )


def test_stale_target_action_reason_and_expiration_are_rejected_not_downgraded() -> None:
    history = synthetic_history()
    with pytest.raises(EvidenceAdmissibilityPolicyError):
        F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1.evaluate(
            history=history,
            expected_evidence_id=EvidenceId.new(),
            expected_evidence_digest=history.latest.evidence_digest,
            requested_action=EvidenceAdmissibilityRequestedAction.ADMIT,
            reason_code=EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED,
            requested_valid_until=None,
            decided_by=DECIDER,
            decided_at=FIXED_TIME,
        )
    with pytest.raises(EvidenceAdmissibilityPolicyError):
        F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1.evaluate(
            history=history,
            expected_evidence_id=history.latest.id,
            expected_evidence_digest=history.latest.evidence_digest,
            requested_action=EvidenceAdmissibilityRequestedAction.RESTRICT,
            reason_code=EvidenceAdmissibilityReason.CONTENT_OR_CONTEXT_REJECTED,
            requested_valid_until=None,
            decided_by=USER_ID,
            decided_at=FIXED_TIME,
        )
    with pytest.raises(EvidenceAdmissibilityPolicyError):
        F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1.evaluate(
            history=history,
            expected_evidence_id=history.latest.id,
            expected_evidence_digest=history.latest.evidence_digest,
            requested_action=EvidenceAdmissibilityRequestedAction.ADMIT,
            reason_code=EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED,
            requested_valid_until=FIXED_TIME,
            decided_by=DECIDER,
            decided_at=FIXED_TIME,
        )


def test_policy_has_no_hidden_freshness_and_valid_until_is_explicit() -> None:
    history = synthetic_history()
    later = FIXED_TIME + timedelta(days=3650)
    result = F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1.evaluate(
        history=history,
        expected_evidence_id=history.latest.id,
        expected_evidence_digest=history.latest.evidence_digest,
        requested_action=EvidenceAdmissibilityRequestedAction.ADMIT,
        reason_code=EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED,
        requested_valid_until=later + timedelta(days=1),
        decided_by=DECIDER,
        decided_at=later,
    )
    assert result.valid_until == later + timedelta(days=1)
