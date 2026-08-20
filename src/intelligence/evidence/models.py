"""Immutable tenant-scoped evidence, provenance, and chain-of-custody records."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

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
from intelligence.domain.time import normalize_utc
from intelligence.evidence.errors import EvidenceHistoryError, EvidenceIntegrityError

EVIDENCE_SCHEMA_VERSION = 1
ARTIFACT_SCHEMA_VERSION = 1
EVIDENCE_LIFECYCLE_SCHEMA_VERSION = 1
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)
_LANGUAGE_PATTERN = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", flags=re.ASCII)
_MEDIA_TYPE_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}",
    flags=re.ASCII,
)


class ArtifactOriginType(StrEnum):
    """Closed provenance origins; they model metadata and perform no I/O."""

    CONNECTOR = "CONNECTOR"
    USER_UPLOAD = "USER_UPLOAD"
    FILE_IMPORT = "FILE_IMPORT"
    MANUAL_REFERENCE = "MANUAL_REFERENCE"


class ArtifactStorageMode(StrEnum):
    """How original content is allowed to be retained."""

    OBJECT = "OBJECT"
    EXCERPT_ONLY = "EXCERPT_ONLY"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    EPHEMERAL_PROCESSING = "EPHEMERAL_PROCESSING"


class RetentionMode(StrEnum):
    """Closed retention instruction captured at acquisition time."""

    UNTIL = "UNTIL"
    INDEFINITE = "INDEFINITE"
    PROHIBITED = "PROHIBITED"


class EvidenceDisplayMode(StrEnum):
    """Maximum display permission snapshotted from source policy."""

    FULL = "FULL"
    REDACTED = "REDACTED"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    PROHIBITED = "PROHIBITED"


class SensitivityClassification(StrEnum):
    """Closed sensitivity classification used by storage and display policy."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class PublicationAbsenceReason(StrEnum):
    """Explicit reasons for an unavailable publication instant."""

    NOT_PROVIDED = "NOT_PROVIDED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    POLICY_RESTRICTED = "POLICY_RESTRICTED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"


class EvidenceKind(StrEnum):
    """Material form of the located evidence."""

    TEXT = "TEXT"
    STRUCTURED_DATA = "STRUCTURED_DATA"
    IMAGE = "IMAGE"
    EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"


class EvidenceAdmissibilityStatus(StrEnum):
    """Contract vocabulary; F5.1 creates only PENDING records."""

    PENDING = "PENDING"
    ADMISSIBLE = "ADMISSIBLE"
    RESTRICTED = "RESTRICTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    REJECTED = "REJECTED"


class EvidenceLocatorType(StrEnum):
    """Reproducible locator kinds required by the evidence contract."""

    PAGE_TEXT = "PAGE_TEXT"
    PDF_REGION = "PDF_REGION"
    HTML_SELECTOR = "HTML_SELECTOR"
    JSON_POINTER = "JSON_POINTER"
    SPREADSHEET_CELL = "SPREADSHEET_CELL"
    IMAGE_REGION = "IMAGE_REGION"
    EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"


class EvidenceLifecycleEventType(StrEnum):
    """Append-only corrections and terminal revocations in F5.1."""

    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


class EvidenceLifecycleReason(StrEnum):
    """Closed reasons for evidence lifecycle changes."""

    CORRECTION = "CORRECTION"
    SOURCE_WITHDRAWN = "SOURCE_WITHDRAWN"
    CONTENT_INVALID = "CONTENT_INVALID"
    ENTITY_MISMATCH = "ENTITY_MISMATCH"
    POLICY_RESTRICTED = "POLICY_RESTRICTED"
    DUPLICATE = "DUPLICATE"


@dataclass(frozen=True, slots=True, kw_only=True)
class PageTextLocator:
    page: int
    start_offset: int
    end_offset: int
    anchor_sha256: str
    type: EvidenceLocatorType = EvidenceLocatorType.PAGE_TEXT

    def __post_init__(self) -> None:
        _positive_int(self.page, "page")
        _nonnegative_int(self.start_offset, "start_offset")
        if not isinstance(self.end_offset, int) or self.end_offset <= self.start_offset:
            raise InvariantViolationError("PAGE_TEXT end_offset must follow start_offset.")
        _digest(self.anchor_sha256, "PAGE_TEXT anchor")


@dataclass(frozen=True, slots=True, kw_only=True)
class PdfRegionLocator:
    page: int
    x1: Decimal
    y1: Decimal
    x2: Decimal
    y2: Decimal
    type: EvidenceLocatorType = EvidenceLocatorType.PDF_REGION

    def __post_init__(self) -> None:
        _positive_int(self.page, "page")
        _region(self.x1, self.y1, self.x2, self.y2, "PDF_REGION")


