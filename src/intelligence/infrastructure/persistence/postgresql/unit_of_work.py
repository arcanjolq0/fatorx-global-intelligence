"""Synchronous SQLAlchemy connection-and-transaction Unit of Work."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from types import TracebackType
from typing import Literal

from sqlalchemy.engine import Connection, Engine, RootTransaction
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from intelligence.application.errors import (
    PersistenceConflictError,
    PersistenceError,
    PersistenceStateError,
)
from intelligence.infrastructure.persistence.postgresql.claim_repository import (
    PostgreSQLClaimRepository,
)
from intelligence.infrastructure.persistence.postgresql.evidence_repository import (
    PostgreSQLEvidenceRepository,
)
from intelligence.infrastructure.persistence.postgresql.repositories import (
    PostgreSQLAuditEventRepository,
    PostgreSQLCollectionExecutionRepository,
    PostgreSQLCollectionRunRepository,
    PostgreSQLCompanyRepository,
    PostgreSQLEntityCandidateBatchRepository,
    PostgreSQLEntityResolutionDecisionRepository,
    PostgreSQLInvestigationPlanRepository,
    PostgreSQLInvestigationRepository,
    PostgreSQLInvestigationTransitionRepository,
    PostgreSQLUserRepository,
    PostgreSQLWorkspaceMembershipRepository,
    PostgreSQLWorkspaceRepository,
)
from intelligence.infrastructure.persistence.postgresql.transaction_guard import (
    PostgreSQLTransactionGuard,
)


class PostgreSQLUnitOfWork:
    """Single-use explicit transaction shared by all persistence repositories."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._connection: Connection | None = None
        self._transaction: RootTransaction | None = None
        self._transaction_guard: PostgreSQLTransactionGuard | None = None
        self._workspaces: PostgreSQLWorkspaceRepository | None = None
        self._companies: PostgreSQLCompanyRepository | None = None
        self._investigations: PostgreSQLInvestigationRepository | None = None
        self._investigation_transitions: PostgreSQLInvestigationTransitionRepository | None = None
        self._investigation_plans: PostgreSQLInvestigationPlanRepository | None = None
        self._collection_runs: PostgreSQLCollectionRunRepository | None = None
        self._collection_executions: PostgreSQLCollectionExecutionRepository | None = None
        self._evidence: PostgreSQLEvidenceRepository | None = None
        self._claims: PostgreSQLClaimRepository | None = None
        self._entity_candidate_batches: PostgreSQLEntityCandidateBatchRepository | None = None
        self._entity_resolution_decisions: PostgreSQLEntityResolutionDecisionRepository | None = (
            None
        )
        self._users: PostgreSQLUserRepository | None = None
        self._memberships: PostgreSQLWorkspaceMembershipRepository | None = None
        self._audit_events: PostgreSQLAuditEventRepository | None = None
        self._entered = False
        self._closed = False
        self._finalization_attempted = False
        self._committed = False
        self._rolled_back = False

    @property
    def workspaces(self) -> PostgreSQLWorkspaceRepository:
        self._require_active()
        repository = self._workspaces
        if repository is None:
            raise PersistenceStateError("Workspace repository is unavailable.")
        return repository

    @property
    def companies(self) -> PostgreSQLCompanyRepository:
        self._require_active()
        repository = self._companies
        if repository is None:
            raise PersistenceStateError("Company repository is unavailable.")
        return repository

    @property
    def investigations(self) -> PostgreSQLInvestigationRepository:
        self._require_active()
        repository = self._investigations
        if repository is None:
            raise PersistenceStateError("Investigation repository is unavailable.")
        return repository

    @property
    def investigation_transitions(self) -> PostgreSQLInvestigationTransitionRepository:
        self._require_active()
        repository = self._investigation_transitions
        if repository is None:
            raise PersistenceStateError("Investigation transition repository is unavailable.")
        return repository

    @property
    def entity_candidate_batches(self) -> PostgreSQLEntityCandidateBatchRepository:
        self._require_active()
        repository = self._entity_candidate_batches
        if repository is None:
            raise PersistenceStateError("Entity candidate batch repository is unavailable.")
        return repository

    @property
    def entity_resolution_decisions(self) -> PostgreSQLEntityResolutionDecisionRepository:
        self._require_active()
        repository = self._entity_resolution_decisions
        if repository is None:
            raise PersistenceStateError("Entity resolution decision repository is unavailable.")
        return repository

    @property
    def investigation_plans(self) -> PostgreSQLInvestigationPlanRepository:
        self._require_active()
        repository = self._investigation_plans
        if repository is None:
            raise PersistenceStateError("Investigation plan repository is unavailable.")
        return repository

    @property
    def collection_runs(self) -> PostgreSQLCollectionRunRepository:
        self._require_active()
        repository = self._collection_runs
        if repository is None:
            raise PersistenceStateError("Collection run repository is unavailable.")
        return repository

    @property
    def collection_executions(self) -> PostgreSQLCollectionExecutionRepository:
        self._require_active()
        repository = self._collection_executions
        if repository is None:
            raise PersistenceStateError("Collection execution repository is unavailable.")
        return repository

    @property
    def evidence(self) -> PostgreSQLEvidenceRepository:
        self._require_active()
        repository = self._evidence
        if repository is None:
            raise PersistenceStateError("Evidence repository is unavailable.")
        return repository

    @property
    def claims(self) -> PostgreSQLClaimRepository:
        self._require_active()
        repository = self._claims
        if repository is None:
            raise PersistenceStateError("Claim repository is unavailable.")
        return repository

    @property
    def users(self) -> PostgreSQLUserRepository:
        self._require_active()
        repository = self._users
        if repository is None:
            raise PersistenceStateError("User repository is unavailable.")
        return repository

    @property
    def memberships(self) -> PostgreSQLWorkspaceMembershipRepository:
        self._require_active()
        repository = self._memberships
        if repository is None:
            raise PersistenceStateError("Membership repository is unavailable.")
        return repository

    @property
    def audit_events(self) -> PostgreSQLAuditEventRepository:
        self._require_active()
        repository = self._audit_events
        if repository is None:
            raise PersistenceStateError("Audit event repository is unavailable.")
        return repository

    @property
    def is_closed(self) -> bool:
        """Report whether the Unit of Work has reached a terminal closed state."""

        return self._closed

    def __enter__(self) -> PostgreSQLUnitOfWork:
        if self._entered or self._closed:
            raise PersistenceStateError("Unit of Work instances are single-use.")
        connection: Connection | None = None
        try:
            connection = self._engine.connect()
            transaction = connection.begin()
        except SQLAlchemyError as error:
            self._closed = True
            if connection is not None:
                with suppress(SQLAlchemyError):
                    connection.close()
            raise PersistenceError("Unable to start the persistence transaction.") from error

        transaction_guard = PostgreSQLTransactionGuard(connection, transaction)
        self._connection = connection
        self._transaction = transaction
        self._transaction_guard = transaction_guard
        self._workspaces = PostgreSQLWorkspaceRepository(transaction_guard)
        self._companies = PostgreSQLCompanyRepository(transaction_guard)
        self._investigations = PostgreSQLInvestigationRepository(transaction_guard)
        self._investigation_transitions = PostgreSQLInvestigationTransitionRepository(
            transaction_guard
        )
        self._entity_candidate_batches = PostgreSQLEntityCandidateBatchRepository(transaction_guard)
        self._entity_resolution_decisions = PostgreSQLEntityResolutionDecisionRepository(
            transaction_guard
        )
        self._investigation_plans = PostgreSQLInvestigationPlanRepository(transaction_guard)
        self._collection_runs = PostgreSQLCollectionRunRepository(transaction_guard)
        self._collection_executions = PostgreSQLCollectionExecutionRepository(transaction_guard)
        self._evidence = PostgreSQLEvidenceRepository(transaction_guard)
        self._claims = PostgreSQLClaimRepository(transaction_guard)
        self._users = PostgreSQLUserRepository(transaction_guard)
        self._memberships = PostgreSQLWorkspaceMembershipRepository(transaction_guard)
        self._audit_events = PostgreSQLAuditEventRepository(transaction_guard)
        self._entered = True
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exception_type, traceback
        rollback_error: PersistenceError | None = None
        close_error: PersistenceError | None = None
        transaction = self._transaction
        connection = self._connection
        transaction_guard = self._transaction_guard
        if transaction_guard is not None:
            transaction_guard.invalidate()
        self._closed = True
        try:
            if transaction is not None and transaction.is_active:
                try:
                    transaction.rollback()
                except SQLAlchemyError as error:
                    rollback_error = PersistenceError(
                        "Unable to roll back the persistence transaction."
                    )
                    rollback_error.__cause__ = error
        finally:
            if connection is not None:
                try:
                    connection.close()
                except SQLAlchemyError as error:
                    close_error = PersistenceError("Unable to close the persistence connection.")
                    close_error.__cause__ = error

        if exception is None:
            if rollback_error is not None:
                raise rollback_error
            if close_error is not None:
                raise close_error
        return False

    def commit(self) -> None:
        if self._committed:
            raise PersistenceStateError("Unit of Work has already been committed.")
        if self._rolled_back:
            raise PersistenceStateError("Unit of Work has already been rolled back.")
        transaction = self._start_finalization()
        try:
            transaction.commit()
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except SQLAlchemyError as error:
            raise PersistenceError("Unable to commit the persistence transaction.") from error
        self._committed = True

    def rollback(self) -> None:
        if self._rolled_back:
            raise PersistenceStateError("Unit of Work has already been rolled back.")
        if self._committed:
            raise PersistenceStateError("Unit of Work has already been committed.")
        transaction = self._start_finalization()
        try:
            transaction.rollback()
        except SQLAlchemyError as error:
            raise PersistenceError("Unable to roll back the persistence transaction.") from error
        self._rolled_back = True

    def _start_finalization(self) -> RootTransaction:
        if self._finalization_attempted:
            raise PersistenceStateError("Unit of Work finalization has already been attempted.")
        transaction = self._require_active()
        transaction_guard = self._transaction_guard
        if transaction_guard is None:
            raise PersistenceStateError("Unit of Work has no active transaction.")
        self._finalization_attempted = True
        transaction_guard.invalidate()
        return transaction

    def _require_active(self) -> RootTransaction:
        transaction = self._transaction
        transaction_guard = self._transaction_guard
        if not self._entered or self._closed or transaction is None or transaction_guard is None:
            raise PersistenceStateError("Unit of Work has no active transaction.")
        transaction_guard.require_active()
        return transaction


@dataclass(frozen=True, slots=True)
class PostgreSQLUnitOfWorkFactory:
    """Create one fresh PostgreSQL Unit of Work per service operation."""

    engine: Engine

    def __call__(self) -> PostgreSQLUnitOfWork:
        return PostgreSQLUnitOfWork(self.engine)


__all__ = ["PostgreSQLUnitOfWork", "PostgreSQLUnitOfWorkFactory"]
