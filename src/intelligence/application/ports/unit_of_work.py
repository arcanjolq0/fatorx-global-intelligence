"""Transaction boundary port for application use cases."""

from types import TracebackType
from typing import Literal, Protocol, Self

from intelligence.application.ports.repositories import (
    AuditEventRepository,
    ClaimRepository,
    ClaimReviewDecisionRepository,
    CollectionExecutionRepository,
    CollectionRunRepository,
    CompanyRepository,
    EntityCandidateBatchRepository,
    EntityResolutionDecisionRepository,
    EvidenceAdmissibilityDecisionRepository,
    EvidenceRepository,
    InvestigationPlanRepository,
    InvestigationRepository,
    InvestigationTransitionRepository,
    UserRepository,
    WorkspaceMembershipRepository,
    WorkspaceRepository,
)


class UnitOfWork(Protocol):
    """One explicit transaction shared by all persistence ports."""

    @property
    def workspaces(self) -> WorkspaceRepository:
        """Return the workspace repository bound to the active transaction."""

    @property
    def companies(self) -> CompanyRepository:
        """Return the company repository bound to the active transaction."""

    @property
    def investigations(self) -> InvestigationRepository:
        """Return the investigation repository bound to the active transaction."""

    @property
    def investigation_transitions(self) -> InvestigationTransitionRepository:
        """Return the append-only transition repository for the active transaction."""

    @property
    def entity_candidate_batches(self) -> EntityCandidateBatchRepository:
        """Return immutable entity-candidate batches for the active transaction."""

    @property
    def entity_resolution_decisions(self) -> EntityResolutionDecisionRepository:
        """Return immutable human entity-resolution decisions for the transaction."""

    @property
    def investigation_plans(self) -> InvestigationPlanRepository:
        """Return immutable investigation plans for the active transaction."""

    @property
    def collection_runs(self) -> CollectionRunRepository:
        """Return immutable collection manifests for the active transaction."""

    @property
    def collection_executions(self) -> CollectionExecutionRepository:
        """Return append-only execution ownership and completions for the transaction."""

    @property
    def evidence(self) -> EvidenceRepository:
        """Return append-only canonical evidence records for the transaction."""

    @property
    def evidence_admissibility(self) -> EvidenceAdmissibilityDecisionRepository:
        """Return append-only global Evidence admissibility decisions."""

    @property
    def claims(self) -> ClaimRepository:
        """Return append-only Claim versions and links for the transaction."""

    @property
    def claim_reviews(self) -> ClaimReviewDecisionRepository:
        """Return append-only exact-version Claim reviews."""

    @property
    def users(self) -> UserRepository:
        """Return the internal-user repository bound to the active transaction."""

    @property
    def memberships(self) -> WorkspaceMembershipRepository:
        """Return the membership repository bound to the active transaction."""

    @property
    def audit_events(self) -> AuditEventRepository:
        """Return the append-only audit repository bound to the active transaction."""

    def __enter__(self) -> Self:
        """Open the transaction and bind all repositories."""

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        """Roll back uncommitted work and close the connection."""

    def commit(self) -> None:
        """Commit the active transaction exactly once."""

    def rollback(self) -> None:
        """Roll back the active transaction explicitly."""


class UnitOfWorkFactory(Protocol):
    """Create a fresh single-use Unit of Work for each application operation."""

    def __call__(self) -> UnitOfWork:
        """Return a new, unopened Unit of Work instance."""


__all__ = ["UnitOfWork", "UnitOfWorkFactory"]
