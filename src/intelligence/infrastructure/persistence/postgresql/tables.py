"""SQLAlchemy Core tables for the first PostgreSQL domain schema."""

from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from intelligence.application.entity_candidate_review import CandidateReviewDecision
from intelligence.application.entity_confirmation import (
    ENTITY_RESOLUTION_DECISION_SCHEMA_VERSION,
    EntityConfirmationReason,
    EntityResolutionDecisionType,
)
from intelligence.application.investigation_lifecycle import (
    InvestigationCancellationReason,
    InvestigationCommandType,
)
from intelligence.connectors.enums import (
    ConnectorAccessType,
    ConnectorCapability,
    ConnectorCoverageKind,
)
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
from intelligence.domain.investigation_inputs import (
    SUPPORTED_IDENTIFICATION_INPUT_SCHEMA_VERSIONS,
)
from intelligence.domain.investigations import (
    TERMINAL_INVESTIGATION_STATES,
    InvestigationState,
)
from intelligence.domain.workspaces import WorkspaceStatus
from intelligence.entity_resolution.policy import (
    MatchClassification,
    MatchDimension,
    MatchExplanationCode,
)
from intelligence.infrastructure.persistence.postgresql.metadata import metadata
from intelligence.orchestration.collection_activation import (
    COLLECTION_OPERATION_SCHEMA_VERSION,
    COLLECTION_OPERATION_VERSION,
    COLLECTION_RUN_SCHEMA_VERSION,
    COLLECTION_RUN_VERSION,
    CollectionOperationStatus,
    CollectionRunStatus,
)
from intelligence.orchestration.planning import (
    INVESTIGATION_PLAN_SCHEMA_VERSION,
    INVESTIGATION_PLAN_VERSION,
    EstimatedCostKind,
    InvestigationPlanStatus,
    PlannedCapabilityStatus,
    PlanningReason,
)


def _sql_values(values: Iterable[str]) -> str:
    """Render trusted enum values for a static CHECK expression."""

    return ", ".join(f"'{value}'" for value in values)


