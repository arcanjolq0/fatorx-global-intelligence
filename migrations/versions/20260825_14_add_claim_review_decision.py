"""Add immutable F5.4 exact-version Claim review decisions.

Revision ID: 20260825_14
Revises: 20260822_13
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "20260825_14"
down_revision: str | None = "20260822_13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the sole append-only F5.4 persistence relation."""

    op.create_unique_constraint(
        "uq_claim_review_exact_scope",
        "claim",
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
        "claim_review_decision",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_resolution_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_series_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_version", sa.Integer(), nullable=False),
        sa.Column("claim_digest", sa.String(length=64), nullable=False),
        sa.Column("decision_sequence", sa.Integer(), nullable=False),
        sa.Column("supersedes_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("policy_id", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("review_basis_digest", sa.String(length=64), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_digest", sa.String(length=64), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_digest", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claim_review_decision")),
        sa.UniqueConstraint(
            "workspace_id", "command_id", name=op.f("uq_claim_review_decision_workspace_command")
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "claim_id",
            "decision_sequence",
            name=op.f("uq_claim_review_decision_workspace_claim_sequence"),
        ),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            "claim_id",
            "claim_series_id",
            "claim_version",
            name="uq_claim_review_predecessor_scope",
        ),
        sa.ForeignKeyConstraint(
            [
                "claim_id",
                "claim_series_id",
                "claim_version",
                "workspace_id",
                "investigation_id",
                "subject_company_id",
                "entity_resolution_decision_id",
            ],
            [
                "claim.id",
                "claim.series_id",
                "claim.version",
                "claim.workspace_id",
                "claim.investigation_id",
                "claim.subject_company_id",
                "claim.entity_resolution_decision_id",
            ],
            name="fk_claim_review_exact_claim_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "supersedes_decision_id",
                "workspace_id",
                "claim_id",
                "claim_series_id",
                "claim_version",
            ],
            [
                "claim_review_decision.id",
                "claim_review_decision.workspace_id",
                "claim_review_decision.claim_id",
                "claim_review_decision.claim_series_id",
                "claim_review_decision.claim_version",
            ],
            name="fk_claim_review_predecessor_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["decided_by"], ["user_account.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "decision_sequence >= 1 AND ((decision_sequence = 1 AND "
            "supersedes_decision_id IS NULL) OR (decision_sequence > 1 AND "
            "supersedes_decision_id IS NOT NULL))",
            name=op.f("ck_claim_review_decision_sequence_predecessor_shape"),
        ),
        sa.CheckConstraint(
            "outcome IN ('ACCEPTED_FOR_INTERNAL_FACTUAL_USE',"
            "'REJECTED_FOR_INTERNAL_FACTUAL_USE','NEEDS_CORRECTION')",
            name=op.f("ck_claim_review_decision_outcome_allowed"),
        ),
        sa.CheckConstraint(
            "reason_code IN ('FACTUAL_BASIS_ACCEPTED',"
            "'INTERNAL_FACTUAL_USE_REJECTED','CLAIM_CORRECTION_REQUIRED')",
            name=op.f("ck_claim_review_decision_reason_allowed"),
        ),
        sa.CheckConstraint(
            "(outcome = 'ACCEPTED_FOR_INTERNAL_FACTUAL_USE' AND "
            "reason_code = 'FACTUAL_BASIS_ACCEPTED') OR "
            "(outcome = 'REJECTED_FOR_INTERNAL_FACTUAL_USE' AND "
            "reason_code = 'INTERNAL_FACTUAL_USE_REJECTED') OR "
            "(outcome = 'NEEDS_CORRECTION' AND "
            "reason_code = 'CLAIM_CORRECTION_REQUIRED')",
            name=op.f("ck_claim_review_decision_outcome_reason_compatible"),
        ),
        sa.CheckConstraint(
            "policy_id = 'F5_4_INTERNAL_FACTUAL_CLAIM_REVIEW_V1' AND policy_version = 1",
            name=op.f("ck_claim_review_decision_policy_supported"),
        ),
        sa.CheckConstraint(
            "purpose = 'INTERNAL_FACTUAL_CLAIM_USE'",
            name=op.f("ck_claim_review_decision_purpose_supported"),
        ),
        sa.CheckConstraint(
            "claim_digest ~ '^[0-9a-f]{64}$' AND review_basis_digest ~ "
            "'^[0-9a-f]{64}$' AND command_digest ~ '^[0-9a-f]{64}$' AND "
            "decision_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_claim_review_decision_digests_format"),
        ),
        sa.CheckConstraint(
            "claim_version >= 1 AND schema_version = 1",
            name=op.f("ck_claim_review_decision_versions_supported"),
        ),
    )
    op.create_index(
        "ix_claim_review_workspace_claim_decided_at",
        "claim_review_decision",
        ["workspace_id", "claim_id", "decided_at"],
    )
    op.create_index(
        "ix_claim_review_workspace_investigation_decided_at",
        "claim_review_decision",
        ["workspace_id", "investigation_id", "decided_at"],
    )
    op.create_index(
        "ix_claim_review_workspace_predecessor",
        "claim_review_decision",
        ["workspace_id", "supersedes_decision_id"],
    )
    op.create_index(
        "ix_claim_review_workspace_actor", "claim_review_decision", ["workspace_id", "decided_by"]
    )


def downgrade() -> None:
    """Refuse to erase immutable Claim-review history."""

    if not context.is_offline_mode():
        count = op.get_bind().scalar(sa.text("SELECT count(*) FROM claim_review_decision"))
        if count:
            raise RuntimeError("Cannot downgrade F5.4 while Claim-review history exists.")
    op.drop_table("claim_review_decision")
    op.drop_constraint("uq_claim_review_exact_scope", "claim", type_="unique")
