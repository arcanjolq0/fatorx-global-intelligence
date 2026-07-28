"""SQLAlchemy Core repository adapters using a caller-owned connection."""

from collections.abc import Mapping
from typing import cast

import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError

from intelligence.application.errors import (
    PersistenceConflictError,
    PersistenceError,
)
from intelligence.domain.audit import AuditEvent
from intelligence.domain.companies import Company
from intelligence.domain.identifiers import CompanyId, InvestigationId, UserId, WorkspaceId
from intelligence.domain.identities import (
    EmailAddress,
    MembershipRole,
    MembershipStatus,
    UserAccount,
    WorkspaceMembership,
)
from intelligence.domain.investigations import Investigation
from intelligence.domain.workspaces import Workspace
from intelligence.infrastructure.persistence.postgresql.mappers import (
    audit_event_to_values,
    company_from_values,
    company_to_values,
    investigation_from_values,
    investigation_to_values,
    user_account_from_values,
    user_account_to_values,
    workspace_from_values,
    workspace_membership_from_values,
    workspace_membership_to_values,
    workspace_to_values,
)
from intelligence.infrastructure.persistence.postgresql.tables import (
    audit_event_table,
    company_table,
    investigation_table,
    user_account_table,
    workspace_membership_table,
    workspace_table,
)
from intelligence.infrastructure.persistence.postgresql.transaction_guard import (
    PostgreSQLTransactionGuard,
)


class PostgreSQLWorkspaceRepository:
    """Core adapter for workspace snapshots."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, workspace: Workspace) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(sa.insert(workspace_table).values(**workspace_to_values(workspace)))
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get(self, workspace_id: WorkspaceId) -> Workspace | None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(
            workspace_table.c.id,
            workspace_table.c.name,
            workspace_table.c.status,
            workspace_table.c.retention_policy_version,
            workspace_table.c.created_at,
            workspace_table.c.updated_at,
        ).where(workspace_table.c.id == workspace_id.value)
        try:
            values = connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            workspace_from_values(cast(Mapping[str, object], values))
            if values is not None
            else None
        )


class PostgreSQLCompanyRepository:
    """Core adapter for workspace-scoped company snapshots."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, company: Company) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(sa.insert(company_table).values(**company_to_values(company)))
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get(self, workspace_id: WorkspaceId, company_id: CompanyId) -> Company | None:
        connection = self._transaction_guard.require_active()
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
            values = connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            company_from_values(cast(Mapping[str, object], values)) if values is not None else None
        )


class PostgreSQLInvestigationRepository:
    """Core adapter for workspace-scoped investigation snapshots."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, investigation: Investigation) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(
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
        connection = self._transaction_guard.require_active()
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
            values = connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            investigation_from_values(cast(Mapping[str, object], values))
            if values is not None
            else None
        )


class PostgreSQLUserRepository:
    """Core adapter for internal user identity snapshots."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, user: UserAccount) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(sa.insert(user_account_table).values(**user_account_to_values(user)))
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get(self, user_id: UserId) -> UserAccount | None:
        return self._find(user_account_table.c.id == user_id.value)

    def get_by_email(self, email: EmailAddress) -> UserAccount | None:
        return self._find(user_account_table.c.email == email.value)

    def _find(self, predicate: sa.ColumnElement[bool]) -> UserAccount | None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(
            user_account_table.c.id,
            user_account_table.c.email,
            user_account_table.c.display_name,
            user_account_table.c.status,
            user_account_table.c.created_at,
            user_account_table.c.updated_at,
        ).where(predicate)
        try:
            values = connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            user_account_from_values(cast(Mapping[str, object], values))
            if values is not None
            else None
        )


class PostgreSQLWorkspaceMembershipRepository:
    """Core adapter for the unique user membership within a workspace."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, membership: WorkspaceMembership) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(
                sa.insert(workspace_membership_table).values(
                    **workspace_membership_to_values(membership)
                )
            )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get(
        self,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership | None:
        return self._find(workspace_id, user_id, for_update=False)

    def get_for_update(
        self,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership | None:
        """Lock the requested membership inside the original UoW transaction."""

        return self._find(workspace_id, user_id, for_update=True)

    def list_active_owners_for_update(
        self,
        workspace_id: WorkspaceId,
    ) -> list[WorkspaceMembership]:
        """Lock active owners by stable membership ID order."""

        connection = self._transaction_guard.require_active()
        statement = (
            self._select_membership()
            .where(
                workspace_membership_table.c.workspace_id == workspace_id.value,
                workspace_membership_table.c.status == MembershipStatus.ACTIVE.value,
                workspace_membership_table.c.role == MembershipRole.OWNER.value,
            )
            .order_by(workspace_membership_table.c.id)
            .with_for_update()
        )
        try:
            values = connection.execute(statement).mappings().all()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return [workspace_membership_from_values(cast(Mapping[str, object], row)) for row in values]

    def update(self, membership: WorkspaceMembership) -> None:
        """Update mutable snapshot fields while matching all stable identity fields."""

        connection = self._transaction_guard.require_active()
        statement = (
            sa.update(workspace_membership_table)
            .where(
                workspace_membership_table.c.workspace_id == membership.workspace_id.value,
                workspace_membership_table.c.user_id == membership.user_id.value,
                workspace_membership_table.c.id == membership.id.value,
            )
            .values(
                role=membership.role.value,
                status=membership.status.value,
                updated_at=membership.updated_at,
                deactivated_at=membership.deactivated_at,
            )
        )
        try:
            result = connection.execute(statement)
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if result.rowcount != 1:
            raise PersistenceConflictError("Persistence constraint conflict.")

    def _find(
        self,
        workspace_id: WorkspaceId,
        user_id: UserId,
        *,
        for_update: bool,
    ) -> WorkspaceMembership | None:
        connection = self._transaction_guard.require_active()
        statement = self._select_membership().where(
            workspace_membership_table.c.workspace_id == workspace_id.value,
            workspace_membership_table.c.user_id == user_id.value,
        )
        if for_update:
            statement = statement.with_for_update()
        try:
            values = connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            workspace_membership_from_values(cast(Mapping[str, object], values))
            if values is not None
            else None
        )

    @staticmethod
    def _select_membership() -> sa.Select[tuple[object, ...]]:
        return sa.select(
            workspace_membership_table.c.id,
            workspace_membership_table.c.workspace_id,
            workspace_membership_table.c.user_id,
            workspace_membership_table.c.role,
            workspace_membership_table.c.status,
            workspace_membership_table.c.created_at,
            workspace_membership_table.c.updated_at,
            workspace_membership_table.c.deactivated_at,
        )


class PostgreSQLAuditEventRepository:
    """Core append-only adapter for minimal audit events."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, event: AuditEvent) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(sa.insert(audit_event_table).values(**audit_event_to_values(event)))
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error


__all__ = [
    "PostgreSQLAuditEventRepository",
    "PostgreSQLCompanyRepository",
    "PostgreSQLInvestigationRepository",
    "PostgreSQLUserRepository",
    "PostgreSQLWorkspaceMembershipRepository",
    "PostgreSQLWorkspaceRepository",
]
