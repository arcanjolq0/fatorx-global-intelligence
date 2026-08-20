"""Typed commands and redacted results for canonical evidence use cases."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256

from intelligence.application.actor_context import ActorContext
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    EntityResolutionDecisionId,
    EvidenceCommandId,
    EvidenceId,
    InvestigationId,
)
from intelligence.domain.time import normalize_utc
from intelligence.evidence.models import (
    ArtifactOriginType,
    ArtifactStorageMode,
    EvidenceDisplayMode,
    EvidenceHistory,
    EvidenceKind,
    EvidenceLifecycleReason,
    EvidenceLocator,
    ExternalReferenceLocator,
    HtmlSelectorLocator,
    ImageRegionLocator,
    JsonPointerLocator,
    PageTextLocator,
    PdfRegionLocator,
    PublicationAbsenceReason,
    RetentionMode,
    SensitivityClassification,
    SpreadsheetCellLocator,
    locator_to_canonical_json,
)

EVIDENCE_COMMAND_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class RegisterEvidence:
    command_id: EvidenceCommandId
    investigation_id: InvestigationId
    entity_resolution_decision_id: EntityResolutionDecisionId
    source_id: str
    source_policy_version: str
    origin_type: ArtifactOriginType
    origin_reference: str
    origin_fingerprint: str
    acquisition_method: str
    acquisition_method_version: str
    retrieved_at: datetime
    published_at: datetime | None
    publication_absence_reason: PublicationAbsenceReason | None
    media_type: str
    original_content: bytes = field(repr=False)
    storage_mode: ArtifactStorageMode
    storage_reference: str | None
    retention_mode: RetentionMode
    retention_until: datetime | None
    display_mode: EvidenceDisplayMode
    sensitivity: SensitivityClassification
    evidence_kind: EvidenceKind
    language: str
    locator: EvidenceLocator
    located_content: bytes = field(repr=False)
    content_original: str | None = field(repr=False)
    extraction_method: str
    extraction_method_version: str
    schema_version: int = EVIDENCE_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.command_id, EvidenceCommandId)
            or not isinstance(self.investigation_id, InvestigationId)
            or not isinstance(self.entity_resolution_decision_id, EntityResolutionDecisionId)
        ):
            raise InvariantViolationError("Evidence registration identifiers must be typed.")
        if not isinstance(self.original_content, bytes) or not isinstance(
            self.located_content, bytes
        ):
            raise InvariantViolationError("Evidence registration content must be bytes.")
        if not self.original_content or not self.located_content:
            raise InvariantViolationError("Evidence registration content cannot be empty.")
        for value, expected, name in (
            (self.origin_type, ArtifactOriginType, "origin_type"),
            (self.storage_mode, ArtifactStorageMode, "storage_mode"),
            (self.retention_mode, RetentionMode, "retention_mode"),
            (self.display_mode, EvidenceDisplayMode, "display_mode"),
            (self.sensitivity, SensitivityClassification, "sensitivity"),
            (self.evidence_kind, EvidenceKind, "evidence_kind"),
        ):
            if not isinstance(value, expected):
                raise InvariantViolationError(f"Evidence registration {name} is invalid.")
        if self.publication_absence_reason is not None and not isinstance(
            self.publication_absence_reason, PublicationAbsenceReason
        ):
            raise InvariantViolationError(
                "Evidence registration publication_absence_reason is invalid."
            )
        _locator(self.locator)
        if self.content_original is not None and (
            not isinstance(self.content_original, str)
            or self.content_original.encode("utf-8") != self.located_content
        ):
            raise InvariantViolationError("Evidence excerpt must exactly match located bytes.")
        if (
            self.storage_mode
            in {
                ArtifactStorageMode.REFERENCE_ONLY,
                ArtifactStorageMode.EPHEMERAL_PROCESSING,
            }
            and self.content_original is not None
        ):
            raise InvariantViolationError("Evidence storage policy forbids retained excerpts.")
        if self.schema_version != EVIDENCE_COMMAND_SCHEMA_VERSION:
            raise InvariantViolationError("Evidence registration command schema is unsupported.")
        object.__setattr__(self, "retrieved_at", normalize_utc(self.retrieved_at))
        object.__setattr__(
            self, "published_at", normalize_utc(self.published_at) if self.published_at else None
        )
        object.__setattr__(
            self,
            "retention_until",
            normalize_utc(self.retention_until) if self.retention_until else None,
        )

    def __repr__(self) -> str:
        return (
            f"RegisterEvidence(command_id={self.command_id!r}, "
            f"investigation_id={self.investigation_id!r}, source_id={self.source_id!r}, "
            "content=<redacted>)"
        )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CorrectEvidence:
    command_id: EvidenceCommandId
    evidence_id: EvidenceId
    expected_evidence_digest: str
    kind: EvidenceKind
    language: str
    locator: EvidenceLocator
    located_content: bytes = field(repr=False)
    content_original: str | None = field(repr=False)
    extraction_method: str
    extraction_method_version: str
    schema_version: int = EVIDENCE_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.command_id, EvidenceCommandId) or not isinstance(
            self.evidence_id, EvidenceId
        ):
            raise InvariantViolationError("Evidence correction identifiers must be typed.")
        _sha256(self.expected_evidence_digest, "expected evidence")
        if not isinstance(self.located_content, bytes) or not self.located_content:
            raise InvariantViolationError("Evidence correction content must be non-empty bytes.")
        if not isinstance(self.kind, EvidenceKind):
            raise InvariantViolationError("Evidence correction kind is invalid.")
        _locator(self.locator)
        if self.content_original is not None and (
            not isinstance(self.content_original, str)
            or self.content_original.encode("utf-8") != self.located_content
        ):
            raise InvariantViolationError("Evidence correction excerpt must match located bytes.")
        if self.schema_version != EVIDENCE_COMMAND_SCHEMA_VERSION:
            raise InvariantViolationError("Evidence correction command schema is unsupported.")

    def __repr__(self) -> str:
        return (
            f"CorrectEvidence(command_id={self.command_id!r}, evidence_id={self.evidence_id!r}, "
            "content=<redacted>)"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RevokeEvidence:
    command_id: EvidenceCommandId
    evidence_id: EvidenceId
    expected_evidence_digest: str
    reason: EvidenceLifecycleReason
    schema_version: int = EVIDENCE_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.command_id, EvidenceCommandId) or not isinstance(
            self.evidence_id, EvidenceId
        ):
            raise InvariantViolationError("Evidence revocation identifiers must be typed.")
        _sha256(self.expected_evidence_digest, "expected evidence")
        if not isinstance(self.reason, EvidenceLifecycleReason) or (
            self.reason is EvidenceLifecycleReason.CORRECTION
        ):
            raise InvariantViolationError("Evidence revocation reason is invalid.")
        if self.schema_version != EVIDENCE_COMMAND_SCHEMA_VERSION:
            raise InvariantViolationError("Evidence revocation command schema is unsupported.")


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceOperationResult:
    history: EvidenceHistory
    replayed: bool


def digest_register_evidence(actor: ActorContext, command: RegisterEvidence) -> str:
    return _command_digest(
        actor,
        command.command_id,
        "REGISTER",
        {
            "acquisition_method": command.acquisition_method,
            "acquisition_method_version": command.acquisition_method_version,
            "content_original_retained": command.content_original is not None,
            "display_mode": command.display_mode.value,
            "entity_resolution_decision_id": str(command.entity_resolution_decision_id),
            "evidence_kind": command.evidence_kind.value,
            "investigation_id": str(command.investigation_id),
            "language": command.language,
            "located_content_sha256": sha256(command.located_content).hexdigest(),
            "locator": json.loads(locator_to_canonical_json(command.locator)),
            "media_type": command.media_type,
            "origin_fingerprint": command.origin_fingerprint,
            "origin_reference": command.origin_reference,
            "origin_type": command.origin_type.value,
            "original_content_sha256": sha256(command.original_content).hexdigest(),
            "publication_absence_reason": (
                command.publication_absence_reason.value
                if command.publication_absence_reason
                else None
            ),
            "published_at": command.published_at.isoformat() if command.published_at else None,
            "retention_mode": command.retention_mode.value,
            "retention_until": (
                command.retention_until.isoformat() if command.retention_until else None
            ),
            "retrieved_at": command.retrieved_at.isoformat(),
            "schema_version": command.schema_version,
            "sensitivity": command.sensitivity.value,
            "source_id": command.source_id,
            "source_policy_version": command.source_policy_version,
            "storage_mode": command.storage_mode.value,
            "storage_reference": command.storage_reference,
            "extraction_method": command.extraction_method,
            "extraction_method_version": command.extraction_method_version,
        },
    )


def digest_correct_evidence(actor: ActorContext, command: CorrectEvidence) -> str:
    return _command_digest(
        actor,
        command.command_id,
        "CORRECT",
        {
            "content_original_retained": command.content_original is not None,
            "evidence_id": str(command.evidence_id),
            "expected_evidence_digest": command.expected_evidence_digest,
            "extraction_method": command.extraction_method,
            "extraction_method_version": command.extraction_method_version,
            "kind": command.kind.value,
            "language": command.language,
            "located_content_sha256": sha256(command.located_content).hexdigest(),
            "locator": json.loads(locator_to_canonical_json(command.locator)),
            "schema_version": command.schema_version,
        },
    )


def digest_revoke_evidence(actor: ActorContext, command: RevokeEvidence) -> str:
    return _command_digest(
        actor,
        command.command_id,
        "REVOKE",
        {
            "evidence_id": str(command.evidence_id),
            "expected_evidence_digest": command.expected_evidence_digest,
            "reason": command.reason.value,
            "schema_version": command.schema_version,
        },
    )


def _command_digest(
    actor: ActorContext,
    command_id: EvidenceCommandId,
    command_type: str,
    payload: dict[str, object],
) -> str:
    value = {
        "actor_user_id": str(actor.user_id),
        "command_id": str(command_id),
        "command_type": command_type,
        "payload": payload,
        "workspace_id": str(actor.workspace_id),
    }
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def _sha256(value: str, name: str) -> None:
    try:
        valid = len(value) == 64 and bytes.fromhex(value).hex() == value
    except TypeError, ValueError:
        valid = False
    if not valid:
        raise InvariantViolationError(f"Evidence {name} digest is invalid.")


def _locator(value: object) -> None:
    if not isinstance(
        value,
        (
            PageTextLocator,
            PdfRegionLocator,
            HtmlSelectorLocator,
            JsonPointerLocator,
            SpreadsheetCellLocator,
            ImageRegionLocator,
            ExternalReferenceLocator,
        ),
    ):
        raise InvariantViolationError("Evidence locator must be typed.")


__all__ = [
    "EVIDENCE_COMMAND_SCHEMA_VERSION",
    "CorrectEvidence",
    "EvidenceOperationResult",
    "RegisterEvidence",
    "RevokeEvidence",
    "digest_correct_evidence",
    "digest_register_evidence",
    "digest_revoke_evidence",
]