@dataclass(frozen=True, slots=True, kw_only=True)
class HtmlSelectorLocator:
    origin: str
    selector: str
    document_sha256: str
    type: EvidenceLocatorType = EvidenceLocatorType.HTML_SELECTOR

    def __post_init__(self) -> None:
        _text(self.origin, "HTML_SELECTOR origin", maximum=2048)
        _text(self.selector, "HTML_SELECTOR selector", maximum=2048)
        _digest(self.document_sha256, "HTML_SELECTOR document")


@dataclass(frozen=True, slots=True, kw_only=True)
class JsonPointerLocator:
    pointer: str
    response_sha256: str
    type: EvidenceLocatorType = EvidenceLocatorType.JSON_POINTER

    def __post_init__(self) -> None:
        if not isinstance(self.pointer, str) or (self.pointer and not self.pointer.startswith("/")):
            raise InvariantViolationError("JSON_POINTER must be empty or start with '/'.")
        if len(self.pointer) > 2048:
            raise InvariantViolationError("JSON_POINTER is too long.")
        _digest(self.response_sha256, "JSON_POINTER response")


@dataclass(frozen=True, slots=True, kw_only=True)
class SpreadsheetCellLocator:
    sheet: str
    cell_range: str
    type: EvidenceLocatorType = EvidenceLocatorType.SPREADSHEET_CELL

    def __post_init__(self) -> None:
        _text(self.sheet, "SPREADSHEET_CELL sheet", maximum=255)
        _text(self.cell_range, "SPREADSHEET_CELL range", maximum=64)


@dataclass(frozen=True, slots=True, kw_only=True)
class ImageRegionLocator:
    frame: int
    x1: Decimal
    y1: Decimal
    x2: Decimal
    y2: Decimal
    type: EvidenceLocatorType = EvidenceLocatorType.IMAGE_REGION

    def __post_init__(self) -> None:
        _nonnegative_int(self.frame, "frame")
        _region(self.x1, self.y1, self.x2, self.y2, "IMAGE_REGION")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExternalReferenceLocator:
    reference: str
    type: EvidenceLocatorType = EvidenceLocatorType.EXTERNAL_REFERENCE

    def __post_init__(self) -> None:
        _text(self.reference, "EXTERNAL_REFERENCE reference", maximum=2048)


