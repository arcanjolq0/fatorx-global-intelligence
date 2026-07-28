"""SQLAlchemy Core repository adapters using a caller-owned connection."""

from collections.abc import Mapping
from typing import cast

import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError, IntegrityError

from intelligence.application.errors import (
    PersistenceConflictError,
    PersistenceError,
    PersistenceStateError,
)
from intelligence.domain.companies import Company
from intelligence.domain.identifiers import CompanyId, InvestigationId, WorkspaceId
from intelligence.domain.investigations import Investigation
from intelligence.domain.workspaces import Workspace
from intelligence.infrastructure.persistence.postgresql.mappers import (
    company_from_values,
    company_to_values,
    investigation_from_values,
    investigation_to_values,
    workspace_from_values,
    workspace_to_values,
)
from intelligence.infrastructure.persistence.postgresql.tables import (
    company_table,
    investigation_table,
    workspace_table,
)


class PostgreSQLWorkspaceRepository:
    """Core adapter for workspace snapshots."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add(self, workspace: Workspace) -> None:
        _require_open(self._connection)
        try:
            self._connection.execute(
                sa.insert(workspace_table).values(**workspace_to_values(workspace))
            )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get(self, workspace_id: WorkspaceId) -> Workspace | None:
        _require_open(self._connection)
        statement = sa.select(
            workspace_table.c.id,
            workspace_table.c.name,
            workspace_table.c.status,
            workspace_table.c.retention_policy_version,
            workspace_table.c.created_at,
            workspace_table.c.updated_at,
        ).where(workspace_table.c.id == workspace_id.value)
        try:
            values = self._connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            workspace_from_values(cast(Mapping[str, object], values))
            if values is not None
            else None
        )


class PostgreSQLCompanyRepository:
    """Core adapter for workspace-scoped company snapshots."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add(self, company: Company) -> None:
        _require_open(self._connection)
        try:
            self._connection.execute(sa.insert(company_table).values(**company_to_values(company)))
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get(self, workspace_id: WorkspaceId, company_id: CompanyId) -> Company | None:
        _require_open(self._connection)
        statement = sa.select(
            company_table.c.id,
            company_table.c.workspace_id,
            company_table.c.legal_name,
            company_table.c.trade_name,
            company_table.c.country_code,
            company_table.c.legal_form,
            company_table.c.status,
            company_table.c.incorporated_on,
            company_table.c.dissolved_on,
            company_table.c.official_domain,
            company_table.c.created_at,
            company_table.c.updated_at,
        ).where(
            company_table.c.workspace_id == workspace_id.value,
            company_table.c.id == company_id.value,
        )
        try:
            values = self._connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            company_from_values(cast(Mapping[str, object], values)) if values is not None else None
        )


class PostgreSQLInvestigationRepository:
    """Core adapter for workspace-scoped investigation snapshots."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add(self, investigation: Investigation) -> None:
        _require_open(self._connection)
        try:
            self._connection.execute(
                sa.insert(investigation_table).values(**investigation_to_values(investigation))
            )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> Investigation | None:
        _require_open(self._connection)
        statement = sa.select(
            investigation_table.c.id,
            investigation_table.c.workspace_id,
            investigation_table.c.requested_by,
            investigation_table.c.profile_code,
            investigation_table.c.country_code,
            investigation_table.c.state,
            investigation_table.c.state_version,
            investigation_table.c.confirmed_company_id,
            investigation_table.c.budget_amount,
            investigation_table.c.budget_currency,
            investigation_table.c.deadline_at,
            investigation_table.c.started_at,
            investigation_table.c.completed_at,
            investigation_table.c.created_at,
        ).where(
            investigation_table.c.workspace_id == workspace_id.value,
            investigation_table.c.id == investigation_id.value,
        )
        try:
            values = self._connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            investigation_from_values(cast(Mapping[str, object], values))
            if values is not None
            else None
        )


def _require_open(connection: Connection) -> None:
    if connection.closed:
        raise PersistenceStateError("Persistence connection is closed.")


__all__ = [
    "PostgreSQLCompanyRepository",
    "PostgreSQLInvestigationRepository",
    "PostgreSQLWorkspaceRepository",
]
