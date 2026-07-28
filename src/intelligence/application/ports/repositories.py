"""Small repository ports for the currently persisted aggregate snapshots."""

from typing import Protocol

from intelligence.domain.audit import AuditEvent
from intelligence.domain.companies import Company
from intelligence.domain.identifiers import CompanyId, InvestigationId, UserId, WorkspaceId
from intelligence.domain.identities import EmailAddress, UserAccount, WorkspaceMembership
from intelligence.domain.investigations import Investigation
from intelligence.domain.workspaces import Workspace


class WorkspaceRepository(Protocol):
    """Persistence operations for the tenant boundary itself."""

    def add(self, workspace: Workspace) -> None:
        """Add a workspace to the current transaction."""

    def get(self, workspace_id: WorkspaceId) -> Workspace | None:
        """Return the workspace identified by its own tenant-boundary ID."""


class CompanyRepository(Protocol):
    """Workspace-scoped persistence operations for companies."""

    def add(self, company: Company) -> None:
        """Add a company to the current transaction."""

    def get(self, workspace_id: WorkspaceId, company_id: CompanyId) -> Company | None:
        """Return a company only when it belongs to the supplied workspace."""


class InvestigationRepository(Protocol):
    """Workspace-scoped persistence operations for investigations."""

    def add(self, investigation: Investigation) -> None:
        """Add an investigation snapshot to the current transaction."""

    def get(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> Investigation | None:
        """Return an investigation only within the supplied workspace."""


class UserRepository(Protocol):
    """Persistence operations for internal user identities."""

    def add(self, user: UserAccount) -> None:
        """Add an internal user to the current transaction."""

    def get(self, user_id: UserId) -> UserAccount | None:
        """Return the internal user identified by its ID."""

    def get_by_email(self, email: EmailAddress) -> UserAccount | None:
        """Return the internal user identified by canonical email."""


class WorkspaceMembershipRepository(Protocol):
    """Persistence operations for workspace membership snapshots."""

    def add(self, membership: WorkspaceMembership) -> None:
        """Add one membership to the current transaction."""

    def get(
        self,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership | None:
        """Return the unique membership for a user within a workspace."""

    def get_for_update(
        self,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership | None:
        """Lock and return the tenant-scoped membership when present."""

    def list_active_owners_for_update(
        self,
        workspace_id: WorkspaceId,
    ) -> list[WorkspaceMembership]:
        """Lock active owners in deterministic order within one workspace."""

    def update(self, membership: WorkspaceMembership) -> None:
        """Persist a new snapshot without changing membership identity or scope."""


class AuditEventRepository(Protocol):
    """Append-only persistence port for minimal audit events."""

    def add(self, event: AuditEvent) -> None:
        """Append an immutable event to the current transaction."""


__all__ = [
    "AuditEventRepository",
    "CompanyRepository",
    "InvestigationRepository",
    "UserRepository",
    "WorkspaceMembershipRepository",
    "WorkspaceRepository",
]
