"""Add deterministic entity-candidate matching and review-pause persistence.

Revision ID: 20260729_04
Revises: 20260729_03
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260729_04"
down_revision: str | None = "20260729_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CLASSIFICATIONS = "'HIGH', 'MEDIUM', 'LOW', 'EXCLUDED'"
_DIMENSIONS = "'IDENTIFIER', 'NAME', 'DOMAIN', 'GEOGRAPHY', 'ADDRESS', 'ADMINISTRATORS', 'TEMPORAL'"
_EXPLANATIONS = (
    "'IDENTIFIER_EXACT', 'IDENTIFIER_CONFLICT', 'IDENTIFIER_UNAVAILABLE', "
    "'NAME_LEGAL_EXACT', 'NAME_TRADE_EXACT', 'NAME_CROSS_EXACT', "
    "'NAME_TOKENS_EQUIVALENT', 'NAME_DIFFERENT', 'NAME_UNAVAILABLE', "
    "'DOMAIN_EXACT', 'DOMAIN_DIFFERENT', 'DOMAIN_UNAVAILABLE', "
    "'GEOGRAPHY_EXACT', 'GEOGRAPHY_CONFLICT', 'ADDRESS_EXACT', "
    "'ADDRESS_PARTIAL', 'ADDRESS_DIFFERENT', 'ADDRESS_UNAVAILABLE', "
    "'ADMINISTRATORS_EXACT', 'ADMINISTRATORS_PARTIAL', "
    "'ADMINISTRATORS_DIFFERENT', 'ADMINISTRATORS_UNAVAILABLE', "
    "'TEMPORAL_EXACT', 'TEMPORAL_DIFFERENT', 'TEMPORAL_UNAVAILABLE'"
)


def upgrade() -> None:
    """Persist one immutable candidate batch and the pause transition atomically."""

    op.drop_constraint(
        op.f("ck_investigation_input_schema_version_supported"),
        "investigation",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_investigation_input_schema_version_supported"),
        "investigation",
        "input_schema_version IS NULL OR input_schema_version IN (1, 2)",
    )

    op.create_table(
        "entity_candidate_batch",
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
        sa.CheckConstraint(
            "batch_version = 1", name=op.f("ck_entity_candidate_batch_batch_version_supported")
        ),
        sa.CheckConstraint(
            "input_digest ~ '^[0-9a-f]{64}$' AND policy_digest ~ '^[0-9a-f]{64}$' "
            "AND submission_digest ~ '^[0-9a-f]{64}$' "
            "AND evaluation_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_entity_candidate_batch_digests_format"),
        ),
        sa.CheckConstraint(
            "policy_id ~ '^[A-Z][A-Z0-9_.:-]*$'",
            name=op.f("ck_entity_candidate_batch_policy_id_format"),
        ),
        sa.CheckConstraint(
            "policy_version >= 1",
            name=op.f("ck_entity_candidate_batch_policy_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user_account.id"],
            name="fk_entity_candidate_batch_created_by",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id", "workspace_id"],
            ["investigation.id", "investigation.workspace_id"],
            name="fk_entity_candidate_batch_investigation_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entity_candidate_batch")),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            "investigation_id",
            name=op.f("uq_entity_candidate_batch_id_workspace_id_investigation_id"),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "command_id",
            name=op.f("uq_entity_candidate_batch_workspace_id_command_id"),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "investigation_id",
            name=op.f("uq_entity_candidate_batch_workspace_id_investigation_id"),
        ),
    )
    op.create_index(
        "ix_entity_candidate_batch_workspace_investigation",
        "entity_candidate_batch",
        ["workspace_id", "investigation_id"],
        unique=False,
    )

    op.create_table(
        "entity_candidate",
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
        sa.CheckConstraint(
            f"classification IN ({_CLASSIFICATIONS})",
            name=op.f("ck_entity_candidate_classification_allowed"),
        ),
        sa.CheckConstraint(
            "hard_conflict = (classification = 'EXCLUDED')",
            name=op.f("ck_entity_candidate_conflict_classification_consistency"),
        ),
        sa.CheckConstraint(
            "identity_digest ~ '^[0-9a-f]{64}$' AND origin_digest ~ '^[0-9a-f]{64}$' "
            "AND evaluation_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_entity_candidate_digests_format"),
        ),
        sa.CheckConstraint(
            "identity_schema_version = 1",
            name=op.f("ck_entity_candidate_identity_schema_supported"),
        ),
        sa.CheckConstraint(
            "origin_schema_version = 1",
            name=op.f("ck_entity_candidate_origin_schema_supported"),
        ),
        sa.CheckConstraint(
            "decision = 'PENDING_REVIEW' AND decision_by IS NULL AND decided_at IS NULL",
            name=op.f("ck_entity_candidate_pending_review_only"),
        ),
        sa.CheckConstraint(
            "rank BETWEEN 1 AND 100",
            name=op.f("ck_entity_candidate_rank_range"),
        ),
        sa.CheckConstraint(
            "total_score BETWEEN 0 AND 10000 AND coverage BETWEEN 0 AND 10000",
            name=op.f("ck_entity_candidate_score_coverage_range"),
        ),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entity_candidate")),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            "investigation_id",
            "batch_id",
            name=op.f("uq_entity_candidate_id_workspace_id_investigation_id_batch_id"),
        ),
        sa.UniqueConstraint(
            "batch_id",
            "candidate_key",
            name=op.f("uq_entity_candidate_batch_id_candidate_key"),
        ),
        sa.UniqueConstraint(
            "batch_id",
            "rank",
            name=op.f("uq_entity_candidate_batch_id_rank"),
        ),
    )
    op.create_index(
        "ix_entity_candidate_batch_rank",
        "entity_candidate",
        ["batch_id", "rank"],
        unique=False,
    )

    op.create_table(
        "entity_candidate_dimension_score",
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
        sa.CheckConstraint(
            "available OR (score = 0 AND contribution = 0 AND NOT hard_conflict)",
            name=op.f("ck_entity_candidate_dimension_score_availability_consistency"),
        ),
        sa.CheckConstraint(
            "score BETWEEN 0 AND 10000 AND weight BETWEEN 0 AND 10000 "
            "AND contribution BETWEEN 0 AND 10000",
            name=op.f("ck_entity_candidate_dimension_score_basis_points_range"),
        ),
        sa.CheckConstraint(
            "contribution = (score::integer * weight::integer) / 10000",
            name=op.f("ck_entity_candidate_dimension_score_contribution_consistency"),
        ),
        sa.CheckConstraint(
            f"dimension IN ({_DIMENSIONS})",
            name=op.f("ck_entity_candidate_dimension_score_dimension_allowed"),
        ),
        sa.CheckConstraint(
            f"explanation_code IN ({_EXPLANATIONS})",
            name=op.f("ck_entity_candidate_dimension_score_explanation_allowed"),
        ),
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
        sa.PrimaryKeyConstraint(
            "candidate_id",
            "dimension",
            name=op.f("pk_entity_candidate_dimension_score"),
        ),
    )

    op.add_column(
        "investigation",
        sa.Column("active_candidate_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_investigation_active_candidate_batch_scope",
        "investigation",
        "entity_candidate_batch",
        ["active_candidate_batch_id", "workspace_id", "id"],
        ["id", "workspace_id", "investigation_id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_check_constraint(
        op.f("ck_investigation_active_candidate_batch_state_consistency"),
        "investigation",
        "(state = 'WAITING_FOR_ENTITY_CONFIRMATION') = (active_candidate_batch_id IS NOT NULL)",
        postgresql_not_valid=True,
    )

    _extend_transition_ledger()
    _extend_audit_event()


def _extend_transition_ledger() -> None:
    op.add_column(
        "investigation_transition",
        sa.Column("candidate_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "investigation_transition",
        sa.Column("candidate_count", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "investigation_transition",
        sa.Column("top_classification", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "investigation_transition",
        sa.Column("policy_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "investigation_transition",
        sa.Column("policy_version", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_investigation_transition_candidate_batch_scope",
        "investigation_transition",
        "entity_candidate_batch",
        ["candidate_batch_id", "workspace_id", "investigation_id"],
        ["id", "workspace_id", "investigation_id"],
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
        "'REQUEST_ENTITY_CONFIRMATION')",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_command_transition_shape"),
        "investigation_transition",
        "(command_type = 'START_IDENTIFICATION' AND state_before = 'CREATED' "
        "AND state_after = 'IDENTIFYING' AND reason_code IS NULL) OR "
        "(command_type = 'CANCEL_INVESTIGATION' AND state_before NOT IN "
        "('COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED') "
        "AND state_after = 'CANCELLED' AND reason_code IN "
        "('USER_REQUESTED', 'DUPLICATE_REQUEST', 'NO_LONGER_REQUIRED', "
        "'POLICY_REQUIRED')) OR (command_type = 'REQUEST_ENTITY_CONFIRMATION' "
        "AND state_before = 'IDENTIFYING' "
        "AND state_after = 'WAITING_FOR_ENTITY_CONFIRMATION' AND reason_code IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_candidate_metadata_complete"),
        "investigation_transition",
        "(command_type = 'REQUEST_ENTITY_CONFIRMATION') = "
        "(candidate_batch_id IS NOT NULL) AND "
        "num_nonnulls(candidate_batch_id, candidate_count, top_classification, "
        "policy_id, policy_version) IN (0, 5)",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_candidate_metadata_valid"),
        "investigation_transition",
        "candidate_batch_id IS NULL OR (candidate_count BETWEEN 1 AND 100 "
        f"AND top_classification IN ({_CLASSIFICATIONS}) "
        "AND policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' AND policy_version >= 1)",
    )


def _extend_audit_event() -> None:
    op.add_column(
        "audit_event",
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("audit_event", sa.Column("policy_id", sa.String(length=64), nullable=True))
    op.add_column("audit_event", sa.Column("policy_version", sa.Integer(), nullable=True))
    op.add_column("audit_event", sa.Column("candidate_count", sa.SmallInteger(), nullable=True))
    op.add_column(
        "audit_event", sa.Column("top_classification", sa.String(length=16), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_audit_event_candidate_review_metadata_complete"),
        "audit_event",
        "num_nonnulls(command_id, policy_id, policy_version, candidate_count, "
        "top_classification) IN (0, 5)",
    )
    op.create_check_constraint(
        op.f("ck_audit_event_candidate_review_metadata_valid"),
        "audit_event",
        "command_id IS NULL OR (outcome = 'SUCCESS' AND resource_type = 'INVESTIGATION' "
        "AND policy_id ~ '^[A-Z][A-Z0-9_.:-]*$' AND policy_version >= 1 "
        "AND candidate_count BETWEEN 1 AND 100 "
        f"AND top_classification IN ({_CLASSIFICATIONS}))",
    )


def downgrade() -> None:
    """Remove only F4.2 structures and restore the accepted F4.1 revision."""

    op.drop_constraint(
        op.f("ck_audit_event_candidate_review_metadata_valid"),
        "audit_event",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_audit_event_candidate_review_metadata_complete"),
        "audit_event",
        type_="check",
    )
    for column in (
        "top_classification",
        "candidate_count",
        "policy_version",
        "policy_id",
        "command_id",
    ):
        op.drop_column("audit_event", column)

    op.drop_constraint(
        op.f("ck_investigation_transition_candidate_metadata_valid"),
        "investigation_transition",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_investigation_transition_candidate_metadata_complete"),
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
    op.drop_constraint(
        "fk_investigation_transition_candidate_batch_scope",
        "investigation_transition",
        type_="foreignkey",
    )
    for column in (
        "policy_version",
        "policy_id",
        "top_classification",
        "candidate_count",
        "candidate_batch_id",
    ):
        op.drop_column("investigation_transition", column)
    op.create_check_constraint(
        op.f("ck_investigation_transition_command_type_allowed"),
        "investigation_transition",
        "command_type IN ('START_IDENTIFICATION', 'CANCEL_INVESTIGATION')",
    )
    op.create_check_constraint(
        op.f("ck_investigation_transition_command_transition_shape"),
        "investigation_transition",
        "(command_type = 'START_IDENTIFICATION' AND state_before = 'CREATED' "
        "AND state_after = 'IDENTIFYING' AND reason_code IS NULL) OR "
        "(command_type = 'CANCEL_INVESTIGATION' AND state_before NOT IN "
        "('COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED') "
        "AND state_after = 'CANCELLED' AND reason_code IN "
        "('USER_REQUESTED', 'DUPLICATE_REQUEST', 'NO_LONGER_REQUIRED', "
        "'POLICY_REQUIRED'))",
    )

    op.drop_constraint(
        op.f("ck_investigation_active_candidate_batch_state_consistency"),
        "investigation",
        type_="check",
    )
    op.drop_constraint(
        "fk_investigation_active_candidate_batch_scope",
        "investigation",
        type_="foreignkey",
    )
    op.drop_column("investigation", "active_candidate_batch_id")

    op.drop_table("entity_candidate_dimension_score")
    op.drop_index("ix_entity_candidate_batch_rank", table_name="entity_candidate")
    op.drop_table("entity_candidate")
    op.drop_index(
        "ix_entity_candidate_batch_workspace_investigation",
        table_name="entity_candidate_batch",
    )
    op.drop_table("entity_candidate_batch")

    op.drop_constraint(
        op.f("ck_investigation_input_schema_version_supported"),
        "investigation",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_investigation_input_schema_version_supported"),
        "investigation",
        "input_schema_version IS NULL OR input_schema_version = 1",
    )