type EvidenceLocator = (
    PageTextLocator
    | PdfRegionLocator
    | HtmlSelectorLocator
    | JsonPointerLocator
    | SpreadsheetCellLocator
    | ImageRegionLocator
    | ExternalReferenceLocator
)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class Artifact:
    """Immutable metadata for original acquired bytes or an allowed reference."""

    id: ArtifactId
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    source_id: str
    source_policy_version: str
    origin_type: ArtifactOriginType
    origin_reference: str
    origin_fingerprint: str
    acquisition_method: str
    acquisition_method_version: str
    acquired_by: UserId
    retrieved_at: datetime
    published_at: datetime | None
    publication_absence_reason: PublicationAbsenceReason | None
    media_type: str
    original_content_sha256: str
    original_byte_length: int
    storage_mode: ArtifactStorageMode
    storage_reference: str | None
    retention_mode: RetentionMode
    retention_until: datetime | None
    display_mode: EvidenceDisplayMode
    sensitivity: SensitivityClassification
    created_at: datetime
    artifact_digest: str
    schema_version: int = ARTIFACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _typed_ids(
            (self.id, ArtifactId),
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.acquired_by, UserId),
        )
        for value, name, maximum in (
            (self.source_id, "source_id", 128),
            (self.source_policy_version, "source_policy_version", 128),
            (self.origin_reference, "origin_reference", 2048),
            (self.acquisition_method, "acquisition_method", 128),
            (self.acquisition_method_version, "acquisition_method_version", 128),
        ):
            _text(value, f"Artifact {name}", maximum=maximum)
        _digest(self.origin_fingerprint, "Artifact origin fingerprint")
        _digest(self.original_content_sha256, "Artifact original content")
        _digest(self.artifact_digest, "Artifact")
        if not isinstance(self.origin_type, ArtifactOriginType):
            raise InvariantViolationError("Artifact origin_type is invalid.")
        if _MEDIA_TYPE_PATTERN.fullmatch(self.media_type) is None:
            raise InvariantViolationError("Artifact media_type is invalid.")
        _nonnegative_int(self.original_byte_length, "original_byte_length")
        for value, expected, name in (
            (self.storage_mode, ArtifactStorageMode, "storage_mode"),
            (self.retention_mode, RetentionMode, "retention_mode"),
            (self.display_mode, EvidenceDisplayMode, "display_mode"),
            (self.sensitivity, SensitivityClassification, "sensitivity"),
        ):
            if not isinstance(value, expected):
                raise InvariantViolationError(f"Artifact {name} is invalid.")
        retrieved_at = normalize_utc(self.retrieved_at)
        created_at = normalize_utc(self.created_at)
        published_at = normalize_utc(self.published_at) if self.published_at else None
        retention_until = normalize_utc(self.retention_until) if self.retention_until else None
        if (published_at is None) == (self.publication_absence_reason is None):
            raise InvariantViolationError(
                "Artifact publication time or one explicit absence reason is required."
            )
        if published_at is not None and published_at > retrieved_at:
            raise InvariantViolationError("Artifact publication cannot follow retrieval.")
        if created_at < retrieved_at:
            raise InvariantViolationError("Artifact creation cannot precede retrieval.")
        if self.storage_mode is ArtifactStorageMode.OBJECT:
            _text(self.storage_reference, "Artifact storage_reference", maximum=1024)
            if self.storage_reference is None:
                raise InvariantViolationError("Artifact OBJECT mode requires a reference.")
            workspace_prefix = f"workspace/{self.workspace_id}/"
            if not self.storage_reference.startswith(workspace_prefix):
                raise InvariantViolationError("Artifact object reference must be workspace-scoped.")
        elif self.storage_reference is not None:
            raise InvariantViolationError("Artifact storage reference requires OBJECT mode.")
        if self.retention_mode is RetentionMode.UNTIL:
            if retention_until is None or retention_until <= retrieved_at:
                raise InvariantViolationError("Artifact retention_until must follow retrieval.")
        elif retention_until is not None:
            raise InvariantViolationError("Artifact retention_until requires UNTIL mode.")
        if self.retention_mode is RetentionMode.PROHIBITED and self.storage_mode not in {
            ArtifactStorageMode.REFERENCE_ONLY,
            ArtifactStorageMode.EPHEMERAL_PROCESSING,
        }:
            raise InvariantViolationError("Prohibited retention cannot keep original content.")
        if (
            self.display_mode
            in {
                EvidenceDisplayMode.REFERENCE_ONLY,
                EvidenceDisplayMode.PROHIBITED,
            }
            and self.storage_mode is ArtifactStorageMode.EXCERPT_ONLY
        ):
            raise InvariantViolationError("Display policy forbids persisted excerpts.")
        if self.schema_version != ARTIFACT_SCHEMA_VERSION:
            raise InvariantViolationError("Artifact schema is unsupported.")
        object.__setattr__(self, "retrieved_at", retrieved_at)
        object.__setattr__(self, "published_at", published_at)
        object.__setattr__(self, "retention_until", retention_until)
        object.__setattr__(self, "created_at", created_at)
        if self.artifact_digest != artifact_digest(self):
            raise EvidenceIntegrityError("Artifact digest verification failed.")

    def __repr__(self) -> str:
        return (
            f"Artifact(id={self.id!r}, workspace_id={self.workspace_id!r}, "
            f"investigation_id={self.investigation_id!r}, source_id={self.source_id!r}, "
            f"storage_mode={self.storage_mode.value!r})"
        )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class Evidence:
    """One immutable and exactly locatable version in an evidence series."""

    id: EvidenceId
    series_id: EvidenceId
    version: int
    supersedes_evidence_id: EvidenceId | None
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    subject_company_id: CompanyId
    entity_resolution_decision_id: EntityResolutionDecisionId
    artifact_id: ArtifactId
    command_id: EvidenceCommandId
    command_digest: str
    kind: EvidenceKind
    language: str
    locator: EvidenceLocator
    content_sha256: str
    content_original: str | None = field(repr=False)
    extraction_method: str
    extraction_method_version: str
    matching_policy_id: str
    matching_policy_version: int
    admissibility_status: EvidenceAdmissibilityStatus
    created_by: UserId
    created_at: datetime
    evidence_digest: str
    schema_version: int = EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _typed_ids(
            (self.id, EvidenceId),
            (self.series_id, EvidenceId),
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.subject_company_id, CompanyId),
            (self.entity_resolution_decision_id, EntityResolutionDecisionId),
            (self.artifact_id, ArtifactId),
            (self.command_id, EvidenceCommandId),
            (self.created_by, UserId),
        )
        if self.supersedes_evidence_id is not None and not isinstance(
            self.supersedes_evidence_id, EvidenceId
        ):
            raise InvariantViolationError("Evidence supersedes ID is invalid.")
        _positive_int(self.version, "version")
        if self.version == 1 and (
            self.series_id != self.id or self.supersedes_evidence_id is not None
        ):
            raise InvariantViolationError("First evidence version must start its own series.")
        if self.version > 1 and (self.series_id == self.id or self.supersedes_evidence_id is None):
            raise InvariantViolationError("Corrected evidence must identify its prior version.")
        if self.supersedes_evidence_id == self.id:
            raise InvariantViolationError("Evidence cannot supersede itself.")
        _digest(self.command_digest, "Evidence command")
        _digest(self.content_sha256, "Evidence content")
        _digest(self.evidence_digest, "Evidence")
        if not isinstance(self.kind, EvidenceKind):
            raise InvariantViolationError("Evidence kind is invalid.")
        if _LANGUAGE_PATTERN.fullmatch(self.language) is None:
            raise InvariantViolationError("Evidence language tag is invalid.")
        if not isinstance(self.locator, _LOCATOR_TYPES):
            raise InvariantViolationError("Evidence locator must be typed.")
        if self.kind is EvidenceKind.EXTERNAL_REFERENCE and not isinstance(
            self.locator, ExternalReferenceLocator
        ):
            raise InvariantViolationError("External evidence requires an external locator.")
        if self.content_original is not None:
            if not isinstance(self.content_original, str) or not self.content_original:
                raise InvariantViolationError("Evidence original excerpt must be non-empty text.")
            if sha256(self.content_original.encode("utf-8")).hexdigest() != self.content_sha256:
                raise EvidenceIntegrityError("Evidence original excerpt does not match its hash.")
        for value, name in (
            (self.extraction_method, "extraction_method"),
            (self.extraction_method_version, "extraction_method_version"),
            (self.matching_policy_id, "matching_policy_id"),
        ):
            _text(value, f"Evidence {name}", maximum=128)
        _positive_int(self.matching_policy_version, "matching_policy_version")
        if self.admissibility_status is not EvidenceAdmissibilityStatus.PENDING:
            raise InvariantViolationError("F5.1 evidence must start and remain PENDING.")
        created_at = normalize_utc(self.created_at)
        if self.schema_version != EVIDENCE_SCHEMA_VERSION:
            raise InvariantViolationError("Evidence schema is unsupported.")
        object.__setattr__(self, "created_at", created_at)
        if self.evidence_digest != evidence_digest(self):
            raise EvidenceIntegrityError("Evidence digest verification failed.")

    def __repr__(self) -> str:
        return (
            f"Evidence(id={self.id!r}, series_id={self.series_id!r}, version={self.version}, "
            f"workspace_id={self.workspace_id!r}, artifact_id={self.artifact_id!r})"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceLifecycleEvent:
    """Append-only supersession or revocation event."""

    id: EvidenceLifecycleEventId
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    evidence_id: EvidenceId
    command_id: EvidenceCommandId
    command_digest: str
    event_type: EvidenceLifecycleEventType
    reason: EvidenceLifecycleReason
    actor_user_id: UserId
    related_evidence_id: EvidenceId | None
    occurred_at: datetime
    event_digest: str
    schema_version: int = EVIDENCE_LIFECYCLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _typed_ids(
            (self.id, EvidenceLifecycleEventId),
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.evidence_id, EvidenceId),
            (self.command_id, EvidenceCommandId),
            (self.actor_user_id, UserId),
        )
        if self.related_evidence_id is not None and not isinstance(
            self.related_evidence_id, EvidenceId
        ):
            raise InvariantViolationError("Evidence lifecycle related ID is invalid.")
        _digest(self.command_digest, "Evidence lifecycle command")
        _digest(self.event_digest, "Evidence lifecycle event")
        if not isinstance(self.event_type, EvidenceLifecycleEventType) or not isinstance(
            self.reason, EvidenceLifecycleReason
        ):
            raise InvariantViolationError("Evidence lifecycle vocabulary is invalid.")
        if self.event_type is EvidenceLifecycleEventType.SUPERSEDED:
            if self.reason is not EvidenceLifecycleReason.CORRECTION or (
                self.related_evidence_id is None or self.related_evidence_id == self.evidence_id
            ):
                raise InvariantViolationError("Supersession requires its corrected evidence.")
        elif (
            self.related_evidence_id is not None
            or self.reason is EvidenceLifecycleReason.CORRECTION
        ):
            raise InvariantViolationError("Revocation cannot identify a corrected evidence.")
        occurred_at = normalize_utc(self.occurred_at)
        if self.schema_version != EVIDENCE_LIFECYCLE_SCHEMA_VERSION:
            raise InvariantViolationError("Evidence lifecycle schema is unsupported.")
        object.__setattr__(self, "occurred_at", occurred_at)
        if self.event_digest != lifecycle_event_digest(self):
            raise EvidenceIntegrityError("Evidence lifecycle event digest verification failed.")


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceHistory:
    """Reconstituted complete history whose structure is validated fail closed."""

    artifact: Artifact
    versions: tuple[Evidence, ...]
    events: tuple[EvidenceLifecycleEvent, ...]

    def __post_init__(self) -> None:
        if not self.versions:
            raise EvidenceHistoryError("Evidence history must contain at least one version.")
        expected_versions = tuple(range(1, len(self.versions) + 1))
        if tuple(item.version for item in self.versions) != expected_versions:
            raise EvidenceHistoryError("Evidence versions must be contiguous and ordered.")
        if len({item.id for item in self.versions}) != len(self.versions) or len(
            {item.command_id for item in self.versions}
        ) != len(self.versions):
            raise EvidenceHistoryError(
                "Evidence versions must have unique identities and commands."
            )
        if len({item.id for item in self.events}) != len(self.events) or len(
            {item.command_id for item in self.events}
        ) != len(self.events):
            raise EvidenceHistoryError("Evidence lifecycle events must be unique.")
        first = self.versions[0]
        if first.series_id != first.id:
            raise EvidenceHistoryError("Evidence history has an invalid series root.")
        for index, version in enumerate(self.versions):
            if (
                version.workspace_id != self.artifact.workspace_id
                or version.investigation_id != self.artifact.investigation_id
                or version.artifact_id != self.artifact.id
                or version.series_id != first.series_id
                or version.subject_company_id != first.subject_company_id
                or version.entity_resolution_decision_id != first.entity_resolution_decision_id
                or version.matching_policy_id != first.matching_policy_id
                or version.matching_policy_version != first.matching_policy_version
            ):
                raise EvidenceHistoryError("Evidence history scope or custody changed.")
            if version.created_at < self.artifact.created_at or (
                index > 0 and version.created_at < self.versions[index - 1].created_at
            ):
                raise EvidenceHistoryError("Evidence history timestamps are regressive.")
            if index > 0 and version.supersedes_evidence_id != self.versions[index - 1].id:
                raise EvidenceHistoryError("Evidence supersession chain is broken.")
            if isinstance(version.locator, JsonPointerLocator) and (
                version.locator.response_sha256 != self.artifact.original_content_sha256
            ):
                raise EvidenceHistoryError("JSON locator does not match its artifact hash.")
            if isinstance(version.locator, HtmlSelectorLocator) and (
                version.locator.document_sha256 != self.artifact.original_content_sha256
            ):
                raise EvidenceHistoryError("HTML locator does not match its artifact hash.")
            if isinstance(version.locator, PageTextLocator) and (
                version.locator.anchor_sha256 != version.content_sha256
            ):
                raise EvidenceHistoryError("Page locator anchor does not match evidence content.")
        if self.artifact.storage_mode in {
            ArtifactStorageMode.REFERENCE_ONLY,
            ArtifactStorageMode.EPHEMERAL_PROCESSING,
        } and any(version.content_original is not None for version in self.versions):
            raise EvidenceHistoryError("Evidence history retained content forbidden by policy.")
        superseded = tuple(
            event
            for event in self.events
            if event.event_type is EvidenceLifecycleEventType.SUPERSEDED
        )
        revoked = tuple(
            event for event in self.events if event.event_type is EvidenceLifecycleEventType.REVOKED
        )
        if len(superseded) != len(self.versions) - 1 or len(revoked) > 1:
            raise EvidenceHistoryError("Evidence lifecycle event cardinality is invalid.")
        expected_links = {
            (old.id, new.id) for old, new in zip(self.versions, self.versions[1:], strict=False)
        }
        actual_links = {(event.evidence_id, event.related_evidence_id) for event in superseded}
        if actual_links != expected_links:
            raise EvidenceHistoryError("Evidence lifecycle supersession links are invalid.")
        version_by_id = {item.id: item for item in self.versions}
        version_command_ids = {item.command_id for item in self.versions}
        all_ids = {item.id for item in self.versions}
        for event in self.events:
            if (
                event.workspace_id != first.workspace_id
                or event.investigation_id != first.investigation_id
                or event.evidence_id not in all_ids
            ):
                raise EvidenceHistoryError("Evidence lifecycle event escaped its history scope.")
            if event.occurred_at < version_by_id[event.evidence_id].created_at:
                raise EvidenceHistoryError("Evidence lifecycle timestamp is regressive.")
            if event.event_type is EvidenceLifecycleEventType.SUPERSEDED:
                if event.related_evidence_id is None:
                    raise EvidenceHistoryError("Evidence correction event has no related version.")
                related = version_by_id.get(event.related_evidence_id)
                if related is None or (
                    event.command_id != related.command_id
                    or event.command_digest != related.command_digest
                    or event.occurred_at != related.created_at
                ):
                    raise EvidenceHistoryError(
                        "Evidence correction event does not match its new version."
                    )
            elif event.command_id in version_command_ids:
                raise EvidenceHistoryError(
                    "Evidence revocation cannot reuse a version command identifier."
                )
        if revoked and revoked[0].evidence_id != self.versions[-1].id:
            raise EvidenceHistoryError("Only the latest evidence version can be revoked.")

    @property
    def latest(self) -> Evidence:
        return self.versions[-1]

    @property
    def is_revoked(self) -> bool:
        return any(event.event_type is EvidenceLifecycleEventType.REVOKED for event in self.events)


