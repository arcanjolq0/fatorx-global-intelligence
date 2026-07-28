"""Small repository ports for the currently persisted aggregate snapshots."""

from typing import Protocol

from intelligence.domain.companies import Company
from intelligence.domain.identifiers import CompanyId, InvestigationId, WorkspaceId
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


__all__ = ["CompanyRepository", "InvestigationRepository", "WorkspaceRepository"]
