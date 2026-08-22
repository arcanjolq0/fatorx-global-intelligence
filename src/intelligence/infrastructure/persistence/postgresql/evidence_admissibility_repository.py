"""PostgreSQL adapter for append-only F5.3 admissibility histories."""

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
from intelligence.domain.errors import DomainError
from intelligence.domain.identifiers import (
    EvidenceAdmissibilityCommandId,
    EvidenceId,
    WorkspaceId,
)
from intelligence.evidence.admissibility import (
    EvidenceAdmissibilityDecision,
    EvidenceAdmissibilityHistory,
)
from intelligence.infrastructure.persistence.postgresql.evidence_admissibility_mappers import (
    evidence_admissibility_decision_from_values,
    evidence_admissibility_decision_to_values,
)
from intelligence.infrastructure.persistence.postgresql.evidence_admissibility_tables import (
    evidence_admissibility_decision_table,
)
from intelligence.infrastructure.persistence.postgresql.transaction_guard import (
    PostgreSQLTransactionGuard,
)


class PostgreSQLEvidenceAdmissibilityDecisionRepository:
    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def acquire_command_lock(
        self, workspace_id: WorkspaceId, command_id: EvidenceAdmissibilityCommandId
    ) -> None:
        self._lock(f"EVIDENCE_ADMISSIBILITY:{workspace_id.value}:{command_id.value}")

    def acquire_history_lock(self, workspace_id: WorkspaceId, evidence_id: EvidenceId) -> None:
        self._lock(f"EVIDENCE_ADMISSIBILITY_HISTORY:{workspace_id.value}:{evidence_id.value}")

    def _lock(self, key: str) -> None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(
            sa.func.pg_advisory_xact_lock(sa.func.hashtextextended(sa.bindparam("lock_key"), 0))
        )
        try:
            connection.execute(statement, {"lock_key": key}).scalar_one()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def add_initial(self, decision: EvidenceAdmissibilityDecision) -> None:
        self._append(decision)

    def add_superseding(self, decision: EvidenceAdmissibilityDecision) -> None:
        self._append(decision)

    def _append(self, decision: EvidenceAdmissibilityDecision) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(
                sa.insert(evidence_admissibility_decision_table).values(
                    **evidence_admissibility_decision_to_values(decision)
                )
            )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get_history(
        self, workspace_id: WorkspaceId, evidence_id: EvidenceId
    ) -> EvidenceAdmissibilityHistory | None:
        connection = self._transaction_guard.require_active()
        statement = (
            sa.select(evidence_admissibility_decision_table)
            .where(
                evidence_admissibility_decision_table.c.workspace_id == workspace_id.value,
                evidence_admissibility_decision_table.c.evidence_id == evidence_id.value,
            )
            .order_by(evidence_admissibility_decision_table.c.decision_sequence)
        )
        try:
            rows = connection.execute(statement).mappings().all()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if not rows:
            return None
        try:
            decisions = tuple(
                evidence_admissibility_decision_from_values(cast(Mapping[str, object], row))
                for row in rows
            )
            return EvidenceAdmissibilityHistory(decisions=decisions)
        except (DomainError, ValueError) as error:
            raise PersistenceDataError("Persisted admissibility history is invalid.") from error

    def get_history_by_command(
        self, workspace_id: WorkspaceId, command_id: EvidenceAdmissibilityCommandId
    ) -> EvidenceAdmissibilityHistory | None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(evidence_admissibility_decision_table.c.evidence_id).where(
            evidence_admissibility_decision_table.c.workspace_id == workspace_id.value,
            evidence_admissibility_decision_table.c.command_id == command_id.value,
        )
        try:
            evidence_id = connection.execute(statement).scalar_one_or_none()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if evidence_id is None:
            return None
        try:
            persisted_evidence_id = EvidenceId(cast(UUID, evidence_id))
        except DomainError as error:
            raise PersistenceDataError(
                "Persisted admissibility command binding is invalid."
            ) from error
        history = self.get_history(workspace_id, persisted_evidence_id)
        if history is None:
            raise PersistenceDataError("Persisted admissibility command history is missing.")
        return history


__all__ = ["PostgreSQLEvidenceAdmissibilityDecisionRepository"]
