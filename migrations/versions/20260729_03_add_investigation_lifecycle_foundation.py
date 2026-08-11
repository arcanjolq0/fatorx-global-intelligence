"""Add the transactional F4.1 investigation lifecycle foundation.

Revision ID: 20260729_03
Revises: 20260728_02
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260729_03"
down_revision: str | None = "20260728_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a versioned input snapshot, CAS support, and append-only command ledger."""

    op.add_column(
        "investigation",
        sa.Column(
            "input_snapshot",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "investigation",
        sa.Column("input_schema_version", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "investigation",
        sa.Column("input_digest", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        op.f("uq_investigation_id_workspace_id"),
        "investigation",
        ["id", "workspace_id"],
    )
    op.create_check_constraint(
        op.f("ck_investigation_input_snapshot_fields_consistency"),
        "investigation",
        "(input_snapshot IS NULL) = (input_schema_version IS NULL) AND "
        "(input_snapshot IS NULL) = (input_digest IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_investigation_input_schema_version_supported"),
        "investigation",
        "input_schema_version IS NULL OR input_schema_version = 1",
    )
    op.create_check_constraint(
        op.f("ck_investigation_input_digest_format"),
        "investigation",
        "input_digest IS NULL OR input_digest ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        op.f("ck_investigation_created_input_absent"),
        "investigation",
        "state <> 'CREATED' OR input_snapshot IS NULL",
    )
    op.create_check_constraint(
        op.f("ck_investigation_started_input_or_company"),
        "investigation",
        "state NOT IN ('IDENTIFYING', 'WAITING_FOR_ENTITY_CONFIRMATION', 'PLANNING', "
        "'COLLECTING', 'NORMALIZING', 'VERIFYING', 'ANALYZING', 'WAITING_FOR_REVIEW', "
        "'COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED') "
        "OR input_snapshot IS NOT NULL OR confirmed_company_id IS NOT NULL",
        postgresql_not_valid=True,
    )

    op.create_table(
        "investigation_transition",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_type", sa.String(length=32), nullable=False),
        sa.Column("state_before", sa.String(length=48), nullable=False),
        sa.Column("version_before", sa.Integer(), nullable=False),
        sa.Column("state_after", sa.String(length=48), nullable=False),
        sa.Column("version_after", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("command_digest", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "command_type IN ('START_IDENTIFICATION', 'CANCEL_INVESTIGATION')",
            name=op.f("ck_investigation_transition_command_type_allowed"),
        ),
        sa.CheckConstraint(
            "state_before IN ('CREATED', 'IDENTIFYING', 'WAITING_FOR_ENTITY_CONFIRMATION', "
            "'PLANNING', 'COLLECTING', 'NORMALIZING', 'VERIFYING', 'ANALYZING', "
            "'WAITING_FOR_REVIEW', 'COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', "
            "'CANCELLED')",
            name=op.f("ck_investigation_transition_state_before_allowed"),
        ),
        sa.CheckConstraint(
            "state_after IN ('CREATED', 'IDENTIFYING', 'WAITING_FOR_ENTITY_CONFIRMATION', "
            "'PLANNING', 'COLLECTING', 'NORMALIZING', 'VERIFYING', 'ANALYZING', "
            "'WAITING_FOR_REVIEW', 'COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', "
            "'CANCELLED')",
            name=op.f("ck_investigation_transition_state_after_allowed"),
        ),
        sa.CheckConstraint(
            "version_before >= 1 AND version_after = version_before + 1",
            name=op.f("ck_investigation_transition_version_increment"),
        ),
        sa.CheckConstraint(
            "command_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_investigation_transition_command_digest_format"),
        ),
        sa.CheckConstraint(
            "(command_type = 'START_IDENTIFICATION' "
            "AND state_before = 'CREATED' "
            "AND state_after = 'IDENTIFYING' "
            "AND reason_code IS NULL) OR "
            "(command_type = 'CANCEL_INVESTIGATION' "
            "AND state_before NOT IN ('COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', "
            "'CANCELLED') "
            "AND state_after = 'CANCELLED' "
            "AND reason_code IN ('USER_REQUESTED', 'DUPLICATE_REQUEST', "
            "'NO_LONGER_REQUIRED', 'POLICY_REQUIRED'))",
            name=op.f("ck_investigation_transition_command_transition_shape"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["user_account.id"],
            name="fk_investigation_transition_actor_user_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id", "workspace_id"],
            ["investigation.id", "investigation.workspace_id"],
            name="fk_investigation_transition_investigation_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name="fk_investigation_transition_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investigation_transition")),
        sa.UniqueConstraint(
            "workspace_id",
            "command_id",
            name=op.f("uq_investigation_transition_workspace_id_command_id"),
        ),
    )
    op.create_index(
        "ix_investigation_transition_workspace_investigation_version",
        "investigation_transition",
        ["workspace_id", "investigation_id", "version_after"],
        unique=False,
    )
    op.create_index(
        "ix_investigation_transition_workspace_occurred_at",
        "investigation_transition",
        ["workspace_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove only F4.1 structures and restore the F3.3 schema revision."""

    op.drop_index(
        "ix_investigation_transition_workspace_occurred_at",
        table_name="investigation_transition",
    )
    op.drop_index(
        "ix_investigation_transition_workspace_investigation_version",
        table_name="investigation_transition",
    )
    op.drop_table("investigation_transition")
    op.drop_constraint(
        op.f("ck_investigation_started_input_or_company"),
        "investigation",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_investigation_created_input_absent"),
        "investigation",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_investigation_input_digest_format"),
        "investigation",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_investigation_input_schema_version_supported"),
        "investigation",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_investigation_input_snapshot_fields_consistency"),
        "investigation",
        type_="check",
    )
    op.drop_constraint(
        op.f("uq_investigation_id_workspace_id"),
        "investigation",
        type_="unique",
    )
    op.drop_column("investigation", "input_digest")
    op.drop_column("investigation", "input_schema_version")
    op.drop_column("investigation", "input_snapshot")
