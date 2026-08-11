"""Add immutable deterministic investigation planning aggregates.

Revision ID: 20260801_06
Revises: 20260801_05
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_06"
down_revision: str | None = "20260801_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CAPABILITIES = (
    "'COMPANY_IDENTITY', 'COMPANY_REGISTRY', 'OWNERSHIP', 'CONTACTS', "
    "'FINANCIALS', 'INSOLVENCY', 'LEGAL_CASES', 'SANCTIONS', "
    "'ADVERSE_MEDIA', 'DOCUMENTS'"
)
_REASONS = (
    "'COMPANY_IDENTITY', 'BUSINESS_REGISTRATION', 'OWNERSHIP_STRUCTURE', "
    "'BUSINESS_CONTACTS', 'FINANCIAL_REVIEW', 'INSOLVENCY_REVIEW', "
    "'LEGAL_CASE_REVIEW', 'CONFIRMED_COMPANY_SANCTIONS', 'ADVERSE_MEDIA_REVIEW', "
    "'SUPPORTING_DOCUMENTS'"
)
_ACCESS_TYPES = "'API', 'FILE', 'WEB_PUBLIC', 'USER_UPLOAD'"


def upgrade() -> None:
    """Persist one immutable READY plan per investigation."""

    _extend_audit_event()
    _create_investigation_plan()
    _create_planned_capability()
    _create_planned_connector_option()


def _extend_audit_event() -> None:
    for column in (
        sa.Column("planning_command_id", postgresql.UUID(as_uuid=True)),
        sa.Column("investigation_plan_id", postgresql.UUID(as_uuid=True)),
        sa.Column("planned_capability_count", sa.SmallInteger()),
        sa.Column("planned_connector_option_count", sa.SmallInteger()),
        sa.Column("planning_policy_id", sa.String(length=64)),
        sa.Column("planning_policy_version", sa.Integer()),
        sa.Column("planning_maximum_estimated_cost_kind", sa.String(length=16)),
        sa.Column("planning_maximum_estimated_cost_amount", sa.Numeric()),
        sa.Column("planning_maximum_estimated_cost_currency", sa.String(length=3)),
    ):
        op.add_column("audit_event", column)
    op.create_check_constraint(
        op.f("ck_audit_event_investigation_planning_metadata_complete"),
        "audit_event",
        "num_nonnulls(planning_command_id, investigation_plan_id, "
        "planned_capability_count, planned_connector_option_count, planning_policy_id, "
        "planning_policy_version, planning_maximum_estimated_cost_kind) IN (0, 7)",
    )
    op.create_check_constraint(
        op.f("ck_audit_event_investigation_planning_metadata_valid"),
        "audit_event",
        "planning_command_id IS NULL OR (outcome = 'SUCCESS' "
        "AND resource_type = 'INVESTIGATION' "
        "AND planned_capability_count BETWEEN 1 AND 10 "
        "AND planned_connector_option_count BETWEEN 0 AND 1000 "
        "AND planning_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND planning_policy_version >= 1 "
        "AND planning_maximum_estimated_cost_kind IN ('KNOWN', 'UNKNOWN'))",
    )
    op.create_check_constraint(
        op.f("ck_audit_event_investigation_planning_cost_consistency"),
        "audit_event",
        "(planning_maximum_estimated_cost_amount IS NULL) = "
        "(planning_maximum_estimated_cost_currency IS NULL) AND "
        "(planning_maximum_estimated_cost_kind = 'KNOWN') = "
        "(planning_maximum_estimated_cost_amount IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_audit_event_investigation_planning_cost_non_negative"),
        "audit_event",
        "planning_maximum_estimated_cost_amount IS NULL OR "
        "planning_maximum_estimated_cost_amount >= 0",
    )
    op.create_check_constraint(
        op.f("ck_audit_event_investigation_planning_cost_finite"),
        "audit_event",
        "planning_maximum_estimated_cost_amount IS NULL OR "
        "planning_maximum_estimated_cost_amount NOT IN "
        "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
    )


def _create_investigation_plan() -> None:
    op.create_table(
        "investigation_plan",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_code", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("plan_version", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("budget_amount", sa.Numeric()),
        sa.Column("budget_currency", sa.String(length=3)),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("maximum_estimated_cost_kind", sa.String(length=16), nullable=False),
        sa.Column("maximum_estimated_cost_amount", sa.Numeric()),
        sa.Column("maximum_estimated_cost_currency", sa.String(length=3)),
        sa.Column("planning_policy_id", sa.String(length=64), nullable=False),
        sa.Column("planning_policy_version", sa.Integer(), nullable=False),
        sa.Column("planning_policy_snapshot", sa.Text(), nullable=False),
        sa.Column("planning_policy_digest", sa.String(length=64), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("company_snapshot_digest", sa.String(length=64), nullable=False),
        sa.Column("plan_digest", sa.String(length=64), nullable=False),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_digest", sa.String(length=64), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("investigation_state_version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investigation_plan")),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            "investigation_id",
            name=op.f("uq_investigation_plan_id_workspace_id_investigation_id"),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "investigation_id",
            name=op.f("uq_investigation_plan_workspace_id_investigation_id"),
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "command_id",
            name=op.f("uq_investigation_plan_workspace_id_command_id"),
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id", "workspace_id"],
            ["investigation.id", "investigation.workspace_id"],
            name="fk_investigation_plan_investigation_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "workspace_id"],
            ["company.id", "company.workspace_id"],
            name="fk_investigation_plan_company_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user_account.id"],
            name="fk_investigation_plan_created_by",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "plan_version = 1 AND schema_version = 1",
            name=op.f("ck_investigation_plan_versions_supported"),
        ),
        sa.CheckConstraint("status = 'READY'", name=op.f("ck_investigation_plan_status_ready")),
        sa.CheckConstraint(
            "char_length(btrim(profile_code)) > 0",
            name=op.f("ck_investigation_plan_profile_not_blank"),
        ),
        sa.CheckConstraint(
            "country_code ~ '^[A-Z]{2}$'",
            name=op.f("ck_investigation_plan_country_format"),
        ),
        sa.CheckConstraint(
            "investigation_state_version >= 1",
            name=op.f("ck_investigation_plan_state_version_positive"),
        ),
        sa.CheckConstraint(
            "(budget_amount IS NULL) = (budget_currency IS NULL) AND "
            "(maximum_estimated_cost_amount IS NULL) = "
            "(maximum_estimated_cost_currency IS NULL)",
            name=op.f("ck_investigation_plan_money_pairs_complete"),
        ),
        sa.CheckConstraint(
            "budget_amount IS NULL OR budget_amount >= 0",
            name=op.f("ck_investigation_plan_budget_non_negative"),
        ),
        sa.CheckConstraint(
            "budget_amount IS NULL OR budget_amount NOT IN "
            "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
            name=op.f("ck_investigation_plan_budget_finite"),
        ),
        sa.CheckConstraint(
            "maximum_estimated_cost_kind IN ('KNOWN', 'UNKNOWN') AND "
            "(maximum_estimated_cost_kind = 'KNOWN') = "
            "(maximum_estimated_cost_amount IS NOT NULL) AND "
            "(maximum_estimated_cost_amount IS NULL OR maximum_estimated_cost_amount >= 0)",
            name=op.f("ck_investigation_plan_maximum_cost_valid"),
        ),
        sa.CheckConstraint(
            "maximum_estimated_cost_amount IS NULL OR "
            "maximum_estimated_cost_amount NOT IN "
            "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
            name=op.f("ck_investigation_plan_maximum_cost_finite"),
        ),
        sa.CheckConstraint(
            "budget_currency IS NULL OR budget_currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_investigation_plan_budget_currency_format"),
        ),
        sa.CheckConstraint(
            "maximum_estimated_cost_currency IS NULL OR "
            "maximum_estimated_cost_currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_investigation_plan_maximum_cost_currency_format"),
        ),
        sa.CheckConstraint(
            "planning_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' AND planning_policy_version >= 1",
            name=op.f("ck_investigation_plan_policy_reference_valid"),
        ),
        sa.CheckConstraint(
            "planning_policy_digest ~ '^[0-9a-f]{64}$' "
            "AND input_digest ~ '^[0-9a-f]{64}$' "
            "AND company_snapshot_digest ~ '^[0-9a-f]{64}$' "
            "AND plan_digest ~ '^[0-9a-f]{64}$' "
            "AND command_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_investigation_plan_digests_format"),
        ),
    )
    op.create_index(
        "ix_investigation_plan_workspace_investigation",
        "investigation_plan",
        ["workspace_id", "investigation_id"],
        unique=False,
    )
    op.create_index(
        "ix_investigation_plan_workspace_command",
        "investigation_plan",
        ["workspace_id", "command_id"],
        unique=False,
    )


def _create_planned_capability() -> None:
    op.create_table(
        "planned_capability",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability", sa.String(length=32), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("dependencies", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("estimated_cost_kind", sa.String(length=16), nullable=False),
        sa.Column("estimated_cost_amount", sa.Numeric()),
        sa.Column("estimated_cost_currency", sa.String(length=3)),
        sa.Column("estimated_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planned_capability")),
        sa.UniqueConstraint(
            "id",
            "plan_id",
            "workspace_id",
            "investigation_id",
            name=op.f("uq_planned_capability_id_plan_id_workspace_id_investigation_id"),
        ),
        sa.UniqueConstraint(
            "plan_id",
            "capability",
            name=op.f("uq_planned_capability_plan_id_capability"),
        ),
        sa.UniqueConstraint(
            "plan_id",
            "priority",
            name=op.f("uq_planned_capability_plan_id_priority"),
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "workspace_id", "investigation_id"],
            [
                "investigation_plan.id",
                "investigation_plan.workspace_id",
                "investigation_plan.investigation_id",
            ],
            name="fk_planned_capability_plan_scope",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"capability IN ({_CAPABILITIES})",
            name=op.f("ck_planned_capability_capability_allowed"),
        ),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 1000",
            name=op.f("ck_planned_capability_priority_range"),
        ),
        sa.CheckConstraint(
            f"reason IN ({_REASONS})",
            name=op.f("ck_planned_capability_reason_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('READY', 'OPTIONAL_UNAVAILABLE')",
            name=op.f("ck_planned_capability_status_allowed"),
        ),
        sa.CheckConstraint(
            "(status = 'READY') OR (status = 'OPTIONAL_UNAVAILABLE' AND NOT required)",
            name=op.f("ck_planned_capability_status_requirement_consistent"),
        ),
        sa.CheckConstraint(
            "estimated_cost_kind IN ('KNOWN', 'UNKNOWN') "
            "AND (estimated_cost_amount IS NULL) = (estimated_cost_currency IS NULL) "
            "AND (estimated_cost_kind = 'KNOWN') = (estimated_cost_amount IS NOT NULL) "
            "AND (estimated_cost_amount IS NULL OR estimated_cost_amount >= 0)",
            name=op.f("ck_planned_capability_estimated_cost_valid"),
        ),
        sa.CheckConstraint(
            "estimated_cost_amount IS NULL OR estimated_cost_amount NOT IN "
            "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
            name=op.f("ck_planned_capability_estimated_cost_finite"),
        ),
        sa.CheckConstraint(
            "estimated_cost_currency IS NULL OR estimated_cost_currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_planned_capability_estimated_cost_currency_format"),
        ),
        sa.CheckConstraint(
            "estimated_duration_seconds BETWEEN 1 AND 2592000",
            name=op.f("ck_planned_capability_estimated_duration_range"),
        ),
    )


def _create_planned_connector_option() -> None:
    op.create_table(
        "planned_connector_option",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("planned_capability_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_id", sa.String(length=128), nullable=False),
        sa.Column("connector_version", sa.String(length=32), nullable=False),
        sa.Column("contract_version", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("coverage_kind", sa.String(length=16), nullable=False),
        sa.Column("access_type", sa.String(length=32), nullable=False),
        sa.Column("operations", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("eligibility_rank", sa.SmallInteger(), nullable=False),
        sa.Column("estimated_cost_kind", sa.String(length=16), nullable=False),
        sa.Column("estimated_cost_amount", sa.Numeric()),
        sa.Column("estimated_cost_currency", sa.String(length=3)),
        sa.Column("estimated_duration_seconds", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planned_connector_option")),
        sa.UniqueConstraint(
            "planned_capability_id",
            "connector_id",
            name=op.f("uq_planned_connector_option_planned_capability_id_connector_id"),
        ),
        sa.UniqueConstraint(
            "planned_capability_id",
            "eligibility_rank",
            name=op.f("uq_planned_connector_option_planned_capability_id_eligibility_rank"),
        ),
        sa.ForeignKeyConstraint(
            ["planned_capability_id", "plan_id", "workspace_id", "investigation_id"],
            [
                "planned_capability.id",
                "planned_capability.plan_id",
                "planned_capability.workspace_id",
                "planned_capability.investigation_id",
            ],
            name="fk_planned_connector_option_capability_scope",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "connector_id ~ '^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$' "
            "AND source_id ~ '^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$'",
            name=op.f("ck_planned_connector_option_connector_source_format"),
        ),
        sa.CheckConstraint(
            r"connector_version ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' "
            r"AND contract_version ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'",
            name=op.f("ck_planned_connector_option_versions_format"),
        ),
        sa.CheckConstraint(
            "coverage_kind IN ('GLOBAL', 'COUNTRY_SET')",
            name=op.f("ck_planned_connector_option_coverage_kind_allowed"),
        ),
        sa.CheckConstraint(
            f"access_type IN ({_ACCESS_TYPES})",
            name=op.f("ck_planned_connector_option_access_type_allowed"),
        ),
        sa.CheckConstraint(
            "cardinality(operations) >= 1",
            name=op.f("ck_planned_connector_option_operations_not_empty"),
        ),
        sa.CheckConstraint(
            "eligibility_rank >= 1",
            name=op.f("ck_planned_connector_option_eligibility_rank_positive"),
        ),
        sa.CheckConstraint(
            "estimated_cost_kind IN ('KNOWN', 'UNKNOWN') "
            "AND (estimated_cost_amount IS NULL) = (estimated_cost_currency IS NULL) "
            "AND (estimated_cost_kind = 'KNOWN') = (estimated_cost_amount IS NOT NULL) "
            "AND (estimated_cost_amount IS NULL OR estimated_cost_amount >= 0)",
            name=op.f("ck_planned_connector_option_estimated_cost_valid"),
        ),
        sa.CheckConstraint(
            "estimated_cost_amount IS NULL OR estimated_cost_amount NOT IN "
            "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
            name=op.f("ck_planned_connector_option_estimated_cost_finite"),
        ),
        sa.CheckConstraint(
            "estimated_cost_currency IS NULL OR estimated_cost_currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_planned_connector_option_estimated_cost_currency_format"),
        ),
        sa.CheckConstraint(
            "estimated_duration_seconds BETWEEN 1 AND 2592000",
            name=op.f("ck_planned_connector_option_estimated_duration_range"),
        ),
    )


def downgrade() -> None:
    """Restore F4.3.1 only when no immutable plan would be lost."""

    plan_rows = op.get_bind().scalar(sa.text("SELECT count(*) FROM investigation_plan"))
    if plan_rows:
        raise RuntimeError("Cannot downgrade F4.4 while investigation plans exist.")
    op.drop_table("planned_connector_option")
    op.drop_table("planned_capability")
    op.drop_index("ix_investigation_plan_workspace_command", table_name="investigation_plan")
    op.drop_index("ix_investigation_plan_workspace_investigation", table_name="investigation_plan")
    op.drop_table("investigation_plan")
    for name in (
        "cost_finite",
        "cost_non_negative",
        "cost_consistency",
        "metadata_valid",
        "metadata_complete",
    ):
        op.drop_constraint(
            op.f(f"ck_audit_event_investigation_planning_{name}"),
            "audit_event",
            type_="check",
        )
    for column in (
        "planning_maximum_estimated_cost_currency",
        "planning_maximum_estimated_cost_amount",
        "planning_maximum_estimated_cost_kind",
        "planning_policy_version",
        "planning_policy_id",
        "planned_connector_option_count",
        "planned_capability_count",
        "investigation_plan_id",
        "planning_command_id",
    ):
        op.drop_column("audit_event", column)
