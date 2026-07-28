"""Create internal identities, memberships, and minimal audit events.

Revision ID: 20260728_02
Revises: 20260728_01
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260728_02"
down_revision: str | None = "20260728_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create only the three relational structures approved for F2.4.1."""

    op.create_table(
        "user_account",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "email = lower(email) AND email = btrim(email)",
            name=op.f("ck_user_account_email_canonical"),
        ),
        sa.CheckConstraint(
            "email ~ '^[^@]+@[^@]+$' AND email !~ '[[:space:]]' AND email !~ '[[:cntrl:]]'",
            name=op.f("ck_user_account_email_format"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(display_name)) > 0",
            name=op.f("ck_user_account_display_name_not_blank"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED')",
            name=op.f("ck_user_account_status_allowed"),
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_user_account_updated_at_order"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_account")),
        sa.UniqueConstraint("email", name=op.f("uq_user_account_email")),
    )

    op.create_table(
        "workspace_membership",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role IN ('OWNER', 'ADMIN', 'ANALYST', 'VIEWER')",
            name=op.f("ck_workspace_membership_role_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')",
            name=op.f("ck_workspace_membership_status_allowed"),
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_workspace_membership_updated_at_order"),
        ),
        sa.CheckConstraint(
            "deactivated_at IS NULL OR deactivated_at >= created_at",
            name=op.f("ck_workspace_membership_deactivated_at_order"),
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND deactivated_at IS NULL) "
            "OR (status = 'INACTIVE' AND deactivated_at IS NOT NULL)",
            name=op.f("ck_workspace_membership_status_deactivation_consistency"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.id"],
            name="fk_workspace_membership_user_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name="fk_workspace_membership_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_membership")),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            name=op.f("uq_workspace_membership_workspace_id_user_id"),
        ),
    )
    op.create_index(
        "ix_workspace_membership_workspace_id_status",
        "workspace_membership",
        ["workspace_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_membership_user_id_workspace_id",
        "workspace_membership",
        ["user_id", "workspace_id"],
        unique=False,
    )

    op.create_table(
        "audit_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_code", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action_code ~ '^[A-Z][A-Z0-9_.:-]*$'",
            name=op.f("ck_audit_event_action_code_format"),
        ),
        sa.CheckConstraint(
            "resource_type IN ('WORKSPACE', 'USER', 'MEMBERSHIP', 'COMPANY', 'INVESTIGATION')",
            name=op.f("ck_audit_event_resource_type_allowed"),
        ),
        sa.CheckConstraint(
            "outcome IN ('SUCCESS', 'DENIED', 'FAILURE')",
            name=op.f("ck_audit_event_outcome_allowed"),
        ),
        sa.CheckConstraint(
            "reason_code IS NULL OR reason_code ~ '^[A-Z][A-Z0-9_.:-]*$'",
            name=op.f("ck_audit_event_reason_code_format"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["user_account.id"],
            name="fk_audit_event_actor_user_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name="fk_audit_event_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_event")),
    )
    op.create_index(
        "ix_audit_event_workspace_id_occurred_at",
        "audit_event",
        ["workspace_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_event_correlation_id",
        "audit_event",
        ["correlation_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove F2.4.1 structures in reverse dependency order."""

    op.drop_index("ix_audit_event_correlation_id", table_name="audit_event")
    op.drop_index("ix_audit_event_workspace_id_occurred_at", table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_index(
        "ix_workspace_membership_user_id_workspace_id",
        table_name="workspace_membership",
    )
    op.drop_index(
        "ix_workspace_membership_workspace_id_status",
        table_name="workspace_membership",
    )
    op.drop_table("workspace_membership")
    op.drop_table("user_account")
