"""Add append-only direct collection execution ownership and receipts.

Revision ID: 20260811_10
Revises: 20260802_09
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "20260811_10"
down_revision: str | None = "20260802_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist immutable ownership and one redacted completion per manifest operation."""

    op.create_unique_constraint(
        op.f("uq_collection_operation_id_collection_run_id_workspace_id_investigation_id"),
        "collection_operation",
        ["id", "collection_run_id", "workspace_id", "investigation_id"],
    )
    op.create_table(
        "collection_operation_execution",
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_digest", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_id", sa.String(length=128), nullable=False),
        sa.Column("connector_version", sa.String(length=32), nullable=False),
        sa.Column("contract_version", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("source_policy_version", sa.String(length=64), nullable=False),
        sa.Column("accepted_locales", postgresql.ARRAY(sa.String(length=16)), nullable=False),
        sa.Column("execution_policy_snapshot", sa.Text(), nullable=False),
        sa.Column("execution_policy_digest", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ownership_digest", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("command_id", name=op.f("pk_collection_operation_execution")),
        sa.UniqueConstraint(
            "workspace_id",
            "collection_operation_id",
            name=op.f("uq_collection_operation_execution_workspace_id_collection_operation_id"),
        ),
        sa.UniqueConstraint(
            "command_id",
            "workspace_id",
            "investigation_id",
            "collection_run_id",
            "collection_operation_id",
            name=op.f(
                "uq_collection_operation_execution_command_id_workspace_id_investigation_id_collection_run_id_collection_operation_id"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["collection_operation_id", "collection_run_id", "workspace_id", "investigation_id"],
            [
                "collection_operation.id",
                "collection_operation.collection_run_id",
                "collection_operation.workspace_id",
                "collection_operation.investigation_id",
            ],
            name=op.f("fk_collection_operation_execution_operation_scope"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["user_account.id"],
            name=op.f("fk_collection_operation_execution_actor"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "schema_version = 1",
            name=op.f("ck_collection_operation_execution_schema_version_supported"),
        ),
        sa.CheckConstraint(
            "command_digest ~ '^[0-9a-f]{64}$' "
            "AND execution_policy_digest ~ '^[0-9a-f]{64}$' "
            "AND ownership_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_collection_operation_execution_digests_format"),
        ),
        sa.CheckConstraint(
            "connector_id ~ '^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$' "
            "AND source_id ~ '^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$'",
            name=op.f("ck_collection_operation_execution_connector_source_format"),
        ),
        sa.CheckConstraint(
            "connector_version ~ '^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\."
            "(0|[1-9][0-9]*)$' AND contract_version ~ "
            "'^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$'",
            name=op.f("ck_collection_operation_execution_versions_format"),
        ),
        sa.CheckConstraint(
            "source_policy_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]*$' "
            "AND cardinality(accepted_locales) >= 1",
            name=op.f("ck_collection_operation_execution_source_policy_locales_valid"),
        ),
    )
    op.create_table(
        "collection_operation_execution_result",
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_digest", sa.String(length=64), nullable=False),
        sa.Column("outcome_status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("warning_codes", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("attempts_started", sa.SmallInteger(), nullable=False),
        sa.Column("usage_calls", sa.Integer(), nullable=False),
        sa.Column("usage_bytes_received", sa.BigInteger(), nullable=False),
        sa.Column("usage_duration_microseconds", sa.BigInteger(), nullable=False),
        sa.Column("usage_cost_amount", sa.Numeric(), nullable=True),
        sa.Column("usage_cost_currency", sa.String(length=3), nullable=True),
        sa.Column("usage_cost_kind", sa.String(length=16), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("execution_digest", sa.String(length=64), nullable=False),
        sa.Column("idempotency_status", sa.String(length=16), nullable=False),
        sa.Column("control_code", sa.String(length=32), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_digest", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint(
            "command_id", name=op.f("pk_collection_operation_execution_result")
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "collection_operation_id",
            name=op.f(
                "uq_collection_operation_execution_result_workspace_id_collection_operation_id"
            ),
        ),
        sa.ForeignKeyConstraint(
            [
                "command_id",
                "workspace_id",
                "investigation_id",
                "collection_run_id",
                "collection_operation_id",
            ],
            [
                "collection_operation_execution.command_id",
                "collection_operation_execution.workspace_id",
                "collection_operation_execution.investigation_id",
                "collection_operation_execution.collection_run_id",
                "collection_operation_execution.collection_operation_id",
            ],
            name=op.f("fk_collection_operation_execution_result_ownership_scope"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "schema_version = 1",
            name=op.f("ck_collection_operation_execution_result_schema_version_supported"),
        ),
        sa.CheckConstraint(
            "outcome_status IN ('SUCCEEDED','NO_RESULTS','PARTIAL','FAILED','CANCELLED')",
            name=op.f("ck_collection_operation_execution_result_outcome_status_allowed"),
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR error_code IN "
            "('INVALID_REQUEST','UNSUPPORTED_COUNTRY','UNSUPPORTED_CAPABILITY',"
            "'UNSUPPORTED_OPERATION','AUTH_REQUIRED','POLICY_BLOCKED','RATE_LIMITED',"
            "'TIMEOUT','UNAVAILABLE','INVALID_RESPONSE','BUDGET_EXCEEDED','CANCELLED',"
            "'INTERNAL_ERROR')",
            name=op.f("ck_collection_operation_execution_result_error_code_allowed"),
        ),
        sa.CheckConstraint(
            "warning_codes <@ ARRAY['TRUNCATED','PARTIAL_DATA','STALE_DATA',"
            "'PAGINATION_LIMITED','POLICY_REDACTED','PARSING_WARNING']::varchar[]",
            name=op.f("ck_collection_operation_execution_result_warning_codes_allowed"),
        ),
        sa.CheckConstraint(
            "idempotency_status IN ('NOT_RESERVED','EXECUTED','REPLAYED','CONFLICT')",
            name=op.f("ck_collection_operation_execution_result_idempotency_status_allowed"),
        ),
        sa.CheckConstraint(
            "control_code IS NULL OR control_code IN "
            "('IDEMPOTENCY_CONFLICT','DEADLINE_EXPIRED','CANCELLATION_OBSERVED',"
            "'BUDGET_BLOCKED','INVALID_CONNECTOR_RESPONSE','CONNECTOR_EXCEPTION')",
            name=op.f("ck_collection_operation_execution_result_control_code_allowed"),
        ),
        sa.CheckConstraint(
            "attempts_started >= 0 AND usage_calls >= 0 "
            "AND usage_bytes_received >= 0 AND usage_duration_microseconds >= 0",
            name=op.f("ck_collection_operation_execution_result_usage_non_negative"),
        ),
        sa.CheckConstraint(
            "(usage_cost_amount IS NULL) = (usage_cost_currency IS NULL) "
            "AND (usage_cost_amount IS NULL) = (usage_cost_kind IS NULL) "
            "AND (usage_cost_amount IS NULL OR usage_cost_amount >= 0) "
            "AND (usage_cost_amount IS NULL OR usage_cost_amount::text NOT IN "
            "('NaN', 'Infinity', '-Infinity')) "
            "AND (usage_cost_currency IS NULL OR usage_cost_currency ~ '^[A-Z]{3}$') "
            "AND (usage_cost_kind IS NULL OR usage_cost_kind IN ('KNOWN','ESTIMATED'))",
            name=op.f("ck_collection_operation_execution_result_usage_cost_valid"),
        ),
        sa.CheckConstraint(
            "command_digest ~ '^[0-9a-f]{64}$' "
            "AND request_fingerprint ~ '^[0-9a-f]{64}$' "
            "AND execution_digest ~ '^[0-9a-f]{64}$' "
            "AND result_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_collection_operation_execution_result_digests_format"),
        ),
    )


def downgrade() -> None:
    """Remove F4.6 only when no execution history would be lost."""

    if not context.is_offline_mode() and op.get_bind().scalar(
        sa.text("SELECT count(*) FROM collection_operation_execution")
    ):
        raise RuntimeError("Cannot downgrade F4.6 while collection executions exist.")
    op.drop_table("collection_operation_execution_result")
    op.drop_table("collection_operation_execution")
    op.drop_constraint(
        op.f("uq_collection_operation_id_collection_run_id_workspace_id_investigation_id"),
        "collection_operation",
        type_="unique",
    )
