"""Strict relational mapping for canonical evidence records."""

import json
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from intelligence.domain.identifiers import (
    ArtifactId,
    CompanyId,
    EntityResolutionDecisionId,
    EvidenceCommandId,
    EvidenceId,
    EvidenceLifecycleEventId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.evidence.models import (
    Artifact,
    ArtifactOriginType,
    ArtifactStorageMode,
    Evidence,
    EvidenceAdmissibilityStatus,
    EvidenceDisplayMode,
    EvidenceKind,
    EvidenceLifecycleEvent,
    EvidenceLifecycleEventType,
    EvidenceLifecycleReason,
    PublicationAbsenceReason,
    RetentionMode,
    SensitivityClassification,
    locator_from_canonical_json,
    locator_to_canonical_json,
)

type RelationalValues = Mapping[str, object]


def artifact_to_values(artifact: Artifact) -> dict[str, object]:
    return {
        "id": artifact.id.value,
        "workspace_id": artifact.workspace_id.value,
        "investigation_id": artifact.investigation_id.value,
        "source_id": artifact.source_id,
        "source_policy_version": artifact.source_policy_version,
        "origin_type": artifact.origin_type.value,
        "origin_reference": artifact.origin_reference,
        "origin_fingerprint": artifact.origin_fingerprint,
        "acquisition_method": artifact.acquisition_method,
        "acquisition_method_version": artifact.acquisition_method_version,
        "acquired_by": artifact.acquired_by.value,
        "retrieved_at": artifact.retrieved_at,
        "published_at": artifact.published_at,
        "publication_absence_reason": (
            artifact.publication_absence_reason.value
            if artifact.publication_absence_reason
            else None
        ),
        "media_type": artifact.media_type,
        "original_content_sha256": artifact.original_content_sha256,
        "original_byte_length": artifact.original_byte_length,
        "storage_mode": artifact.storage_mode.value,
        "storage_reference": artifact.storage_reference,
        "retention_mode": artifact.retention_mode.value,
        "retention_until": artifact.retention_until,
        "display_mode": artifact.display_mode.value,
        "sensitivity": artifact.sensitivity.value,
        "created_at": artifact.created_at,
        "artifact_digest": artifact.artifact_digest,
        "schema_version": artifact.schema_version,
    }


def artifact_from_values(values: RelationalValues) -> Artifact:
    return Artifact(
        id=ArtifactId(_required(values, "id", UUID)),
        workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
        investigation_id=InvestigationId(_required(values, "investigation_id", UUID)),
        source_id=_required(values, "source_id", str),
        source_policy_version=_required(values, "source_policy_version", str),
        origin_type=ArtifactOriginType(_required(values, "origin_type", str)),
        origin_reference=_required(values, "origin_reference", str),
        origin_fingerprint=_required(values, "origin_fingerprint", str),
        acquisition_method=_required(values, "acquisition_method", str),
        acquisition_method_version=_required(values, "acquisition_method_version", str),
        acquired_by=UserId(_required(values, "acquired_by", UUID)),
        retrieved_at=_required(values, "retrieved_at", datetime),
        published_at=_optional(values, "published_at", datetime),
        publication_absence_reason=(
            PublicationAbsenceReason(reason)
            if (reason := _optional(values, "publication_absence_reason", str))
            else None
        ),
        media_type=_required(values, "media_type", str),
        original_content_sha256=_required(values, "original_content_sha256", str),
        original_byte_length=_required_int(values, "original_byte_length"),
        storage_mode=ArtifactStorageMode(_required(values, "storage_mode", str)),
        storage_reference=_optional(values, "storage_reference", str),
        retention_mode=RetentionMode(_required(values, "retention_mode", str)),
        retention_until=_optional(values, "retention_until", datetime),
        display_mode=EvidenceDisplayMode(_required(values, "display_mode", str)),
        sensitivity=SensitivityClassification(_required(values, "sensitivity", str)),
        created_at=_required(values, "created_at", datetime),
        artifact_digest=_required(values, "artifact_digest", str),
        schema_version=_required_int(values, "schema_version"),
    )


def evidence_to_values(evidence: Evidence) -> dict[str, object]:
    return {
        "id": evidence.id.value,
        "series_id": evidence.series_id.value,
        "version": evidence.version,
        "supersedes_evidence_id": (
            evidence.supersedes_evidence_id.value if evidence.supersedes_evidence_id else None
        ),
        "workspace_id": evidence.workspace_id.value,
        "investigation_id": evidence.investigation_id.value,
        "subject_company_id": evidence.subject_company_id.value,
        "entity_resolution_decision_id": evidence.entity_resolution_decision_id.value,
        "artifact_id": evidence.artifact_id.value,
        "command_id": evidence.command_id.value,
        "command_digest": evidence.command_digest,
        "kind": evidence.kind.value,
        "language": evidence.language,
        "locator_type": evidence.locator.type.value,
        "locator_snapshot": json.loads(locator_to_canonical_json(evidence.locator)),
        "content_sha256": evidence.content_sha256,
        "content_original": evidence.content_original,
        "extraction_method": evidence.extraction_method,
        "extraction_method_version": evidence.extraction_method_version,
        "matching_policy_id": evidence.matching_policy_id,
        "matching_policy_version": evidence.matching_policy_version,
        "admissibility_status": evidence.admissibility_status.value,
        "created_by": evidence.created_by.value,
        "created_at": evidence.created_at,
        "evidence_digest": evidence.evidence_digest,
        "schema_version": evidence.schema_version,
    }


def evidence_from_values(values: RelationalValues) -> Evidence:
    locator_snapshot = _required(values, "locator_snapshot", dict)
    locator_serialized = json.dumps(
        locator_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    locator = locator_from_canonical_json(locator_serialized)
    if locator.type.value != _required(values, "locator_type", str):
        raise ValueError("Persisted evidence locator discriminator is inconsistent.")
    return Evidence(
        id=EvidenceId(_required(values, "id", UUID)),
        series_id=EvidenceId(_required(values, "series_id", UUID)),
        version=_required_int(values, "version"),
        supersedes_evidence_id=(
            EvidenceId(value)
            if (value := _optional(values, "supersedes_evidence_id", UUID))
            else None
        ),
        workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
        investigation_id=InvestigationId(_required(values, "investigation_id", UUID)),
        subject_company_id=CompanyId(_required(values, "subject_company_id", UUID)),
        entity_resolution_decision_id=EntityResolutionDecisionId(
            _required(values, "entity_resolution_decision_id", UUID)
        ),
        artifact_id=ArtifactId(_required(values, "artifact_id", UUID)),
        command_id=EvidenceCommandId(_required(values, "command_id", UUID)),
        command_digest=_required(values, "command_digest", str),
        kind=EvidenceKind(_required(values, "kind", str)),
        language=_required(values, "language", str),
        locator=locator,
        content_sha256=_required(values, "content_sha256", str),
        content_original=_optional(values, "content_original", str),
        extraction_method=_required(values, "extraction_method", str),
        extraction_method_version=_required(values, "extraction_method_version", str),
        matching_policy_id=_required(values, "matching_policy_id", str),
        matching_policy_version=_required_int(values, "matching_policy_version"),
        admissibility_status=EvidenceAdmissibilityStatus(
            _required(values, "admissibility_status", str)
        ),
        created_by=UserId(_required(values, "created_by", UUID)),
        created_at=_required(values, "created_at", datetime),
        evidence_digest=_required(values, "evidence_digest", str),
        schema_version=_required_int(values, "schema_version"),
    )


def lifecycle_event_to_values(event: EvidenceLifecycleEvent) -> dict[str, object]:
    return {
        "id": event.id.value,
        "workspace_id": event.workspace_id.value,
        "investigation_id": event.investigation_id.value,
        "evidence_id": event.evidence_id.value,
        "command_id": event.command_id.value,
        "command_digest": event.command_digest,
        "event_type": event.event_type.value,
        "reason": event.reason.value,
        "actor_user_id": event.actor_user_id.value,
        "related_evidence_id": (
            event.related_evidence_id.value if event.related_evidence_id else None
        ),
        "occurred_at": event.occurred_at,
        "event_digest": event.event_digest,
        "schema_version": event.schema_version,
    }


def lifecycle_event_from_values(values: RelationalValues) -> EvidenceLifecycleEvent:
    return EvidenceLifecycleEvent(
        id=EvidenceLifecycleEventId(_required(values, "id", UUID)),
        workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
        investigation_id=InvestigationId(_required(values, "investigation_id", UUID)),
        evidence_id=EvidenceId(_required(values, "evidence_id", UUID)),
        command_id=EvidenceCommandId(_required(values, "command_id", UUID)),
        command_digest=_required(values, "command_digest", str),
        event_type=EvidenceLifecycleEventType(_required(values, "event_type", str)),
        reason=EvidenceLifecycleReason(_required(values, "reason", str)),
        actor_user_id=UserId(_required(values, "actor_user_id", UUID)),
        related_evidence_id=(
            EvidenceId(value) if (value := _optional(values, "related_evidence_id", UUID)) else None
        ),
        occurred_at=_required(values, "occurred_at", datetime),
        event_digest=_required(values, "event_digest", str),
        schema_version=_required_int(values, "schema_version"),
    )


def _required[T](values: RelationalValues, key: str, expected_type: type[T]) -> T:
    value = values.get(key)
    if not isinstance(value, expected_type):
        raise ValueError(f"Persisted evidence field {key} is invalid.")
    return value


def _optional[T](values: RelationalValues, key: str, expected_type: type[T]) -> T | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, expected_type):
        raise ValueError(f"Persisted evidence field {key} is invalid.")
    return value


def _required_int(values: RelationalValues, key: str) -> int:
    value = _required(values, key, int)
    if isinstance(value, bool):
        raise ValueError(f"Persisted evidence field {key} is invalid.")
    return value


__all__ = [
    "artifact_from_values",
    "artifact_to_values",
    "evidence_from_values",
    "evidence_to_values",
    "lifecycle_event_from_values",
    "lifecycle_event_to_values",
]
