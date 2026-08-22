"""Failure-boundary tests for the F5.3 PostgreSQL repository."""

from typing import Never, cast
from uuid import UUID

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError, OperationalError

from intelligence.application.errors import (
    PersistenceConflictError,
    PersistenceDataError,
    PersistenceError,
)
from intelligence.domain.identifiers import EvidenceAdmissibilityCommandId, EvidenceId, WorkspaceId
from intelligence.infrastructure.persistence.postgresql.evidence_admissibility_repository import (
    PostgreSQLEvidenceAdmissibilityDecisionRepository,
)
from intelligence.infrastructure.persistence.postgresql.transaction_guard import (
    PostgreSQLTransactionGuard,
)
from tests.unit.evidence.test_evidence_admissibility import _decision


class _Guard:
    def __init__(self, connection: object) -> None:
        self._connection = connection

    def require_active(self) -> Connection:
        return cast(Connection, self._connection)


class _RaisingConnection:
    def __init__(self, error: OperationalError | IntegrityError) -> None:
        self._error = error

    def execute(self, *args: object, **kwargs: object) -> Never:
        del args, kwargs
        raise self._error


class _ScalarResult:
    def __init__(self, value: UUID | None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> UUID | None:
        return self._value


class _ScalarConnection:
    def __init__(self, value: UUID | None) -> None:
        self._value = value

    def execute(self, *args: object, **kwargs: object) -> _ScalarResult:
        del args, kwargs
        return _ScalarResult(self._value)


def _technical_error() -> OperationalError:
    return OperationalError("SELECT sensitive", {"token": "secret"}, RuntimeError("driver"))


def _repository(connection: object) -> PostgreSQLEvidenceAdmissibilityDecisionRepository:
    return PostgreSQLEvidenceAdmissibilityDecisionRepository(
        cast(PostgreSQLTransactionGuard, _Guard(connection))
    )


def test_repository_redacts_lock_and_read_database_failures() -> None:
    repository = _repository(_RaisingConnection(_technical_error()))
    decision = _decision()
    with pytest.raises(PersistenceError, match="Persistence operation failed") as lock_error:
        repository.acquire_history_lock(decision.workspace_id, decision.evidence_id)
    with pytest.raises(PersistenceError, match="Persistence operation failed") as history_error:
        repository.get_history(decision.workspace_id, decision.evidence_id)
    with pytest.raises(PersistenceError, match="Persistence operation failed") as command_error:
        repository.get_history_by_command(decision.workspace_id, decision.command_id)
    for error in (lock_error.value, history_error.value, command_error.value):
        assert "sensitive" not in str(error)
        assert "secret" not in str(error)


def test_repository_classifies_insert_failures() -> None:
    decision = _decision()
    conflict = IntegrityError("INSERT sensitive", {"token": "secret"}, RuntimeError("driver"))
    with pytest.raises(PersistenceConflictError, match="Persistence constraint conflict"):
        _repository(_RaisingConnection(conflict)).add_initial(decision)
    with pytest.raises(PersistenceError, match="Persistence operation failed"):
        _repository(_RaisingConnection(_technical_error())).add_superseding(decision)


def test_command_lookup_handles_absence_and_inconsistent_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision = _decision()
    absent = _repository(_ScalarConnection(None))
    assert absent.get_history_by_command(decision.workspace_id, decision.command_id) is None

    inconsistent = _repository(_ScalarConnection(decision.evidence_id.value))
    monkeypatch.setattr(inconsistent, "get_history", lambda *_args: None)
    with pytest.raises(PersistenceDataError, match="command history is missing"):
        inconsistent.get_history_by_command(decision.workspace_id, decision.command_id)


def test_command_lookup_rejects_invalid_evidence_identifier() -> None:
    repository = _repository(_ScalarConnection(cast(UUID, "not-a-uuid")))
    with pytest.raises(PersistenceDataError, match="command binding is invalid"):
        repository.get_history_by_command(WorkspaceId.new(), EvidenceAdmissibilityCommandId.new())


def test_lock_commands_use_both_scoped_lock_paths() -> None:
    repository = _repository(_RaisingConnection(_technical_error()))
    with pytest.raises(PersistenceError):
        repository.acquire_command_lock(WorkspaceId.new(), EvidenceAdmissibilityCommandId.new())
    with pytest.raises(PersistenceError):
        repository.acquire_history_lock(WorkspaceId.new(), EvidenceId.new())
