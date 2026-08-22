"""Traceable synthetic F5.2 bytes and Evidence construction helpers."""

from datetime import UTC, datetime
from hashlib import sha256

from intelligence.application.claim_evidence_policy import locator_digest
from intelligence.domain.identifiers import (
    ArtifactId,
    CompanyId,
    EntityResolutionDecisionId,
    EvidenceCommandId,
    EvidenceId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.evidence.models import (
    ArtifactOriginType,
    ArtifactStorageMode,
    EvidenceDisplayMode,
    EvidenceHistory,
    EvidenceKind,
    JsonPointerLocator,
    PublicationAbsenceReason,
    RetentionMode,
    SensitivityClassification,
    build_artifact,
    build_evidence,
    locator_to_canonical_json,
)

SYNTHETIC_ARTIFACT_BYTES = (
    b'{"company":{"legal_name":"Synthetic Alpha Registry Test Ltd.",'
    b'"registration_status":"ACTIVE","incorporation_date":"2020-01-15",'
    b'"country":"BR","registration_identifier":"TEST-REG-0001"}}'
)
SYNTHETIC_LOCATED_TEXT = "Synthetic Alpha Registry Test Ltd."
SYNTHETIC_LOCATED_BYTES = SYNTHETIC_LOCATED_TEXT.encode("utf-8")
FIXED_TIME = datetime(2026, 8, 21, 12, tzinfo=UTC)
WORKSPACE_ID = WorkspaceId.from_value("20000000-0000-4000-8000-000000000001")
INVESTIGATION_ID = InvestigationId.from_value("20000000-0000-4000-8000-000000000002")
COMPANY_ID = CompanyId.from_value("20000000-0000-4000-8000-000000000003")
DECISION_ID = EntityResolutionDecisionId.from_value("20000000-0000-4000-8000-000000000004")
USER_ID = UserId.from_value("20000000-0000-4000-8000-000000000005")


def artifact_hash() -> str:
    return sha256(SYNTHETIC_ARTIFACT_BYTES).hexdigest()


def content_hash(content: bytes = SYNTHETIC_LOCATED_BYTES) -> str:
    return sha256(content).hexdigest()


def synthetic_locator(pointer: str = "/company/legal_name") -> JsonPointerLocator:
    return JsonPointerLocator(pointer=pointer, response_sha256=artifact_hash())


def canonical_locator(pointer: str = "/company/legal_name") -> str:
    return locator_to_canonical_json(synthetic_locator(pointer))


def synthetic_locator_digest(pointer: str = "/company/legal_name") -> str:
    return locator_digest(synthetic_locator(pointer))


def synthetic_history(
    *,
    original: bytes = SYNTHETIC_ARTIFACT_BYTES,
    located: bytes = SYNTHETIC_LOCATED_BYTES,
    pointer: str = "/company/legal_name",
    kind: EvidenceKind = EvidenceKind.STRUCTURED_DATA,
    storage_mode: ArtifactStorageMode = ArtifactStorageMode.EXCERPT_ONLY,
    retention_mode: RetentionMode = RetentionMode.INDEFINITE,
    display_mode: EvidenceDisplayMode = EvidenceDisplayMode.FULL,
    retain_content: bool = True,
    source_id: str = "untrusted.fixture.label",
    origin_type: ArtifactOriginType = ArtifactOriginType.FILE_IMPORT,
) -> EvidenceHistory:
    artifact = build_artifact(
        artifact_id=ArtifactId.from_value("30000000-0000-4000-8000-000000000001"),
        workspace_id=WORKSPACE_ID,
        investigation_id=INVESTIGATION_ID,
        source_id=source_id,
        source_policy_version="UNTRUSTED_TEXT_V1",
        origin_type=origin_type,
        origin_reference="synthetic/f5.2/controlled-evidence-v1.json",
        origin_fingerprint=sha256(b"synthetic-f5.2-origin").hexdigest(),
        acquisition_method="SYNTHETIC_TEST_FIXTURE",
        acquisition_method_version="1",
        acquired_by=USER_ID,
        retrieved_at=FIXED_TIME,
        published_at=None,
        publication_absence_reason=PublicationAbsenceReason.NOT_APPLICABLE,
        media_type="application/json",
        original_content=original,
        storage_mode=storage_mode,
        storage_reference=(
            f"workspace/{WORKSPACE_ID}/synthetic.json"
            if storage_mode is ArtifactStorageMode.OBJECT
            else None
        ),
        retention_mode=retention_mode,
        retention_until=(
            datetime(2027, 8, 21, 12, tzinfo=UTC) if retention_mode is RetentionMode.UNTIL else None
        ),
        display_mode=display_mode,
        sensitivity=SensitivityClassification.INTERNAL,
        created_at=FIXED_TIME,
    )
    evidence_id = EvidenceId.from_value("30000000-0000-4000-8000-000000000002")
    locator = JsonPointerLocator(
        pointer=pointer,
        response_sha256=artifact.original_content_sha256,
    )
    evidence = build_evidence(
        evidence_id=evidence_id,
        series_id=evidence_id,
        version=1,
        supersedes_evidence_id=None,
        workspace_id=WORKSPACE_ID,
        investigation_id=INVESTIGATION_ID,
        subject_company_id=COMPANY_ID,
        entity_resolution_decision_id=DECISION_ID,
        artifact_id=artifact.id,
        command_id=EvidenceCommandId.from_value("30000000-0000-4000-8000-000000000003"),
        command_digest=sha256(b"synthetic-evidence-command").hexdigest(),
        kind=kind,
        language="en",
        locator=locator,
        located_content=located,
        content_original=located.decode("utf-8") if retain_content else None,
        extraction_method="SYNTHETIC_JSON_POINTER",
        extraction_method_version="1",
        matching_policy_id="ENTITY_MATCHING_V1",
        matching_policy_version=1,
        created_by=USER_ID,
        created_at=FIXED_TIME,
    )
    return EvidenceHistory(artifact=artifact, versions=(evidence,), events=())


__all__ = [
    "COMPANY_ID",
    "DECISION_ID",
    "FIXED_TIME",
    "INVESTIGATION_ID",
    "SYNTHETIC_ARTIFACT_BYTES",
    "SYNTHETIC_LOCATED_BYTES",
    "SYNTHETIC_LOCATED_TEXT",
    "USER_ID",
    "WORKSPACE_ID",
    "artifact_hash",
    "canonical_locator",
    "content_hash",
    "synthetic_history",
    "synthetic_locator",
    "synthetic_locator_digest",
]
