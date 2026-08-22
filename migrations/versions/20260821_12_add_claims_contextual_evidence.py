"""Add immutable Claims and contextual Evidence eligibility links.

Revision ID: 20260821_12
Revises: 20260814_11
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "20260821_12"
down_revision: str | None = "20260814_11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist append-only Claim versions and their exact Evidence links."""

    op.create_unique_constraint(
        "uq_evidence_claim_link_scope",
        "evidence",
        [
            "id",
            "workspace_id",
            "investigation_id",
            "subject_company_id",
            "entity_resolution_decision_id",
        ],
    )
    op.create_table(
        "claim",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("supersedes_claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_resolution_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_digest", sa.String(length=64), nullable=False),
        sa.Column("predicate_code", sa.String(length=64), nullable=False),
        sa.Column("predicate_version", sa.Integer(), nullable=False),
        sa.Column("value_type", sa.String(length=32), nullable=False),
        sa.Column("value_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("temporal_type", sa.String(length=32), nullable=False),
        sa.Column("temporal_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("criticality", sa.String(length=32), nullable=False),
        sa.Column("creation_method", sa.String(length=32), nullable=False),
        sa.Column("creation_method_version", sa.Integer(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correction_reason", sa.String(length=64), nullable=True),
        sa.Column("claim_digest", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claim")),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            "investigation_id",
            name=op.f("uq_claim_id_workspace_id_investigation_id"),
        ),
        sa.UniqueConstraint(
            "id",
            "version",
            "workspace_id",
            "investigation_id",
            "subject_company_id",
            "entity_resolution_decision_id",
            name="uq_claim_link_scope",
        ),
        sa.UniqueConstraint(
            "workspace_id", "command_id", name=op.f("uq_claim_workspace_id_command_id")
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "series_id",
            "version",
            name=op.f("uq_claim_workspace_id_series_id_version"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name="fk_claim_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id", "workspace_id"],
            ["investigation.id", "investigation.workspace_id"],
            name="fk_claim_investigation_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_company_id", "workspace_id"],
            ["company.id", "company.workspace_id"],
            name="fk_claim_company_scope",
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
            name="fk_claim_decision_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["series_id", "workspace_id", "investigation_id"],
            ["claim.id", "claim.workspace_id", "claim.investigation_id"],
            name="fk_claim_series_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_claim_id", "workspace_id", "investigation_id"],
            ["claim.id", "claim.workspace_id", "claim.investigation_id"],
            name="fk_claim_supersedes_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user_account.id"],
            name="fk_claim_actor",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_claim_version_positive")),
        sa.CheckConstraint(
            "(version = 1 AND series_id = id AND supersedes_claim_id IS NULL "
            "AND correction_reason IS NULL) OR "
            "(version > 1 AND series_id <> id AND supersedes_claim_id IS NOT NULL "
            "AND correction_reason IS NOT NULL)",
            name=op.f("ck_claim_version_chain_shape"),
        ),
        sa.CheckConstraint(
            "predicate_code IN ('LEGAL_NAME','REGISTRATION_STATUS','INCORPORATION_DATE',"
            "'COUNTRY_OF_REGISTRATION','REGISTRATION_IDENTIFIER')",
            name=op.f("ck_claim_predicate_allowed"),
        ),
        sa.CheckConstraint(
            "predicate_version = 1", name=op.f("ck_claim_predicate_version_supported")
        ),
        sa.CheckConstraint(
            "value_type IN ('TEXT','REGISTRATION_STATUS','DATE','COUNTRY_CODE',"
            "'REGISTRATION_IDENTIFIER')",
            name=op.f("ck_claim_value_type_allowed"),
        ),
        sa.CheckConstraint(
            "temporal_type IN ('POINT','PERIOD','UNDATED')",
            name=op.f("ck_claim_temporal_type_allowed"),
        ),
        sa.CheckConstraint(
            "criticality IN ('STANDARD','CRITICAL')",
            name=op.f("ck_claim_criticality_allowed"),
        ),
        sa.CheckConstraint(
            "creation_method = 'MANUAL'", name=op.f("ck_claim_creation_method_allowed")
        ),
        sa.CheckConstraint(
            "creation_method_version >= 1",
            name=op.f("ck_claim_method_version_positive"),
        ),
        sa.CheckConstraint(
            "correction_reason IS NULL OR correction_reason IN "
            "('VALUE_CORRECTION','TEMPORAL_CORRECTION','CRITICALITY_CORRECTION',"
            "'METHOD_CORRECTION','EVIDENCE_LINK_CORRECTION','MULTIPLE_FIELDS_CORRECTION')",
            name=op.f("ck_claim_correction_reason_allowed"),
        ),
        sa.CheckConstraint(
            "command_digest ~ '^[0-9a-f]{64}$' AND claim_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_claim_digests_format"),
        ),
        sa.CheckConstraint("schema_version = 1", name=op.f("ck_claim_schema_supported")),
    )
    op.create_index(
        "ix_claim_workspace_investigation",
        "claim",
        ["workspace_id", "investigation_id"],
    )
    op.create_index("ix_claim_workspace_series", "claim", ["workspace_id", "series_id"])
    op.create_table(
        "claim_evidence_link",
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_version", sa.Integer(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_resolution_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_digest", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("use_outcome", sa.String(length=32), nullable=False),
        sa.Column("use_reason", sa.String(length=64), nullable=False),
        sa.Column("policy_id", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("manifest_version", sa.Integer(), nullable=False),
        sa.Column("manifest_digest", sa.String(length=64), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("link_digest", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("claim_id", "evidence_id", name=op.f("pk_claim_evidence_link")),
        sa.ForeignKeyConstraint(
            [
                "claim_id",
                "claim_version",
                "workspace_id",
                "investigation_id",
                "subject_company_id",
                "entity_resolution_decision_id",
            ],
            [
                "claim.id",
                "claim.version",
                "claim.workspace_id",
                "claim.investigation_id",
                "claim.subject_company_id",
                "claim.entity_resolution_decision_id",
            ],
            name="fk_claim_evidence_link_claim_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "evidence_id",
                "workspace_id",
                "investigation_id",
                "subject_company_id",
                "entity_resolution_decision_id",
            ],
            [
                "evidence.id",
                "evidence.workspace_id",
                "evidence.investigation_id",
                "evidence.subject_company_id",
                "evidence.entity_resolution_decision_id",
            ],
            name="fk_claim_evidence_link_evidence_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["user_account.id"],
            name="fk_claim_evidence_link_requester",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "claim_version >= 1", name=op.f("ck_claim_evidence_link_claim_version_positive")
        ),
        sa.CheckConstraint(
            "role IN ('SUPPORTS','CONTRADICTS','QUALIFIES')",
            name=op.f("ck_claim_evidence_link_role_allowed"),
        ),
        sa.CheckConstraint(
            "use_outcome IN ('ELIGIBLE','RESTRICTED','REJECTED')",
            name=op.f("ck_claim_evidence_link_outcome_allowed"),
        ),
        sa.CheckConstraint(
            "use_reason IN ('CONTROLLED_EVIDENCE_ELIGIBLE','CONTROLLED_CORPUS_NOT_PROVEN',"
            "'CONTROLLED_EVIDENCE_NOT_PROVEN','STORAGE_MODE_RESTRICTED',"
            "'RETENTION_MODE_RESTRICTED','DISPLAY_MODE_RESTRICTED',"
            "'CONTENT_ORIGINAL_REQUIRED','USE_EXPLICITLY_PROHIBITED')",
            name=op.f("ck_claim_evidence_link_reason_allowed"),
        ),
        sa.CheckConstraint(
            "policy_id = 'F5_2_CONTROLLED_CORPUS_V1'",
            name=op.f("ck_claim_evidence_link_policy_id_supported"),
        ),
        sa.CheckConstraint(
            "policy_version = 1", name=op.f("ck_claim_evidence_link_policy_version_supported")
        ),
        sa.CheckConstraint(
            "purpose = 'INTERNAL_CLAIM_VERIFICATION'",
            name=op.f("ck_claim_evidence_link_purpose_supported"),
        ),
        sa.CheckConstraint(
            "manifest_version = 1",
            name=op.f("ck_claim_evidence_link_manifest_version_supported"),
        ),
        sa.CheckConstraint(
            "evidence_digest ~ '^[0-9a-f]{64}$' AND manifest_digest ~ '^[0-9a-f]{64}$' "
            "AND link_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_claim_evidence_link_digests_format"),
        ),
        sa.CheckConstraint(
            "schema_version = 1", name=op.f("ck_claim_evidence_link_schema_supported")
        ),
    )
    op.create_index(
        "ix_claim_evidence_link_workspace_claim",
        "claim_evidence_link",
        ["workspace_id", "claim_id"],
    )
    op.create_index(
        "ix_claim_evidence_link_workspace_evidence",
        "claim_evidence_link",
        ["workspace_id", "evidence_id"],
    )


def downgrade() -> None:
    """Refuse to erase immutable Claim history."""

    if not context.is_offline_mode():
        claim_count = op.get_bind().scalar(sa.text("SELECT count(*) FROM claim"))
        if claim_count:
            raise RuntimeError("Cannot downgrade F5.2 while Claim history exists.")
    op.drop_table("claim_evidence_link")
    op.drop_table("claim")
    op.drop_constraint("uq_evidence_claim_link_scope", "evidence", type_="unique")
