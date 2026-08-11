"""Add transactional collection activation and immutable manifests.

Revision ID: 20260802_08
Revises: 20260801_07
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "20260802_08"
down_revision: str | None = "20260801_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CAPABILITIES = (
    "'COMPANY_IDENTITY', 'COMPANY_REGISTRY', 'OWNERSHIP', 'CONTACTS', "
    "'FINANCIALS', 'INSOLVENCY', 'LEGAL_CASES', 'SANCTIONS', "
    "'ADVERSE_MEDIA', 'DOCUMENTS'"
)
_ACCESS_TYPES = "'API', 'FILE', 'WEB_PUBLIC', 'USER_UPLOAD'"
_COMMAND_TYPES = (
    "'START_IDENTIFICATION', 'CANCEL_INVESTIGATION', "
    "'REQUEST_ENTITY_CONFIRMATION', 'CONFIRM_ENTITY_CANDIDATE', 'START_COLLECTION'"
)
_TRANSITION_SHAPE = (
    "(command_type = 'START_IDENTIFICATION' AND state_before = 'CREATED' "
    "AND state_after = 'IDENTIFYING' AND reason_code IS NULL) OR "
    "(command_type = 'CANCEL_INVESTIGATION' "
    "AND state_before NOT IN ('COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED') "
    "AND state_after = 'CANCELLED' AND reason_code IN "
    "('USER_REQUESTED', 'DUPLICATE_REQUEST', 'NO_LONGER_REQUIRED', 'POLICY_REQUIRED')) OR "
    "(command_type = 'REQUEST_ENTITY_CONFIRMATION' AND state_before = 'IDENTIFYING' "
    "AND state_after = 'WAITING_FOR_ENTITY_CONFIRMATION' AND reason_code IS NULL) OR "
    "(command_type = 'CONFIRM_ENTITY_CANDIDATE' "
    "AND state_before = 'WAITING_FOR_ENTITY_CONFIRMATION' "
    "AND state_after = 'PLANNING' AND reason_code IS NULL) OR "
    "(command_type = 'START_COLLECTION' AND state_before = 'PLANNING' "
    "AND state_after = 'COLLECTING' AND reason_code IS NULL)"
)
_PREVIOUS_COMMAND_TYPES = (
    "'START_IDENTIFICATION', 'CANCEL_INVESTIGATION', "
    "'REQUEST_ENTITY_CONFIRMATION', 'CONFIRM_ENTITY_CANDIDATE'"
)
_PREVIOUS_TRANSITION_SHAPE = _TRANSITION_SHAPE.rsplit(" OR ", 1)[0]


def upgrade() -> None:
    """Create F4.5 manifests, activation ledger metadata, and minimal audit fields."""

    _extend_audit_event()
    op.create_unique_constraint(
        op.f(
            "uq_planned_connector_option_id_planned_capability_id_plan_id_workspace_id_investigation_id"
        ),
        "planned_connector_option",
        ["id", "planned_capability_id", "plan_id", "workspace_id", "investigation_id"],
    )
    _create_collection_run()
    _create_collection_operation()
    _create_collection_dependency()
    _extend_transition()


def _extend_audit_event() -> None:
    for column in (
        sa.Column("collection_command_id", postgresql.UUID(as_uuid=True)),
        sa.Column("collection_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("collection_operation_count", sa.SmallInteger()),
        sa.Column("collection_activation_policy_id", sa.String(length=64)),
        sa.Column("collection_activation_policy_version", sa.Integer()),
        sa.Column("collection_maximum_estimated_cost_kind", sa.String(length=16)),
        sa.Column("collection_maximum_estimated_cost_amount", sa.Numeric()),
        sa.Column("collection_maximum_estimated_cost_currency", sa.String(length=3)),
    ):
        op.add_column("audit_event", column)
    op.create_check_constraint(
        op.f("ck_audit_event_collection_activation_metadata_complete"),
        "audit_event",
        "num_nonnulls(collection_command_id, collection_run_id, collection_operation_count, "
        "collection_activation_policy_id, collection_activation_policy_version, "
        "collection_maximum_estimated_cost_kind) IN (0, 6)",
    )
    op.create_check_constraint(
        op.f("ck_audit_event_collection_activation_metadata_valid"),
        "audit_event",
        "collection_command_id IS NULL OR (outcome = 'SUCCESS' "
        "AND resource_type = 'INVESTIGATION' "
        "AND collection_operation_count BETWEEN 1 AND 10 "
        "AND collection_activation_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND collection_activation_policy_version >= 1 "
        "AND collection_maximum_estimated_cost_kind IN ('KNOWN', 'UNKNOWN'))",
    )
    op.create_check_constraint(
        op.f("ck_audit_event_collection_activation_cost_consistency"),
        "audit_event",
        "(collection_command_id IS NULL AND collection_maximum_estimated_cost_kind IS NULL "
        "AND collection_maximum_estimated_cost_amount IS NULL "
        "AND collection_maximum_estimated_cost_currency IS NULL) OR "
        "(collection_command_id IS NOT NULL AND "
        "((collection_maximum_estimated_cost_kind = 'UNKNOWN' "
        "AND collection_maximum_estimated_cost_amount IS NULL "
        "AND collection_maximum_estimated_cost_currency IS NULL) OR "
        "(collection_maximum_estimated_cost_kind = 'KNOWN' "
        "AND collection_maximum_estimated_cost_amount IS NOT NULL "
        "AND collection_maximum_estimated_cost_currency IS NOT NULL)))",
    )
    op.create_check_constraint(
        op.f("ck_audit_event_collection_activation_cost_valid"),
        "audit_event",
        "collection_maximum_estimated_cost_amount IS NULL OR "
        "(collection_maximum_estimated_cost_amount >= 0 AND "
        "collection_maximum_estimated_cost_amount NOT IN "
        "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))",
    )


def _create_collection_run() -> None:
    op.create_table(
        "collection_run",
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
        sa.Column("budget_amount", sa.Numeric()),
        sa.Column("budget_currency", sa.String(length=3)),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("maximum_estimated_cost_kind", sa.String(length=16), nullable=False),
        sa.Column("maximum_estimated_cost_amount", sa.Numeric()),
        sa.Column("maximum_estimated_cost_currency", sa.String(length=3)),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_digest", sa.String(length=64), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("investigation_state_version", sa.Integer(), nullable=False),
        sa.Column("run_digest", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_run")),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            "investigation_id",
            name=op.f("uq_collection_run_id_workspace_id_investigation_id"),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "investigation_id",
            name=op.f("uq_collection_run_workspace_id_investigation_id"),
        ),
        sa.UniqueConstraint(
            "workspace_id", "plan_id", name=op.f("uq_collection_run_workspace_id_plan_id")
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "command_id",
            name=op.f("uq_collection_run_workspace_id_command_id"),
        ),
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
            "run_version = 1 AND schema_version = 1",
            name=op.f("ck_collection_run_versions_supported"),
        ),
        sa.CheckConstraint("status = 'PENDING'", name=op.f("ck_collection_run_status_allowed")),
        sa.CheckConstraint(
            "activation_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' AND activation_policy_version >= 1",
            name=op.f("ck_collection_run_policy_reference_valid"),
        ),
        sa.CheckConstraint(
            "activation_policy_digest ~ '^[0-9a-f]{64}$' "
            "AND plan_digest ~ '^[0-9a-f]{64}$' "
            "AND company_snapshot_digest ~ '^[0-9a-f]{64}$' "
            "AND command_digest ~ '^[0-9a-f]{64}$' "
            "AND run_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_collection_run_digests_format"),
        ),
        sa.CheckConstraint(
            "investigation_state_version >= 2", name=op.f("ck_collection_run_state_version_valid")
        ),
        sa.CheckConstraint(
            "(budget_amount IS NULL) = (budget_currency IS NULL) "
            "AND (budget_amount IS NULL OR budget_amount >= 0) "
            "AND (budget_amount IS NULL OR budget_amount NOT IN "
            "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))",
            name=op.f("ck_collection_run_budget_valid"),
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
            name=op.f("ck_collection_run_maximum_cost_valid"),
        ),
        sa.CheckConstraint(
            "budget_currency IS NULL OR budget_currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_collection_run_budget_currency_format"),
        ),
        sa.CheckConstraint(
            "maximum_estimated_cost_currency IS NULL OR "
            "maximum_estimated_cost_currency ~ '^[A-Z]{3}$'",
            name=op.f("ck_collection_run_maximum_cost_currency_format"),
        ),
    )
    op.create_index(
        "ix_collection_run_workspace_created_at", "collection_run", ["workspace_id", "created_at"]
    )


def _create_collection_operation() -> None:
    op.create_table(
        "collection_operation",
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
        sa.Column("estimated_cost_amount", sa.Numeric()),
        sa.Column("estimated_cost_currency", sa.String(length=3)),
        sa.Column("estimated_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt", sa.SmallInteger(), nullable=False),
        sa.Column("operation_digest", sa.String(length=64), nullable=False),
        sa.Column("operation_version", sa.SmallInteger(), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_operation")),
        sa.UniqueConstraint(
            "id",
            "collection_run_id",
            "workspace_id",
            "investigation_id",
            "plan_id",
            name=op.f(
                "uq_collection_operation_id_collection_run_id_workspace_id_investigation_id_plan_id"
            ),
        ),
        sa.UniqueConstraint(
            "collection_run_id",
            "capability",
            name=op.f("uq_collection_operation_collection_run_id_capability"),
        ),
        sa.UniqueConstraint(
            "collection_run_id",
            "priority",
            name=op.f("uq_collection_operation_collection_run_id_priority"),
        ),
        sa.UniqueConstraint(
            "collection_run_id",
            "planned_capability_id",
            name=op.f("uq_collection_operation_collection_run_id_planned_capability_id"),
        ),
        sa.UniqueConstraint(
            "collection_run_id",
            "planned_connector_option_id",
            name=op.f("uq_collection_operation_collection_run_id_planned_connector_option_id"),
        ),
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
            "operation_version = 1 AND schema_version = 1",
            name=op.f("ck_collection_operation_versions_supported"),
        ),
        sa.CheckConstraint(
            "status = 'PENDING' AND attempt = 0",
            name=op.f("ck_collection_operation_initial_state_valid"),
        ),
        sa.CheckConstraint(
            f"capability IN ({_CAPABILITIES})",
            name=op.f("ck_collection_operation_capability_allowed"),
        ),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 1000", name=op.f("ck_collection_operation_priority_valid")
        ),
        sa.CheckConstraint(
            "connector_id ~ '^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$' "
            "AND source_id ~ '^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$'",
            name=op.f("ck_collection_operation_connector_source_format"),
        ),
        sa.CheckConstraint(
            r"connector_version ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\."
            r"(0|[1-9][0-9]*)$' AND contract_version ~ '^(0|[1-9][0-9]*)\."
            r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'",
            name=op.f("ck_collection_operation_versions_format"),
        ),
        sa.CheckConstraint(
            "coverage_kind IN ('GLOBAL', 'COUNTRY_SET')",
            name=op.f("ck_collection_operation_coverage_kind_allowed"),
        ),
        sa.CheckConstraint(
            f"access_type IN ({_ACCESS_TYPES})",
            name=op.f("ck_collection_operation_access_type_allowed"),
        ),
        sa.CheckConstraint(
            "cardinality(connector_operations) >= 1",
            name=op.f("ck_collection_operation_operations_not_empty"),
        ),
        sa.CheckConstraint(
            "estimated_cost_kind IN ('KNOWN', 'UNKNOWN') "
            "AND (estimated_cost_amount IS NULL) = (estimated_cost_currency IS NULL) "
            "AND (estimated_cost_kind = 'KNOWN') = (estimated_cost_amount IS NOT NULL) "
            "AND (estimated_cost_amount IS NULL OR estimated_cost_amount >= 0) "
            "AND (estimated_cost_amount IS NULL OR estimated_cost_amount NOT IN "
            "('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric))",
            name=op.f("ck_collection_operation_estimated_cost_valid"),
        ),
        sa.CheckConstraint(
            "estimated_duration_seconds BETWEEN 1 AND 2592000",
            name=op.f("ck_collection_operation_estimated_duration_valid"),
        ),
        sa.CheckConstraint(
            "operation_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_collection_operation_digest_format"),
        ),
    )


def _create_collection_dependency() -> None:
    op.create_table(
        "collection_operation_dependency",
        sa.Column("collection_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("depends_on_operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dependency_order", sa.SmallInteger(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "collection_run_id",
            "operation_id",
            "depends_on_operation_id",
            name=op.f("pk_collection_operation_dependency"),
        ),
        sa.UniqueConstraint(
            "collection_run_id",
            "operation_id",
            "dependency_order",
            name=op.f(
                "uq_collection_operation_dependency_collection_run_id_operation_id_dependency_order"
            ),
        ),
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
        sa.CheckConstraint(
            "operation_id <> depends_on_operation_id",
            name=op.f("ck_collection_operation_dependency_not_self"),
        ),
        sa.CheckConstraint(
            "dependency_order >= 1",
            name=op.f("ck_collection_operation_dependency_dependency_order_positive"),
        ),
    )


def _extend_transition() -> None:
    for column in (
        sa.Column("collection_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("collection_operation_count", sa.SmallInteger()),
        sa.Column("collection_activation_policy_id", sa.String(length=64)),
        sa.Column("collection_activation_policy_version", sa.Integer()),
    ):
        op.add_column("investigation_transition", column)
    op.drop_constraint(
        op.f("ck_investigation_transition_command_type_allowed"),
        "investigation_transition",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_investigation_transition_command_transition_shape"),
        "investigation_transition",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_command_type_allowed"),
        "investigation_transition",
        f"command_type IN ({_COMMAND_TYPES})",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_command_transition_shape"),
        "investigation_transition",
        _TRANSITION_SHAPE,
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_collection_activation_metadata_complete"),
        "investigation_transition",
        "(command_type = 'START_COLLECTION') = (collection_run_id IS NOT NULL) AND "
        "num_nonnulls(collection_run_id, collection_operation_count, "
        "collection_activation_policy_id, collection_activation_policy_version) IN (0, 4)",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_collection_activation_metadata_valid"),
        "investigation_transition",
        "collection_run_id IS NULL OR (collection_operation_count BETWEEN 1 AND 10 "
        "AND collection_activation_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND collection_activation_policy_version >= 1)",
    )
    op.create_foreign_key(
        "fk_investigation_transition_collection_run_scope",
        "investigation_transition",
        "collection_run",
        ["collection_run_id", "workspace_id", "investigation_id"],
        ["id", "workspace_id", "investigation_id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
        use_alter=True,
    )


def downgrade() -> None:
    """Remove F4.5 only when no immutable collection history would be lost."""

    if not context.is_offline_mode() and op.get_bind().scalar(
        sa.text("SELECT count(*) FROM collection_run")
    ):
        raise RuntimeError("Cannot downgrade F4.5 while collection runs exist.")
    op.drop_constraint(
        "fk_investigation_transition_collection_run_scope",
        "investigation_transition",
        type_="foreignkey",
    )
    for name in ("metadata_valid", "metadata_complete"):
        op.drop_constraint(
            op.f(f"ck_investigation_transition_collection_activation_{name}"),
            "investigation_transition",
            type_="check",
        )
    op.drop_constraint(
        op.f("ck_investigation_transition_command_transition_shape"),
        "investigation_transition",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_investigation_transition_command_type_allowed"),
        "investigation_transition",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_command_type_allowed"),
        "investigation_transition",
        f"command_type IN ({_PREVIOUS_COMMAND_TYPES})",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_command_transition_shape"),
        "investigation_transition",
        _PREVIOUS_TRANSITION_SHAPE,
    )
    for column in (
        "collection_activation_policy_version",
        "collection_activation_policy_id",
        "collection_operation_count",
        "collection_run_id",
    ):
        op.drop_column("investigation_transition", column)
    op.drop_table("collection_operation_dependency")
    op.drop_table("collection_operation")
    op.drop_index("ix_collection_run_workspace_created_at", table_name="collection_run")
    op.drop_table("collection_run")
    op.drop_constraint(
        op.f(
            "uq_planned_connector_option_id_planned_capability_id_plan_id_workspace_id_investigation_id"
        ),
        "planned_connector_option",
        type_="unique",
    )
    for name in ("cost_valid", "cost_consistency", "metadata_valid", "metadata_complete"):
        op.drop_constraint(
            op.f(f"ck_audit_event_collection_activation_{name}"), "audit_event", type_="check"
        )
    for column in (
        "collection_maximum_estimated_cost_currency",
        "collection_maximum_estimated_cost_amount",
        "collection_maximum_estimated_cost_kind",
        "collection_activation_policy_version",
        "collection_activation_policy_id",
        "collection_operation_count",
        "collection_run_id",
        "collection_command_id",
    ):
        op.drop_column("audit_event", column)
