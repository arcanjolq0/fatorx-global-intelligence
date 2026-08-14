"""Small repository ports for the currently persisted aggregate snapshots."""

from typing import Protocol

from intelligence.application.collection_execution import (
    CollectionExecutionOwnership,
    CollectionExecutionResultRecord,
)
from intelligence.application.entity_candidate_review import EntityCandidateBatchRecord
from intelligence.application.entity_confirmation import EntityResolutionDecisionRecord
from intelligence.application.investigation_lifecycle import InvestigationTransitionRecord
from intelligence.domain.audit import AuditEvent
from intelligence.domain.companies import Company
from intelligence.domain.identifiers import (
    CollectionOperationId,
    CollectionRunId,
    CompanyId,
    EntityCandidateBatchId,
    EntityResolutionDecisionId,
    InvestigationCommandId,
    InvestigationId,
    InvestigationPlanId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.identities import EmailAddress, UserAccount, WorkspaceMembership
from intelligence.domain.investigations import Investigation
from intelligence.domain.workspaces import Workspace
from intelligence.orchestration.collection_activation import CollectionRun
from intelligence.orchestration.planning import InvestigationPlan


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

    def get_for_update(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> Investigation | None:
        """Lock and return an investigation only within the supplied workspace."""

    def update_if_version(
        self,
        investigation: Investigation,
        *,
        expected_state_version: int,
    ) -> bool:
        """Compare-and-swap lifecycle fields under tenant and version scope."""


class InvestigationTransitionRepository(Protocol):
    """Append-only durable lifecycle command and transition records."""

    def acquire_command_lock(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> None:
        """Serialize one tenant-scoped idempotency key in the current transaction."""

    def get_by_command(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> InvestigationTransitionRecord | None:
        """Return a prior record only from the supplied workspace."""

    def add(self, record: InvestigationTransitionRecord) -> None:
        """Append an immutable record to the current transaction."""


class EntityCandidateBatchRepository(Protocol):
    """Append-only tenant-scoped candidate batches with immutable children."""

    def add(self, record: EntityCandidateBatchRecord) -> None:
        """Append a complete batch, candidates, and dimensions to this transaction."""

    def get(
        self,
        workspace_id: WorkspaceId,
        batch_id: EntityCandidateBatchId,
    ) -> EntityCandidateBatchRecord | None:
        """Reconstitute a complete batch only inside the supplied workspace."""


class EntityResolutionDecisionRepository(Protocol):
    """Append-only tenant-scoped human entity-resolution decisions."""

    def add(self, record: EntityResolutionDecisionRecord) -> None:
        """Append one immutable decision to the current transaction."""

    def get_by_command(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> EntityResolutionDecisionRecord | None:
        """Return a fully validated decision for a tenant-scoped command."""

    def get_by_investigation(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> EntityResolutionDecisionRecord | None:
        """Return the unique validated decision for one investigation."""

    def get_by_id(
        self,
        workspace_id: WorkspaceId,
        decision_id: EntityResolutionDecisionId,
    ) -> EntityResolutionDecisionRecord | None:
        """Return a validated decision by its strong identifier."""


class InvestigationPlanRepository(Protocol):
    """Append-only plan and child records that also form the durable command ledger."""

    def add(self, plan: InvestigationPlan) -> None:
        """Append one complete plan, its capabilities, and connector options."""

    def get_by_command(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> InvestigationPlan | None:
        """Return a fully validated plan for one tenant-scoped command."""

    def get_by_investigation(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> InvestigationPlan | None:
        """Return the sole validated plan for one investigation."""

    def get_by_id(
        self,
        workspace_id: WorkspaceId,
        plan_id: InvestigationPlanId,
    ) -> InvestigationPlan | None:
        """Return a validated plan by its strong identifier."""


class CollectionRunRepository(Protocol):
    """Append-only collection manifests and their prepared operations."""

    def add(self, run: CollectionRun) -> None:
        """Append a complete run, operations, and dependencies."""

    def get_by_command(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> CollectionRun | None:
        """Return a validated manifest for a tenant-scoped command."""

    def get_by_investigation(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> CollectionRun | None:
        """Return the sole manifest for one investigation."""

    def get_by_plan(
        self,
        workspace_id: WorkspaceId,
        plan_id: InvestigationPlanId,
    ) -> CollectionRun | None:
        """Return the sole manifest for one plan."""

    def get_by_id(
        self,
        workspace_id: WorkspaceId,
        run_id: CollectionRunId,
    ) -> CollectionRun | None:
        """Return a validated manifest by its strong identifier."""


class CollectionExecutionRepository(Protocol):
    """Append-only ownership and redacted completions for direct manifest execution."""

    def try_add_ownership(self, ownership: CollectionExecutionOwnership) -> bool:
        """Atomically append ownership, returning false on command or operation conflict."""

    def add_result(self, result: CollectionExecutionResultRecord) -> None:
        """Append the sole completion for one owned command."""

    def get_ownership_by_command(
        self, workspace_id: WorkspaceId, command_id: InvestigationCommandId
    ) -> CollectionExecutionOwnership | None:
        """Return tenant-scoped execution ownership by command."""

    def get_ownership_by_operation(
        self, workspace_id: WorkspaceId, operation_id: CollectionOperationId
    ) -> CollectionExecutionOwnership | None:
        """Return the sole tenant-scoped ownership for one manifest operation."""

    def get_result_by_command(
        self, workspace_id: WorkspaceId, command_id: InvestigationCommandId
    ) -> CollectionExecutionResultRecord | None:
        """Return a validated completion by command."""

    def get_result_by_operation(
        self, workspace_id: WorkspaceId, operation_id: CollectionOperationId
    ) -> CollectionExecutionResultRecord | None:
        """Return a validated completion by manifest operation."""

    def list_results_by_run(
        self, workspace_id: WorkspaceId, run_id: CollectionRunId
    ) -> tuple[CollectionExecutionResultRecord, ...]:
        """Return all validated completions for a run in operation order."""


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
    "CollectionExecutionRepository",
    "CollectionRunRepository",
    "CompanyRepository",
    "EntityCandidateBatchRepository",
    "EntityResolutionDecisionRepository",
    "InvestigationPlanRepository",
    "InvestigationRepository",
    "InvestigationTransitionRepository",
    "UserRepository",
    "WorkspaceMembershipRepository",
    "WorkspaceRepository",
]
