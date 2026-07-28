"""Synchronous SQLAlchemy connection-and-transaction Unit of Work."""

from __future__ import annotations

from types import TracebackType
from typing import Literal

from sqlalchemy.engine import Connection, Engine, RootTransaction
from sqlalchemy.exc import DBAPIError, IntegrityError

from intelligence.application.errors import (
    PersistenceConflictError,
    PersistenceError,
    PersistenceStateError,
)
from intelligence.infrastructure.persistence.postgresql.repositories import (
    PostgreSQLCompanyRepository,
    PostgreSQLInvestigationRepository,
    PostgreSQLWorkspaceRepository,
)


class PostgreSQLUnitOfWork:
    """Single-use explicit transaction shared by three repositories."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._connection: Connection | None = None
        self._transaction: RootTransaction | None = None
        self._workspaces: PostgreSQLWorkspaceRepository | None = None
        self._companies: PostgreSQLCompanyRepository | None = None
        self._investigations: PostgreSQLInvestigationRepository | None = None
        self._entered = False
        self._closed = False
        self._committed = False

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
    def is_closed(self) -> bool:
        """Report whether the caller-owned context has closed its connection."""

        return self._closed

    def __enter__(self) -> PostgreSQLUnitOfWork:
        if self._entered or self._closed:
            raise PersistenceStateError("Unit of Work instances are single-use.")
        connection: Connection | None = None
        try:
            connection = self._engine.connect()
            transaction = connection.begin()
        except DBAPIError as error:
            if connection is not None:
                connection.close()
            raise PersistenceError("Unable to start the persistence transaction.") from error

        self._connection = connection
        self._transaction = transaction
        self._workspaces = PostgreSQLWorkspaceRepository(connection)
        self._companies = PostgreSQLCompanyRepository(connection)
        self._investigations = PostgreSQLInvestigationRepository(connection)
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
        transaction = self._transaction
        connection = self._connection
        try:
            if transaction is not None and transaction.is_active:
                try:
                    transaction.rollback()
                except DBAPIError as error:
                    rollback_error = PersistenceError(
                        "Unable to roll back the persistence transaction."
                    )
                    rollback_error.__cause__ = error
        finally:
            if connection is not None:
                connection.close()
            self._closed = True

        if rollback_error is not None and exception is None:
            raise rollback_error
        return False

    def commit(self) -> None:
        if self._committed:
            raise PersistenceStateError("Unit of Work has already been committed.")
        transaction = self._require_active()
        try:
            transaction.commit()
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Unable to commit the persistence transaction.") from error
        self._committed = True

    def rollback(self) -> None:
        transaction = self._require_active()
        try:
            transaction.rollback()
        except DBAPIError as error:
            raise PersistenceError("Unable to roll back the persistence transaction.") from error

    def _require_active(self) -> RootTransaction:
        connection = self._connection
        transaction = self._transaction
        if (
            not self._entered
            or self._closed
            or connection is None
            or connection.closed
            or transaction is None
            or not transaction.is_active
        ):
            raise PersistenceStateError("Unit of Work has no active transaction.")
        return transaction


__all__ = ["PostgreSQLUnitOfWork"]