def build_artifact(
    *,
    artifact_id: ArtifactId,
    workspace_id: WorkspaceId,
    investigation_id: InvestigationId,
    source_id: str,
    source_policy_version: str,
    origin_type: ArtifactOriginType,
    origin_reference: str,
    origin_fingerprint: str,
    acquisition_method: str,
    acquisition_method_version: str,
    acquired_by: UserId,
    retrieved_at: datetime,
    published_at: datetime | None,
    publication_absence_reason: PublicationAbsenceReason | None,
    media_type: str,
    original_content: bytes,
    storage_mode: ArtifactStorageMode,
    storage_reference: str | None,
    retention_mode: RetentionMode,
    retention_until: datetime | None,
    display_mode: EvidenceDisplayMode,
    sensitivity: SensitivityClassification,
    created_at: datetime,
) -> Artifact:
    """Hash transient original bytes and return metadata without retaining the bytes."""

    if not isinstance(original_content, bytes):
        raise InvariantViolationError("Artifact original content must be bytes.")
    values: dict[str, object] = {
        "id": artifact_id,
        "workspace_id": workspace_id,
        "investigation_id": investigation_id,
        "source_id": source_id,
        "source_policy_version": source_policy_version,
        "origin_type": origin_type,
        "origin_reference": origin_reference,
        "origin_fingerprint": origin_fingerprint,
        "acquisition_method": acquisition_method,
        "acquisition_method_version": acquisition_method_version,
        "acquired_by": acquired_by,
        "retrieved_at": normalize_utc(retrieved_at),
        "published_at": normalize_utc(published_at) if published_at else None,
        "publication_absence_reason": publication_absence_reason,
        "media_type": media_type,
        "original_content_sha256": sha256(original_content).hexdigest(),
        "original_byte_length": len(original_content),
        "storage_mode": storage_mode,
        "storage_reference": storage_reference,
        "retention_mode": retention_mode,
        "retention_until": normalize_utc(retention_until) if retention_until else None,
        "display_mode": display_mode,
        "sensitivity": sensitivity,
        "created_at": normalize_utc(created_at),
        "schema_version": ARTIFACT_SCHEMA_VERSION,
    }
    return Artifact(**values, artifact_digest=_artifact_digest_values(values))  # type: ignore[arg-type]


