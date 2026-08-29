"""SQLAlchemy Core metadata for append-only F5.2 Claims and Evidence links."""

from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from intelligence.application.claim_evidence_policy import (
    CLAIM_EVIDENCE_POLICY_ID,
    CLAIM_EVIDENCE_POLICY_VERSION,
    CONTROLLED_CORPUS_MANIFEST_VERSION,
)
from intelligence.claims.models import (
    CLAIM_LINK_SCHEMA_VERSION,
    CLAIM_PREDICATE_VERSION,
    CLAIM_SCHEMA_VERSION,
    ClaimCorrectionReason,
    ClaimCreationMethod,
    ClaimCriticality,
    ClaimEvidencePurpose,
    ClaimEvidenceRole,
    ClaimEvidenceUseOutcome,
    ClaimEvidenceUseReason,
    ClaimPredicate,
)
from intelligence.infrastructure.persistence.postgresql.metadata import metadata


def _sql_values(values: Iterable[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


claim_table = sa.Table(
    "claim",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("supersedes_claim_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("subject_company_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("entity_resolution_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("command_digest", sa.String(length=64), nullable=False),
    sa.Column("predicate_code", sa.String(length=64), nullable=False),
    sa.Column("predicate_version", sa.Integer(), nullable=False),
    sa.Column("value_type", sa.String(length=32), nullable=False),
    sa.Column("value_snapshot", postgresql.JSONB(none_as_null=True), nullable=False),
    sa.Column("temporal_type", sa.String(length=32), nullable=False),
    sa.Column("temporal_snapshot", postgresql.JSONB(none_as_null=True), nullable=False),
    sa.Column("criticality", sa.String(length=32), nullable=False),
    sa.Column("creation_method", sa.String(length=32), nullable=False),
    sa.Column("creation_method_version", sa.Integer(), nullable=False),
    sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("correction_reason", sa.String(length=64), nullable=True),
    sa.Column("claim_digest", sa.String(length=64), nullable=False),
    sa.Column("schema_version", sa.SmallInteger(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("id", "workspace_id", "investigation_id"),
    sa.UniqueConstraint(
        "id",
        "version",
        "workspace_id",
        "investigation_id",
        "subject_company_id",
        "entity_resolution_decision_id",
        name="uq_claim_link_scope",
    ),
    sa.UniqueConstraint("workspace_id", "command_id"),
    sa.UniqueConstraint("workspace_id", "series_id", "version"),
    sa.UniqueConstraint(
        "id",
        "series_id",
        "version",
        "workspace_id",
        "investigation_id",
        "subject_company_id",
        "entity_resolution_decision_id",
        name="uq_claim_review_exact_scope",
    ),
    sa.ForeignKeyConstraint(
        ["workspace_id"], ["workspace.id"], ondelete="RESTRICT", name="fk_claim_workspace"
    ),
    sa.ForeignKeyConstraint(
        ["investigation_id", "workspace_id"],
        ["investigation.id", "investigation.workspace_id"],
        ondelete="RESTRICT",
        name="fk_claim_investigation_scope",
    ),
    sa.ForeignKeyConstraint(
        ["subject_company_id", "workspace_id"],
        ["company.id", "company.workspace_id"],
        ondelete="RESTRICT",
        name="fk_claim_company_scope",
    ),
    sa.ForeignKeyConstraint(
        [
            "entity_resolution_decision_id",
            "workspace_id",
            "investigation_id",
            "subject_company_id",
        ],
        [
            "entity_resolution_decision.id",
            "entity_resolution_decision.workspace_id",
            "entity_resolution_decision.investigation_id",
            "entity_resolution_decision.company_id",
        ],
        ondelete="RESTRICT",
        name="fk_claim_decision_scope",
    ),
    sa.ForeignKeyConstraint(
        ["series_id", "workspace_id", "investigation_id"],
        ["claim.id", "claim.workspace_id", "claim.investigation_id"],
        ondelete="RESTRICT",
        name="fk_claim_series_scope",
    ),
    sa.ForeignKeyConstraint(
        ["supersedes_claim_id", "workspace_id", "investigation_id"],
        ["claim.id", "claim.workspace_id", "claim.investigation_id"],
        ondelete="RESTRICT",
        name="fk_claim_supersedes_scope",
    ),
    sa.ForeignKeyConstraint(
        ["created_by"], ["user_account.id"], ondelete="RESTRICT", name="fk_claim_actor"
    ),
    sa.CheckConstraint("version >= 1", name="version_positive"),
    sa.CheckConstraint(
        "(version = 1 AND series_id = id AND supersedes_claim_id IS NULL "
        "AND correction_reason IS NULL) OR "
        "(version > 1 AND series_id <> id AND supersedes_claim_id IS NOT NULL "
        "AND correction_reason IS NOT NULL)",
        name="version_chain_shape",
    ),
    sa.CheckConstraint(
        f"predicate_code IN ({_sql_values(item.value for item in ClaimPredicate)})",
        name="predicate_allowed",
    ),
    sa.CheckConstraint(
        f"predicate_version = {CLAIM_PREDICATE_VERSION}", name="predicate_version_supported"
    ),
    sa.CheckConstraint(
        "value_type IN ('TEXT','REGISTRATION_STATUS','DATE','COUNTRY_CODE',"
        "'REGISTRATION_IDENTIFIER')",
        name="value_type_allowed",
    ),
    sa.CheckConstraint(
        "temporal_type IN ('POINT','PERIOD','UNDATED')", name="temporal_type_allowed"
    ),
    sa.CheckConstraint(
        f"criticality IN ({_sql_values(item.value for item in ClaimCriticality)})",
        name="criticality_allowed",
    ),
    sa.CheckConstraint(
        f"creation_method IN ({_sql_values(item.value for item in ClaimCreationMethod)})",
        name="creation_method_allowed",
    ),
    sa.CheckConstraint("creation_method_version >= 1", name="method_version_positive"),
    sa.CheckConstraint(
        "correction_reason IS NULL OR correction_reason IN "
        f"({_sql_values(item.value for item in ClaimCorrectionReason)})",
        name="correction_reason_allowed",
    ),
    sa.CheckConstraint(
        "command_digest ~ '^[0-9a-f]{64}$' AND claim_digest ~ '^[0-9a-f]{64}$'",
        name="digests_format",
    ),
    sa.CheckConstraint(f"schema_version = {CLAIM_SCHEMA_VERSION}", name="schema_supported"),
)
sa.Index(
    "ix_claim_workspace_investigation",
    claim_table.c.workspace_id,
    claim_table.c.investigation_id,
)
sa.Index("ix_claim_workspace_series", claim_table.c.workspace_id, claim_table.c.series_id)


claim_evidence_link_table = sa.Table(
    "claim_evidence_link",
    metadata,
    sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("claim_version", sa.Integer(), nullable=False),
    sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("subject_company_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("entity_resolution_decision_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("evidence_digest", sa.String(length=64), nullable=False),
    sa.Column("role", sa.String(length=32), nullable=False),
    sa.Column("use_outcome", sa.String(length=32), nullable=False),
    sa.Column("use_reason", sa.String(length=64), nullable=False),
    sa.Column("policy_id", sa.String(length=128), nullable=False),
    sa.Column("policy_version", sa.Integer(), nullable=False),
    sa.Column("purpose", sa.String(length=64), nullable=False),
    sa.Column("manifest_version", sa.Integer(), nullable=False),
    sa.Column("manifest_digest", sa.String(length=64), nullable=False),
    sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("link_digest", sa.String(length=64), nullable=False),
    sa.Column("schema_version", sa.SmallInteger(), nullable=False),
    sa.PrimaryKeyConstraint("claim_id", "evidence_id"),
    sa.ForeignKeyConstraint(
        [
            "claim_id",
            "claim_version",
            "workspace_id",
            "investigation_id",
            "subject_company_id",
            "entity_resolution_decision_id",
        ],
        [
            "claim.id",
            "claim.version",
            "claim.workspace_id",
            "claim.investigation_id",
            "claim.subject_company_id",
            "claim.entity_resolution_decision_id",
        ],
        ondelete="RESTRICT",
        name="fk_claim_evidence_link_claim_scope",
    ),
    sa.ForeignKeyConstraint(
        [
            "evidence_id",
            "workspace_id",
            "investigation_id",
            "subject_company_id",
            "entity_resolution_decision_id",
        ],
        [
            "evidence.id",
            "evidence.workspace_id",
            "evidence.investigation_id",
            "evidence.subject_company_id",
            "evidence.entity_resolution_decision_id",
        ],
        ondelete="RESTRICT",
        name="fk_claim_evidence_link_evidence_scope",
    ),
    sa.ForeignKeyConstraint(
        ["requested_by"],
        ["user_account.id"],
        ondelete="RESTRICT",
        name="fk_claim_evidence_link_requester",
    ),
    sa.CheckConstraint("claim_version >= 1", name="claim_version_positive"),
    sa.CheckConstraint(
        f"role IN ({_sql_values(item.value for item in ClaimEvidenceRole)})",
        name="role_allowed",
    ),
    sa.CheckConstraint(
        f"use_outcome IN ({_sql_values(item.value for item in ClaimEvidenceUseOutcome)})",
        name="outcome_allowed",
    ),
    sa.CheckConstraint(
        f"use_reason IN ({_sql_values(item.value for item in ClaimEvidenceUseReason)})",
        name="reason_allowed",
    ),
    sa.CheckConstraint(f"policy_id = '{CLAIM_EVIDENCE_POLICY_ID}'", name="policy_id_supported"),
    sa.CheckConstraint(
        f"policy_version = {CLAIM_EVIDENCE_POLICY_VERSION}", name="policy_version_supported"
    ),
    sa.CheckConstraint(
        f"purpose = '{ClaimEvidencePurpose.INTERNAL_CLAIM_VERIFICATION.value}'",
        name="purpose_supported",
    ),
    sa.CheckConstraint(
        f"manifest_version = {CONTROLLED_CORPUS_MANIFEST_VERSION}",
        name="manifest_version_supported",
    ),
    sa.CheckConstraint(
        "evidence_digest ~ '^[0-9a-f]{64}$' AND manifest_digest ~ '^[0-9a-f]{64}$' "
        "AND link_digest ~ '^[0-9a-f]{64}$'",
        name="digests_format",
    ),
    sa.CheckConstraint(f"schema_version = {CLAIM_LINK_SCHEMA_VERSION}", name="schema_supported"),
)
sa.Index(
    "ix_claim_evidence_link_workspace_claim",
    claim_evidence_link_table.c.workspace_id,
    claim_evidence_link_table.c.claim_id,
)
sa.Index(
    "ix_claim_evidence_link_workspace_evidence",
    claim_evidence_link_table.c.workspace_id,
    claim_evidence_link_table.c.evidence_id,
)


__all__ = ["claim_evidence_link_table", "claim_table"]
