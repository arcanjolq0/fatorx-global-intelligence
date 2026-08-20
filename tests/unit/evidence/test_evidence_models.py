"""F5.1 immutable evidence, provenance, locator, and custody invariants."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256

import pytest

from intelligence.domain.errors import InvariantViolationError
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
from intelligence.evidence.errors import EvidenceHistoryError, EvidenceIntegrityError
from intelligence.evidence.models import (
    Artifact,
    ArtifactOriginType,
    ArtifactStorageMode,
    Evidence,
    EvidenceDisplayMode,
    EvidenceHistory,
    EvidenceKind,
    EvidenceLifecycleEventType,
    EvidenceLifecycleReason,
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
    build_artifact,
    build_evidence,
    build_lifecycle_event,
    locator_from_canonical_json,
    locator_to_canonical_json,
)

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
ORIGINAL = b'{"company":{"name":"Empresa Exemplo"}}'
LOCATED = b"Empresa Exemplo"


def _locator() -> JsonPointerLocator:
    return JsonPointerLocator(pointer="/company/name", response_sha256=sha256(ORIGINAL).hexdigest())


def _artifact(**overrides: object) -> Artifact:
    values: dict[str, object] = {
        "artifact_id": ArtifactId.new(),
        "workspace_id": WorkspaceId.new(),
        "investigation_id": InvestigationId.new(),
        "source_id": "SYNTHETIC_REGISTRY",
        "source_policy_version": "SYNTHETIC_POLICY_V1",
        "origin_type": ArtifactOriginType.FILE_IMPORT,
        "origin_reference": "fixture/company.json",
        "origin_fingerprint": sha256(b"synthetic-origin").hexdigest(),
        "acquisition_method": "SYNTHETIC_IMPORT",
        "acquisition_method_version": "1.0.0",
        "acquired_by": UserId.new(),
        "retrieved_at": NOW - timedelta(minutes=1),
        "published_at": None,
        "publication_absence_reason": PublicationAbsenceReason.NOT_PROVIDED,
        "media_type": "application/json",
        "original_content": ORIGINAL,
        "storage_mode": ArtifactStorageMode.EXCERPT_ONLY,
        "storage_reference": None,
        "retention_mode": RetentionMode.INDEFINITE,
        "retention_until": None,
        "display_mode": EvidenceDisplayMode.FULL,
        "sensitivity": SensitivityClassification.INTERNAL,
        "created_at": NOW,
    }
    values.update(overrides)
    return build_artifact(**values)  # type: ignore[arg-type]


def _evidence(artifact: Artifact, **overrides: object) -> Evidence:
    evidence_id = EvidenceId.new()
    values: dict[str, object] = {
        "evidence_id": evidence_id,
        "series_id": evidence_id,
        "version": 1,
        "supersedes_evidence_id": None,
        "workspace_id": artifact.workspace_id,
        "investigation_id": artifact.investigation_id,
        "subject_company_id": CompanyId.new(),
        "entity_resolution_decision_id": EntityResolutionDecisionId.new(),
        "artifact_id": artifact.id,
        "command_id": EvidenceCommandId.new(),
        "command_digest": sha256(b"register-command").hexdigest(),
        "kind": EvidenceKind.STRUCTURED_DATA,
        "language": "pt-BR",
        "locator": _locator(),
        "located_content": LOCATED,
        "content_original": LOCATED.decode(),
        "extraction_method": "JSON_POINTER",
        "extraction_method_version": "1.0.0",
        "matching_policy_id": "ENTITY_MATCH_V1",
        "matching_policy_version": 1,
        "created_by": artifact.acquired_by,
        "created_at": NOW,
    }
    values.update(overrides)
    return build_evidence(**values)  # type: ignore[arg-type]


def test_artifact_hashes_transient_bytes_and_redacts_repr() -> None:
    artifact = _artifact()

    assert artifact.original_content_sha256 == sha256(ORIGINAL).hexdigest()
    assert artifact.original_byte_length == len(ORIGINAL)
    assert "Empresa Exemplo" not in repr(artifact)
    assert not hasattr(artifact, "original_content")


def test_artifact_requires_explicit_publication_absence_and_coherent_storage() -> None:
    with pytest.raises(InvariantViolationError):
        _artifact(publication_absence_reason=None)
    with pytest.raises(InvariantViolationError):
        _artifact(storage_mode=ArtifactStorageMode.OBJECT, storage_reference="other/key")
    with pytest.raises(InvariantViolationError):
        _artifact(
            retention_mode=RetentionMode.PROHIBITED,
            storage_mode=ArtifactStorageMode.EXCERPT_ONLY,
        )


def test_all_required_locator_types_round_trip_canonically() -> None:
    digest = sha256(b"locator").hexdigest()
    locators = (
        PageTextLocator(page=1, start_offset=0, end_offset=4, anchor_sha256=digest),
        PdfRegionLocator(
            page=2,
            x1=Decimal("1.25"),
            y1=Decimal("2.5"),
            x2=Decimal("10.0"),
            y2=Decimal("11.5"),
        ),
        HtmlSelectorLocator(
            origin="synthetic://document/1", selector="#company", document_sha256=digest
        ),
        JsonPointerLocator(pointer="/company/name", response_sha256=digest),
        SpreadsheetCellLocator(sheet="Companies", cell_range="B2:B3"),
        ImageRegionLocator(
            frame=0,
            x1=Decimal("0"),
            y1=Decimal("0"),
            x2=Decimal("100"),
            y2=Decimal("50"),
        ),
        ExternalReferenceLocator(reference="official-record:synthetic-1"),
    )

    for locator in locators:
        serialized = locator_to_canonical_json(locator)
        assert locator_from_canonical_json(serialized) == locator


def test_evidence_hashes_exact_located_bytes_and_never_claims_admissibility() -> None:
    artifact = _artifact()
    evidence = _evidence(artifact)

    assert evidence.content_sha256 == sha256(LOCATED).hexdigest()
    assert evidence.admissibility_status.value == "PENDING"
    assert "Empresa Exemplo" not in repr(evidence)
    with pytest.raises(EvidenceIntegrityError):
        _evidence(artifact, content_original="different")


def test_digest_tampering_fails_closed_on_reconstitution() -> None:
    artifact = _artifact()
    evidence = _evidence(artifact)

    with pytest.raises(EvidenceIntegrityError):
        replace(artifact, source_id="OTHER_SOURCE")
    with pytest.raises(EvidenceIntegrityError):
        replace(evidence, language="en")


def test_correction_and_revocation_form_one_append_only_history() -> None:
    artifact = _artifact()
    first = _evidence(artifact)
    corrected = _evidence(
        artifact,
        evidence_id=EvidenceId.new(),
        series_id=first.series_id,
        version=2,
        supersedes_evidence_id=first.id,
        subject_company_id=first.subject_company_id,
        entity_resolution_decision_id=first.entity_resolution_decision_id,
        matching_policy_id=first.matching_policy_id,
        matching_policy_version=first.matching_policy_version,
        located_content=b"Empresa Exemplo S.A.",
        content_original="Empresa Exemplo S.A.",
        command_digest=sha256(b"correct-command").hexdigest(),
        created_at=NOW + timedelta(minutes=1),
    )
    correction = build_lifecycle_event(
        event_id=EvidenceLifecycleEventId.new(),
        workspace_id=first.workspace_id,
        investigation_id=first.investigation_id,
        evidence_id=first.id,
        command_id=corrected.command_id,
        command_digest=corrected.command_digest,
        event_type=EvidenceLifecycleEventType.SUPERSEDED,
        reason=EvidenceLifecycleReason.CORRECTION,
        actor_user_id=first.created_by,
        related_evidence_id=corrected.id,
        occurred_at=NOW + timedelta(minutes=1),
    )
    revocation = build_lifecycle_event(
        event_id=EvidenceLifecycleEventId.new(),
        workspace_id=first.workspace_id,
        investigation_id=first.investigation_id,
        evidence_id=corrected.id,
        command_id=EvidenceCommandId.new(),
        command_digest=sha256(b"revoke-command").hexdigest(),
        event_type=EvidenceLifecycleEventType.REVOKED,
        reason=EvidenceLifecycleReason.CONTENT_INVALID,
        actor_user_id=first.created_by,
        related_evidence_id=None,
        occurred_at=NOW + timedelta(minutes=2),
    )

    history = EvidenceHistory(
        artifact=artifact,
        versions=(first, corrected),
        events=(correction, revocation),
    )

    assert history.latest == corrected
    assert history.is_revoked


def test_history_rejects_missing_supersession_and_tenant_drift() -> None:
    artifact = _artifact()
    first = _evidence(artifact)
    corrected = _evidence(
        artifact,
        evidence_id=EvidenceId.new(),
        series_id=first.series_id,
        version=2,
        supersedes_evidence_id=first.id,
        subject_company_id=first.subject_company_id,
        entity_resolution_decision_id=first.entity_resolution_decision_id,
        matching_policy_id=first.matching_policy_id,
        matching_policy_version=first.matching_policy_version,
    )
    with pytest.raises(EvidenceHistoryError):
        EvidenceHistory(artifact=artifact, versions=(first, corrected), events=())
    with pytest.raises(EvidenceIntegrityError):
        replace(first, workspace_id=WorkspaceId.new())


def test_history_rejects_duplicate_ids_and_revocation_command_reuse() -> None:
    artifact = _artifact()
    first = _evidence(artifact)
    self_referencing_id = EvidenceId.new()
    with pytest.raises(InvariantViolationError):
        _evidence(
            artifact,
            evidence_id=self_referencing_id,
            series_id=first.series_id,
            version=2,
            supersedes_evidence_id=self_referencing_id,
        )
    revocation = build_lifecycle_event(
        event_id=EvidenceLifecycleEventId.new(),
        workspace_id=first.workspace_id,
        investigation_id=first.investigation_id,
        evidence_id=first.id,
        command_id=first.command_id,
        command_digest=first.command_digest,
        event_type=EvidenceLifecycleEventType.REVOKED,
        reason=EvidenceLifecycleReason.CONTENT_INVALID,
        actor_user_id=first.created_by,
        related_evidence_id=None,
        occurred_at=NOW + timedelta(minutes=1),
    )
    with pytest.raises(EvidenceHistoryError):
        EvidenceHistory(artifact=artifact, versions=(first,), events=(revocation,))


def test_external_evidence_requires_external_reference_locator() -> None:
    artifact = _artifact(
        storage_mode=ArtifactStorageMode.REFERENCE_ONLY,
        display_mode=EvidenceDisplayMode.REFERENCE_ONLY,
    )
    with pytest.raises(InvariantViolationError):
        _evidence(
            artifact,
            kind=EvidenceKind.EXTERNAL_REFERENCE,
            content_original=None,
        )
