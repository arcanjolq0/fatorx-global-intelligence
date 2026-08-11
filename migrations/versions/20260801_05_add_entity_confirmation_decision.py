"""Add human entity confirmation decision and canonical Company materialization.

Revision ID: 20260801_05
Revises: 20260729_04
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_05"
down_revision: str | None = "20260729_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONFIRMATION_REASONS = (
    "'IDENTIFIERS_REVIEWED', 'CORPORATE_DATA_REVIEWED', "
    "'SOURCE_REFERENCE_REVIEWED', 'MANUAL_OVERRIDE'"
)
_NON_EXCLUDED_CLASSIFICATIONS = "'HIGH', 'MEDIUM', 'LOW'"
_TERMINAL_STATES = "'COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED'"
_POST_CONFIRMATION_STATES = (
    "'PLANNING', 'COLLECTING', 'NORMALIZING', 'VERIFYING', 'ANALYZING', "
    "'WAITING_FOR_REVIEW', 'COMPLETED', 'PARTIALLY_COMPLETED'"
)


def upgrade() -> None:
    """Persist positive human confirmation and its canonical materialization."""

    _allow_unknown_company_status()
    op.create_check_constraint(
        op.f("ck_investigation_entity_confirmation_state_consistency"),
        "investigation",
        "(state IN ('CREATED', 'IDENTIFYING', 'WAITING_FOR_ENTITY_CONFIRMATION') "
        "AND confirmed_company_id IS NULL) OR "
        f"(state IN ({_POST_CONFIRMATION_STATES}) AND confirmed_company_id IS NOT NULL) OR "
        "(state IN ('FAILED', 'CANCELLED'))",
        postgresql_not_valid=True,
    )
    _create_entity_resolution_decision()
    _extend_transition_ledger()
    _extend_audit_event()


def _allow_unknown_company_status() -> None:
    op.drop_constraint(op.f("ck_company_status_allowed"), "company", type_="check")
    op.create_check_constraint(
        op.f("ck_company_status_allowed"),
        "company",
        "status IN ('ACTIVE', 'INACTIVE', 'DISSOLVED', 'UNKNOWN')",
    )


def _create_entity_resolution_decision() -> None:
    op.create_table(
        "entity_resolution_decision",
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
        sa.CheckConstraint(
            "decision_type = 'CONFIRMED'",
            name=op.f("ck_entity_resolution_decision_decision_type_confirmed"),
        ),
        sa.CheckConstraint(
            "decision_schema_version = 1",
            name=op.f("ck_entity_resolution_decision_decision_schema_supported"),
        ),
        sa.CheckConstraint(
            f"review_reason IN ({_CONFIRMATION_REASONS})",
            name=op.f("ck_entity_resolution_decision_review_reason_allowed"),
        ),
        sa.CheckConstraint(
            f"candidate_classification IN ({_NON_EXCLUDED_CLASSIFICATIONS})",
            name=op.f("ck_entity_resolution_decision_candidate_classification_allowed"),
        ),
        sa.CheckConstraint(
            "review_reason = 'MANUAL_OVERRIDE' OR "
            "(candidate_rank = 1 AND candidate_classification IN ('HIGH', 'MEDIUM'))",
            name=op.f("ck_entity_resolution_decision_review_reason_compatible"),
        ),
        sa.CheckConstraint(
            "candidate_rank BETWEEN 1 AND 100",
            name=op.f("ck_entity_resolution_decision_candidate_rank_range"),
        ),
        sa.CheckConstraint(
            "candidate_total_score BETWEEN 0 AND 10000 AND candidate_coverage BETWEEN 0 AND 10000",
            name=op.f("ck_entity_resolution_decision_candidate_score_coverage_range"),
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
            name=op.f("ck_entity_resolution_decision_digests_format"),
        ),
        sa.CheckConstraint(
            "matching_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
            "AND materialization_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
            "AND matching_policy_version >= 1 AND materialization_policy_version >= 1",
            name=op.f("ck_entity_resolution_decision_policy_references_valid"),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entity_resolution_decision")),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            "investigation_id",
            "command_id",
            name=op.f("uq_entity_resolution_decision_id_workspace_id_investigation_id_command_id"),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "investigation_id",
            name=op.f("uq_entity_resolution_decision_workspace_id_investigation_id"),
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "command_id",
            name=op.f("uq_entity_resolution_decision_workspace_id_command_id"),
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "company_id",
            name=op.f("uq_entity_resolution_decision_workspace_id_company_id"),
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    for suffix, columns in (
        ("investigation", ["workspace_id", "investigation_id"]),
        ("company", ["workspace_id", "company_id"]),
        ("batch", ["workspace_id", "candidate_batch_id"]),
        ("command", ["workspace_id", "command_id"]),
    ):
        op.create_index(
            f"ix_entity_resolution_decision_workspace_{suffix}",
            "entity_resolution_decision",
            columns,
            unique=False,
        )


def _extend_transition_ledger() -> None:
    columns = (
        sa.Column("confirmation_decision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("confirmed_company_id", postgresql.UUID(as_uuid=True)),
        sa.Column("confirmed_candidate_batch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("confirmed_candidate_id", postgresql.UUID(as_uuid=True)),
        sa.Column("confirmation_reason_code", sa.String(length=64)),
        sa.Column("confirmed_candidate_classification", sa.String(length=16)),
        sa.Column("confirmed_candidate_rank", sa.SmallInteger()),
        sa.Column("matching_policy_id", sa.String(length=64)),
        sa.Column("matching_policy_version", sa.Integer()),
        sa.Column("materialization_policy_id", sa.String(length=64)),
        sa.Column("materialization_policy_version", sa.Integer()),
    )
    for column in columns:
        op.add_column("investigation_transition", column)
    op.create_foreign_key(
        "fk_investigation_transition_confirmed_company_scope",
        "investigation_transition",
        "company",
        ["confirmed_company_id", "workspace_id"],
        ["id", "workspace_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_investigation_transition_confirmed_batch_scope",
        "investigation_transition",
        "entity_candidate_batch",
        ["confirmed_candidate_batch_id", "workspace_id", "investigation_id"],
        ["id", "workspace_id", "investigation_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_investigation_transition_confirmed_candidate_scope",
        "investigation_transition",
        "entity_candidate",
        [
            "confirmed_candidate_id",
            "workspace_id",
            "investigation_id",
            "confirmed_candidate_batch_id",
        ],
        ["id", "workspace_id", "investigation_id", "batch_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_investigation_transition_confirmation_decision",
        "investigation_transition",
        "entity_resolution_decision",
        ["confirmation_decision_id", "workspace_id", "investigation_id", "command_id"],
        ["id", "workspace_id", "investigation_id", "command_id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
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
        "command_type IN ('START_IDENTIFICATION', 'CANCEL_INVESTIGATION', "
        "'REQUEST_ENTITY_CONFIRMATION', 'CONFIRM_ENTITY_CANDIDATE')",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_command_transition_shape"),
        "investigation_transition",
        "(command_type = 'START_IDENTIFICATION' AND state_before = 'CREATED' "
        "AND state_after = 'IDENTIFYING' AND reason_code IS NULL) OR "
        "(command_type = 'CANCEL_INVESTIGATION' AND state_before NOT IN "
        f"({_TERMINAL_STATES}) AND state_after = 'CANCELLED' AND reason_code IN "
        "('USER_REQUESTED', 'DUPLICATE_REQUEST', 'NO_LONGER_REQUIRED', "
        "'POLICY_REQUIRED')) OR (command_type = 'REQUEST_ENTITY_CONFIRMATION' "
        "AND state_before = 'IDENTIFYING' AND state_after = "
        "'WAITING_FOR_ENTITY_CONFIRMATION' AND reason_code IS NULL) OR "
        "(command_type = 'CONFIRM_ENTITY_CANDIDATE' AND state_before = "
        "'WAITING_FOR_ENTITY_CONFIRMATION' AND state_after = 'PLANNING' "
        "AND reason_code IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_entity_confirmation_metadata_complete"),
        "investigation_transition",
        "(command_type = 'CONFIRM_ENTITY_CANDIDATE') = "
        "(confirmation_decision_id IS NOT NULL) AND "
        "num_nonnulls(confirmation_decision_id, confirmed_company_id, "
        "confirmed_candidate_batch_id, confirmed_candidate_id, confirmation_reason_code, "
        "confirmed_candidate_classification, confirmed_candidate_rank, matching_policy_id, "
        "matching_policy_version, materialization_policy_id, "
        "materialization_policy_version) IN (0, 11)",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_entity_confirmation_metadata_valid"),
        "investigation_transition",
        "confirmation_decision_id IS NULL OR (confirmation_reason_code IN "
        f"({_CONFIRMATION_REASONS}) AND confirmed_candidate_classification IN "
        f"({_NON_EXCLUDED_CLASSIFICATIONS}) AND confirmed_candidate_rank BETWEEN 1 AND 100 "
        "AND matching_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND matching_policy_version >= 1 "
        "AND materialization_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND materialization_policy_version >= 1)",
    )


def _extend_audit_event() -> None:
    columns = (
        sa.Column("confirmation_command_id", postgresql.UUID(as_uuid=True)),
        sa.Column("entity_resolution_decision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("confirmed_company_id", postgresql.UUID(as_uuid=True)),
        sa.Column("confirmed_candidate_batch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("confirmed_candidate_id", postgresql.UUID(as_uuid=True)),
        sa.Column("confirmation_reason_code", sa.String(length=64)),
        sa.Column("confirmed_candidate_classification", sa.String(length=16)),
        sa.Column("confirmed_candidate_rank", sa.SmallInteger()),
        sa.Column("matching_policy_id", sa.String(length=64)),
        sa.Column("matching_policy_version", sa.Integer()),
        sa.Column("materialization_policy_id", sa.String(length=64)),
        sa.Column("materialization_policy_version", sa.Integer()),
    )
    for column in columns:
        op.add_column("audit_event", column)
    op.create_check_constraint(
        op.f("ck_audit_event_entity_confirmation_metadata_complete"),
        "audit_event",
        "num_nonnulls(confirmation_command_id, entity_resolution_decision_id, "
        "confirmed_company_id, confirmed_candidate_batch_id, confirmed_candidate_id, "
        "confirmation_reason_code, confirmed_candidate_classification, "
        "confirmed_candidate_rank, matching_policy_id, matching_policy_version, "
        "materialization_policy_id, materialization_policy_version) IN (0, 12)",
    )
    op.create_check_constraint(
        op.f("ck_audit_event_entity_confirmation_metadata_valid"),
        "audit_event",
        "confirmation_command_id IS NULL OR (outcome = 'SUCCESS' "
        "AND resource_type = 'INVESTIGATION' AND confirmation_reason_code IN "
        f"({_CONFIRMATION_REASONS}) AND confirmed_candidate_classification IN "
        f"({_NON_EXCLUDED_CLASSIFICATIONS}) AND confirmed_candidate_rank BETWEEN 1 AND 100 "
        "AND matching_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND matching_policy_version >= 1 "
        "AND materialization_policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' "
        "AND materialization_policy_version >= 1)",
    )


def downgrade() -> None:
    """Restore F4.2.1, refusing to lose persisted UNKNOWN semantics."""

    confirmation_rows = op.get_bind().scalar(
        sa.text(
            "SELECT (SELECT count(*) FROM entity_resolution_decision) + "
            "(SELECT count(*) FROM investigation_transition "
            "WHERE command_type = 'CONFIRM_ENTITY_CANDIDATE')"
        )
    )
    if confirmation_rows:
        raise RuntimeError("Cannot downgrade F4.3 while entity confirmation records exist.")
    unknown_rows = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM company WHERE status = 'UNKNOWN'")
    )
    if unknown_rows:
        raise RuntimeError("Cannot downgrade F4.3 while Company rows use UNKNOWN status.")
    _downgrade_audit_event()
    _downgrade_transition_ledger()
    for suffix in ("command", "batch", "company", "investigation"):
        op.drop_index(
            f"ix_entity_resolution_decision_workspace_{suffix}",
            table_name="entity_resolution_decision",
        )
    op.drop_table("entity_resolution_decision")
    op.drop_constraint(
        op.f("ck_investigation_entity_confirmation_state_consistency"),
        "investigation",
        type_="check",
    )
    op.drop_constraint(op.f("ck_company_status_allowed"), "company", type_="check")
    op.create_check_constraint(
        op.f("ck_company_status_allowed"),
        "company",
        "status IN ('ACTIVE', 'INACTIVE', 'DISSOLVED')",
    )


def _downgrade_audit_event() -> None:
    for name in (
        "entity_confirmation_metadata_valid",
        "entity_confirmation_metadata_complete",
    ):
        op.drop_constraint(op.f(f"ck_audit_event_{name}"), "audit_event", type_="check")
    for column in (
        "materialization_policy_version",
        "materialization_policy_id",
        "matching_policy_version",
        "matching_policy_id",
        "confirmed_candidate_rank",
        "confirmed_candidate_classification",
        "confirmation_reason_code",
        "confirmed_candidate_id",
        "confirmed_candidate_batch_id",
        "confirmed_company_id",
        "entity_resolution_decision_id",
        "confirmation_command_id",
    ):
        op.drop_column("audit_event", column)


def _downgrade_transition_ledger() -> None:
    for name in (
        "entity_confirmation_metadata_valid",
        "entity_confirmation_metadata_complete",
        "command_transition_shape",
        "command_type_allowed",
    ):
        op.drop_constraint(
            op.f(f"ck_investigation_transition_{name}"),
            "investigation_transition",
            type_="check",
        )
    for name in (
        "fk_investigation_transition_confirmation_decision",
        "fk_investigation_transition_confirmed_candidate_scope",
        "fk_investigation_transition_confirmed_batch_scope",
        "fk_investigation_transition_confirmed_company_scope",
    ):
        op.drop_constraint(name, "investigation_transition", type_="foreignkey")
    for column in (
        "materialization_policy_version",
        "materialization_policy_id",
        "matching_policy_version",
        "matching_policy_id",
        "confirmed_candidate_rank",
        "confirmed_candidate_classification",
        "confirmation_reason_code",
        "confirmed_candidate_id",
        "confirmed_candidate_batch_id",
        "confirmed_company_id",
        "confirmation_decision_id",
    ):
        op.drop_column("investigation_transition", column)
    op.create_check_constraint(
        op.f("ck_investigation_transition_command_type_allowed"),
        "investigation_transition",
        "command_type IN ('START_IDENTIFICATION', 'CANCEL_INVESTIGATION', "
        "'REQUEST_ENTITY_CONFIRMATION')",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_command_transition_shape"),
        "investigation_transition",
        "(command_type = 'START_IDENTIFICATION' AND state_before = 'CREATED' "
        "AND state_after = 'IDENTIFYING' AND reason_code IS NULL) OR "
        "(command_type = 'CANCEL_INVESTIGATION' AND state_before NOT IN "
        f"({_TERMINAL_STATES}) AND state_after = 'CANCELLED' AND reason_code IN "
        "('USER_REQUESTED', 'DUPLICATE_REQUEST', 'NO_LONGER_REQUIRED', "
        "'POLICY_REQUIRED')) OR (command_type = 'REQUEST_ENTITY_CONFIRMATION' "
        "AND state_before = 'IDENTIFYING' AND state_after = "
        "'WAITING_FOR_ENTITY_CONFIRMATION' AND reason_code IS NULL)",
    )
