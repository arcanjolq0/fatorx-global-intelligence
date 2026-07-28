"""Create the initial workspace, company, and investigation schema.

Revision ID: 20260728_01
Revises: None
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260728_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create only the three domain tables approved for F2.2."""

    op.create_table(
        "workspace",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("retention_policy_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(btrim(name)) > 0",
            name=op.f("ck_workspace_name_not_blank"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(retention_policy_version)) > 0",
            name=op.f("ck_workspace_retention_policy_version_not_blank"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'ARCHIVED')",
            name=op.f("ck_workspace_status_allowed"),
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_workspace_updated_at_order"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace")),
    )
    op.create_index("ix_workspace_status", "workspace", ["status"], unique=False)

    op.create_table(
        "company",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("trade_name", sa.Text(), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("legal_form", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("incorporated_on", sa.Date(), nullable=True),
        sa.Column("dissolved_on", sa.Date(), nullable=True),
        sa.Column("official_domain", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(btrim(legal_name)) > 0",
            name=op.f("ck_company_legal_name_not_blank"),
        ),
        sa.CheckConstraint(
            "trade_name IS NULL OR char_length(btrim(trade_name)) > 0",
            name=op.f("ck_company_trade_name_not_blank"),
        ),
        sa.CheckConstraint(
            "legal_form IS NULL OR char_length(btrim(legal_form)) > 0",
            name=op.f("ck_company_legal_form_not_blank"),
        ),
        sa.CheckConstraint(
            "country_code ~ '^[A-Z]{2}$'",
            name=op.f("ck_company_country_code_format"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE', 'DISSOLVED')",
            name=op.f("ck_company_status_allowed"),
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_company_updated_at_order"),
        ),
        sa.CheckConstraint(
            "dissolved_on IS NULL OR incorporated_on IS NULL OR dissolved_on >= incorporated_on",
            name=op.f("ck_company_dissolution_date_order"),
        ),
        sa.CheckConstraint(
            "(status = 'DISSOLVED' AND dissolved_on IS NOT NULL) "
            "OR (status <> 'DISSOLVED' AND dissolved_on IS NULL)",
            name=op.f("ck_company_dissolution_status_consistency"),
        ),
        sa.CheckConstraint(
            "official_domain IS NULL OR ("
            "char_length(official_domain) <= 253 AND "
            "official_domain ~ "
            "'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
            "(\\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$'"
            ")",
            name=op.f("ck_company_official_domain_format"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name="fk_company_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company")),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            name=op.f("uq_company_id_workspace_id"),
        ),
    )
    op.create_index(
        "ix_company_workspace_id_id",
        "company",
        ["workspace_id", "id"],
        unique=False,
    )

    op.create_table(
        "investigation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_code", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("state", sa.String(length=48), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("confirmed_company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("budget_amount", sa.Numeric(), nullable=True),
        sa.Column("budget_currency", sa.String(length=3), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(btrim(profile_code)) > 0",
            name=op.f("ck_investigation_profile_code_not_blank"),
        ),
        sa.CheckConstraint(
            "country_code ~ '^[A-Z]{2}$'",
            name=op.f("ck_investigation_country_code_format"),
        ),
        sa.CheckConstraint(
            "state IN ('CREATED', 'IDENTIFYING', 'WAITING_FOR_ENTITY_CONFIRMATION', "
            "'PLANNING', 'COLLECTING', 'NORMALIZING', 'VERIFYING', 'ANALYZING', "
            "'WAITING_FOR_REVIEW', 'COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', "
            "'CANCELLED')",
            name=op.f("ck_investigation_state_allowed"),
        ),
        sa.CheckConstraint(
            "state_version >= 1",
            name=op.f("ck_investigation_state_version_positive"),
        ),
        sa.CheckConstraint(
            "(budget_amount IS NULL) = (budget_currency IS NULL)",
            name=op.f("ck_investigation_budget_pair"),
        ),
        sa.CheckConstraint(
            "budget_amount IS NULL OR budget_amount NOT IN "
            "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
            name=op.f("ck_investigation_budget_amount_finite"),
        ),
        sa.CheckConstraint(
            "budget_currency IS NULL OR budget_currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_investigation_budget_currency_format"),
        ),
        sa.CheckConstraint(
            "deadline_at IS NULL OR deadline_at >= created_at",
            name=op.f("ck_investigation_deadline_order"),
        ),
        sa.CheckConstraint(
            "started_at IS NULL OR started_at >= created_at",
            name=op.f("ck_investigation_started_at_order"),
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR started_at IS NOT NULL",
            name=op.f("ck_investigation_completion_requires_start"),
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name=op.f("ck_investigation_completed_at_order"),
        ),
        sa.CheckConstraint(
            "(state = 'CREATED') = (started_at IS NULL)",
            name=op.f("ck_investigation_state_start_consistency"),
        ),
        sa.CheckConstraint(
            "(state IN ('COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED')) "
            "= (completed_at IS NOT NULL)",
            name=op.f("ck_investigation_state_completion_consistency"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name="fk_investigation_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_company_id", "workspace_id"],
            ["company.id", "company.workspace_id"],
            name="fk_investigation_confirmed_company_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investigation")),
    )
    op.create_index(
        "ix_investigation_workspace_id_state",
        "investigation",
        ["workspace_id", "state"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the initial domain schema in reverse dependency order."""

    op.drop_index(
        "ix_investigation_workspace_id_state",
        table_name="investigation",
    )
    op.drop_table("investigation")
    op.drop_index("ix_company_workspace_id_id", table_name="company")
    op.drop_table("company")
    op.drop_index("ix_workspace_status", table_name="workspace")
    op.drop_table("workspace")
