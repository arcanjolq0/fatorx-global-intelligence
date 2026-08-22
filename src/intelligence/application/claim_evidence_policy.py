"""Deterministic F5.2 controlled-corpus manifest and contextual-use policy."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from hashlib import sha256

from intelligence.claims.models import (
    ClaimEvidencePurpose,
    ClaimEvidenceUseDecision,
    ClaimEvidenceUseOutcome,
    ClaimEvidenceUseReason,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    CompanyId,
    EntityResolutionDecisionId,
    EvidenceId,
    InvestigationId,
    UserId,
    WorkspaceId,
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

CONTROLLED_CORPUS_MANIFEST_ID = "F5_2_CONTROLLED_CORPUS_MANIFEST_V1"
CONTROLLED_CORPUS_MANIFEST_VERSION = 1
CLAIM_EVIDENCE_POLICY_ID = "F5_2_CONTROLLED_CORPUS_V1"
CLAIM_EVIDENCE_POLICY_VERSION = 1
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


class ClaimEvidencePolicyError(Exception):
    """Evidence state or scope prevents a safe contextual-use decision."""


@dataclass(frozen=True, slots=True, order=True)
class ControlledEvidenceAnchorV1:
    """Runtime-ID-free identity for one exact synthetic Evidence extraction."""

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
            if not isinstance(value, str):
                raise InvariantViolationError("Controlled Evidence anchor hash must be text.")
            normalized = value.lower()
            if _SHA256_PATTERN.fullmatch(normalized) is None:
                raise InvariantViolationError("Controlled Evidence anchor hash is invalid.")
            object.__setattr__(self, name, normalized)
        if not isinstance(self.evidence_kind, EvidenceKind) or not isinstance(
            self.locator_type, EvidenceLocatorType
        ):
            raise InvariantViolationError("Controlled Evidence anchor vocabulary is invalid.")

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
class ControlledCorpusManifestV1:
    manifest_id: str
    version: int
    anchors: tuple[ControlledEvidenceAnchorV1, ...]
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        if self.manifest_id != CONTROLLED_CORPUS_MANIFEST_ID:
            raise InvariantViolationError("Controlled corpus manifest ID is unsupported.")
        if self.version != CONTROLLED_CORPUS_MANIFEST_VERSION:
            raise InvariantViolationError("Controlled corpus manifest version is unsupported.")
        if not self.anchors or not all(
            isinstance(anchor, ControlledEvidenceAnchorV1) for anchor in self.anchors
        ):
            raise InvariantViolationError("Controlled corpus manifest anchors are invalid.")
        canonical = tuple(sorted(self.anchors, key=ControlledEvidenceAnchorV1.canonical_json))
        if len(set(canonical)) != len(canonical):
            raise InvariantViolationError("Controlled corpus manifest contains duplicate anchors.")
        if self.anchors != canonical:
            raise InvariantViolationError("Controlled corpus manifest anchors are not canonical.")
        object.__setattr__(
            self,
            "digest",
            manifest_digest(self.manifest_id, self.version, self.anchors),
        )


def build_manifest(
    anchors: tuple[ControlledEvidenceAnchorV1, ...],
) -> ControlledCorpusManifestV1:
    canonical = tuple(sorted(anchors, key=ControlledEvidenceAnchorV1.canonical_json))
    if len(set(canonical)) != len(canonical):
        raise InvariantViolationError("Controlled corpus manifest contains duplicate anchors.")
    return ControlledCorpusManifestV1(
        manifest_id=CONTROLLED_CORPUS_MANIFEST_ID,
        version=CONTROLLED_CORPUS_MANIFEST_VERSION,
        anchors=canonical,
    )


def manifest_digest(
    manifest_id: str,
    version: int,
    anchors: tuple[ControlledEvidenceAnchorV1, ...],
) -> str:
    value = {
        "anchors": [anchor.canonical_value() for anchor in anchors],
        "manifest_id": manifest_id,
        "manifest_version": version,
    }
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def locator_digest(locator: EvidenceLocator) -> str:
    """Hash the sole canonical locator representation owned by F5.1."""

    return sha256(locator_to_canonical_json(locator).encode("utf-8")).hexdigest()


class ClaimEvidenceEligibilityPolicyV1:
    """Derive contextual eligibility without accepting actor-controlled outcomes."""

    def __init__(self, manifest: ControlledCorpusManifestV1) -> None:
        if not isinstance(manifest, ControlledCorpusManifestV1):
            raise TypeError("manifest must be a ControlledCorpusManifestV1")
        validated = ControlledCorpusManifestV1(
            manifest_id=manifest.manifest_id,
            version=manifest.version,
            anchors=manifest.anchors,
        )
        if manifest.digest != validated.digest:
            raise InvariantViolationError("Controlled corpus manifest digest is invalid.")
        self._manifest = manifest

    @property
    def manifest(self) -> ControlledCorpusManifestV1:
        return self._manifest

    def evaluate(
        self,
        *,
        history: EvidenceHistory,
        expected_evidence_id: EvidenceId,
        expected_evidence_digest: str,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
        subject_company_id: CompanyId,
        entity_resolution_decision_id: EntityResolutionDecisionId,
        requested_by: UserId,
        evaluated_at: object,
    ) -> ClaimEvidenceUseDecision:
        from datetime import datetime

        if not isinstance(history, EvidenceHistory):
            raise TypeError("history must be an EvidenceHistory")
        if not isinstance(evaluated_at, datetime):
            raise TypeError("evaluated_at must be a datetime")
        evidence = history.latest
        if (
            evidence.id != expected_evidence_id
            or evidence.evidence_digest != expected_evidence_digest
            or evidence.workspace_id != workspace_id
            or evidence.investigation_id != investigation_id
            or evidence.subject_company_id != subject_company_id
            or evidence.entity_resolution_decision_id != entity_resolution_decision_id
            or history.is_revoked
        ):
            raise ClaimEvidencePolicyError("Evidence is stale, revoked, or out of scope.")

        artifact_hash_matches = tuple(
            anchor
            for anchor in self._manifest.anchors
            if anchor.artifact_original_sha256 == history.artifact.original_content_sha256
        )
        if not artifact_hash_matches:
            return self._decision(
                ClaimEvidenceUseOutcome.RESTRICTED,
                ClaimEvidenceUseReason.CONTROLLED_CORPUS_NOT_PROVEN,
                requested_by,
                evaluated_at,
            )
        actual = ControlledEvidenceAnchorV1(
            artifact_original_sha256=history.artifact.original_content_sha256,
            evidence_content_sha256=evidence.content_sha256,
            evidence_kind=evidence.kind,
            locator_type=evidence.locator.type,
            locator_digest=locator_digest(evidence.locator),
        )
        if actual not in artifact_hash_matches:
            return self._decision(
                ClaimEvidenceUseOutcome.RESTRICTED,
                ClaimEvidenceUseReason.CONTROLLED_EVIDENCE_NOT_PROVEN,
                requested_by,
                evaluated_at,
            )
        artifact = history.artifact
        if artifact.storage_mode is not ArtifactStorageMode.EXCERPT_ONLY:
            return self._decision(
                ClaimEvidenceUseOutcome.RESTRICTED,
                ClaimEvidenceUseReason.STORAGE_MODE_RESTRICTED,
                requested_by,
                evaluated_at,
            )
        if artifact.retention_mode is not RetentionMode.INDEFINITE:
            return self._decision(
                ClaimEvidenceUseOutcome.RESTRICTED,
                ClaimEvidenceUseReason.RETENTION_MODE_RESTRICTED,
                requested_by,
                evaluated_at,
            )
        if artifact.display_mode is not EvidenceDisplayMode.FULL:
            return self._decision(
                ClaimEvidenceUseOutcome.RESTRICTED,
                ClaimEvidenceUseReason.DISPLAY_MODE_RESTRICTED,
                requested_by,
                evaluated_at,
            )
        if evidence.content_original is None:
            return self._decision(
                ClaimEvidenceUseOutcome.RESTRICTED,
                ClaimEvidenceUseReason.CONTENT_ORIGINAL_REQUIRED,
                requested_by,
                evaluated_at,
            )
        if sha256(evidence.content_original.encode("utf-8")).hexdigest() != evidence.content_sha256:
            raise ClaimEvidencePolicyError("Evidence retained content failed integrity validation.")
        return self._decision(
            ClaimEvidenceUseOutcome.ELIGIBLE,
            ClaimEvidenceUseReason.CONTROLLED_EVIDENCE_ELIGIBLE,
            requested_by,
            evaluated_at,
        )

    def _decision(
        self,
        outcome: ClaimEvidenceUseOutcome,
        reason: ClaimEvidenceUseReason,
        requested_by: UserId,
        evaluated_at: object,
    ) -> ClaimEvidenceUseDecision:
        from datetime import datetime

        if not isinstance(evaluated_at, datetime):
            raise TypeError("evaluated_at must be a datetime")
        return ClaimEvidenceUseDecision(
            outcome=outcome,
            reason_code=reason,
            policy_id=CLAIM_EVIDENCE_POLICY_ID,
            policy_version=CLAIM_EVIDENCE_POLICY_VERSION,
            purpose=ClaimEvidencePurpose.INTERNAL_CLAIM_VERIFICATION,
            controlled_corpus_manifest_version=self._manifest.version,
            controlled_corpus_manifest_digest=self._manifest.digest,
            requested_by=requested_by,
            evaluated_at=evaluated_at,
        )


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# Recomputed independently in tests/claims/synthetic_fixtures.py from explicit synthetic bytes,
# located text, and the F5.1 JsonPointerLocator canonical representation.
_SYNTHETIC_LEGAL_NAME_ANCHOR = ControlledEvidenceAnchorV1(
    artifact_original_sha256="ff92aca078d20304c02760d2422e1ad40fade2bab5c6fe0a1f63f688eea1028f",
    evidence_content_sha256="f6b8b96c84ceab6097d05a544ca484c191b28e1ad5a14297aeff8990ea6e4065",
    evidence_kind=EvidenceKind.STRUCTURED_DATA,
    locator_type=EvidenceLocatorType.JSON_POINTER,
    locator_digest="49e82c4c831b3972bde43fb80868aea23ec1d2eed771d9265b9d3f6759dee9ad",
)

F5_2_CONTROLLED_CORPUS_MANIFEST_V1 = build_manifest((_SYNTHETIC_LEGAL_NAME_ANCHOR,))
F5_2_CONTROLLED_CORPUS_V1 = ClaimEvidenceEligibilityPolicyV1(F5_2_CONTROLLED_CORPUS_MANIFEST_V1)


__all__ = [
    "CLAIM_EVIDENCE_POLICY_ID",
    "CLAIM_EVIDENCE_POLICY_VERSION",
    "CONTROLLED_CORPUS_MANIFEST_ID",
    "CONTROLLED_CORPUS_MANIFEST_VERSION",
    "F5_2_CONTROLLED_CORPUS_MANIFEST_V1",
    "F5_2_CONTROLLED_CORPUS_V1",
    "ClaimEvidenceEligibilityPolicyV1",
    "ClaimEvidencePolicyError",
    "ControlledCorpusManifestV1",
    "ControlledEvidenceAnchorV1",
    "build_manifest",
    "locator_digest",
    "manifest_digest",
]