_TERMINAL_STATES_SQL = _sql_values(
    state.value for state in InvestigationState if state in TERMINAL_INVESTIGATION_STATES
)
_INPUT_REQUIRED_STATES_SQL = _sql_values(
    state.value
    for state in InvestigationState
    if state not in {InvestigationState.CREATED, InvestigationState.CANCELLED}
)
_POST_CONFIRMATION_STATES_SQL = _sql_values(
    state.value
    for state in InvestigationState
    if state
    in {
        InvestigationState.PLANNING,
        InvestigationState.COLLECTING,
        InvestigationState.NORMALIZING,
        InvestigationState.VERIFYING,
        InvestigationState.ANALYZING,
        InvestigationState.WAITING_FOR_REVIEW,
        InvestigationState.COMPLETED,
        InvestigationState.PARTIALLY_COMPLETED,
    }
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
    sa.Column(
        "input_snapshot",
        postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
        nullable=True,
    ),
    sa.Column("input_schema_version", sa.SmallInteger(), nullable=True),
    sa.Column("input_digest", sa.String(length=64), nullable=True),
    sa.Column("active_candidate_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("confirmed_company_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("budget_amount", sa.Numeric(asdecimal=True), nullable=True),
    sa.Column("budget_currency", sa.String(length=3), nullable=True),
    sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("id", "workspace_id"),
    sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["workspace.id"],
        name="fk_investigation_workspace",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["active_candidate_batch_id", "workspace_id", "id"],
        [
            "entity_candidate_batch.id",
            "entity_candidate_batch.workspace_id",
            "entity_candidate_batch.investigation_id",
        ],
        name="fk_investigation_active_candidate_batch_scope",
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
        use_alter=True,
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
        "(input_snapshot IS NULL) = (input_schema_version IS NULL) AND "
        "(input_snapshot IS NULL) = (input_digest IS NULL)",
        name="input_snapshot_fields_consistency",
    ),
    sa.CheckConstraint(
        "input_schema_version IS NULL OR input_schema_version IN "
        f"({_sql_values(str(value) for value in SUPPORTED_IDENTIFICATION_INPUT_SCHEMA_VERSIONS)})",
        name="input_schema_version_supported",
    ),
    sa.CheckConstraint(
        "input_digest IS NULL OR input_digest ~ '^[0-9a-f]{64}$'",
        name="input_digest_format",
    ),
    sa.CheckConstraint(
        "state <> 'CREATED' OR input_snapshot IS NULL",
        name="created_input_absent",
    ),
    sa.CheckConstraint(
        f"state NOT IN ({_INPUT_REQUIRED_STATES_SQL}) OR "
        "input_snapshot IS NOT NULL OR confirmed_company_id IS NOT NULL",
        name="started_input_or_company",
        postgresql_not_valid=True,
    ),
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
    sa.CheckConstraint(
        "(state = 'WAITING_FOR_ENTITY_CONFIRMATION') = (active_candidate_batch_id IS NOT NULL)",
        name="active_candidate_batch_state_consistency",
        postgresql_not_valid=True,
    ),
    sa.CheckConstraint(
        "(state IN ('CREATED', 'IDENTIFYING', 'WAITING_FOR_ENTITY_CONFIRMATION') "
        "AND confirmed_company_id IS NULL) OR "
        f"(state IN ({_POST_CONFIRMATION_STATES_SQL}) AND confirmed_company_id IS NOT NULL) OR "
        "state IN ('FAILED', 'CANCELLED')",
        name="entity_confirmation_state_consistency",
        postgresql_not_valid=True,
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
    sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("policy_id", sa.String(length=64), nullable=True),
    sa.Column("policy_version", sa.Integer(), nullable=True),
    sa.Column("candidate_count", sa.SmallInteger(), nullable=True),
    sa.Column("top_classification", sa.String(length=16), nullable=True),
    sa.Column("confirmation_command_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("entity_resolution_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("confirmed_company_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("confirmed_candidate_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("confirmed_candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("confirmation_reason_code", sa.String(length=64), nullable=True),
    sa.Column("confirmed_candidate_classification", sa.String(length=16), nullable=True),
    sa.Column("confirmed_candidate_rank", sa.SmallInteger(), nullable=True),
    sa.Column("matching_policy_id", sa.String(length=64), nullable=True),
    sa.Column("matching_policy_version", sa.Integer(), nullable=True),
    sa.Column("materialization_policy_id", sa.String(length=64), nullable=True),
    sa.Column("materialization_policy_version", sa.Integer(), nullable=True),
    sa.Column("planning_command_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("investigation_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("planned_capability_count", sa.SmallInteger(), nullable=True),
    sa.Column("planned_connector_option_count", sa.SmallInteger(), nullable=True),
    sa.Column("planning_policy_id", sa.String(length=64), nullable=True),
    sa.Column("planning_policy_version", sa.Integer(), nullable=True),
    sa.Column(
        "planning_maximum_estimated_cost_kind",
        sa.String(length=16),
        nullable=True,
    ),
    sa.Column("planning_maximum_estimated_cost_amount", sa.Numeric(), nullable=True),
    sa.Column("planning_maximum_estimated_cost_currency", sa.String(length=3), nullable=True),
    sa.Column("collection_command_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("collection_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("collection_operation_count", sa.SmallInteger(), nullable=True),
    sa.Column("collection_activation_policy_id", sa.String(length=64), nullable=True),
    sa.Column("collection_activation_policy_version", sa.Integer(), nullable=True),
    sa.Column("collection_maximum_estimated_cost_kind", sa.String(length=16), nullable=True),
    sa.Column("collection_maximum_estimated_cost_amount", sa.Numeric(), nullable=True),
    sa.Column("collection_maximum_estimated_cost_currency", sa.String(length=3), nullable=True),
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
    sa.CheckConstraint(
        "num_nonnulls(command_id, policy_id, policy_version, candidate_count, "
        "top_classification) IN (0, 5)",
        name="candidate_review_metadata_complete",
    ),
    sa.CheckConstraint(
        "command_id IS NULL OR (outcome = 'SUCCESS' AND resource_type = 'INVESTIGATION' "
        "AND policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' AND policy_version >= 1 "
        "AND candidate_count BETWEEN 1 AND 100 "
        f"AND top_classification IN "
        f"({_sql_values(value.value for value in MatchClassification)}))",
        name="candidate_review_metadata_valid",
    ),
    sa.CheckConstraint(
        "num_nonnulls(confirmation_command_id, entity_resolution_decision_id, "
        "confirmed_company_id, confirmed_candidate_batch_id, confirmed_candidate_id, "
        "confirmation_reason_code, confirmed_candidate_classification, "
        "confirmed_candidate_rank, matching_policy_id, matching_policy_version, "
        "materialization_policy_id, materialization_policy_version) IN (0, 12)",
        name="entity_confirmation_metadata_complete",
    ),
    sa.CheckConstraint(
        "confirmation_command_id IS NULL OR (outcome = 'SUCCESS' "
        "AND resource_type = 'INVESTIGATION' "
        f"AND confirmation_reason_code IN "
        f"({_sql_values(value.value for value in EntityConfirmationReason)}) "
        "AND confirmed_candidate_classification IN ('HIGH', 'MEDIUM', 'LOW') "
        "AND confirmed_candidate_rank BETWEEN 1 AND 100 "
        "AND matching_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND matching_policy_version >= 1 "
        "AND materialization_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND materialization_policy_version >= 1)",
        name="entity_confirmation_metadata_valid",
    ),
    sa.CheckConstraint(
        "num_nonnulls(planning_command_id, investigation_plan_id, "
        "planned_capability_count, planned_connector_option_count, planning_policy_id, "
        "planning_policy_version, planning_maximum_estimated_cost_kind) IN (0, 7)",
        name="investigation_planning_metadata_complete",
    ),
    sa.CheckConstraint(
        "planning_command_id IS NULL OR (outcome = 'SUCCESS' "
        "AND resource_type = 'INVESTIGATION' "
        "AND planned_capability_count BETWEEN 1 AND 10 "
        "AND planned_connector_option_count BETWEEN 0 AND 1000 "
        "AND planning_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND planning_policy_version >= 1 "
        "AND planning_maximum_estimated_cost_kind IN ('KNOWN', 'UNKNOWN'))",
        name="investigation_planning_metadata_valid",
    ),
    sa.CheckConstraint(
        "(planning_command_id IS NULL "
        "AND planning_maximum_estimated_cost_kind IS NULL "
        "AND planning_maximum_estimated_cost_amount IS NULL "
        "AND planning_maximum_estimated_cost_currency IS NULL) OR "
        "(planning_command_id IS NOT NULL "
        "AND planning_maximum_estimated_cost_kind IS NOT NULL AND "
        "((planning_maximum_estimated_cost_kind = 'UNKNOWN' "
        "AND planning_maximum_estimated_cost_amount IS NULL "
        "AND planning_maximum_estimated_cost_currency IS NULL) OR "
        "(planning_maximum_estimated_cost_kind = 'KNOWN' "
        "AND planning_maximum_estimated_cost_amount IS NOT NULL "
        "AND planning_maximum_estimated_cost_currency IS NOT NULL)))",
        name="investigation_planning_cost_consistency",
    ),
    sa.CheckConstraint(
        "planning_maximum_estimated_cost_amount IS NULL OR "
        "planning_maximum_estimated_cost_amount >= 0",
        name="investigation_planning_cost_non_negative",
    ),
    sa.CheckConstraint(
        "planning_maximum_estimated_cost_amount IS NULL OR "
        "planning_maximum_estimated_cost_amount NOT IN "
        "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
        name="investigation_planning_cost_finite",
    ),
    sa.CheckConstraint(
        "num_nonnulls(collection_command_id, collection_run_id, "
        "collection_operation_count, collection_activation_policy_id, "
        "collection_activation_policy_version, collection_maximum_estimated_cost_kind) "
        "IN (0, 6)",
        name="collection_activation_metadata_complete",
    ),
    sa.CheckConstraint(
        "collection_command_id IS NULL OR (outcome = 'SUCCESS' "
        "AND resource_type = 'INVESTIGATION' "
        "AND collection_operation_count BETWEEN 1 AND 10 "
        "AND collection_activation_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND collection_activation_policy_version >= 1 "
        "AND collection_maximum_estimated_cost_kind IN ('KNOWN', 'UNKNOWN'))",
        name="collection_activation_metadata_valid",
    ),
    sa.CheckConstraint(
        "(collection_command_id IS NULL "
        "AND collection_maximum_estimated_cost_kind IS NULL "
        "AND collection_maximum_estimated_cost_amount IS NULL "
        "AND collection_maximum_estimated_cost_currency IS NULL) OR "
        "(collection_command_id IS NOT NULL AND "
        "((collection_maximum_estimated_cost_kind = 'UNKNOWN' "
        "AND collection_maximum_estimated_cost_amount IS NULL "
        "AND collection_maximum_estimated_cost_currency IS NULL) OR "
        "(collection_maximum_estimated_cost_kind = 'KNOWN' "
        "AND collection_maximum_estimated_cost_amount IS NOT NULL "
        "AND collection_maximum_estimated_cost_currency IS NOT NULL)))",
        name="collection_activation_cost_consistency",
    ),
    sa.CheckConstraint(
        "collection_maximum_estimated_cost_amount IS NULL OR "
        "(collection_maximum_estimated_cost_amount >= 0 AND "
        "collection_maximum_estimated_cost_amount NOT IN "
        "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))",
        name="collection_activation_cost_valid",
    ),
)
sa.Index(
    "ix_audit_event_workspace_id_occurred_at",
    audit_event_table.c.workspace_id,
    audit_event_table.c.occurred_at,
)
sa.Index("ix_audit_event_correlation_id", audit_event_table.c.correlation_id)


investigation_transition_table = sa.Table(
    "investigation_transition",
    metadata,
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
    sa.Column("candidate_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("candidate_count", sa.SmallInteger(), nullable=True),
    sa.Column("top_classification", sa.String(length=16), nullable=True),
    sa.Column("policy_id", sa.String(length=64), nullable=True),
    sa.Column("policy_version", sa.Integer(), nullable=True),
    sa.Column("confirmation_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("confirmed_company_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("confirmed_candidate_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("confirmed_candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("confirmation_reason_code", sa.String(length=64), nullable=True),
    sa.Column("confirmed_candidate_classification", sa.String(length=16), nullable=True),
    sa.Column("confirmed_candidate_rank", sa.SmallInteger(), nullable=True),
    sa.Column("matching_policy_id", sa.String(length=64), nullable=True),
    sa.Column("matching_policy_version", sa.Integer(), nullable=True),
    sa.Column("materialization_policy_id", sa.String(length=64), nullable=True),
    sa.Column("materialization_policy_version", sa.Integer(), nullable=True),
    sa.Column("collection_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("collection_company_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("collection_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("collection_operation_count", sa.SmallInteger(), nullable=True),
    sa.Column("collection_activation_policy_id", sa.String(length=64), nullable=True),
    sa.Column("collection_activation_policy_version", sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint("id"),
    sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["workspace.id"],
        name="fk_investigation_transition_workspace",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["candidate_batch_id", "workspace_id", "investigation_id"],
        [
            "entity_candidate_batch.id",
            "entity_candidate_batch.workspace_id",
            "entity_candidate_batch.investigation_id",
        ],
        name="fk_investigation_transition_candidate_batch_scope",
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
        use_alter=True,
    ),
    sa.ForeignKeyConstraint(
        ["investigation_id", "workspace_id"],
        ["investigation.id", "investigation.workspace_id"],
        name="fk_investigation_transition_investigation_workspace",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["actor_user_id"],
        ["user_account.id"],
        name="fk_investigation_transition_actor_user_account",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["confirmed_company_id", "workspace_id"],
        ["company.id", "company.workspace_id"],
        name="fk_investigation_transition_confirmed_company_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["confirmed_candidate_batch_id", "workspace_id", "investigation_id"],
        [
            "entity_candidate_batch.id",
            "entity_candidate_batch.workspace_id",
            "entity_candidate_batch.investigation_id",
        ],
        name="fk_investigation_transition_confirmed_batch_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        [
            "confirmed_candidate_id",
            "workspace_id",
            "investigation_id",
            "confirmed_candidate_batch_id",
        ],
        [
            "entity_candidate.id",
            "entity_candidate.workspace_id",
            "entity_candidate.investigation_id",
            "entity_candidate.batch_id",
        ],
        name="fk_investigation_transition_confirmed_candidate_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["confirmation_decision_id", "workspace_id", "investigation_id", "command_id"],
        [
            "entity_resolution_decision.id",
            "entity_resolution_decision.workspace_id",
            "entity_resolution_decision.investigation_id",
            "entity_resolution_decision.command_id",
        ],
        name="fk_investigation_transition_confirmation_decision",
        ondelete="RESTRICT",
        use_alter=True,
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.ForeignKeyConstraint(
        [
            "collection_run_id",
            "workspace_id",
            "investigation_id",
            "collection_company_id",
            "collection_plan_id",
        ],
        [
            "collection_run.id",
            "collection_run.workspace_id",
            "collection_run.investigation_id",
            "collection_run.company_id",
            "collection_run.plan_id",
        ],
        name="fk_investigation_transition_collection_run_scope",
        ondelete="RESTRICT",
        use_alter=True,
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.UniqueConstraint("workspace_id", "command_id"),
    sa.CheckConstraint(
        f"command_type IN ({_sql_values(value.value for value in InvestigationCommandType)})",
        name="command_type_allowed",
    ),
    sa.CheckConstraint(
        f"state_before IN ({_sql_values(state.value for state in InvestigationState)})",
        name="state_before_allowed",
    ),
    sa.CheckConstraint(
        f"state_after IN ({_sql_values(state.value for state in InvestigationState)})",
        name="state_after_allowed",
    ),
    sa.CheckConstraint(
        "version_before >= 1 AND version_after = version_before + 1",
        name="version_increment",
    ),
    sa.CheckConstraint(
        "command_digest ~ '^[0-9a-f]{64}$'",
        name="command_digest_format",
    ),
    sa.CheckConstraint(
        "(command_type = 'START_IDENTIFICATION' "
        "AND state_before = 'CREATED' "
        "AND state_after = 'IDENTIFYING' "
        "AND reason_code IS NULL) OR "
        "(command_type = 'CANCEL_INVESTIGATION' "
        f"AND state_before NOT IN ({_TERMINAL_STATES_SQL}) "
        "AND state_after = 'CANCELLED' "
        f"AND reason_code IN "
        f"({_sql_values(reason.value for reason in InvestigationCancellationReason)})) OR "
        "(command_type = 'REQUEST_ENTITY_CONFIRMATION' "
        "AND state_before = 'IDENTIFYING' "
        "AND state_after = 'WAITING_FOR_ENTITY_CONFIRMATION' "
        "AND reason_code IS NULL) OR "
        "(command_type = 'CONFIRM_ENTITY_CANDIDATE' "
        "AND state_before = 'WAITING_FOR_ENTITY_CONFIRMATION' "
        "AND state_after = 'PLANNING' AND reason_code IS NULL) OR "
        "(command_type = 'START_COLLECTION' "
        "AND state_before = 'PLANNING' "
        "AND state_after = 'COLLECTING' AND reason_code IS NULL)",
        name="command_transition_shape",
    ),
    sa.CheckConstraint(
        "(command_type = 'REQUEST_ENTITY_CONFIRMATION') = "
        "(candidate_batch_id IS NOT NULL) AND "
        "num_nonnulls(candidate_batch_id, candidate_count, top_classification, "
        "policy_id, policy_version) IN (0, 5)",
        name="candidate_metadata_complete",
    ),
    sa.CheckConstraint(
        "candidate_batch_id IS NULL OR (candidate_count BETWEEN 1 AND 100 "
        f"AND top_classification IN "
        f"({_sql_values(value.value for value in MatchClassification)}) "
        "AND policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' AND policy_version >= 1)",
        name="candidate_metadata_valid",
    ),
    sa.CheckConstraint(
        "(command_type = 'CONFIRM_ENTITY_CANDIDATE') = "
        "(confirmation_decision_id IS NOT NULL) AND "
        "num_nonnulls(confirmation_decision_id, confirmed_company_id, "
        "confirmed_candidate_batch_id, confirmed_candidate_id, confirmation_reason_code, "
        "confirmed_candidate_classification, confirmed_candidate_rank, matching_policy_id, "
        "matching_policy_version, materialization_policy_id, "
        "materialization_policy_version) IN (0, 11)",
        name="entity_confirmation_metadata_complete",
    ),
    sa.CheckConstraint(
        "confirmation_decision_id IS NULL OR ("
        f"confirmation_reason_code IN "
        f"({_sql_values(value.value for value in EntityConfirmationReason)}) "
        "AND confirmed_candidate_classification IN ('HIGH', 'MEDIUM', 'LOW') "
        "AND confirmed_candidate_rank BETWEEN 1 AND 100 "
        "AND matching_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND matching_policy_version >= 1 "
        "AND materialization_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND materialization_policy_version >= 1)",
        name="entity_confirmation_metadata_valid",
    ),
    sa.CheckConstraint(
        "(command_type = 'START_COLLECTION') = (collection_run_id IS NOT NULL) AND "
        "num_nonnulls(collection_run_id, collection_company_id, collection_plan_id, "
        "collection_operation_count, collection_activation_policy_id, "
        "collection_activation_policy_version) IN (0, 6)",
        name="collection_activation_metadata_complete",
    ),
    sa.CheckConstraint(
        "collection_run_id IS NULL OR (collection_operation_count BETWEEN 1 AND 10 "
        "AND collection_activation_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND collection_activation_policy_version >= 1)",
        name="collection_activation_metadata_valid",
    ),
)
sa.Index(
    "ix_investigation_transition_workspace_investigation_version",
    investigation_transition_table.c.workspace_id,
    investigation_transition_table.c.investigation_id,
    investigation_transition_table.c.version_after,
)


entity_candidate_batch_table = sa.Table(
    "entity_candidate_batch",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("batch_version", sa.SmallInteger(), nullable=False),
    sa.Column("input_digest", sa.String(length=64), nullable=False),
    sa.Column("policy_id", sa.String(length=64), nullable=False),
    sa.Column("policy_version", sa.Integer(), nullable=False),
    sa.Column("policy_digest", sa.String(length=64), nullable=False),
    sa.Column(
        "policy_snapshot",
        postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
        nullable=False,
    ),
    sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("submission_digest", sa.String(length=64), nullable=False),
    sa.Column("evaluation_digest", sa.String(length=64), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("id", "workspace_id", "investigation_id"),
    sa.UniqueConstraint("workspace_id", "investigation_id"),
    sa.UniqueConstraint("workspace_id", "command_id"),
    sa.ForeignKeyConstraint(
        ["investigation_id", "workspace_id"],
        ["investigation.id", "investigation.workspace_id"],
        name="fk_entity_candidate_batch_investigation_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["created_by"],
        ["user_account.id"],
        name="fk_entity_candidate_batch_created_by",
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint("batch_version = 1", name="batch_version_supported"),
    sa.CheckConstraint(
        "input_digest ~ '^[0-9a-f]{64}$' AND policy_digest ~ '^[0-9a-f]{64}$' "
        "AND submission_digest ~ '^[0-9a-f]{64}$' "
        "AND evaluation_digest ~ '^[0-9a-f]{64}$'",
        name="digests_format",
    ),
    sa.CheckConstraint("policy_version >= 1", name="policy_version_positive"),
    sa.CheckConstraint(
        "policy_id ~ '^[A-Z][A-Z0-9_.:-]*$'",
        name="policy_id_format",
    ),
)
sa.Index(
    "ix_entity_candidate_batch_workspace_investigation",
    entity_candidate_batch_table.c.workspace_id,
    entity_candidate_batch_table.c.investigation_id,
)


entity_candidate_table = sa.Table(
    "entity_candidate",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("candidate_key", sa.String(length=128), nullable=False),
    sa.Column("rank", sa.SmallInteger(), nullable=False),
    sa.Column("total_score", sa.SmallInteger(), nullable=False),
    sa.Column("coverage", sa.SmallInteger(), nullable=False),
    sa.Column("classification", sa.String(length=16), nullable=False),
    sa.Column("hard_conflict", sa.Boolean(), nullable=False),
    sa.Column(
        "identity_snapshot",
        postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
        nullable=False,
    ),
    sa.Column("identity_schema_version", sa.SmallInteger(), nullable=False),
    sa.Column("identity_digest", sa.String(length=64), nullable=False),
    sa.Column(
        "origin_snapshot",
        postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
        nullable=False,
    ),
    sa.Column("origin_schema_version", sa.SmallInteger(), nullable=False),
    sa.Column("origin_digest", sa.String(length=64), nullable=False),
    sa.Column("evaluation_digest", sa.String(length=64), nullable=False),
    sa.Column("decision", sa.String(length=32), nullable=False),
    sa.Column("decision_by", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("id", "workspace_id", "investigation_id", "batch_id"),
    sa.UniqueConstraint("batch_id", "candidate_key"),
    sa.UniqueConstraint("batch_id", "rank"),
    sa.ForeignKeyConstraint(
        ["batch_id", "workspace_id", "investigation_id"],
        [
            "entity_candidate_batch.id",
            "entity_candidate_batch.workspace_id",
            "entity_candidate_batch.investigation_id",
        ],
        name="fk_entity_candidate_batch_scope",
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint("rank BETWEEN 1 AND 100", name="rank_range"),
    sa.CheckConstraint(
        "total_score BETWEEN 0 AND 10000 AND coverage BETWEEN 0 AND 10000",
        name="score_coverage_range",
    ),
    sa.CheckConstraint(
        f"classification IN ({_sql_values(value.value for value in MatchClassification)})",
        name="classification_allowed",
    ),
    sa.CheckConstraint(
        "hard_conflict = (classification = 'EXCLUDED')",
        name="conflict_classification_consistency",
    ),
    sa.CheckConstraint("identity_schema_version = 1", name="identity_schema_supported"),
    sa.CheckConstraint("origin_schema_version = 1", name="origin_schema_supported"),
    sa.CheckConstraint(
        "identity_digest ~ '^[0-9a-f]{64}$' AND origin_digest ~ '^[0-9a-f]{64}$' "
        "AND evaluation_digest ~ '^[0-9a-f]{64}$'",
        name="digests_format",
    ),
    sa.CheckConstraint(
        f"decision = '{CandidateReviewDecision.PENDING_REVIEW.value}' "
        "AND decision_by IS NULL AND decided_at IS NULL",
        name="pending_review_only",
    ),
)
sa.Index(
    "ix_entity_candidate_batch_rank",
    entity_candidate_table.c.batch_id,
    entity_candidate_table.c.rank,
)


entity_candidate_dimension_score_table = sa.Table(
    "entity_candidate_dimension_score",
    metadata,
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("dimension", sa.String(length=32), nullable=False),
    sa.Column("score", sa.SmallInteger(), nullable=False),
    sa.Column("weight", sa.SmallInteger(), nullable=False),
    sa.Column("contribution", sa.SmallInteger(), nullable=False),
    sa.Column("available", sa.Boolean(), nullable=False),
    sa.Column("hard_conflict", sa.Boolean(), nullable=False),
    sa.Column("explanation_code", sa.String(length=64), nullable=False),
    sa.PrimaryKeyConstraint("candidate_id", "dimension"),
    sa.ForeignKeyConstraint(
        ["candidate_id", "workspace_id", "investigation_id", "batch_id"],
        [
            "entity_candidate.id",
            "entity_candidate.workspace_id",
            "entity_candidate.investigation_id",
            "entity_candidate.batch_id",
        ],
        name="fk_entity_candidate_dimension_candidate_scope",
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        f"dimension IN ({_sql_values(value.value for value in MatchDimension)})",
        name="dimension_allowed",
    ),
    sa.CheckConstraint(
        "score BETWEEN 0 AND 10000 AND weight BETWEEN 0 AND 10000 "
        "AND contribution BETWEEN 0 AND 10000",
        name="basis_points_range",
    ),
    sa.CheckConstraint(
        "contribution = (score::integer * weight::integer) / 10000",
        name="contribution_consistency",
    ),
    sa.CheckConstraint(
        "available OR (score = 0 AND contribution = 0 AND NOT hard_conflict)",
        name="availability_consistency",
    ),
    sa.CheckConstraint(
        f"explanation_code IN ({_sql_values(value.value for value in MatchExplanationCode)})",
        name="explanation_allowed",
    ),
)


entity_resolution_decision_table = sa.Table(
    "entity_resolution_decision",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("command_digest", sa.String(length=64), nullable=False),
    sa.Column("candidate_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("review_reason", sa.String(length=64), nullable=False),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("decision_type", sa.String(length=32), nullable=False),
    sa.Column("decision_schema_version", sa.SmallInteger(), nullable=False),
    sa.Column("candidate_rank", sa.SmallInteger(), nullable=False),
    sa.Column("candidate_classification", sa.String(length=16), nullable=False),
    sa.Column("candidate_total_score", sa.SmallInteger(), nullable=False),
    sa.Column("candidate_coverage", sa.SmallInteger(), nullable=False),
    sa.Column("candidate_identity_digest", sa.String(length=64), nullable=False),
    sa.Column("candidate_evaluation_digest", sa.String(length=64), nullable=False),
    sa.Column("batch_submission_digest", sa.String(length=64), nullable=False),
    sa.Column("batch_evaluation_digest", sa.String(length=64), nullable=False),
    sa.Column("matching_policy_id", sa.String(length=64), nullable=False),
    sa.Column("matching_policy_version", sa.Integer(), nullable=False),
    sa.Column("matching_policy_digest", sa.String(length=64), nullable=False),
    sa.Column("input_digest", sa.String(length=64), nullable=False),
    sa.Column("materialization_policy_id", sa.String(length=64), nullable=False),
    sa.Column("materialization_policy_version", sa.Integer(), nullable=False),
    sa.Column("materialization_policy_digest", sa.String(length=64), nullable=False),
    sa.Column(
        "materialization_policy_snapshot",
        postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
        nullable=False,
    ),
    sa.Column("company_snapshot_digest", sa.String(length=64), nullable=False),
    sa.Column("decision_digest", sa.String(length=64), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("id", "workspace_id", "investigation_id", "command_id"),
    sa.UniqueConstraint(
        "workspace_id",
        "investigation_id",
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.UniqueConstraint(
        "workspace_id",
        "command_id",
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.UniqueConstraint(
        "workspace_id",
        "company_id",
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["workspace.id"],
        name="fk_entity_resolution_decision_workspace",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["investigation_id", "workspace_id"],
        ["investigation.id", "investigation.workspace_id"],
        name="fk_entity_resolution_decision_investigation_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["candidate_batch_id", "workspace_id", "investigation_id"],
        [
            "entity_candidate_batch.id",
            "entity_candidate_batch.workspace_id",
            "entity_candidate_batch.investigation_id",
        ],
        name="fk_entity_resolution_decision_batch_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["candidate_id", "workspace_id", "investigation_id", "candidate_batch_id"],
        [
            "entity_candidate.id",
            "entity_candidate.workspace_id",
            "entity_candidate.investigation_id",
            "entity_candidate.batch_id",
        ],
        name="fk_entity_resolution_decision_candidate_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["company_id", "workspace_id"],
        ["company.id", "company.workspace_id"],
        name="fk_entity_resolution_decision_company_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["reviewed_by"],
        ["user_account.id"],
        name="fk_entity_resolution_decision_reviewer",
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        f"decision_type = '{EntityResolutionDecisionType.CONFIRMED.value}'",
        name="decision_type_confirmed",
    ),
    sa.CheckConstraint(
        f"decision_schema_version = {ENTITY_RESOLUTION_DECISION_SCHEMA_VERSION}",
        name="decision_schema_supported",
    ),
    sa.CheckConstraint(
        f"review_reason IN ({_sql_values(value.value for value in EntityConfirmationReason)})",
        name="review_reason_allowed",
    ),
    sa.CheckConstraint(
        "candidate_classification IN ('HIGH', 'MEDIUM', 'LOW')",
        name="candidate_classification_allowed",
    ),
    sa.CheckConstraint(
        "review_reason = 'MANUAL_OVERRIDE' OR "
        "(candidate_rank = 1 AND candidate_classification IN ('HIGH', 'MEDIUM'))",
        name="review_reason_compatible",
    ),
    sa.CheckConstraint("candidate_rank BETWEEN 1 AND 100", name="candidate_rank_range"),
    sa.CheckConstraint(
        "candidate_total_score BETWEEN 0 AND 10000 AND candidate_coverage BETWEEN 0 AND 10000",
        name="candidate_score_coverage_range",
    ),
    sa.CheckConstraint(
        "command_digest ~ '^[0-9a-f]{64}$' "
        "AND candidate_identity_digest ~ '^[0-9a-f]{64}$' "
        "AND candidate_evaluation_digest ~ '^[0-9a-f]{64}$' "
        "AND batch_submission_digest ~ '^[0-9a-f]{64}$' "
        "AND batch_evaluation_digest ~ '^[0-9a-f]{64}$' "
        "AND matching_policy_digest ~ '^[0-9a-f]{64}$' "
        "AND input_digest ~ '^[0-9a-f]{64}$' "
        "AND materialization_policy_digest ~ '^[0-9a-f]{64}$' "
        "AND company_snapshot_digest ~ '^[0-9a-f]{64}$' "
        "AND decision_digest ~ '^[0-9a-f]{64}$'",
        name="digests_format",
    ),
    sa.CheckConstraint(
        "matching_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND materialization_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND matching_policy_version >= 1 AND materialization_policy_version >= 1",
        name="policy_references_valid",
    ),
)
sa.Index(
    "ix_entity_resolution_decision_workspace_investigation",
    entity_resolution_decision_table.c.workspace_id,
    entity_resolution_decision_table.c.investigation_id,
)
sa.Index(
    "ix_entity_resolution_decision_workspace_company",
    entity_resolution_decision_table.c.workspace_id,
    entity_resolution_decision_table.c.company_id,
)
sa.Index(
    "ix_entity_resolution_decision_workspace_batch",
    entity_resolution_decision_table.c.workspace_id,
    entity_resolution_decision_table.c.candidate_batch_id,
)
sa.Index(
    "ix_entity_resolution_decision_workspace_command",
    entity_resolution_decision_table.c.workspace_id,
    entity_resolution_decision_table.c.command_id,
)
sa.Index(
    "ix_investigation_transition_workspace_occurred_at",
    investigation_transition_table.c.workspace_id,
    investigation_transition_table.c.occurred_at,
)


investigation_plan_table = sa.Table(
    "investigation_plan",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("profile_code", sa.Text(), nullable=False),
    sa.Column("country_code", sa.String(length=2), nullable=False),
    sa.Column("plan_version", sa.SmallInteger(), nullable=False),
    sa.Column("status", sa.String(length=16), nullable=False),
    sa.Column("budget_amount", sa.Numeric(), nullable=True),
    sa.Column("budget_currency", sa.String(length=3), nullable=True),
    sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("maximum_estimated_cost_kind", sa.String(length=16), nullable=False),
    sa.Column("maximum_estimated_cost_amount", sa.Numeric(), nullable=True),
    sa.Column("maximum_estimated_cost_currency", sa.String(length=3), nullable=True),
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
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("id", "workspace_id", "investigation_id"),
    sa.UniqueConstraint(
        "workspace_id",
        "investigation_id",
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.UniqueConstraint(
        "workspace_id",
        "command_id",
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
        f"plan_version = {INVESTIGATION_PLAN_VERSION} AND "
        f"schema_version = {INVESTIGATION_PLAN_SCHEMA_VERSION}",
        name="versions_supported",
    ),
    sa.CheckConstraint(
        f"status = '{InvestigationPlanStatus.READY.value}'",
        name="status_ready",
    ),
    sa.CheckConstraint("char_length(btrim(profile_code)) > 0", name="profile_not_blank"),
    sa.CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="country_format"),
    sa.CheckConstraint("investigation_state_version >= 1", name="state_version_positive"),
    sa.CheckConstraint(
        "(budget_amount IS NULL) = (budget_currency IS NULL) AND "
        "(maximum_estimated_cost_amount IS NULL) = "
        "(maximum_estimated_cost_currency IS NULL)",
        name="money_pairs_complete",
    ),
    sa.CheckConstraint(
        "budget_amount IS NULL OR budget_amount >= 0",
        name="budget_non_negative",
    ),
    sa.CheckConstraint(
        "budget_amount IS NULL OR budget_amount NOT IN "
        "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
        name="budget_finite",
    ),
    sa.CheckConstraint(
        f"maximum_estimated_cost_kind IN "
        f"({_sql_values(value.value for value in EstimatedCostKind)}) AND "
        "(maximum_estimated_cost_kind = 'KNOWN') = "
        "(maximum_estimated_cost_amount IS NOT NULL) AND "
        "(maximum_estimated_cost_amount IS NULL OR maximum_estimated_cost_amount >= 0)",
        name="maximum_cost_valid",
    ),
    sa.CheckConstraint(
        "maximum_estimated_cost_amount IS NULL OR "
        "maximum_estimated_cost_amount NOT IN "
        "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
        name="maximum_cost_finite",
    ),
    sa.CheckConstraint(
        "budget_currency IS NULL OR budget_currency ~ '^[A-Z]{3}$'",
        name="budget_currency_format",
    ),
    sa.CheckConstraint(
        "maximum_estimated_cost_currency IS NULL OR maximum_estimated_cost_currency ~ '^[A-Z]{3}$'",
        name="maximum_cost_currency_format",
    ),
    sa.CheckConstraint(
        "planning_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' AND planning_policy_version >= 1",
        name="policy_reference_valid",
    ),
    sa.CheckConstraint(
        "planning_policy_digest ~ '^[0-9a-f]{64}$' "
        "AND input_digest ~ '^[0-9a-f]{64}$' "
        "AND company_snapshot_digest ~ '^[0-9a-f]{64}$' "
        "AND plan_digest ~ '^[0-9a-f]{64}$' "
        "AND command_digest ~ '^[0-9a-f]{64}$'",
        name="digests_format",
    ),
)
sa.Index(
    "ix_investigation_plan_workspace_investigation",
    investigation_plan_table.c.workspace_id,
    investigation_plan_table.c.investigation_id,
)
sa.Index(
    "ix_investigation_plan_workspace_command",
    investigation_plan_table.c.workspace_id,
    investigation_plan_table.c.command_id,
)


planned_capability_table = sa.Table(
    "planned_capability",
    metadata,
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
    sa.Column("estimated_cost_amount", sa.Numeric(), nullable=True),
    sa.Column("estimated_cost_currency", sa.String(length=3), nullable=True),
    sa.Column("estimated_duration_seconds", sa.Integer(), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("id", "plan_id", "workspace_id", "investigation_id"),
    sa.UniqueConstraint("plan_id", "capability"),
    sa.UniqueConstraint("plan_id", "priority"),
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
        f"capability IN ({_sql_values(value.value for value in ConnectorCapability)})",
        name="capability_allowed",
    ),
    sa.CheckConstraint("priority BETWEEN 1 AND 1000", name="priority_range"),
    sa.CheckConstraint(
        f"reason IN ({_sql_values(value.value for value in PlanningReason)})",
        name="reason_allowed",
    ),
    sa.CheckConstraint(
        f"status IN ({_sql_values(value.value for value in PlannedCapabilityStatus)})",
        name="status_allowed",
    ),
    sa.CheckConstraint(
        "(status = 'READY') OR (status = 'OPTIONAL_UNAVAILABLE' AND NOT required)",
        name="status_requirement_consistent",
    ),
    sa.CheckConstraint(
        f"estimated_cost_kind IN ({_sql_values(value.value for value in EstimatedCostKind)}) "
        "AND (estimated_cost_amount IS NULL) = (estimated_cost_currency IS NULL) "
        "AND (estimated_cost_kind = 'KNOWN') = (estimated_cost_amount IS NOT NULL) "
        "AND (estimated_cost_amount IS NULL OR estimated_cost_amount >= 0)",
        name="estimated_cost_valid",
    ),
    sa.CheckConstraint(
        "estimated_cost_amount IS NULL OR estimated_cost_amount NOT IN "
        "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
        name="estimated_cost_finite",
    ),
    sa.CheckConstraint(
        "estimated_cost_currency IS NULL OR estimated_cost_currency ~ '^[A-Z]{3}$'",
        name="estimated_cost_currency_format",
    ),
    sa.CheckConstraint(
        "estimated_duration_seconds BETWEEN 1 AND 2592000",
        name="estimated_duration_range",
    ),
)


planned_connector_option_table = sa.Table(
    "planned_connector_option",
    metadata,
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
    sa.Column("estimated_cost_amount", sa.Numeric(), nullable=True),
    sa.Column("estimated_cost_currency", sa.String(length=3), nullable=True),
    sa.Column("estimated_duration_seconds", sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("planned_capability_id", "connector_id"),
    sa.UniqueConstraint("planned_capability_id", "eligibility_rank"),
    sa.UniqueConstraint(
        "id", "planned_capability_id", "plan_id", "workspace_id", "investigation_id"
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
        name="connector_source_format",
    ),
    sa.CheckConstraint(
        "connector_version ~ '^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$' "
        "AND contract_version ~ '^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$'",
        name="versions_format",
    ),
    sa.CheckConstraint(
        f"coverage_kind IN ({_sql_values(value.value for value in ConnectorCoverageKind)})",
        name="coverage_kind_allowed",
    ),
    sa.CheckConstraint(
        f"access_type IN ({_sql_values(value.value for value in ConnectorAccessType)})",
        name="access_type_allowed",
    ),
    sa.CheckConstraint("cardinality(operations) >= 1", name="operations_not_empty"),
    sa.CheckConstraint("eligibility_rank >= 1", name="eligibility_rank_positive"),
    sa.CheckConstraint(
        f"estimated_cost_kind IN ({_sql_values(value.value for value in EstimatedCostKind)}) "
        "AND (estimated_cost_amount IS NULL) = (estimated_cost_currency IS NULL) "
        "AND (estimated_cost_kind = 'KNOWN') = (estimated_cost_amount IS NOT NULL) "
        "AND (estimated_cost_amount IS NULL OR estimated_cost_amount >= 0)",
        name="estimated_cost_valid",
    ),
    sa.CheckConstraint(
        "estimated_cost_amount IS NULL OR estimated_cost_amount NOT IN "
        "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
        name="estimated_cost_finite",
    ),
    sa.CheckConstraint(
        "estimated_cost_currency IS NULL OR estimated_cost_currency ~ '^[A-Z]{3}$'",
        name="estimated_cost_currency_format",
    ),
    sa.CheckConstraint(
        "estimated_duration_seconds BETWEEN 1 AND 2592000",
        name="estimated_duration_range",
    ),
)


collection_run_table = sa.Table(
    "collection_run",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("run_version", sa.SmallInteger(), nullable=False),
    sa.Column("status", sa.String(length=16), nullable=False),
    sa.Column("activation_policy_id", sa.String(length=64), nullable=False),
    sa.Column("activation_policy_version", sa.Integer(), nullable=False),
    sa.Column("activation_policy_snapshot", sa.Text(), nullable=False),
    sa.Column("activation_policy_digest", sa.String(length=64), nullable=False),
    sa.Column("plan_digest", sa.String(length=64), nullable=False),
    sa.Column("company_snapshot_digest", sa.String(length=64), nullable=False),
    sa.Column("budget_amount", sa.Numeric(), nullable=True),
    sa.Column("budget_currency", sa.String(length=3), nullable=True),
    sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("maximum_estimated_cost_kind", sa.String(length=16), nullable=False),
    sa.Column("maximum_estimated_cost_amount", sa.Numeric(), nullable=True),
    sa.Column("maximum_estimated_cost_currency", sa.String(length=3), nullable=True),
    sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("command_digest", sa.String(length=64), nullable=False),
    sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("investigation_state_version", sa.Integer(), nullable=False),
    sa.Column("run_digest", sa.String(length=64), nullable=False),
    sa.Column("schema_version", sa.SmallInteger(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("id", "workspace_id", "investigation_id"),
    sa.UniqueConstraint("id", "workspace_id", "investigation_id", "company_id", "plan_id"),
    sa.UniqueConstraint("workspace_id", "investigation_id"),
    sa.UniqueConstraint("workspace_id", "plan_id"),
    sa.UniqueConstraint("workspace_id", "command_id"),
    sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["workspace.id"],
        name="fk_collection_run_workspace",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["investigation_id", "workspace_id"],
        ["investigation.id", "investigation.workspace_id"],
        name="fk_collection_run_investigation_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["company_id", "workspace_id"],
        ["company.id", "company.workspace_id"],
        name="fk_collection_run_company_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["plan_id", "workspace_id", "investigation_id"],
        [
            "investigation_plan.id",
            "investigation_plan.workspace_id",
            "investigation_plan.investigation_id",
        ],
        name="fk_collection_run_plan_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["created_by"],
        ["user_account.id"],
        name="fk_collection_run_created_by",
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        f"run_version = {COLLECTION_RUN_VERSION} AND "
        f"schema_version = {COLLECTION_RUN_SCHEMA_VERSION}",
        name="versions_supported",
    ),
    sa.CheckConstraint(
        f"status IN ({_sql_values(value.value for value in CollectionRunStatus)})",
        name="status_allowed",
    ),
    sa.CheckConstraint(
        "activation_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' AND activation_policy_version >= 1",
        name="policy_reference_valid",
    ),
    sa.CheckConstraint(
        "activation_policy_digest ~ '^[0-9a-f]{64}$' "
        "AND plan_digest ~ '^[0-9a-f]{64}$' "
        "AND company_snapshot_digest ~ '^[0-9a-f]{64}$' "
        "AND command_digest ~ '^[0-9a-f]{64}$' "
        "AND run_digest ~ '^[0-9a-f]{64}$'",
        name="digests_format",
    ),
    sa.CheckConstraint("investigation_state_version >= 2", name="state_version_valid"),
    sa.CheckConstraint(
        "(budget_amount IS NULL) = (budget_currency IS NULL) "
        "AND (budget_amount IS NULL OR budget_amount >= 0) "
        "AND (budget_amount IS NULL OR budget_amount NOT IN "
        "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))",
        name="budget_valid",
    ),
    sa.CheckConstraint(
        "maximum_estimated_cost_kind IN ('KNOWN', 'UNKNOWN') "
        "AND (maximum_estimated_cost_amount IS NULL) = "
        "(maximum_estimated_cost_currency IS NULL) "
        "AND (maximum_estimated_cost_kind = 'KNOWN') = "
        "(maximum_estimated_cost_amount IS NOT NULL) "
        "AND (maximum_estimated_cost_amount IS NULL OR "
        "maximum_estimated_cost_amount >= 0) "
        "AND (maximum_estimated_cost_amount IS NULL OR "
        "maximum_estimated_cost_amount NOT IN "
        "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))",
        name="maximum_cost_valid",
    ),
    sa.CheckConstraint(
        "budget_currency IS NULL OR budget_currency ~ '^[A-Z]{3}$'",
        name="budget_currency_format",
    ),
    sa.CheckConstraint(
        "maximum_estimated_cost_currency IS NULL OR maximum_estimated_cost_currency ~ '^[A-Z]{3}$'",
        name="maximum_cost_currency_format",
    ),
)
sa.Index(
    "ix_collection_run_workspace_created_at",
    collection_run_table.c.workspace_id,
    collection_run_table.c.created_at,
)


collection_operation_table = sa.Table(
    "collection_operation",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("collection_run_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("capability", sa.String(length=32), nullable=False),
    sa.Column("priority", sa.SmallInteger(), nullable=False),
    sa.Column("planned_capability_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("planned_connector_option_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("connector_id", sa.String(length=128), nullable=False),
    sa.Column("connector_version", sa.String(length=32), nullable=False),
    sa.Column("contract_version", sa.String(length=32), nullable=False),
    sa.Column("source_id", sa.String(length=128), nullable=False),
    sa.Column("connector_operations", postgresql.ARRAY(sa.String(length=32)), nullable=False),
    sa.Column("coverage_kind", sa.String(length=16), nullable=False),
    sa.Column("access_type", sa.String(length=32), nullable=False),
    sa.Column("estimated_cost_kind", sa.String(length=16), nullable=False),
    sa.Column("estimated_cost_amount", sa.Numeric(), nullable=True),
    sa.Column("estimated_cost_currency", sa.String(length=3), nullable=True),
    sa.Column("estimated_duration_seconds", sa.Integer(), nullable=False),
    sa.Column("status", sa.String(length=16), nullable=False),
    sa.Column("attempt", sa.SmallInteger(), nullable=False),
    sa.Column("operation_digest", sa.String(length=64), nullable=False),
    sa.Column("operation_version", sa.SmallInteger(), nullable=False),
    sa.Column("schema_version", sa.SmallInteger(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("id", "collection_run_id", "workspace_id", "investigation_id", "plan_id"),
    sa.UniqueConstraint("collection_run_id", "capability"),
    sa.UniqueConstraint("collection_run_id", "priority"),
    sa.UniqueConstraint("collection_run_id", "planned_capability_id"),
    sa.UniqueConstraint("collection_run_id", "planned_connector_option_id"),
    sa.ForeignKeyConstraint(
        ["collection_run_id", "workspace_id", "investigation_id"],
        ["collection_run.id", "collection_run.workspace_id", "collection_run.investigation_id"],
        name="fk_collection_operation_run_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["planned_capability_id", "plan_id", "workspace_id", "investigation_id"],
        [
            "planned_capability.id",
            "planned_capability.plan_id",
            "planned_capability.workspace_id",
            "planned_capability.investigation_id",
        ],
        name="fk_collection_operation_capability_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        [
            "planned_connector_option_id",
            "planned_capability_id",
            "plan_id",
            "workspace_id",
            "investigation_id",
        ],
        [
            "planned_connector_option.id",
            "planned_connector_option.planned_capability_id",
            "planned_connector_option.plan_id",
            "planned_connector_option.workspace_id",
            "planned_connector_option.investigation_id",
        ],
        name="fk_collection_operation_option_scope",
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        f"operation_version = {COLLECTION_OPERATION_VERSION} AND "
        f"schema_version = {COLLECTION_OPERATION_SCHEMA_VERSION}",
        name="versions_supported",
    ),
    sa.CheckConstraint(
        f"status IN ({_sql_values(value.value for value in CollectionOperationStatus)}) "
        "AND attempt = 0",
        name="initial_state_valid",
    ),
    sa.CheckConstraint(
        f"capability IN ({_sql_values(value.value for value in ConnectorCapability)})",
        name="capability_allowed",
    ),
    sa.CheckConstraint("priority BETWEEN 1 AND 1000", name="priority_valid"),
    sa.CheckConstraint(
        "connector_id ~ '^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$' "
        "AND source_id ~ '^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$'",
        name="connector_source_format",
    ),
    sa.CheckConstraint(
        "connector_version ~ '^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$' "
        "AND contract_version ~ '^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$'",
        name="versions_format",
    ),
    sa.CheckConstraint(
        f"coverage_kind IN ({_sql_values(value.value for value in ConnectorCoverageKind)})",
        name="coverage_kind_allowed",
    ),
    sa.CheckConstraint(
        f"access_type IN ({_sql_values(value.value for value in ConnectorAccessType)})",
        name="access_type_allowed",
    ),
    sa.CheckConstraint("cardinality(connector_operations) >= 1", name="operations_not_empty"),
    sa.CheckConstraint(
        "estimated_cost_kind IN ('KNOWN', 'UNKNOWN') "
        "AND (estimated_cost_amount IS NULL) = (estimated_cost_currency IS NULL) "
        "AND (estimated_cost_kind = 'KNOWN') = (estimated_cost_amount IS NOT NULL) "
        "AND (estimated_cost_amount IS NULL OR estimated_cost_amount >= 0) "
        "AND (estimated_cost_amount IS NULL OR estimated_cost_amount NOT IN "
        "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))",
        name="estimated_cost_valid",
    ),
    sa.CheckConstraint(
        "estimated_duration_seconds BETWEEN 1 AND 2592000",
        name="estimated_duration_valid",
    ),
    sa.CheckConstraint("operation_digest ~ '^[0-9a-f]{64}$'", name="digest_format"),
)


collection_operation_dependency_table = sa.Table(
    "collection_operation_dependency",
    metadata,
    sa.Column("collection_run_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("depends_on_operation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("dependency_order", sa.SmallInteger(), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.PrimaryKeyConstraint("collection_run_id", "operation_id", "depends_on_operation_id"),
    sa.UniqueConstraint("collection_run_id", "operation_id", "dependency_order"),
    sa.ForeignKeyConstraint(
        ["operation_id", "collection_run_id", "workspace_id", "investigation_id", "plan_id"],
        [
            "collection_operation.id",
            "collection_operation.collection_run_id",
            "collection_operation.workspace_id",
            "collection_operation.investigation_id",
            "collection_operation.plan_id",
        ],
        name="fk_collection_operation_dependency_operation_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        [
            "depends_on_operation_id",
            "collection_run_id",
            "workspace_id",
            "investigation_id",
            "plan_id",
        ],
        [
            "collection_operation.id",
            "collection_operation.collection_run_id",
            "collection_operation.workspace_id",
            "collection_operation.investigation_id",
            "collection_operation.plan_id",
        ],
        name="fk_collection_operation_dependency_parent_scope",
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint("operation_id <> depends_on_operation_id", name="not_self"),
    sa.CheckConstraint("dependency_order >= 1", name="dependency_order_positive"),
)

__all__ = [
    "audit_event_table",
    "collection_operation_dependency_table",
    "collection_operation_table",
    "collection_run_table",
    "company_table",
    "entity_candidate_batch_table",
    "entity_candidate_dimension_score_table",
    "entity_candidate_table",
    "entity_resolution_decision_table",
    "investigation_plan_table",
    "investigation_table",
    "investigation_transition_table",
    "planned_capability_table",
    "planned_connector_option_table",
    "user_account_table",
    "workspace_membership_table",
    "workspace_table",
]
