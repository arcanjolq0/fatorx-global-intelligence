"""Controlled Evidence anchors, manifest integrity, and conservative policy tests."""

from dataclasses import replace
from hashlib import sha256

import pytest

from intelligence.application.claim_evidence_policy import (
    CLAIM_EVIDENCE_POLICY_ID,
    CLAIM_EVIDENCE_POLICY_VERSION,
    CONTROLLED_CORPUS_MANIFEST_ID,
    CONTROLLED_CORPUS_MANIFEST_VERSION,
    F5_2_CONTROLLED_CORPUS_MANIFEST_V1,
    F5_2_CONTROLLED_CORPUS_V1,
    ClaimEvidenceEligibilityPolicyV1,
    ClaimEvidencePolicyError,
    ControlledCorpusManifestV1,
    ControlledEvidenceAnchorV1,
    build_manifest,
    locator_digest,
    manifest_digest,
)
from intelligence.claims.models import (
    ClaimEvidenceUseDecision,
    ClaimEvidenceUseOutcome,
    ClaimEvidenceUseReason,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.evidence.models import (
    ArtifactOriginType,
    ArtifactStorageMode,
    EvidenceDisplayMode,
    EvidenceHistory,
    EvidenceKind,
    EvidenceLocatorType,
    RetentionMode,
)
from tests.claims.synthetic_fixtures import (
    COMPANY_ID,
    DECISION_ID,
    FIXED_TIME,
    INVESTIGATION_ID,
    USER_ID,
    WORKSPACE_ID,
    artifact_hash,
    content_hash,
    synthetic_history,
    synthetic_locator,
    synthetic_locator_digest,
)


def _evaluate(history: EvidenceHistory) -> ClaimEvidenceUseDecision:
    return F5_2_CONTROLLED_CORPUS_V1.evaluate(
        history=history,
        expected_evidence_id=history.latest.id,
        expected_evidence_digest=history.latest.evidence_digest,
        workspace_id=WORKSPACE_ID,
        investigation_id=INVESTIGATION_ID,
        subject_company_id=COMPANY_ID,
        entity_resolution_decision_id=DECISION_ID,
        requested_by=USER_ID,
        evaluated_at=FIXED_TIME,
    )


def test_fixture_recomputes_every_anchor_and_manifest_digest() -> None:
    anchor = ControlledEvidenceAnchorV1(
        artifact_original_sha256=artifact_hash(),
        evidence_content_sha256=content_hash(),
        evidence_kind=EvidenceKind.STRUCTURED_DATA,
        locator_type=EvidenceLocatorType.JSON_POINTER,
        locator_digest=synthetic_locator_digest(),
    )
    assert F5_2_CONTROLLED_CORPUS_MANIFEST_V1.anchors == (anchor,)
    assert locator_digest(synthetic_locator()) == synthetic_locator_digest()
    assert F5_2_CONTROLLED_CORPUS_MANIFEST_V1.digest == manifest_digest(
        CONTROLLED_CORPUS_MANIFEST_ID,
        CONTROLLED_CORPUS_MANIFEST_VERSION,
        (anchor,),
    )


def test_exact_anchor_is_eligible_and_policy_metadata_is_internal() -> None:
    decision = _evaluate(synthetic_history())
    assert decision.outcome is ClaimEvidenceUseOutcome.ELIGIBLE
    assert decision.reason_code is ClaimEvidenceUseReason.CONTROLLED_EVIDENCE_ELIGIBLE
    assert decision.policy_id == CLAIM_EVIDENCE_POLICY_ID
    assert decision.policy_version == CLAIM_EVIDENCE_POLICY_VERSION
    assert decision.controlled_corpus_manifest_digest == F5_2_CONTROLLED_CORPUS_MANIFEST_V1.digest


@pytest.mark.parametrize(
    "history",
    [
        synthetic_history(source_id="TRUST_ME_I_AM_REAL"),
        synthetic_history(origin_type=ArtifactOriginType.MANUAL_REFERENCE),
    ],
)
def test_source_and_origin_labels_cannot_grant_or_remove_trust(history: EvidenceHistory) -> None:
    assert _evaluate(history).outcome is ClaimEvidenceUseOutcome.ELIGIBLE


@pytest.mark.parametrize(
    ("history", "reason"),
    [
        (
            synthetic_history(located=b"Synthetic Beta Registry Test Ltd."),
            ClaimEvidenceUseReason.CONTROLLED_EVIDENCE_NOT_PROVEN,
        ),
        (
            synthetic_history(pointer="/company/registration_status"),
            ClaimEvidenceUseReason.CONTROLLED_EVIDENCE_NOT_PROVEN,
        ),
        (
            synthetic_history(kind=EvidenceKind.TEXT),
            ClaimEvidenceUseReason.CONTROLLED_EVIDENCE_NOT_PROVEN,
        ),
        (
            synthetic_history(original=b'{"company":{"legal_name":"Unknown"}}'),
            ClaimEvidenceUseReason.CONTROLLED_CORPUS_NOT_PROVEN,
        ),
    ],
)
def test_anchor_mismatch_is_restricted(
    history: EvidenceHistory, reason: ClaimEvidenceUseReason
) -> None:
    decision = _evaluate(history)
    assert decision.outcome is ClaimEvidenceUseOutcome.RESTRICTED
    assert decision.reason_code is reason


@pytest.mark.parametrize(
    ("history", "reason"),
    [
        (
            synthetic_history(storage_mode=ArtifactStorageMode.OBJECT),
            ClaimEvidenceUseReason.STORAGE_MODE_RESTRICTED,
        ),
        (
            synthetic_history(retention_mode=RetentionMode.UNTIL),
            ClaimEvidenceUseReason.RETENTION_MODE_RESTRICTED,
        ),
        (
            synthetic_history(display_mode=EvidenceDisplayMode.REDACTED),
            ClaimEvidenceUseReason.DISPLAY_MODE_RESTRICTED,
        ),
        (
            synthetic_history(retain_content=False),
            ClaimEvidenceUseReason.CONTENT_ORIGINAL_REQUIRED,
        ),
    ],
)
def test_conservative_modes_are_restricted(
    history: EvidenceHistory, reason: ClaimEvidenceUseReason
) -> None:
    decision = _evaluate(history)
    assert decision.outcome is ClaimEvidenceUseOutcome.RESTRICTED
    assert decision.reason_code is reason


def test_locator_digest_changes_with_every_semantic_locator_change() -> None:
    assert locator_digest(synthetic_locator()) != locator_digest(
        synthetic_locator("/company/registration_status")
    )


def test_duplicate_and_case_normalized_duplicate_manifest_fail() -> None:
    anchor = F5_2_CONTROLLED_CORPUS_MANIFEST_V1.anchors[0]
    with pytest.raises(InvariantViolationError, match="duplicate"):
        build_manifest((anchor, anchor))
    upper = replace(
        anchor,
        artifact_original_sha256=anchor.artifact_original_sha256.upper(),
        evidence_content_sha256=anchor.evidence_content_sha256.upper(),
        locator_digest=anchor.locator_digest.upper(),
    )
    with pytest.raises(InvariantViolationError, match="duplicate"):
        build_manifest((anchor, upper))


def test_invalid_hash_and_tampered_manifest_digest_fail() -> None:
    anchor = F5_2_CONTROLLED_CORPUS_MANIFEST_V1.anchors[0]
    with pytest.raises(InvariantViolationError, match="hash"):
        replace(anchor, locator_digest="not-a-digest")
    manifest = ControlledCorpusManifestV1(
        manifest_id=CONTROLLED_CORPUS_MANIFEST_ID,
        version=CONTROLLED_CORPUS_MANIFEST_VERSION,
        anchors=(anchor,),
    )
    object.__setattr__(manifest, "digest", sha256(b"tampered").hexdigest())
    with pytest.raises(InvariantViolationError, match="digest"):
        ClaimEvidenceEligibilityPolicyV1(manifest)


def test_content_original_integrity_failure_is_not_a_normal_outcome() -> None:
    history = synthetic_history()
    object.__setattr__(history.latest, "content_original", "tampered after reconstitution")

    with pytest.raises(ClaimEvidencePolicyError, match="integrity"):
        _evaluate(history)
