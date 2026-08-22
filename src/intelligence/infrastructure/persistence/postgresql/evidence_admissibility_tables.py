"""SQLAlchemy Core metadata for append-only F5.3 admissibility decisions."""

from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from intelligence.application.evidence_admissibility_policy import (
    CONTROLLED_TEST_EVIDENCE_MANIFEST_ID,
    CONTROLLED_TEST_EVIDENCE_MANIFEST_VERSION,
    EVIDENCE_ADMISSIBILITY_POLICY_ID,
    EVIDENCE_ADMISSIBILITY_POLICY_VERSION,
    F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1,
)
from intelligence.evidence.admissibility import (
    EVIDENCE_ADMISSIBILITY_DECISION_SCHEMA_VERSION,
    EvidenceAdmissibilityDecisionOutcome,
    EvidenceAdmissibilityPurpose,
    EvidenceAdmissibilityReason,
    EvidenceAdmissionBasis,
)
from intelligence.infrastructure.persistence.postgresql.metadata import metadata


def _sql_values(values: Iterable[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


evidence_admissibility_decision_table = sa.Table(
    "evidence_admissibility_decision",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("subject_company_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("entity_resolution_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("evidence_series_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("evidence_version", sa.Integer(), nullable=False),
    sa.Column("evidence_digest", sa.String(length=64), nullable=False),
    sa.Column("decision_sequence", sa.Integer(), nullable=False),
    sa.Column("supersedes_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("outcome", sa.String(length=32), nullable=False),
    sa.Column("reason_code", sa.String(length=64), nullable=False),
    sa.Column("policy_id", sa.String(length=128), nullable=False),
    sa.Column("policy_version", sa.Integer(), nullable=False),
    sa.Column("purpose", sa.String(length=64), nullable=False),
    sa.Column("admission_basis", sa.String(length=64), nullable=False),
    sa.Column("controlled_trust_root_id", sa.String(length=128), nullable=False),
    sa.Column("controlled_trust_root_version", sa.Integer(), nullable=False),
    sa.Column("controlled_trust_root_digest", sa.String(length=64), nullable=False),
    sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
    sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("command_digest", sa.String(length=64), nullable=False),
    sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("decision_digest", sa.String(length=64), nullable=False),
    sa.Column("schema_version", sa.SmallInteger(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("workspace_id", "command_id"),
    sa.UniqueConstraint("workspace_id", "evidence_id", "decision_sequence"),
    sa.UniqueConstraint(
        "id",
        "workspace_id",
        "evidence_id",
        "evidence_series_id",
        "evidence_version",
        name="uq_admissibility_predecessor_scope",
    ),
    sa.ForeignKeyConstraint(
        [
            "evidence_id",
            "evidence_series_id",
            "evidence_version",
            "workspace_id",
            "investigation_id",
            "subject_company_id",
            "entity_resolution_decision_id",
        ],
        [
            "evidence.id",
            "evidence.series_id",
            "evidence.version",
            "evidence.workspace_id",
            "evidence.investigation_id",
            "evidence.subject_company_id",
            "evidence.entity_resolution_decision_id",
        ],
        name="fk_admissibility_exact_evidence_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        [
            "supersedes_decision_id",
            "workspace_id",
            "evidence_id",
            "evidence_series_id",
            "evidence_version",
        ],
        [
            "evidence_admissibility_decision.id",
            "evidence_admissibility_decision.workspace_id",
            "evidence_admissibility_decision.evidence_id",
            "evidence_admissibility_decision.evidence_series_id",
            "evidence_admissibility_decision.evidence_version",
        ],
        name="fk_admissibility_predecessor_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["decided_by"], ["user_account.id"], name="fk_admissibility_actor", ondelete="RESTRICT"
    ),
    sa.CheckConstraint(
        "decision_sequence >= 1 AND ((decision_sequence = 1 AND "
        "supersedes_decision_id IS NULL) OR (decision_sequence > 1 AND "
        "supersedes_decision_id IS NOT NULL))",
        name="sequence_predecessor_shape",
    ),
    sa.CheckConstraint(
        f"outcome IN ({_sql_values(item.value for item in EvidenceAdmissibilityDecisionOutcome)})",
        name="outcome_allowed",
    ),
    sa.CheckConstraint(
        f"reason_code IN ({_sql_values(item.value for item in EvidenceAdmissibilityReason)})",
        name="reason_allowed",
    ),
    sa.CheckConstraint(
        "(outcome = 'ADMISSIBLE' AND reason_code = 'CONTROLLED_TEST_EVIDENCE_ADMITTED') "
        "OR (outcome = 'RESTRICTED' AND "
        "reason_code = 'POLICY_OR_VERIFIABILITY_RESTRICTED') OR "
        "(outcome = 'REJECTED' AND reason_code = 'CONTENT_OR_CONTEXT_REJECTED')",
        name="outcome_reason_compatible",
    ),
    sa.CheckConstraint(
        "(outcome = 'ADMISSIBLE' AND (valid_until IS NULL OR valid_until > decided_at)) "
        "OR (outcome IN ('RESTRICTED','REJECTED') AND valid_until IS NULL)",
        name="expiration_valid",
    ),
    sa.CheckConstraint(
        f"policy_id = '{EVIDENCE_ADMISSIBILITY_POLICY_ID}' AND "
        f"policy_version = {EVIDENCE_ADMISSIBILITY_POLICY_VERSION}",
        name="policy_supported",
    ),
    sa.CheckConstraint(
        f"purpose = '{EvidenceAdmissibilityPurpose.INTERNAL_FACTUAL_EVIDENCE_USE.value}'",
        name="purpose_supported",
    ),
    sa.CheckConstraint(
        f"admission_basis = '{EvidenceAdmissionBasis.CONTROLLED_TEST_EVIDENCE.value}'",
        name="basis_supported",
    ),
    sa.CheckConstraint(
        f"controlled_trust_root_id = '{CONTROLLED_TEST_EVIDENCE_MANIFEST_ID}' AND "
        f"controlled_trust_root_version = {CONTROLLED_TEST_EVIDENCE_MANIFEST_VERSION} AND "
        "controlled_trust_root_digest = "
        f"'{F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.digest}'",
        name="trust_root_supported",
    ),
    sa.CheckConstraint(
        "evidence_digest ~ '^[0-9a-f]{64}$' AND "
        "controlled_trust_root_digest ~ '^[0-9a-f]{64}$' AND "
        "command_digest ~ '^[0-9a-f]{64}$' AND decision_digest ~ '^[0-9a-f]{64}$'",
        name="digests_format",
    ),
    sa.CheckConstraint(
        f"evidence_version >= 1 AND schema_version = "
        f"{EVIDENCE_ADMISSIBILITY_DECISION_SCHEMA_VERSION}",
        name="versions_supported",
    ),
)
sa.Index(
    "ix_admissibility_workspace_evidence_decided_at",
    evidence_admissibility_decision_table.c.workspace_id,
    evidence_admissibility_decision_table.c.evidence_id,
    evidence_admissibility_decision_table.c.decided_at,
)
sa.Index(
    "ix_admissibility_workspace_investigation_decided_at",
    evidence_admissibility_decision_table.c.workspace_id,
    evidence_admissibility_decision_table.c.investigation_id,
    evidence_admissibility_decision_table.c.decided_at,
)
sa.Index(
    "ix_admissibility_workspace_predecessor",
    evidence_admissibility_decision_table.c.workspace_id,
    evidence_admissibility_decision_table.c.supersedes_decision_id,
)
sa.Index(
    "ix_admissibility_workspace_actor",
    evidence_admissibility_decision_table.c.workspace_id,
    evidence_admissibility_decision_table.c.decided_by,
)


__all__ = ["evidence_admissibility_decision_table"]
