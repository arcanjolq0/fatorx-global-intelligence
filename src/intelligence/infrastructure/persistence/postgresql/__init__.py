"""PostgreSQL schema metadata and configuration."""

from intelligence.infrastructure.persistence.postgresql.claim_tables import (
    claim_evidence_link_table,
    claim_table,
)
from intelligence.infrastructure.persistence.postgresql.configuration import (
    DatabaseConfigurationError,
    require_database_url,
)
from intelligence.infrastructure.persistence.postgresql.evidence_admissibility_tables import (
    evidence_admissibility_decision_table,
)
from intelligence.infrastructure.persistence.postgresql.evidence_tables import (
    evidence_artifact_table,
    evidence_lifecycle_event_table,
    evidence_table,
)
from intelligence.infrastructure.persistence.postgresql.metadata import metadata
from intelligence.infrastructure.persistence.postgresql.tables import (
    audit_event_table,
    collection_operation_dependency_table,
    collection_operation_execution_result_table,
    collection_operation_execution_table,
    collection_operation_table,
    collection_run_table,
    company_table,
    entity_candidate_batch_table,
    entity_candidate_dimension_score_table,
    entity_candidate_table,
    entity_resolution_decision_table,
    investigation_plan_table,
    investigation_table,
    planned_capability_table,
    planned_connector_option_table,
    user_account_table,
    workspace_membership_table,
    workspace_table,
)

__all__ = [
    "DatabaseConfigurationError",
    "audit_event_table",
    "claim_evidence_link_table",
    "claim_table",
    "collection_operation_dependency_table",
    "collection_operation_execution_result_table",
    "collection_operation_execution_table",
    "collection_operation_table",
    "collection_run_table",
    "company_table",
    "entity_candidate_batch_table",
    "entity_candidate_dimension_score_table",
    "entity_candidate_table",
    "entity_resolution_decision_table",
    "evidence_admissibility_decision_table",
    "evidence_artifact_table",
    "evidence_lifecycle_event_table",
    "evidence_table",
    "investigation_plan_table",
    "investigation_table",
    "metadata",
    "planned_capability_table",
    "planned_connector_option_table",
    "require_database_url",
    "user_account_table",
    "workspace_membership_table",
    "workspace_table",
]