def build_evidence(
    *,
    evidence_id: EvidenceId,
    series_id: EvidenceId,
    version: int,
    supersedes_evidence_id: EvidenceId | None,
    workspace_id: WorkspaceId,
    investigation_id: InvestigationId,
    subject_company_id: CompanyId,
    entity_resolution_decision_id: EntityResolutionDecisionId,
    artifact_id: ArtifactId,
    command_id: EvidenceCommandId,
    command_digest: str,
    kind: EvidenceKind,
    language: str,
    locator: EvidenceLocator,
    located_content: bytes,
    content_original: str | None,
    extraction_method: str,
    extraction_method_version: str,
    matching_policy_id: str,
    matching_policy_version: int,
    created_by: UserId,
    created_at: datetime,
) -> Evidence:
    """Create one PENDING evidence version from transient exactly located bytes."""

    if not isinstance(located_content, bytes) or not located_content:
        raise InvariantViolationError("Evidence located content must be non-empty bytes.")
    values: dict[str, object] = {
        "id": evidence_id,
        "series_id": series_id,
        "version": version,
        "supersedes_evidence_id": supersedes_evidence_id,
        "workspace_id": workspace_id,
        "investigation_id": investigation_id,
        "subject_company_id": subject_company_id,
        "entity_resolution_decision_id": entity_resolution_decision_id,
        "artifact_id": artifact_id,
        "command_id": command_id,
        "command_digest": command_digest,
        "kind": kind,
        "language": language,
        "locator": locator,
        "content_sha256": sha256(located_content).hexdigest(),
        "content_original": content_original,
        "extraction_method": extraction_method,
        "extraction_method_version": extraction_method_version,
        "matching_policy_id": matching_policy_id,
        "matching_policy_version": matching_policy_version,
        "admissibility_status": EvidenceAdmissibilityStatus.PENDING,
        "created_by": created_by,
        "created_at": normalize_utc(created_at),
        "schema_version": EVIDENCE_SCHEMA_VERSION,
    }
    return Evidence(**values, evidence_digest=_evidence_digest_values(values))  # type: ignore[arg-type]


