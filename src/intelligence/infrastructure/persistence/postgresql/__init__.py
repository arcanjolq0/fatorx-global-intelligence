"""PostgreSQL schema metadata and configuration."""

from intelligence.infrastructure.persistence.postgresql.configuration import (
    DatabaseConfigurationError,
    require_database_url,
)
from intelligence.infrastructure.persistence.postgresql.metadata import metadata
from intelligence.infrastructure.persistence.postgresql.tables import (
    audit_event_table,
    company_table,
    investigation_table,
    user_account_table,
    workspace_membership_table,
    workspace_table,
)

__all__ = [
    "DatabaseConfigurationError",
    "audit_event_table",
    "company_table",
    "investigation_table",
    "metadata",
    "require_database_url",
    "user_account_table",
    "workspace_membership_table",
    "workspace_table",
]
