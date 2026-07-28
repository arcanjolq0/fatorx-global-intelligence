"""Unit tests for Unit of Work lifecycle using controlled doubles."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.engine import Engine

from intelligence.application.errors import PersistenceStateError
from intelligence.application.ports.unit_of_work import UnitOfWork
from intelligence.domain.identifiers import WorkspaceId
from intelligence.infrastructure.persistence.postgresql.unit_of_work import (
    PostgreSQLUnitOfWork,
)


class FakeTransaction:
    def __init__(self) -> None:
        self.is_active = True
        self.commit_calls = 0
        self.rollback_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1
        self.is_active = False

    def rollback(self) -> None:
        self.rollback_calls += 1
        self.is_active = False


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False
        self.transaction = FakeTransaction()

    def begin(self) -> FakeTransaction:
        return self.transaction

    def close(self) -> None:
        self.closed = True


class FakeEngine:
    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.connect_calls = 0

    def connect(self) -> FakeConnection:
        self.connect_calls += 1
        return self.connection


def _unit_of_work() -> tuple[PostgreSQLUnitOfWork, FakeEngine]:
    engine = FakeEngine()
    return PostgreSQLUnitOfWork(cast(Engine, engine)), engine


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

    with unit_of_work:
        assert unit_of_work.workspaces._connection is expected_connection
        assert unit_of_work.companies._connection is expected_connection
        assert unit_of_work.investigations._connection is expected_connection


def test_unit_of_work_and_repositories_reject_use_after_close() -> None:
    unit_of_work, _ = _unit_of_work()

    with unit_of_work:
        repository = unit_of_work.workspaces

    with pytest.raises(PersistenceStateError):
        _ = unit_of_work.workspaces
    with pytest.raises(PersistenceStateError):
        repository.get(cast(WorkspaceId, None))
    with pytest.raises(PersistenceStateError):
        unit_of_work.__enter__()