def build_lifecycle_event(
    *,
    event_id: EvidenceLifecycleEventId,
    workspace_id: WorkspaceId,
    investigation_id: InvestigationId,
    evidence_id: EvidenceId,
    command_id: EvidenceCommandId,
    command_digest: str,
    event_type: EvidenceLifecycleEventType,
    reason: EvidenceLifecycleReason,
    actor_user_id: UserId,
    related_evidence_id: EvidenceId | None,
    occurred_at: datetime,
) -> EvidenceLifecycleEvent:
    values: dict[str, object] = {
        "id": event_id,
        "workspace_id": workspace_id,
        "investigation_id": investigation_id,
        "evidence_id": evidence_id,
        "command_id": command_id,
        "command_digest": command_digest,
        "event_type": event_type,
        "reason": reason,
        "actor_user_id": actor_user_id,
        "related_evidence_id": related_evidence_id,
        "occurred_at": normalize_utc(occurred_at),
        "schema_version": EVIDENCE_LIFECYCLE_SCHEMA_VERSION,
    }
    return EvidenceLifecycleEvent(
        id=event_id,
        workspace_id=workspace_id,
        investigation_id=investigation_id,
        evidence_id=evidence_id,
        command_id=command_id,
        command_digest=command_digest,
        event_type=event_type,
        reason=reason,
        actor_user_id=actor_user_id,
        related_evidence_id=related_evidence_id,
        occurred_at=normalize_utc(occurred_at),
        event_digest=_lifecycle_event_digest_values(values),
    )


