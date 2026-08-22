"""Deterministic F5.3 trust root and global Evidence admissibility policy."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256

from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import EvidenceId, UserId
from intelligence.domain.time import normalize_utc
from intelligence.evidence.admissibility import (
    EvidenceAdmissibilityDecisionOutcome,
    EvidenceAdmissibilityPurpose,
    EvidenceAdmissibilityReason,
    EvidenceAdmissibilityRequestedAction,
    EvidenceAdmissionBasis,
)
from intelligence.evidence.models import (
    ArtifactStorageMode,
    EvidenceDisplayMode,
    EvidenceHistory,
    EvidenceKind,
    EvidenceLocator,
    EvidenceLocatorType,
    RetentionMode,
    locator_to_canonical_json,
)

CONTROLLED_TEST_EVIDENCE_MANIFEST_ID = "F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1"
CONTROLLED_TEST_EVIDENCE_MANIFEST_VERSION = 1
EVIDENCE_ADMISSIBILITY_POLICY_ID = "F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1"
EVIDENCE_ADMISSIBILITY_POLICY_VERSION = 1
_SHA256 = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


class EvidenceAdmissibilityPolicyError(Exception):
    """The requested decision cannot safely be produced by policy V1."""


class EvidenceSelfApprovalPolicyError(EvidenceAdmissibilityPolicyError):
    """The exact Evidence version creator attempted a positive approval."""


@dataclass(frozen=True, slots=True, order=True)
class ControlledTestEvidenceAnchorV1:
    artifact_original_sha256: str
    evidence_content_sha256: str
    evidence_kind: EvidenceKind
    locator_type: EvidenceLocatorType
    locator_digest: str

    def __post_init__(self) -> None:
        for name in (
            "artifact_original_sha256",
            "evidence_content_sha256",
            "locator_digest",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise InvariantViolationError("Controlled-test anchor hash is invalid.")
        if not isinstance(self.evidence_kind, EvidenceKind) or not isinstance(
            self.locator_type, EvidenceLocatorType
        ):
            raise InvariantViolationError("Controlled-test anchor vocabulary is invalid.")

    def canonical_value(self) -> dict[str, object]:
        return {
            "artifact_original_sha256": self.artifact_original_sha256,
            "evidence_content_sha256": self.evidence_content_sha256,
            "evidence_kind": self.evidence_kind.value,
            "locator_digest": self.locator_digest,
            "locator_type": self.locator_type.value,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_value())


@dataclass(frozen=True, slots=True)
class ControlledTestEvidenceManifestV1:
    manifest_id: str
    version: int
    anchors: tuple[ControlledTestEvidenceAnchorV1, ...]
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        if self.manifest_id != CONTROLLED_TEST_EVIDENCE_MANIFEST_ID or (
            self.version != CONTROLLED_TEST_EVIDENCE_MANIFEST_VERSION
        ):
            raise InvariantViolationError("Controlled-test manifest identity is unsupported.")
        if not self.anchors or not all(
            isinstance(item, ControlledTestEvidenceAnchorV1) for item in self.anchors
        ):
            raise InvariantViolationError("Controlled-test manifest anchors are invalid.")
        canonical = tuple(sorted(self.anchors, key=ControlledTestEvidenceAnchorV1.canonical_json))
        if len(set(canonical)) != len(canonical):
            raise InvariantViolationError("Controlled-test manifest contains duplicates.")
        if canonical != self.anchors:
            raise InvariantViolationError("Controlled-test manifest is not canonical.")
        object.__setattr__(
            self, "digest", manifest_digest(self.manifest_id, self.version, canonical)
        )


def build_manifest(
    anchors: tuple[ControlledTestEvidenceAnchorV1, ...],
) -> ControlledTestEvidenceManifestV1:
    canonical = tuple(sorted(anchors, key=ControlledTestEvidenceAnchorV1.canonical_json))
    if len(set(canonical)) != len(canonical):
        raise InvariantViolationError("Controlled-test manifest contains duplicates.")
    return ControlledTestEvidenceManifestV1(
        manifest_id=CONTROLLED_TEST_EVIDENCE_MANIFEST_ID,
        version=CONTROLLED_TEST_EVIDENCE_MANIFEST_VERSION,
        anchors=canonical,
    )


def manifest_digest(
    manifest_id: str,
    version: int,
    anchors: tuple[ControlledTestEvidenceAnchorV1, ...],
) -> str:
    return sha256(
        _canonical_json(
            {
                "anchors": [item.canonical_value() for item in anchors],
                "manifest_id": manifest_id,
                "manifest_version": version,
            }
        ).encode()
    ).hexdigest()


def locator_digest(locator: EvidenceLocator) -> str:
    return sha256(locator_to_canonical_json(locator).encode()).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceAdmissibilityPolicyEvaluation:
    outcome: EvidenceAdmissibilityDecisionOutcome
    reason_code: EvidenceAdmissibilityReason
    policy_id: str
    policy_version: int
    purpose: EvidenceAdmissibilityPurpose
    admission_basis: EvidenceAdmissionBasis
    controlled_trust_root_id: str
    controlled_trust_root_version: int
    controlled_trust_root_digest: str
    valid_until: datetime | None


class EvidenceAdmissibilityPolicyV1:
    def __init__(self, manifest: ControlledTestEvidenceManifestV1) -> None:
        if not isinstance(manifest, ControlledTestEvidenceManifestV1):
            raise TypeError("manifest must be a ControlledTestEvidenceManifestV1")
        validated = ControlledTestEvidenceManifestV1(
            manifest_id=manifest.manifest_id,
            version=manifest.version,
            anchors=manifest.anchors,
        )
        if manifest.digest != validated.digest:
            raise InvariantViolationError("Controlled-test manifest digest is invalid.")
        self._manifest = manifest

    @property
    def manifest(self) -> ControlledTestEvidenceManifestV1:
        return self._manifest

    def evaluate(
        self,
        *,
        history: EvidenceHistory,
        expected_evidence_id: EvidenceId,
        expected_evidence_digest: str,
        requested_action: EvidenceAdmissibilityRequestedAction,
        reason_code: EvidenceAdmissibilityReason,
        requested_valid_until: datetime | None,
        decided_by: UserId,
        decided_at: datetime,
    ) -> EvidenceAdmissibilityPolicyEvaluation:
        instant = normalize_utc(decided_at)
        evidence = history.latest
        if (
            evidence.id != expected_evidence_id
            or evidence.evidence_digest != expected_evidence_digest
        ):
            raise EvidenceAdmissibilityPolicyError("Evidence is stale or does not match exactly.")
        if history.is_revoked:
            raise EvidenceAdmissibilityPolicyError("Revoked Evidence cannot be decided.")
        if instant < evidence.created_at:
            raise EvidenceAdmissibilityPolicyError("Decision precedes Evidence creation.")
        if requested_valid_until is not None:
            requested_valid_until = normalize_utc(requested_valid_until)
        expected_reason = {
            EvidenceAdmissibilityRequestedAction.ADMIT: (
                EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED
            ),
            EvidenceAdmissibilityRequestedAction.RESTRICT: (
                EvidenceAdmissibilityReason.POLICY_OR_VERIFIABILITY_RESTRICTED
            ),
            EvidenceAdmissibilityRequestedAction.REJECT: (
                EvidenceAdmissibilityReason.CONTENT_OR_CONTEXT_REJECTED
            ),
        }[requested_action]
        if reason_code is not expected_reason:
            raise EvidenceAdmissibilityPolicyError("Action and reason are incompatible.")
        if requested_action is not EvidenceAdmissibilityRequestedAction.ADMIT:
            if requested_valid_until is not None:
                raise EvidenceAdmissibilityPolicyError("Negative decisions cannot expire.")
            outcome = (
                EvidenceAdmissibilityDecisionOutcome.RESTRICTED
                if requested_action is EvidenceAdmissibilityRequestedAction.RESTRICT
                else EvidenceAdmissibilityDecisionOutcome.REJECTED
            )
            return self._evaluation(outcome, reason_code, None)
        if decided_by == evidence.created_by:
            raise EvidenceSelfApprovalPolicyError("Evidence creator cannot self-approve ADMIT.")
        if requested_valid_until is not None and requested_valid_until <= instant:
            raise EvidenceAdmissibilityPolicyError("Expiration must follow decision time.")
        artifact_matches = tuple(
            item
            for item in self._manifest.anchors
            if item.artifact_original_sha256 == history.artifact.original_content_sha256
        )
        actual = ControlledTestEvidenceAnchorV1(
            artifact_original_sha256=history.artifact.original_content_sha256,
            evidence_content_sha256=evidence.content_sha256,
            evidence_kind=evidence.kind,
            locator_type=evidence.locator.type,
            locator_digest=locator_digest(evidence.locator),
        )
        if actual not in artifact_matches:
            raise EvidenceAdmissibilityPolicyError("Exact F5.3 trust-root match is absent.")
        artifact = history.artifact
        if artifact.storage_mode is not ArtifactStorageMode.EXCERPT_ONLY:
            raise EvidenceAdmissibilityPolicyError("Storage policy blocks ADMIT.")
        if artifact.retention_mode is not RetentionMode.INDEFINITE:
            raise EvidenceAdmissibilityPolicyError("Retention policy blocks ADMIT.")
        if artifact.display_mode is not EvidenceDisplayMode.FULL:
            raise EvidenceAdmissibilityPolicyError("Display policy blocks ADMIT.")
        if (
            evidence.content_original is None
            or sha256(evidence.content_original.encode()).hexdigest() != evidence.content_sha256
        ):
            raise EvidenceAdmissibilityPolicyError("Retained Evidence content is unavailable.")
        return self._evaluation(
            EvidenceAdmissibilityDecisionOutcome.ADMISSIBLE,
            reason_code,
            requested_valid_until,
        )

    def _evaluation(
        self,
        outcome: EvidenceAdmissibilityDecisionOutcome,
        reason: EvidenceAdmissibilityReason,
        valid_until: datetime | None,
    ) -> EvidenceAdmissibilityPolicyEvaluation:
        return EvidenceAdmissibilityPolicyEvaluation(
            outcome=outcome,
            reason_code=reason,
            policy_id=EVIDENCE_ADMISSIBILITY_POLICY_ID,
            policy_version=EVIDENCE_ADMISSIBILITY_POLICY_VERSION,
            purpose=EvidenceAdmissibilityPurpose.INTERNAL_FACTUAL_EVIDENCE_USE,
            admission_basis=EvidenceAdmissionBasis.CONTROLLED_TEST_EVIDENCE,
            controlled_trust_root_id=self._manifest.manifest_id,
            controlled_trust_root_version=self._manifest.version,
            controlled_trust_root_digest=self._manifest.digest,
            valid_until=valid_until,
        )


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_SYNTHETIC_LEGAL_NAME_ANCHOR = ControlledTestEvidenceAnchorV1(
    artifact_original_sha256="ff92aca078d20304c02760d2422e1ad40fade2bab5c6fe0a1f63f688eea1028f",
    evidence_content_sha256="f6b8b96c84ceab6097d05a544ca484c191b28e1ad5a14297aeff8990ea6e4065",
    evidence_kind=EvidenceKind.STRUCTURED_DATA,
    locator_type=EvidenceLocatorType.JSON_POINTER,
    locator_digest="49e82c4c831b3972bde43fb80868aea23ec1d2eed771d9265b9d3f6759dee9ad",
)

F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1 = build_manifest((_SYNTHETIC_LEGAL_NAME_ANCHOR,))
F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1 = EvidenceAdmissibilityPolicyV1(
    F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1
)


__all__ = [
    "CONTROLLED_TEST_EVIDENCE_MANIFEST_ID",
    "CONTROLLED_TEST_EVIDENCE_MANIFEST_VERSION",
    "EVIDENCE_ADMISSIBILITY_POLICY_ID",
    "EVIDENCE_ADMISSIBILITY_POLICY_VERSION",
    "F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1",
    "F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1",
    "ControlledTestEvidenceAnchorV1",
    "ControlledTestEvidenceManifestV1",
    "EvidenceAdmissibilityPolicyError",
    "EvidenceAdmissibilityPolicyEvaluation",
    "EvidenceAdmissibilityPolicyV1",
    "EvidenceSelfApprovalPolicyError",
    "build_manifest",
    "locator_digest",
    "manifest_digest",
]
