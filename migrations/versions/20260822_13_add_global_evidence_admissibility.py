"""Add immutable global Evidence admissibility decisions.

Revision ID: 20260822_13
Revises: 20260821_12
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "20260822_13"
down_revision: str | None = "20260821_12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist exact-version append-only F5.3 decisions."""

    op.create_unique_constraint(
        "uq_evidence_admissibility_scope",
        "evidence",
        [
            "id",
            "series_id",
            "version",
            "workspace_id",
            "investigation_id",
            "subject_company_id",
            "entity_resolution_decision_id",
        ],
    )
    op.create_table(
        "evidence_admissibility_decision",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_resolution_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_series_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_version", sa.Integer(), nullable=False),
        sa.Column("evidence_digest", sa.String(length=64), nullable=False),
        sa.Column("decision_sequence", sa.Integer(), nullable=False),
        sa.Column("supersedes_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("policy_id", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("admission_basis", sa.String(length=64), nullable=False),
        sa.Column("controlled_trust_root_id", sa.String(length=128), nullable=False),
        sa.Column("controlled_trust_root_version", sa.Integer(), nullable=False),
        sa.Column("controlled_trust_root_digest", sa.String(length=64), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_digest", sa.String(length=64), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_digest", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_admissibility_decision")),
        sa.UniqueConstraint(
            "workspace_id",
            "command_id",
            name=op.f("uq_evidence_admissibility_decision_workspace_id_command_id"),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "evidence_id",
            "decision_sequence",
            name=op.f(
                "uq_evidence_admissibility_decision_workspace_id_evidence_id_decision_sequence"
            ),
        ),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            "evidence_id",
            "evidence_series_id",
            "evidence_version",
            name="uq_admissibility_predecessor_scope",
        ),
        sa.ForeignKeyConstraint(
            [
                "evidence_id",
                "evidence_series_id",
                "evidence_version",
                "workspace_id",
                "investigation_id",
                "subject_company_id",
                "entity_resolution_decision_id",
            ],
            [
                "evidence.id",
                "evidence.series_id",
                "evidence.version",
                "evidence.workspace_id",
                "evidence.investigation_id",
                "evidence.subject_company_id",
                "evidence.entity_resolution_decision_id",
            ],
            name="fk_admissibility_exact_evidence_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "supersedes_decision_id",
                "workspace_id",
                "evidence_id",
                "evidence_series_id",
                "evidence_version",
            ],
            [
                "evidence_admissibility_decision.id",
                "evidence_admissibility_decision.workspace_id",
                "evidence_admissibility_decision.evidence_id",
                "evidence_admissibility_decision.evidence_series_id",
                "evidence_admissibility_decision.evidence_version",
            ],
            name="fk_admissibility_predecessor_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["user_account.id"],
            name="fk_admissibility_actor",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "decision_sequence >= 1 AND ((decision_sequence = 1 AND "
            "supersedes_decision_id IS NULL) OR (decision_sequence > 1 AND "
            "supersedes_decision_id IS NOT NULL))",
            name=op.f("ck_evidence_admissibility_decision_sequence_predecessor_shape"),
        ),
        sa.CheckConstraint(
            "outcome IN ('ADMISSIBLE','RESTRICTED','REJECTED')",
            name=op.f("ck_evidence_admissibility_decision_outcome_allowed"),
        ),
        sa.CheckConstraint(
            "reason_code IN ('CONTROLLED_TEST_EVIDENCE_ADMITTED',"
            "'POLICY_OR_VERIFIABILITY_RESTRICTED','CONTENT_OR_CONTEXT_REJECTED')",
            name=op.f("ck_evidence_admissibility_decision_reason_allowed"),
        ),
        sa.CheckConstraint(
            "(outcome = 'ADMISSIBLE' AND reason_code = "
            "'CONTROLLED_TEST_EVIDENCE_ADMITTED') OR (outcome = 'RESTRICTED' AND "
            "reason_code = 'POLICY_OR_VERIFIABILITY_RESTRICTED') OR "
            "(outcome = 'REJECTED' AND reason_code = 'CONTENT_OR_CONTEXT_REJECTED')",
            name=op.f("ck_evidence_admissibility_decision_outcome_reason_compatible"),
        ),
        sa.CheckConstraint(
            "(outcome = 'ADMISSIBLE' AND (valid_until IS NULL OR valid_until > decided_at)) "
            "OR (outcome IN ('RESTRICTED','REJECTED') AND valid_until IS NULL)",
            name=op.f("ck_evidence_admissibility_decision_expiration_valid"),
        ),
        sa.CheckConstraint(
            "policy_id = 'F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1' AND policy_version = 1",
            name=op.f("ck_evidence_admissibility_decision_policy_supported"),
        ),
        sa.CheckConstraint(
            "purpose = 'INTERNAL_FACTUAL_EVIDENCE_USE'",
            name=op.f("ck_evidence_admissibility_decision_purpose_supported"),
        ),
        sa.CheckConstraint(
            "admission_basis = 'CONTROLLED_TEST_EVIDENCE'",
            name=op.f("ck_evidence_admissibility_decision_basis_supported"),
        ),
        sa.CheckConstraint(
            "controlled_trust_root_id = 'F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1' "
            "AND controlled_trust_root_version = 1 AND controlled_trust_root_digest = "
            "'44637895ffa8a3c6758a0a63fb33bff29eb73090a606f12f990d4342bd24639d'",
            name=op.f("ck_evidence_admissibility_decision_trust_root_supported"),
        ),
        sa.CheckConstraint(
            "evidence_digest ~ '^[0-9a-f]{64}$' AND controlled_trust_root_digest ~ "
            "'^[0-9a-f]{64}$' AND command_digest ~ '^[0-9a-f]{64}$' AND "
            "decision_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_evidence_admissibility_decision_digests_format"),
        ),
        sa.CheckConstraint(
            "evidence_version >= 1 AND schema_version = 1",
            name=op.f("ck_evidence_admissibility_decision_versions_supported"),
        ),
    )
    op.create_index(
        "ix_admissibility_workspace_evidence_decided_at",
        "evidence_admissibility_decision",
        ["workspace_id", "evidence_id", "decided_at"],
    )
    op.create_index(
        "ix_admissibility_workspace_investigation_decided_at",
        "evidence_admissibility_decision",
        ["workspace_id", "investigation_id", "decided_at"],
    )
    op.create_index(
        "ix_admissibility_workspace_predecessor",
        "evidence_admissibility_decision",
        ["workspace_id", "supersedes_decision_id"],
    )
    op.create_index(
        "ix_admissibility_workspace_actor",
        "evidence_admissibility_decision",
        ["workspace_id", "decided_by"],
    )


def downgrade() -> None:
    """Refuse to erase immutable admissibility history."""

    if not context.is_offline_mode():
        count = op.get_bind().scalar(
            sa.text("SELECT count(*) FROM evidence_admissibility_decision")
        )
        if count:
            raise RuntimeError("Cannot downgrade F5.3 while admissibility history exists.")
    op.drop_table("evidence_admissibility_decision")
    op.drop_constraint("uq_evidence_admissibility_scope", "evidence", type_="unique")