def artifact_digest(artifact: Artifact) -> str:
    return _artifact_digest_values(_artifact_values(artifact))


def evidence_digest(evidence: Evidence) -> str:
    return _evidence_digest_values(_evidence_values(evidence))


def lifecycle_event_digest(event: EvidenceLifecycleEvent) -> str:
    return _lifecycle_event_digest_values(_event_values(event))


def locator_to_canonical_json(locator: EvidenceLocator) -> str:
    return _canonical_json(_locator_values(locator))


def locator_from_canonical_json(serialized: str) -> EvidenceLocator:
    try:
        raw = json.loads(serialized)
        if not isinstance(raw, dict):
            raise TypeError
        locator_type = EvidenceLocatorType(raw["type"])
        if locator_type is EvidenceLocatorType.PAGE_TEXT:
            locator: EvidenceLocator = PageTextLocator(
                page=raw["page"],
                start_offset=raw["start_offset"],
                end_offset=raw["end_offset"],
                anchor_sha256=raw["anchor_sha256"],
            )
        elif locator_type is EvidenceLocatorType.PDF_REGION:
            locator = PdfRegionLocator(
                page=raw["page"],
                x1=Decimal(raw["x1"]),
                y1=Decimal(raw["y1"]),
                x2=Decimal(raw["x2"]),
                y2=Decimal(raw["y2"]),
            )
        elif locator_type is EvidenceLocatorType.HTML_SELECTOR:
            locator = HtmlSelectorLocator(
                origin=raw["origin"],
                selector=raw["selector"],
                document_sha256=raw["document_sha256"],
            )
        elif locator_type is EvidenceLocatorType.JSON_POINTER:
            locator = JsonPointerLocator(
                pointer=raw["pointer"], response_sha256=raw["response_sha256"]
            )
        elif locator_type is EvidenceLocatorType.SPREADSHEET_CELL:
            locator = SpreadsheetCellLocator(sheet=raw["sheet"], cell_range=raw["cell_range"])
        elif locator_type is EvidenceLocatorType.IMAGE_REGION:
            locator = ImageRegionLocator(
                frame=raw["frame"],
                x1=Decimal(raw["x1"]),
                y1=Decimal(raw["y1"]),
                x2=Decimal(raw["x2"]),
                y2=Decimal(raw["y2"]),
            )
        else:
            locator = ExternalReferenceLocator(reference=raw["reference"])
    except (KeyError, TypeError, ValueError, InvariantViolationError) as error:
        raise EvidenceIntegrityError("Persisted evidence locator is invalid.") from error
    if locator_to_canonical_json(locator) != serialized:
        raise EvidenceIntegrityError("Persisted evidence locator is not canonical.")
    return locator


