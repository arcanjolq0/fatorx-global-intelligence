"""Unit tests for Unit of Work lifecycle using controlled doubles."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from intelligence.application.errors import PersistenceError, PersistenceStateError
from intelligence.application.ports.unit_of_work import UnitOfWork
from intelligence.domain.identifiers import WorkspaceId
from intelligence.domain.workspaces import Workspace
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
    return OperationalError("sensitive statement", {}, RuntimeError(marker))


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
        unit_of_work.commit()
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
        unit_of_work.commit()

        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.get(WorkspaceId.new())
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.add(cast(Workspace, None))

        assert engine.connection.get_transaction() is None


def test_captured_repository_rejects_read_and_write_after_rollback() -> None:
    unit_of_work, engine = _unit_of_work()

    with unit_of_work:
        repository = unit_of_work.workspaces
        unit_of_work.rollback()

        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.get(WorkspaceId.new())
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.add(cast(Workspace, None))

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

    with unit_of_work:
        repository = unit_of_work.workspaces

    with pytest.raises(PersistenceStateError):
        _ = unit_of_work.workspaces
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        repository.get(WorkspaceId.new())
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

    assert str(captured.value) == "Unable to start the persistence transaction."
    assert marker not in str(captured.value)
    assert engine.connection.closed


def test_commit_failure_is_translated_without_technical_details() -> None:
    unit_of_work, engine = _unit_of_work()
    marker = "commit-technical-marker"
    engine.connection.transaction.commit_error = _technical_error(marker)

    with pytest.raises(PersistenceError) as captured, unit_of_work:
        unit_of_work.commit()

    assert str(captured.value) == "Unable to commit the persistence transaction."
    assert marker not in str(captured.value)
    assert engine.connection.closed


def test_rollback_failure_is_translated_without_technical_details() -> None:
    unit_of_work, engine = _unit_of_work()
    marker = "rollback-technical-marker"

    with unit_of_work:
        engine.connection.transaction.rollback_error = _technical_error(marker)
        with pytest.raises(PersistenceError) as captured:
            unit_of_work.rollback()
        engine.connection.transaction.rollback_error = None

    assert str(captured.value) == "Unable to roll back the persistence transaction."
    assert marker not in str(captured.value)
    assert engine.connection.closed
