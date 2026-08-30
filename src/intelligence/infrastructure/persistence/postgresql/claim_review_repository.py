"""PostgreSQL adapter for append-only F5.4 Claim-review histories."""

from collections.abc import Mapping
from typing import cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError

from intelligence.application.errors import (
    PersistenceConflictError,
    PersistenceDataError,
    PersistenceError,
)
from intelligence.claims.review import ClaimReviewDecision, ClaimReviewHistory
from intelligence.domain.errors import DomainError
from intelligence.domain.identifiers import ClaimId, ClaimReviewCommandId, WorkspaceId
from intelligence.infrastructure.persistence.postgresql.claim_review_mappers import (
    claim_review_decision_from_values,
    claim_review_decision_to_values,
)
from intelligence.infrastructure.persistence.postgresql.claim_review_tables import (
    claim_review_decision_table,
)
from intelligence.infrastructure.persistence.postgresql.transaction_guard import (
    PostgreSQLTransactionGuard,
)


class PostgreSQLClaimReviewDecisionRepository:
    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def acquire_command_lock(
        self, workspace_id: WorkspaceId, command_id: ClaimReviewCommandId
    ) -> None:
        self._lock(f"CLAIM_REVIEW:{workspace_id.value}:{command_id.value}")

    def acquire_history_lock(self, workspace_id: WorkspaceId, claim_id: ClaimId) -> None:
        self._lock(f"CLAIM_REVIEW_HISTORY:{workspace_id.value}:{claim_id.value}")

    def _lock(self, key: str) -> None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(
            sa.func.pg_advisory_xact_lock(sa.func.hashtextextended(sa.bindparam("lock_key"), 0))
        )
        try:
            connection.execute(statement, {"lock_key": key}).scalar_one()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def add_initial(self, decision: ClaimReviewDecision) -> None:
        self._append(decision)

    def add_superseding(self, decision: ClaimReviewDecision) -> None:
        self._append(decision)

    def _append(self, decision: ClaimReviewDecision) -> None:
        try:
            self._transaction_guard.require_active().execute(
                sa.insert(claim_review_decision_table).values(
                    **claim_review_decision_to_values(decision)
                )
            )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get_history(
        self, workspace_id: WorkspaceId, claim_id: ClaimId
    ) -> ClaimReviewHistory | None:
        statement = (
            sa.select(claim_review_decision_table)
            .where(
                claim_review_decision_table.c.workspace_id == workspace_id.value,
                claim_review_decision_table.c.claim_id == claim_id.value,
            )
            .order_by(claim_review_decision_table.c.decision_sequence)
        )
        try:
            rows = self._transaction_guard.require_active().execute(statement).mappings().all()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if not rows:
            return None
        try:
            return ClaimReviewHistory(
                decisions=tuple(
                    claim_review_decision_from_values(cast(Mapping[str, object], row))
                    for row in rows
                )
            )
        except (DomainError, ValueError) as error:
            raise PersistenceDataError("Persisted Claim-review history is invalid.") from error

    def get_history_by_command(
        self, workspace_id: WorkspaceId, command_id: ClaimReviewCommandId
    ) -> ClaimReviewHistory | None:
        statement = sa.select(claim_review_decision_table.c.claim_id).where(
            claim_review_decision_table.c.workspace_id == workspace_id.value,
            claim_review_decision_table.c.command_id == command_id.value,
        )
        try:
            claim_id = (
                self._transaction_guard.require_active().execute(statement).scalar_one_or_none()
            )
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if claim_id is None:
            return None
        try:
            persisted_claim_id = ClaimId(cast(UUID, claim_id))
        except DomainError as error:
            raise PersistenceDataError(
                "Persisted Claim-review command binding is invalid."
            ) from error
        history = self.get_history(workspace_id, persisted_claim_id)
        if history is None:
            raise PersistenceDataError("Persisted Claim-review command history is missing.")
        return history


__all__ = ["PostgreSQLClaimReviewDecisionRepository"]