_LOCATOR_TYPES = (
    PageTextLocator,
    PdfRegionLocator,
    HtmlSelectorLocator,
    JsonPointerLocator,
    SpreadsheetCellLocator,
    ImageRegionLocator,
    ExternalReferenceLocator,
)


def _artifact_values(artifact: Artifact) -> dict[str, object]:
    return {
        name: getattr(artifact, name)
        for name in Artifact.__dataclass_fields__
        if name != "artifact_digest"
    }


def _evidence_values(evidence: Evidence) -> dict[str, object]:
    return {
        name: getattr(evidence, name)
        for name in Evidence.__dataclass_fields__
        if name != "evidence_digest"
    }


def _event_values(event: EvidenceLifecycleEvent) -> dict[str, object]:
    return {
        name: getattr(event, name)
        for name in EvidenceLifecycleEvent.__dataclass_fields__
        if name != "event_digest"
    }


def _artifact_digest_values(values: dict[str, object]) -> str:
    return _record_digest(values)


def _evidence_digest_values(values: dict[str, object]) -> str:
    return _record_digest(values)


def _lifecycle_event_digest_values(values: dict[str, object]) -> str:
    return _record_digest(values)


def _record_digest(values: dict[str, object]) -> str:
    return sha256(_canonical_json(_canonical_value(values)).encode("utf-8")).hexdigest()


def _canonical_value(value: object) -> object:
    if isinstance(value, dict):
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return normalize_utc(value).isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(
        value,
        (
            ArtifactId,
            CompanyId,
            EntityResolutionDecisionId,
            EvidenceCommandId,
            EvidenceId,
            EvidenceLifecycleEventId,
            InvestigationId,
            UserId,
            WorkspaceId,
        ),
    ):
        return str(value)
    if isinstance(value, _LOCATOR_TYPES):
        return _locator_values(value)
    return value


def _locator_values(locator: EvidenceLocator) -> dict[str, object]:
    return {name: _canonical_value(getattr(locator, name)) for name in locator.__dataclass_fields__}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _typed_ids(*pairs: tuple[object, type[object]]) -> None:
    if any(not isinstance(value, expected) for value, expected in pairs):
        raise InvariantViolationError("Evidence record identifiers must be strongly typed.")


def _digest(value: str, name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise InvariantViolationError(f"{name} SHA-256 is invalid.")


def _text(value: object, name: str, *, maximum: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise InvariantViolationError(f"{name} must be non-blank bounded text.")


def _positive_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvariantViolationError(f"Evidence {name} must be positive.")


def _nonnegative_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvariantViolationError(f"Evidence {name} must be non-negative.")


def _region(x1: Decimal, y1: Decimal, x2: Decimal, y2: Decimal, name: str) -> None:
    coordinates = (x1, y1, x2, y2)
    if any(not isinstance(value, Decimal) or not value.is_finite() for value in coordinates):
        raise InvariantViolationError(f"{name} coordinates must be finite decimals.")
    if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
        raise InvariantViolationError(f"{name} coordinates are invalid.")


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "EVIDENCE_LIFECYCLE_SCHEMA_VERSION",
    "EVIDENCE_SCHEMA_VERSION",
    "Artifact",
    "ArtifactOriginType",
    "ArtifactStorageMode",
    "Evidence",
    "EvidenceAdmissibilityStatus",
    "EvidenceDisplayMode",
    "EvidenceHistory",
    "EvidenceKind",
    "EvidenceLifecycleEvent",
    "EvidenceLifecycleEventType",
    "EvidenceLifecycleReason",
    "EvidenceLocator",
    "EvidenceLocatorType",
    "ExternalReferenceLocator",
    "HtmlSelectorLocator",
    "ImageRegionLocator",
    "JsonPointerLocator",
    "PageTextLocator",
    "PdfRegionLocator",
    "PublicationAbsenceReason",
    "RetentionMode",
    "SensitivityClassification",
    "SpreadsheetCellLocator",
    "artifact_digest",
    "build_artifact",
    "build_evidence",
    "build_lifecycle_event",
    "evidence_digest",
    "lifecycle_event_digest",
    "locator_from_canonical_json",
    "locator_to_canonical_json",
]
