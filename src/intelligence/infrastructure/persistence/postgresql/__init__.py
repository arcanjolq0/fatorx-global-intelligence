"""PostgreSQL schema metadata and configuration."""

from intelligence.infrastructure.persistence.postgresql.configuration import (
    DatabaseConfigurationError,
    require_database_url,
)
from intelligence.infrastructure.persistence.postgresql.metadata import metadata
from intelligence.infrastructure.persistence.postgresql.tables import (
    company_table,
    investigation_table,
    workspace_table,
)

__all__ = [
    "DatabaseConfigurationError",
    "company_table",
    "investigation_table",
    "metadata",
    "require_database_url",
    "workspace_table",
]
