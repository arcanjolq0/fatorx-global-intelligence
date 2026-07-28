"""SQLAlchemy Core tables for the first PostgreSQL domain schema."""

from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from intelligence.domain.audit import (
    ACTION_CODE_MAX_LENGTH,
    REASON_CODE_MAX_LENGTH,
    AuditOutcome,
    AuditResourceType,
)
from intelligence.domain.companies import CompanyStatus
from intelligence.domain.identities import (
    EMAIL_ADDRESS_MAX_LENGTH,
    MembershipRole,
    MembershipStatus,
    UserAccountStatus,
)
from intelligence.domain.investigations import (
    TERMINAL_INVESTIGATION_STATES,
    InvestigationState,
)
from intelligence.domain.workspaces import WorkspaceStatus
from intelligence.infrastructure.persistence.postgresql.metadata import metadata


def _sql_values(values: Iterable[str]) -> str:
    """Render trusted enum values for a static CHECK expression."""

    return ", ".join(f"'{value}'" for value in values)


_TERMINAL_STATES_SQL = _sql_values(
    state.value for state in InvestigationState if state in TERMINAL_INVESTIGATION_STATES
)


workspace_table = sa.Table(
    "workspace",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("name", sa.Text(), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("retention_policy_version", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.CheckConstraint("char_length(btrim(name)) > 0", name="name_not_blank"),
    sa.CheckConstraint(
        "char_length(btrim(retention_policy_version)) > 0",
        name="retention_policy_version_not_blank",
    ),
    sa.CheckConstraint(
        f"status IN ({_sql_values(status.value for status in WorkspaceStatus)})",
        name="status_allowed",
    ),
    sa.CheckConstraint("updated_at >= created_at", name="updated_at_order"),
)
sa.Index("ix_workspace_status", workspace_table.c.status)


company_table = sa.Table(
    "company",
    metadata,
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
    sa.PrimaryKeyConstraint("id"),
    sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["workspace.id"],
        name="fk_company_workspace",
        ondelete="RESTRICT",
    ),
    sa.UniqueConstraint("id", "workspace_id"),
    sa.CheckConstraint("char_length(btrim(legal_name)) > 0", name="legal_name_not_blank"),
    sa.CheckConstraint(
        "trade_name IS NULL OR char_length(btrim(trade_name)) > 0",
        name="trade_name_not_blank",
    ),
    sa.CheckConstraint(
        "legal_form IS NULL OR char_length(btrim(legal_form)) > 0",
        name="legal_form_not_blank",
    ),
    sa.CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="country_code_format"),
    sa.CheckConstraint(
        f"status IN ({_sql_values(status.value for status in CompanyStatus)})",
        name="status_allowed",
    ),
    sa.CheckConstraint("updated_at >= created_at", name="updated_at_order"),
    sa.CheckConstraint(
        "dissolved_on IS NULL OR incorporated_on IS NULL OR dissolved_on >= incorporated_on",
        name="dissolution_date_order",
    ),
    sa.CheckConstraint(
        "(status = 'DISSOLVED' AND dissolved_on IS NOT NULL) "
        "OR (status <> 'DISSOLVED' AND dissolved_on IS NULL)",
        name="dissolution_status_consistency",
    ),
    sa.CheckConstraint(
        "official_domain IS NULL OR ("
        "char_length(official_domain) <= 253 AND "
        "official_domain ~ "
        "'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
        "(\\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$'"
        ")",
        name="official_domain_format",
    ),
)
sa.Index("ix_company_workspace_id_id", company_table.c.workspace_id, company_table.c.id)


investigation_table = sa.Table(
    "investigation",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("profile_code", sa.Text(), nullable=False),
    sa.Column("country_code", sa.String(length=2), nullable=False),
    sa.Column("state", sa.String(length=48), nullable=False),
    sa.Column("state_version", sa.Integer(), nullable=False),
    sa.Column("confirmed_company_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("budget_amount", sa.Numeric(asdecimal=True), nullable=True),
    sa.Column("budget_currency", sa.String(length=3), nullable=True),
    sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint("id"),
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
    sa.CheckConstraint("char_length(btrim(profile_code)) > 0", name="profile_code_not_blank"),
    sa.CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="country_code_format"),
    sa.CheckConstraint(
        f"state IN ({_sql_values(state.value for state in InvestigationState)})",
        name="state_allowed",
    ),
    sa.CheckConstraint("state_version >= 1", name="state_version_positive"),
    sa.CheckConstraint(
        "(budget_amount IS NULL) = (budget_currency IS NULL)",
        name="budget_pair",
    ),
    sa.CheckConstraint(
        "budget_amount IS NULL OR budget_amount NOT IN "
        "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
        name="budget_amount_finite",
    ),
    sa.CheckConstraint(
        "budget_currency IS NULL OR budget_currency ~ '^[A-Z]{3}$'",
        name="budget_currency_format",
    ),
    sa.CheckConstraint(
        "deadline_at IS NULL OR deadline_at >= created_at",
        name="deadline_order",
    ),
    sa.CheckConstraint(
        "started_at IS NULL OR started_at >= created_at",
        name="started_at_order",
    ),
    sa.CheckConstraint(
        "completed_at IS NULL OR started_at IS NOT NULL",
        name="completion_requires_start",
    ),
    sa.CheckConstraint(
        "completed_at IS NULL OR completed_at >= started_at",
        name="completed_at_order",
    ),
    sa.CheckConstraint(
        "(state = 'CREATED') = (started_at IS NULL)",
        name="state_start_consistency",
    ),
    sa.CheckConstraint(
        f"(state IN ({_TERMINAL_STATES_SQL})) = (completed_at IS NOT NULL)",
        name="state_completion_consistency",
    ),
)
sa.Index(
    "ix_investigation_workspace_id_state",
    investigation_table.c.workspace_id,
    investigation_table.c.state,
)


