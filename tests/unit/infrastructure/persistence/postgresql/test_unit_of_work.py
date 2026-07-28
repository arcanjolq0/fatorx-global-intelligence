"""Unit tests for Unit of Work lifecycle using controlled doubles."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from intelligence.application.errors import PersistenceError, PersistenceStateError
from intelligence.application.ports.unit_of_work import UnitOfWork
from intelligence.domain.audit import AuditEvent
from intelligence.domain.identifiers import UserId, WorkspaceId
from intelligence.domain.identities import EmailAddress, UserAccount, WorkspaceMembership
from intelligence.domain.workspaces import Workspace
from intelligence.infrastructure.persistence.postgresql.repositories import (
    PostgreSQLAuditEventRepository,
    PostgreSQLUserRepository,
    PostgreSQLWorkspaceMembershipRepository,
)
from intelligence.infrastructure.persistence.postgresql.unit_of_work import (
    PostgreSQLUnitOfWork,
)


class FakeTransaction:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.is_active = True
        self.commit_calls = 0
        self.rollback_calls = 0
        self.commit_error: SQLAlchemyError | None = None
        self.rollback_error: SQLAlchemyError | None = None

    def commit(self) -> None:
        self.commit_calls += 1
        if self.commit_error is not None:
            raise self.commit_error
        self.is_active = False
        self.connection.current_transaction = None

    def rollback(self) -> None:
        self.rollback_calls += 1
        if self.rollback_error is not None:
            raise self.rollback_error
        self.is_active = False
        self.connection.current_transaction = None


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False
        self.close_calls = 0
        self.close_error: SQLAlchemyError | None = None
        self.transaction = FakeTransaction(self)
        self.current_transaction: object | None = None
        self.begin_error: SQLAlchemyError | None = None

    def begin(self) -> FakeTransaction:
        if self.begin_error is not None:
            raise self.begin_error
        self.current_transaction = self.transaction
        return self.transaction

    def get_transaction(self) -> object | None:
        return self.current_transaction

    def close(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


class FakeEngine:
    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.connect_calls = 0
        self.connect_error: SQLAlchemyError | None = None

    def connect(self) -> FakeConnection:
        self.connect_calls += 1
        if self.connect_error is not None:
            raise self.connect_error
        return self.connection


def _unit_of_work() -> tuple[PostgreSQLUnitOfWork, FakeEngine]:
    engine = FakeEngine()
    return PostgreSQLUnitOfWork(cast(Engine, engine)), engine


def _technical_error(marker: str) -> OperationalError:
    return OperationalError(
        "SELECT secret_value FROM private_table",
        {
            "url": "postgresql+psycopg://sensitive-user:sensitive-password@database/private",
            "password": "sensitive-password",
        },
        RuntimeError(marker),
    )


def _assert_public_error_is_redacted(
    error: PersistenceError,
    expected_message: str,
    marker: str,
) -> None:
    message = str(error)
    assert message == expected_message
    for sensitive_fragment in (
        "SELECT secret_value",
        "postgresql+psycopg://",
        "sensitive-password",
        marker,
    ):
        assert sensitive_fragment not in message


def _capture_new_repositories(
    unit_of_work: PostgreSQLUnitOfWork,
) -> tuple[
    PostgreSQLUserRepository,
    PostgreSQLWorkspaceMembershipRepository,
    PostgreSQLAuditEventRepository,
]:
    return (
        unit_of_work.users,
        unit_of_work.memberships,
        unit_of_work.audit_events,
    )


def _assert_new_repositories_reject_operations(
    repositories: tuple[
        PostgreSQLUserRepository,
        PostgreSQLWorkspaceMembershipRepository,
        PostgreSQLAuditEventRepository,
    ],
) -> None:
    users, memberships, audit_events = repositories

    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        users.get(UserId.new())
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        users.get_by_email(EmailAddress("analyst@example.com"))
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        users.add(cast(UserAccount, None))
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        memberships.get(WorkspaceId.new(), UserId.new())
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        memberships.add(cast(WorkspaceMembership, None))
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        audit_events.add(cast(AuditEvent, None))


def test_concrete_unit_of_work_satisfies_the_application_port() -> None:
    unit_of_work, _ = _unit_of_work()
    application_port: UnitOfWork = unit_of_work

    assert application_port is unit_of_work


def test_exit_without_explicit_commit_rolls_back_and_closes_connection() -> None:
    unit_of_work, engine = _unit_of_work()

    with unit_of_work:
        assert engine.connection.transaction.is_active

    assert engine.connection.transaction.rollback_calls == 1
    assert engine.connection.closed
    assert unit_of_work.is_closed


def test_explicit_commit_happens_once_and_exit_only_closes() -> None:
    unit_of_work, engine = _unit_of_work()

    with unit_of_work:
        guard = unit_of_work.workspaces._transaction_guard
        unit_of_work.commit()
        assert guard.is_invalidated
        with pytest.raises(PersistenceStateError):
            unit_of_work.commit()

    assert engine.connection.transaction.commit_calls == 1
    assert engine.connection.transaction.rollback_calls == 0
    assert engine.connection.closed


def test_repositories_share_the_connection_opened_by_the_unit_of_work() -> None:
    unit_of_work, engine = _unit_of_work()
    expected_connection: object = engine.connection
    expected_transaction: object = engine.connection.transaction

    with unit_of_work:
        guards = {
            id(unit_of_work.workspaces._transaction_guard),
            id(unit_of_work.companies._transaction_guard),
            id(unit_of_work.investigations._transaction_guard),
            id(unit_of_work.users._transaction_guard),
            id(unit_of_work.memberships._transaction_guard),
            id(unit_of_work.audit_events._transaction_guard),
        }
        guard = unit_of_work.workspaces._transaction_guard

        assert len(guards) == 1
        assert guard.connection is expected_connection
        assert guard.transaction is expected_transaction
        assert guard.require_active() is expected_connection


def test_captured_repository_rejects_read_and_write_after_commit() -> None:
    unit_of_work, engine = _unit_of_work()

    with unit_of_work:
        repository = unit_of_work.workspaces
        new_repositories = _capture_new_repositories(unit_of_work)
        unit_of_work.commit()

        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.get(WorkspaceId.new())
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.add(cast(Workspace, None))
        _assert_new_repositories_reject_operations(new_repositories)

        assert engine.connection.get_transaction() is None


def test_captured_repository_rejects_read_and_write_after_rollback() -> None:
    unit_of_work, engine = _unit_of_work()

    with unit_of_work:
        repository = unit_of_work.workspaces
        new_repositories = _capture_new_repositories(unit_of_work)
        guard = repository._transaction_guard
        unit_of_work.rollback()

        assert guard.is_invalidated
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.get(WorkspaceId.new())
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.add(cast(Workspace, None))
        _assert_new_repositories_reject_operations(new_repositories)

        assert engine.connection.get_transaction() is None


def test_repository_rejects_a_different_active_transaction_identity() -> None:
    unit_of_work, engine = _unit_of_work()

    with unit_of_work:
        repository = unit_of_work.workspaces
        replacement = FakeTransaction(engine.connection)
        engine.connection.current_transaction = replacement

        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.get(WorkspaceId.new())

        engine.connection.current_transaction = engine.connection.transaction


def test_unit_of_work_and_repositories_reject_use_after_close() -> None:
    unit_of_work, _ = _unit_of_work()

    for repository_name in (
        "workspaces",
        "companies",
        "investigations",
        "users",
        "memberships",
        "audit_events",
    ):
        with pytest.raises(PersistenceStateError):
            getattr(unit_of_work, repository_name)

    with unit_of_work:
        repository = unit_of_work.workspaces
        new_repositories = _capture_new_repositories(unit_of_work)

    for repository_name in (
        "workspaces",
        "companies",
        "investigations",
        "users",
        "memberships",
        "audit_events",
    ):
        with pytest.raises(PersistenceStateError):
            getattr(unit_of_work, repository_name)
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        repository.get(WorkspaceId.new())
    _assert_new_repositories_reject_operations(new_repositories)
    with pytest.raises(PersistenceStateError):
        unit_of_work.__enter__()


def test_duplicate_rollback_fails_clearly() -> None:
    unit_of_work, engine = _unit_of_work()

    with unit_of_work:
        unit_of_work.rollback()
        with pytest.raises(PersistenceStateError, match="already been rolled back"):
            unit_of_work.rollback()

    assert engine.connection.transaction.rollback_calls == 1


def test_start_failure_is_translated_and_closes_the_connection() -> None:
    unit_of_work, engine = _unit_of_work()
    marker = "begin-technical-marker"
    engine.connection.begin_error = _technical_error(marker)

    with pytest.raises(PersistenceError) as captured:
        unit_of_work.__enter__()

    _assert_public_error_is_redacted(
        captured.value,
        "Unable to start the persistence transaction.",
        marker,
    )
    assert engine.connection.closed
    assert unit_of_work.is_closed
    with pytest.raises(PersistenceStateError, match="single-use"):
        unit_of_work.__enter__()
    assert engine.connect_calls == 1


def test_commit_failure_poisons_guard_repositories_and_public_finalization() -> None:
    unit_of_work, engine = _unit_of_work()
    marker = "commit-technical-marker"
    engine.connection.transaction.commit_error = _technical_error(marker)

    with unit_of_work:
        repository = unit_of_work.workspaces
        new_repositories = _capture_new_repositories(unit_of_work)
        guard = repository._transaction_guard
        with pytest.raises(PersistenceError) as captured:
            unit_of_work.commit()

        assert engine.connection.transaction.is_active
        assert guard.is_invalidated
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.get(WorkspaceId.new())
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.add(cast(Workspace, None))
        _assert_new_repositories_reject_operations(new_repositories)
        with pytest.raises(PersistenceStateError, match="finalization has already been attempted"):
            unit_of_work.commit()
        with pytest.raises(PersistenceStateError, match="finalization has already been attempted"):
            unit_of_work.rollback()

    _assert_public_error_is_redacted(
        captured.value,
        "Unable to commit the persistence transaction.",
        marker,
    )
    assert engine.connection.transaction.commit_calls == 1
    assert engine.connection.transaction.rollback_calls == 1
    assert engine.connection.closed


def test_rollback_failure_poisons_guard_repositories_and_public_finalization() -> None:
    unit_of_work, engine = _unit_of_work()
    marker = "rollback-technical-marker"

    with unit_of_work:
        repository = unit_of_work.workspaces
        new_repositories = _capture_new_repositories(unit_of_work)
        guard = repository._transaction_guard
        engine.connection.transaction.rollback_error = _technical_error(marker)
        with pytest.raises(PersistenceError) as captured:
            unit_of_work.rollback()

        assert engine.connection.transaction.is_active
        assert guard.is_invalidated
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.get(WorkspaceId.new())
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.add(cast(Workspace, None))
        _assert_new_repositories_reject_operations(new_repositories)
        with pytest.raises(PersistenceStateError, match="finalization has already been attempted"):
            unit_of_work.commit()
        with pytest.raises(PersistenceStateError, match="finalization has already been attempted"):
            unit_of_work.rollback()
        engine.connection.transaction.rollback_error = None

    _assert_public_error_is_redacted(
        captured.value,
        "Unable to roll back the persistence transaction.",
        marker,
    )
    assert engine.connection.transaction.rollback_calls == 2
    assert engine.connection.closed


def test_close_failure_keeps_unit_of_work_and_guard_terminal() -> None:
    unit_of_work, engine = _unit_of_work()
    marker = "close-technical-marker"
    engine.connection.close_error = _technical_error(marker)

    with pytest.raises(PersistenceError) as captured, unit_of_work:
        repository = unit_of_work.workspaces
        new_repositories = _capture_new_repositories(unit_of_work)
        guard = repository._transaction_guard

    _assert_public_error_is_redacted(
        captured.value,
        "Unable to close the persistence connection.",
        marker,
    )
    assert unit_of_work.is_closed
    assert guard.is_invalidated
    assert not engine.connection.closed
    assert engine.connection.close_calls == 1
    with pytest.raises(PersistenceStateError):
        _ = unit_of_work.workspaces
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        repository.get(WorkspaceId.new())
    _assert_new_repositories_reject_operations(new_repositories)
    with pytest.raises(PersistenceStateError, match="no active transaction"):
        unit_of_work.commit()
    with pytest.raises(PersistenceStateError, match="no active transaction"):
        unit_of_work.rollback()
    with pytest.raises(PersistenceStateError, match="single-use"):
        unit_of_work.__enter__()
