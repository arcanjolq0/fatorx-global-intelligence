"""Failure-boundary tests for the F5.4 PostgreSQL Claim-review repository."""

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
from intelligence.claims.review import ClaimReviewDecision
from intelligence.infrastructure.persistence.postgresql.claim_review_repository import (
    PostgreSQLClaimReviewDecisionRepository,
)
from intelligence.infrastructure.persistence.postgresql.transaction_guard import (
    PostgreSQLTransactionGuard,
)
from tests.unit.application.test_claim_review_service import _command, _setup


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


class _EmptyMappingsResult:
    def mappings(self) -> _EmptyMappingsResult:
        return self

    def all(self) -> list[object]:
        return []


class _CommandBindingWithoutHistoryConnection:
    def __init__(self, claim_id: UUID) -> None:
        self._claim_id = claim_id
        self._calls = 0

    def execute(self, *args: object, **kwargs: object) -> _ScalarResult | _EmptyMappingsResult:
        del args, kwargs
        self._calls += 1
        if self._calls == 1:
            return _ScalarResult(self._claim_id)
        return _EmptyMappingsResult()


def _technical_error() -> OperationalError:
    return OperationalError("SELECT sensitive", {"token": "secret"}, RuntimeError("driver"))


def _repository(connection: object) -> PostgreSQLClaimReviewDecisionRepository:
    return PostgreSQLClaimReviewDecisionRepository(
        cast(PostgreSQLTransactionGuard, _Guard(connection))
    )


def _decision() -> ClaimReviewDecision:
    _creator, reviewer, _factory, reviews, claim, _admitted = _setup()
    return reviews.decide(reviewer, _command(claim)).history.latest


def test_repository_redacts_lock_history_and_command_database_failures() -> None:
    decision = _decision()
    repository = _repository(_RaisingConnection(_technical_error()))
    with pytest.raises(PersistenceError, match="Persistence operation failed") as lock_error:
        repository.acquire_history_lock(decision.workspace_id, decision.claim_id)
    with pytest.raises(PersistenceError, match="Persistence operation failed") as history_error:
        repository.get_history(decision.workspace_id, decision.claim_id)
    with pytest.raises(PersistenceError, match="Persistence operation failed") as command_error:
        repository.get_history_by_command(decision.workspace_id, decision.command_id)
    for error in (lock_error.value, history_error.value, command_error.value):
        assert "sensitive" not in str(error)
        assert "secret" not in str(error)


def test_repository_classifies_insert_integrity_conflicts() -> None:
    conflict = IntegrityError("INSERT sensitive", {"token": "secret"}, RuntimeError("driver"))
    with pytest.raises(PersistenceConflictError, match="Persistence constraint conflict"):
        _repository(_RaisingConnection(conflict)).add_initial(_decision())
    with pytest.raises(PersistenceError, match="Persistence operation failed"):
        _repository(_RaisingConnection(_technical_error())).add_superseding(_decision())


def test_command_lookup_handles_absence_and_missing_bound_history() -> None:
    decision = _decision()
    absent = _repository(_ScalarConnection(None))
    assert absent.get_history_by_command(decision.workspace_id, decision.command_id) is None

    inconsistent = _repository(_CommandBindingWithoutHistoryConnection(decision.claim_id.value))
    with pytest.raises(PersistenceDataError, match="command history is missing"):
        inconsistent.get_history_by_command(decision.workspace_id, decision.command_id)