user_account_table = sa.Table(
    "user_account",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("email", sa.String(length=EMAIL_ADDRESS_MAX_LENGTH), nullable=False),
    sa.Column("display_name", sa.Text(), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("email"),
    sa.CheckConstraint(
        "email = lower(email) AND email = btrim(email)",
        name="email_canonical",
    ),
    sa.CheckConstraint(
        "email ~ '^[^@]+@[^@]+$' AND email !~ '[[:space:]]' AND email !~ '[[:cntrl:]]'",
        name="email_format",
    ),
    sa.CheckConstraint("char_length(btrim(display_name)) > 0", name="display_name_not_blank"),
    sa.CheckConstraint(
        f"status IN ({_sql_values(status.value for status in UserAccountStatus)})",
        name="status_allowed",
    ),
    sa.CheckConstraint("updated_at >= created_at", name="updated_at_order"),
)


workspace_membership_table = sa.Table(
    "workspace_membership",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("role", sa.String(length=32), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint("id"),
    sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["workspace.id"],
        name="fk_workspace_membership_workspace",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["user_id"],
        ["user_account.id"],
        name="fk_workspace_membership_user_account",
        ondelete="RESTRICT",
    ),
    sa.UniqueConstraint("workspace_id", "user_id"),
    sa.CheckConstraint(
        f"role IN ({_sql_values(role.value for role in MembershipRole)})",
        name="role_allowed",
    ),
    sa.CheckConstraint(
        f"status IN ({_sql_values(status.value for status in MembershipStatus)})",
        name="status_allowed",
    ),
    sa.CheckConstraint("updated_at >= created_at", name="updated_at_order"),
    sa.CheckConstraint(
        "deactivated_at IS NULL OR deactivated_at >= created_at",
        name="deactivated_at_order",
    ),
    sa.CheckConstraint(
        "(status = 'ACTIVE' AND deactivated_at IS NULL) "
        "OR (status = 'INACTIVE' AND deactivated_at IS NOT NULL)",
        name="status_deactivation_consistency",
    ),
)
sa.Index(
    "ix_workspace_membership_workspace_id_status",
    workspace_membership_table.c.workspace_id,
    workspace_membership_table.c.status,
)
sa.Index(
    "ix_workspace_membership_user_id_workspace_id",
    workspace_membership_table.c.user_id,
    workspace_membership_table.c.workspace_id,
)


audit_event_table = sa.Table(
    "audit_event",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("action_code", sa.String(length=ACTION_CODE_MAX_LENGTH), nullable=False),
    sa.Column("resource_type", sa.String(length=32), nullable=False),
    sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("outcome", sa.String(length=32), nullable=False),
    sa.Column("reason_code", sa.String(length=REASON_CODE_MAX_LENGTH), nullable=True),
    sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["workspace.id"],
        name="fk_audit_event_workspace",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["actor_user_id"],
        ["user_account.id"],
        name="fk_audit_event_actor_user_account",
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        "action_code ~ '^[A-Z][A-Z0-9_.:-]*$'",
        name="action_code_format",
    ),
    sa.CheckConstraint(
        f"resource_type IN ({_sql_values(resource.value for resource in AuditResourceType)})",
        name="resource_type_allowed",
    ),
    sa.CheckConstraint(
        f"outcome IN ({_sql_values(outcome.value for outcome in AuditOutcome)})",
        name="outcome_allowed",
    ),
    sa.CheckConstraint(
        "reason_code IS NULL OR reason_code ~ '^[A-Z][A-Z0-9_.:-]*$'",
        name="reason_code_format",
    ),
)
sa.Index(
    "ix_audit_event_workspace_id_occurred_at",
    audit_event_table.c.workspace_id,
    audit_event_table.c.occurred_at,
)
sa.Index("ix_audit_event_correlation_id", audit_event_table.c.correlation_id)

__all__ = [
    "audit_event_table",
    "company_table",
    "investigation_table",
    "user_account_table",
    "workspace_membership_table",
    "workspace_table",
]
