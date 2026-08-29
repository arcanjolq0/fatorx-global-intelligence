"""SQLAlchemy Core metadata for append-only F5.4 Claim-review decisions."""

from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from intelligence.application.claim_review_policy import (
    CLAIM_REVIEW_POLICY_ID,
    CLAIM_REVIEW_POLICY_VERSION,
)
from intelligence.claims.review import (
    CLAIM_REVIEW_DECISION_SCHEMA_VERSION,
    ClaimReviewOutcome,
    ClaimReviewPurpose,
    ClaimReviewReason,
)
from intelligence.infrastructure.persistence.postgresql.metadata import metadata


def _sql_values(values: Iterable[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


claim_review_decision_table = sa.Table(
    "claim_review_decision",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("subject_company_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("entity_resolution_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("claim_series_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("claim_version", sa.Integer(), nullable=False),
    sa.Column("claim_digest", sa.String(length=64), nullable=False),
    sa.Column("decision_sequence", sa.Integer(), nullable=False),
    sa.Column("supersedes_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("outcome", sa.String(length=64), nullable=False),
    sa.Column("reason_code", sa.String(length=64), nullable=False),
    sa.Column("policy_id", sa.String(length=128), nullable=False),
    sa.Column("policy_version", sa.Integer(), nullable=False),
    sa.Column("purpose", sa.String(length=64), nullable=False),
    sa.Column("review_basis_digest", sa.String(length=64), nullable=False),
    sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("command_digest", sa.String(length=64), nullable=False),
    sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("decision_digest", sa.String(length=64), nullable=False),
    sa.Column("schema_version", sa.SmallInteger(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint(
        "workspace_id",
        "command_id",
        name="uq_claim_review_decision_workspace_command",
    ),
    sa.UniqueConstraint(
        "workspace_id",
        "claim_id",
        "decision_sequence",
        name="uq_claim_review_decision_workspace_claim_sequence",
    ),
    sa.UniqueConstraint(
        "id",
        "workspace_id",
        "claim_id",
        "claim_series_id",
        "claim_version",
        name="uq_claim_review_predecessor_scope",
    ),
    sa.ForeignKeyConstraint(
        [
            "claim_id",
            "claim_series_id",
            "claim_version",
            "workspace_id",
            "investigation_id",
            "subject_company_id",
            "entity_resolution_decision_id",
        ],
        [
            "claim.id",
            "claim.series_id",
            "claim.version",
            "claim.workspace_id",
            "claim.investigation_id",
            "claim.subject_company_id",
            "claim.entity_resolution_decision_id",
        ],
        name="fk_claim_review_exact_claim_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["supersedes_decision_id", "workspace_id", "claim_id", "claim_series_id", "claim_version"],
        [
            "claim_review_decision.id",
            "claim_review_decision.workspace_id",
            "claim_review_decision.claim_id",
            "claim_review_decision.claim_series_id",
            "claim_review_decision.claim_version",
        ],
        name="fk_claim_review_predecessor_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(["decided_by"], ["user_account.id"], ondelete="RESTRICT"),
    sa.CheckConstraint(
        "decision_sequence >= 1 AND ((decision_sequence = 1 AND supersedes_decision_id IS NULL) "
        "OR (decision_sequence > 1 AND supersedes_decision_id IS NOT NULL))",
        name="sequence_predecessor_shape",
    ),
    sa.CheckConstraint(
        f"outcome IN ({_sql_values(item.value for item in ClaimReviewOutcome)})",
        name="outcome_allowed",
    ),
    sa.CheckConstraint(
        f"reason_code IN ({_sql_values(item.value for item in ClaimReviewReason)})",
        name="reason_allowed",
    ),
    sa.CheckConstraint(
        "(outcome = 'ACCEPTED_FOR_INTERNAL_FACTUAL_USE' AND "
        "reason_code = 'FACTUAL_BASIS_ACCEPTED') "
        "OR (outcome = 'REJECTED_FOR_INTERNAL_FACTUAL_USE' AND "
        "reason_code = 'INTERNAL_FACTUAL_USE_REJECTED') OR "
        "(outcome = 'NEEDS_CORRECTION' AND reason_code = 'CLAIM_CORRECTION_REQUIRED')",
        name="outcome_reason_compatible",
    ),
    sa.CheckConstraint(
        f"policy_id = '{CLAIM_REVIEW_POLICY_ID}' AND "
        f"policy_version = {CLAIM_REVIEW_POLICY_VERSION}",
        name="policy_supported",
    ),
    sa.CheckConstraint(
        f"purpose = '{ClaimReviewPurpose.INTERNAL_FACTUAL_CLAIM_USE.value}'",
        name="purpose_supported",
    ),
    sa.CheckConstraint(
        "claim_digest ~ '^[0-9a-f]{64}$' AND review_basis_digest ~ '^[0-9a-f]{64}$' "
        "AND command_digest ~ '^[0-9a-f]{64}$' AND decision_digest ~ '^[0-9a-f]{64}$'",
        name="digests_format",
    ),
    sa.CheckConstraint(
        f"claim_version >= 1 AND schema_version = {CLAIM_REVIEW_DECISION_SCHEMA_VERSION}",
        name="versions_supported",
    ),
)
sa.Index(
    "ix_claim_review_workspace_claim_decided_at",
    claim_review_decision_table.c.workspace_id,
    claim_review_decision_table.c.claim_id,
    claim_review_decision_table.c.decided_at,
)
sa.Index(
    "ix_claim_review_workspace_investigation_decided_at",
    claim_review_decision_table.c.workspace_id,
    claim_review_decision_table.c.investigation_id,
    claim_review_decision_table.c.decided_at,
)
sa.Index(
    "ix_claim_review_workspace_predecessor",
    claim_review_decision_table.c.workspace_id,
    claim_review_decision_table.c.supersedes_decision_id,
)
sa.Index(
    "ix_claim_review_workspace_actor",
    claim_review_decision_table.c.workspace_id,
    claim_review_decision_table.c.decided_by,
)


__all__ = ["claim_review_decision_table"]
