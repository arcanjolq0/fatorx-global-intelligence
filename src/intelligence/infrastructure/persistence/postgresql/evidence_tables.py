"""SQLAlchemy Core metadata for the append-only F5.1 evidence core."""

from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from intelligence.evidence.models import (
    ARTIFACT_SCHEMA_VERSION,
    EVIDENCE_LIFECYCLE_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    ArtifactOriginType,
    ArtifactStorageMode,
    EvidenceAdmissibilityStatus,
    EvidenceDisplayMode,
    EvidenceKind,
    EvidenceLifecycleEventType,
    EvidenceLifecycleReason,
    EvidenceLocatorType,
    PublicationAbsenceReason,
    RetentionMode,
    SensitivityClassification,
)
from intelligence.infrastructure.persistence.postgresql.metadata import metadata


def _sql_values(values: Iterable[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


evidence_artifact_table = sa.Table(
    "evidence_artifact",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("source_id", sa.String(length=128), nullable=False),
    sa.Column("source_policy_version", sa.String(length=128), nullable=False),
    sa.Column("origin_type", sa.String(length=32), nullable=False),
    sa.Column("origin_reference", sa.Text(), nullable=False),
    sa.Column("origin_fingerprint", sa.String(length=64), nullable=False),
    sa.Column("acquisition_method", sa.String(length=128), nullable=False),
    sa.Column("acquisition_method_version", sa.String(length=128), nullable=False),
    sa.Column("acquired_by", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("publication_absence_reason", sa.String(length=32), nullable=True),
    sa.Column("media_type", sa.String(length=255), nullable=False),
    sa.Column("original_content_sha256", sa.String(length=64), nullable=False),
    sa.Column("original_byte_length", sa.BigInteger(), nullable=False),
    sa.Column("storage_mode", sa.String(length=32), nullable=False),
    sa.Column("storage_reference", sa.Text(), nullable=True),
    sa.Column("retention_mode", sa.String(length=32), nullable=False),
    sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
    sa.Column("display_mode", sa.String(length=32), nullable=False),
    sa.Column("sensitivity", sa.String(length=32), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("artifact_digest", sa.String(length=64), nullable=False),
    sa.Column("schema_version", sa.SmallInteger(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("id", "workspace_id", "investigation_id"),
    sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["workspace.id"],
        ondelete="RESTRICT",
        name="fk_evidence_artifact_workspace",
    ),
    sa.ForeignKeyConstraint(
        ["investigation_id", "workspace_id"],
        ["investigation.id", "investigation.workspace_id"],
        ondelete="RESTRICT",
        name="fk_evidence_artifact_investigation_scope",
    ),
    sa.ForeignKeyConstraint(
        ["acquired_by"],
        ["user_account.id"],
        ondelete="RESTRICT",
        name="fk_evidence_artifact_actor",
    ),
    sa.CheckConstraint(
        f"origin_type IN ({_sql_values(item.value for item in ArtifactOriginType)})",
        name="origin_type_allowed",
    ),
    sa.CheckConstraint(
        f"storage_mode IN ({_sql_values(item.value for item in ArtifactStorageMode)})",
        name="storage_mode_allowed",
    ),
    sa.CheckConstraint(
        f"retention_mode IN ({_sql_values(item.value for item in RetentionMode)})",
        name="retention_mode_allowed",
    ),
    sa.CheckConstraint(
        f"display_mode IN ({_sql_values(item.value for item in EvidenceDisplayMode)})",
        name="display_mode_allowed",
    ),
    sa.CheckConstraint(
        f"sensitivity IN ({_sql_values(item.value for item in SensitivityClassification)})",
        name="sensitivity_allowed",
    ),
    sa.CheckConstraint(
        "publication_absence_reason IS NULL OR publication_absence_reason IN "
        f"({_sql_values(item.value for item in PublicationAbsenceReason)})",
        name="publication_absence_reason_allowed",
    ),
    sa.CheckConstraint(
        "num_nonnulls(published_at, publication_absence_reason) = 1",
        name="publication_explicit",
    ),
    sa.CheckConstraint(
        "published_at IS NULL OR published_at <= retrieved_at", name="publication_order"
    ),
    sa.CheckConstraint("created_at >= retrieved_at", name="creation_order"),
    sa.CheckConstraint("original_byte_length > 0", name="byte_length_positive"),
    sa.CheckConstraint(
        "(storage_mode = 'OBJECT' AND storage_reference IS NOT NULL "
        "AND storage_reference LIKE 'workspace/' || workspace_id::text || '/%') OR "
        "(storage_mode <> 'OBJECT' AND storage_reference IS NULL)",
        name="storage_reference_consistent",
    ),
    sa.CheckConstraint(
        "(retention_mode = 'UNTIL' AND retention_until > retrieved_at) OR "
        "(retention_mode <> 'UNTIL' AND retention_until IS NULL)",
        name="retention_until_consistent",
    ),
    sa.CheckConstraint(
        "retention_mode <> 'PROHIBITED' OR "
        "storage_mode IN ('REFERENCE_ONLY', 'EPHEMERAL_PROCESSING')",
        name="prohibited_retention_consistent",
    ),
    sa.CheckConstraint(
        "NOT (display_mode IN ('REFERENCE_ONLY', 'PROHIBITED') AND storage_mode = 'EXCERPT_ONLY')",
        name="display_storage_consistent",
    ),
    sa.CheckConstraint(
        "origin_fingerprint ~ '^[0-9a-f]{64}$' "
        "AND original_content_sha256 ~ '^[0-9a-f]{64}$' "
        "AND artifact_digest ~ '^[0-9a-f]{64}$'",
        name="digests_format",
    ),
    sa.CheckConstraint(f"schema_version = {ARTIFACT_SCHEMA_VERSION}", name="schema_supported"),
)
sa.Index(
    "ix_evidence_artifact_workspace_investigation",
    evidence_artifact_table.c.workspace_id,
    evidence_artifact_table.c.investigation_id,
)


evidence_table = sa.Table(
    "evidence",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("supersedes_evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("subject_company_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("entity_resolution_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("command_digest", sa.String(length=64), nullable=False),
    sa.Column("kind", sa.String(length=32), nullable=False),
    sa.Column("language", sa.String(length=64), nullable=False),
    sa.Column("locator_type", sa.String(length=32), nullable=False),
    sa.Column("locator_snapshot", postgresql.JSONB(none_as_null=True), nullable=False),
    sa.Column("content_sha256", sa.String(length=64), nullable=False),
    sa.Column("content_original", sa.Text(), nullable=True),
    sa.Column("extraction_method", sa.String(length=128), nullable=False),
    sa.Column("extraction_method_version", sa.String(length=128), nullable=False),
    sa.Column("matching_policy_id", sa.String(length=128), nullable=False),
    sa.Column("matching_policy_version", sa.Integer(), nullable=False),
    sa.Column("admissibility_status", sa.String(length=32), nullable=False),
    sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("evidence_digest", sa.String(length=64), nullable=False),
    sa.Column("schema_version", sa.SmallInteger(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("id", "workspace_id", "investigation_id"),
    sa.UniqueConstraint("workspace_id", "command_id"),
    sa.UniqueConstraint("workspace_id", "series_id", "version"),
    sa.ForeignKeyConstraint(
        ["workspace_id"], ["workspace.id"], ondelete="RESTRICT", name="fk_evidence_workspace"
    ),
    sa.ForeignKeyConstraint(
        ["investigation_id", "workspace_id"],
        ["investigation.id", "investigation.workspace_id"],
        ondelete="RESTRICT",
        name="fk_evidence_investigation_scope",
    ),
    sa.ForeignKeyConstraint(
        ["subject_company_id", "workspace_id"],
        ["company.id", "company.workspace_id"],
        ondelete="RESTRICT",
        name="fk_evidence_company_scope",
    ),
    sa.ForeignKeyConstraint(
        [
            "entity_resolution_decision_id",
            "workspace_id",
            "investigation_id",
            "subject_company_id",
        ],
        [
            "entity_resolution_decision.id",
            "entity_resolution_decision.workspace_id",
            "entity_resolution_decision.investigation_id",
            "entity_resolution_decision.company_id",
        ],
        ondelete="RESTRICT",
        name="fk_evidence_decision_scope",
    ),
    sa.ForeignKeyConstraint(
        ["artifact_id", "workspace_id", "investigation_id"],
        [
            "evidence_artifact.id",
            "evidence_artifact.workspace_id",
            "evidence_artifact.investigation_id",
        ],
        ondelete="RESTRICT",
        name="fk_evidence_artifact_scope",
    ),
    sa.ForeignKeyConstraint(
        ["series_id", "workspace_id", "investigation_id"],
        ["evidence.id", "evidence.workspace_id", "evidence.investigation_id"],
        ondelete="RESTRICT",
        name="fk_evidence_series_scope",
    ),
    sa.ForeignKeyConstraint(
        ["supersedes_evidence_id", "workspace_id", "investigation_id"],
        ["evidence.id", "evidence.workspace_id", "evidence.investigation_id"],
        ondelete="RESTRICT",
        name="fk_evidence_supersedes_scope",
    ),
    sa.ForeignKeyConstraint(
        ["created_by"], ["user_account.id"], ondelete="RESTRICT", name="fk_evidence_actor"
    ),
    sa.CheckConstraint("version >= 1", name="version_positive"),
    sa.CheckConstraint(
        "(version = 1 AND series_id = id AND supersedes_evidence_id IS NULL) OR "
        "(version > 1 AND series_id <> id AND supersedes_evidence_id IS NOT NULL)",
        name="version_chain_shape",
    ),
    sa.CheckConstraint(
        f"kind IN ({_sql_values(item.value for item in EvidenceKind)})", name="kind_allowed"
    ),
    sa.CheckConstraint(
        f"locator_type IN ({_sql_values(item.value for item in EvidenceLocatorType)})",
        name="locator_type_allowed",
    ),
    sa.CheckConstraint(
        f"admissibility_status = '{EvidenceAdmissibilityStatus.PENDING.value}'",
        name="admissibility_pending",
    ),
    sa.CheckConstraint("matching_policy_version >= 1", name="matching_policy_version_positive"),
    sa.CheckConstraint(
        "command_digest ~ '^[0-9a-f]{64}$' AND content_sha256 ~ '^[0-9a-f]{64}$' "
        "AND evidence_digest ~ '^[0-9a-f]{64}$'",
        name="digests_format",
    ),
    sa.CheckConstraint(f"schema_version = {EVIDENCE_SCHEMA_VERSION}", name="schema_supported"),
)
sa.Index(
    "ix_evidence_workspace_investigation",
    evidence_table.c.workspace_id,
    evidence_table.c.investigation_id,
)
sa.Index("ix_evidence_workspace_series", evidence_table.c.workspace_id, evidence_table.c.series_id)


evidence_lifecycle_event_table = sa.Table(
    "evidence_lifecycle_event",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("command_digest", sa.String(length=64), nullable=False),
    sa.Column("event_type", sa.String(length=32), nullable=False),
    sa.Column("reason", sa.String(length=32), nullable=False),
    sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("related_evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("event_digest", sa.String(length=64), nullable=False),
    sa.Column("schema_version", sa.SmallInteger(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("workspace_id", "command_id"),
    sa.UniqueConstraint("evidence_id", "event_type"),
    sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["workspace.id"],
        ondelete="RESTRICT",
        name="fk_evidence_lifecycle_event_workspace",
    ),
    sa.ForeignKeyConstraint(
        ["investigation_id", "workspace_id"],
        ["investigation.id", "investigation.workspace_id"],
        ondelete="RESTRICT",
        name="fk_evidence_lifecycle_event_investigation_scope",
    ),
    sa.ForeignKeyConstraint(
        ["evidence_id", "workspace_id", "investigation_id"],
        ["evidence.id", "evidence.workspace_id", "evidence.investigation_id"],
        ondelete="RESTRICT",
        name="fk_evidence_lifecycle_event_evidence_scope",
    ),
    sa.ForeignKeyConstraint(
        ["related_evidence_id", "workspace_id", "investigation_id"],
        ["evidence.id", "evidence.workspace_id", "evidence.investigation_id"],
        ondelete="RESTRICT",
        name="fk_evidence_lifecycle_event_related_evidence_scope",
    ),
    sa.ForeignKeyConstraint(
        ["actor_user_id"],
        ["user_account.id"],
        ondelete="RESTRICT",
        name="fk_evidence_lifecycle_event_actor",
    ),
    sa.CheckConstraint(
        f"event_type IN ({_sql_values(item.value for item in EvidenceLifecycleEventType)})",
        name="event_type_allowed",
    ),
    sa.CheckConstraint(
        f"reason IN ({_sql_values(item.value for item in EvidenceLifecycleReason)})",
        name="reason_allowed",
    ),
    sa.CheckConstraint(
        "(event_type = 'SUPERSEDED' AND reason = 'CORRECTION' "
        "AND related_evidence_id IS NOT NULL AND related_evidence_id <> evidence_id) OR "
        "(event_type = 'REVOKED' AND reason <> 'CORRECTION' "
        "AND related_evidence_id IS NULL)",
        name="event_shape",
    ),
    sa.CheckConstraint(
        "command_digest ~ '^[0-9a-f]{64}$' AND event_digest ~ '^[0-9a-f]{64}$'",
        name="digests_format",
    ),
    sa.CheckConstraint(
        f"schema_version = {EVIDENCE_LIFECYCLE_SCHEMA_VERSION}", name="schema_supported"
    ),
)
sa.Index(
    "ix_evidence_event_workspace_investigation",
    evidence_lifecycle_event_table.c.workspace_id,
    evidence_lifecycle_event_table.c.investigation_id,
)


__all__ = [
    "evidence_artifact_table",
    "evidence_lifecycle_event_table",
    "evidence_table",
]
