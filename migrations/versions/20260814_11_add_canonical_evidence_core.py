"""Add immutable tenant-scoped canonical evidence records.

Revision ID: 20260814_11
Revises: 20260811_10
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_11"
down_revision: str | None = "20260811_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist artifact custody, evidence versions, and lifecycle events."""

    op.create_unique_constraint(
        op.f("uq_entity_resolution_decision_id_workspace_id_investigation_id_company_id"),
        "entity_resolution_decision",
        ["id", "workspace_id", "investigation_id", "company_id"],
    )
    op.create_table(
        "evidence_artifact",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_artifact")),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            "investigation_id",
            name=op.f("uq_evidence_artifact_id_workspace_id_investigation_id"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("fk_evidence_artifact_workspace"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id", "workspace_id"],
            ["investigation.id", "investigation.workspace_id"],
            name=op.f("fk_evidence_artifact_investigation_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["acquired_by"],
            ["user_account.id"],
            name=op.f("fk_evidence_artifact_actor"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "origin_type IN ('CONNECTOR','USER_UPLOAD','FILE_IMPORT','MANUAL_REFERENCE')",
            name=op.f("ck_evidence_artifact_origin_type_allowed"),
        ),
        sa.CheckConstraint(
            "storage_mode IN ('OBJECT','EXCERPT_ONLY','REFERENCE_ONLY','EPHEMERAL_PROCESSING')",
            name=op.f("ck_evidence_artifact_storage_mode_allowed"),
        ),
        sa.CheckConstraint(
            "retention_mode IN ('UNTIL','INDEFINITE','PROHIBITED')",
            name=op.f("ck_evidence_artifact_retention_mode_allowed"),
        ),
        sa.CheckConstraint(
            "display_mode IN ('FULL','REDACTED','REFERENCE_ONLY','PROHIBITED')",
            name=op.f("ck_evidence_artifact_display_mode_allowed"),
        ),
        sa.CheckConstraint(
            "sensitivity IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')",
            name=op.f("ck_evidence_artifact_sensitivity_allowed"),
        ),
        sa.CheckConstraint(
            "publication_absence_reason IS NULL OR publication_absence_reason IN "
            "('NOT_PROVIDED','NOT_APPLICABLE','POLICY_RESTRICTED','EXTRACTION_FAILED')",
            name=op.f("ck_evidence_artifact_publication_absence_reason_allowed"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(published_at, publication_absence_reason) = 1",
            name=op.f("ck_evidence_artifact_publication_explicit"),
        ),
        sa.CheckConstraint(
            "published_at IS NULL OR published_at <= retrieved_at",
            name=op.f("ck_evidence_artifact_publication_order"),
        ),
        sa.CheckConstraint(
            "created_at >= retrieved_at", name=op.f("ck_evidence_artifact_creation_order")
        ),
        sa.CheckConstraint(
            "original_byte_length > 0",
            name=op.f("ck_evidence_artifact_byte_length_positive"),
        ),
        sa.CheckConstraint(
            "(storage_mode = 'OBJECT' AND storage_reference IS NOT NULL "
            "AND storage_reference LIKE 'workspace/' || workspace_id::text || '/%') OR "
            "(storage_mode <> 'OBJECT' AND storage_reference IS NULL)",
            name=op.f("ck_evidence_artifact_storage_reference_consistent"),
        ),
        sa.CheckConstraint(
            "(retention_mode = 'UNTIL' AND retention_until > retrieved_at) OR "
            "(retention_mode <> 'UNTIL' AND retention_until IS NULL)",
            name=op.f("ck_evidence_artifact_retention_until_consistent"),
        ),
        sa.CheckConstraint(
            "retention_mode <> 'PROHIBITED' OR "
            "storage_mode IN ('REFERENCE_ONLY', 'EPHEMERAL_PROCESSING')",
            name=op.f("ck_evidence_artifact_prohibited_retention_consistent"),
        ),
        sa.CheckConstraint(
            "NOT (display_mode IN ('REFERENCE_ONLY', 'PROHIBITED') "
            "AND storage_mode = 'EXCERPT_ONLY')",
            name=op.f("ck_evidence_artifact_display_storage_consistent"),
        ),
        sa.CheckConstraint(
            "origin_fingerprint ~ '^[0-9a-f]{64}$' "
            "AND original_content_sha256 ~ '^[0-9a-f]{64}$' "
            "AND artifact_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_evidence_artifact_digests_format"),
        ),
        sa.CheckConstraint(
            "schema_version = 1", name=op.f("ck_evidence_artifact_schema_supported")
        ),
    )
    op.create_index(
        "ix_evidence_artifact_workspace_investigation",
        "evidence_artifact",
        ["workspace_id", "investigation_id"],
    )
    op.create_table(
        "evidence",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence")),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            "investigation_id",
            name=op.f("uq_evidence_id_workspace_id_investigation_id"),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "command_id",
            name=op.f("uq_evidence_workspace_id_command_id"),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "series_id",
            "version",
            name=op.f("uq_evidence_workspace_id_series_id_version"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("fk_evidence_workspace"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id", "workspace_id"],
            ["investigation.id", "investigation.workspace_id"],
            name=op.f("fk_evidence_investigation_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_company_id", "workspace_id"],
            ["company.id", "company.workspace_id"],
            name=op.f("fk_evidence_company_scope"),
            ondelete="RESTRICT",
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
            name=op.f("fk_evidence_decision_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id", "workspace_id", "investigation_id"],
            [
                "evidence_artifact.id",
                "evidence_artifact.workspace_id",
                "evidence_artifact.investigation_id",
            ],
            name=op.f("fk_evidence_artifact_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["series_id", "workspace_id", "investigation_id"],
            ["evidence.id", "evidence.workspace_id", "evidence.investigation_id"],
            name=op.f("fk_evidence_series_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_evidence_id", "workspace_id", "investigation_id"],
            ["evidence.id", "evidence.workspace_id", "evidence.investigation_id"],
            name=op.f("fk_evidence_supersedes_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user_account.id"],
            name=op.f("fk_evidence_actor"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_evidence_version_positive")),
        sa.CheckConstraint(
            "(version = 1 AND series_id = id AND supersedes_evidence_id IS NULL) OR "
            "(version > 1 AND series_id <> id AND supersedes_evidence_id IS NOT NULL)",
            name=op.f("ck_evidence_version_chain_shape"),
        ),
        sa.CheckConstraint(
            "kind IN ('TEXT','STRUCTURED_DATA','IMAGE','EXTERNAL_REFERENCE')",
            name=op.f("ck_evidence_kind_allowed"),
        ),
        sa.CheckConstraint(
            "locator_type IN ('PAGE_TEXT','PDF_REGION','HTML_SELECTOR','JSON_POINTER',"
            "'SPREADSHEET_CELL','IMAGE_REGION','EXTERNAL_REFERENCE')",
            name=op.f("ck_evidence_locator_type_allowed"),
        ),
        sa.CheckConstraint(
            "admissibility_status = 'PENDING'",
            name=op.f("ck_evidence_admissibility_pending"),
        ),
        sa.CheckConstraint(
            "matching_policy_version >= 1",
            name=op.f("ck_evidence_matching_policy_version_positive"),
        ),
        sa.CheckConstraint(
            "command_digest ~ '^[0-9a-f]{64}$' AND content_sha256 ~ '^[0-9a-f]{64}$' "
            "AND evidence_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_evidence_digests_format"),
        ),
        sa.CheckConstraint("schema_version = 1", name=op.f("ck_evidence_schema_supported")),
    )
    op.create_index(
        "ix_evidence_workspace_investigation",
        "evidence",
        ["workspace_id", "investigation_id"],
    )
    op.create_index("ix_evidence_workspace_series", "evidence", ["workspace_id", "series_id"])
    op.create_table(
        "evidence_lifecycle_event",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_lifecycle_event")),
        sa.UniqueConstraint(
            "workspace_id",
            "command_id",
            name=op.f("uq_evidence_lifecycle_event_workspace_id_command_id"),
        ),
        sa.UniqueConstraint(
            "evidence_id",
            "event_type",
            name=op.f("uq_evidence_lifecycle_event_evidence_id_event_type"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("fk_evidence_lifecycle_event_workspace"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id", "workspace_id"],
            ["investigation.id", "investigation.workspace_id"],
            name=op.f("fk_evidence_lifecycle_event_investigation_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "workspace_id", "investigation_id"],
            ["evidence.id", "evidence.workspace_id", "evidence.investigation_id"],
            name=op.f("fk_evidence_lifecycle_event_evidence_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["related_evidence_id", "workspace_id", "investigation_id"],
            ["evidence.id", "evidence.workspace_id", "evidence.investigation_id"],
            name=op.f("fk_evidence_lifecycle_event_related_evidence_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["user_account.id"],
            name=op.f("fk_evidence_lifecycle_event_actor"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "event_type IN ('SUPERSEDED','REVOKED')",
            name=op.f("ck_evidence_lifecycle_event_event_type_allowed"),
        ),
        sa.CheckConstraint(
            "reason IN ('CORRECTION','SOURCE_WITHDRAWN','CONTENT_INVALID','ENTITY_MISMATCH',"
            "'POLICY_RESTRICTED','DUPLICATE')",
            name=op.f("ck_evidence_lifecycle_event_reason_allowed"),
        ),
        sa.CheckConstraint(
            "(event_type = 'SUPERSEDED' AND reason = 'CORRECTION' "
            "AND related_evidence_id IS NOT NULL AND related_evidence_id <> evidence_id) OR "
            "(event_type = 'REVOKED' AND reason <> 'CORRECTION' "
            "AND related_evidence_id IS NULL)",
            name=op.f("ck_evidence_lifecycle_event_event_shape"),
        ),
        sa.CheckConstraint(
            "command_digest ~ '^[0-9a-f]{64}$' AND event_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_evidence_lifecycle_event_digests_format"),
        ),
        sa.CheckConstraint(
            "schema_version = 1",
            name=op.f("ck_evidence_lifecycle_event_schema_supported"),
        ),
    )
    op.create_index(
        "ix_evidence_event_workspace_investigation",
        "evidence_lifecycle_event",
        ["workspace_id", "investigation_id"],
    )


def downgrade() -> None:
    """Refuse to erase any immutable evidence history."""

    if not context.is_offline_mode() and op.get_bind().scalar(
        sa.text("SELECT count(*) FROM evidence_artifact")
    ):
        raise RuntimeError("Cannot downgrade F5.1 while canonical evidence exists.")
    op.drop_table("evidence_lifecycle_event")
    op.drop_table("evidence")
    op.drop_table("evidence_artifact")
    op.drop_constraint(
        op.f("uq_entity_resolution_decision_id_workspace_id_investigation_id_company_id"),
        "entity_resolution_decision",
        type_="unique",
    )
