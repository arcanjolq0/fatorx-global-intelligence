"""PostgreSQL adapter for append-only canonical evidence histories."""

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
from intelligence.domain.identifiers import EvidenceCommandId, EvidenceId, WorkspaceId
from intelligence.evidence.models import Artifact, Evidence, EvidenceHistory, EvidenceLifecycleEvent
from intelligence.infrastructure.persistence.postgresql.evidence_mappers import (
    artifact_from_values,
    artifact_to_values,
    evidence_from_values,
    evidence_to_values,
    lifecycle_event_from_values,
    lifecycle_event_to_values,
)
from intelligence.infrastructure.persistence.postgresql.evidence_tables import (
    evidence_artifact_table,
    evidence_lifecycle_event_table,
    evidence_table,
)
from intelligence.infrastructure.persistence.postgresql.transaction_guard import (
    PostgreSQLTransactionGuard,
)


class PostgreSQLEvidenceRepository:
    """Append and reconstitute complete evidence series with fail-closed validation."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def acquire_command_lock(
        self, workspace_id: WorkspaceId, command_id: EvidenceCommandId
    ) -> None:
        key = f"EVIDENCE:{workspace_id.value}:{command_id.value}"
        self._acquire_advisory_lock(key)

    def acquire_history_lock(self, workspace_id: WorkspaceId, evidence_id: EvidenceId) -> None:
        key = f"EVIDENCE_HISTORY:{workspace_id.value}:{evidence_id.value}"
        self._acquire_advisory_lock(key)

    def _acquire_advisory_lock(self, key: str) -> None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(
            sa.func.pg_advisory_xact_lock(
                sa.func.hashtextextended(sa.bindparam("evidence_command_lock_key"), 0)
            )
        )
        try:
            connection.execute(statement, {"evidence_command_lock_key": key}).scalar_one()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def add_initial(self, artifact: Artifact, evidence: Evidence) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(
                sa.insert(evidence_artifact_table).values(**artifact_to_values(artifact))
            )
            connection.execute(sa.insert(evidence_table).values(**evidence_to_values(evidence)))
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def add_correction(self, evidence: Evidence, event: EvidenceLifecycleEvent) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(sa.insert(evidence_table).values(**evidence_to_values(evidence)))
            connection.execute(
                sa.insert(evidence_lifecycle_event_table).values(**lifecycle_event_to_values(event))
            )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def add_lifecycle_event(self, event: EvidenceLifecycleEvent) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(
                sa.insert(evidence_lifecycle_event_table).values(**lifecycle_event_to_values(event))
            )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get_history(
        self, workspace_id: WorkspaceId, evidence_id: EvidenceId
    ) -> EvidenceHistory | None:
        connection = self._transaction_guard.require_active()
        root_statement = sa.select(evidence_table.c.series_id).where(
            evidence_table.c.workspace_id == workspace_id.value,
            evidence_table.c.id == evidence_id.value,
        )
        try:
            series_id = connection.execute(root_statement).scalar_one_or_none()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if series_id is None:
            return None
        versions_statement = (
            sa.select(evidence_table)
            .where(
                evidence_table.c.workspace_id == workspace_id.value,
                evidence_table.c.series_id == series_id,
            )
            .order_by(evidence_table.c.version)
        )
        artifact_statement = (
            sa.select(evidence_artifact_table)
            .select_from(
                evidence_artifact_table.join(
                    evidence_table,
                    sa.and_(
                        evidence_table.c.artifact_id == evidence_artifact_table.c.id,
                        evidence_table.c.workspace_id == evidence_artifact_table.c.workspace_id,
                    ),
                )
            )
            .where(
                evidence_table.c.workspace_id == workspace_id.value,
                evidence_table.c.series_id == series_id,
                evidence_table.c.version == 1,
            )
        )
        events_statement = (
            sa.select(evidence_lifecycle_event_table)
            .select_from(
                evidence_lifecycle_event_table.join(
                    evidence_table,
                    sa.and_(
                        evidence_lifecycle_event_table.c.evidence_id == evidence_table.c.id,
                        evidence_lifecycle_event_table.c.workspace_id
                        == evidence_table.c.workspace_id,
                    ),
                )
            )
            .where(
                evidence_table.c.workspace_id == workspace_id.value,
                evidence_table.c.series_id == series_id,
            )
            .order_by(
                evidence_table.c.version,
                evidence_lifecycle_event_table.c.occurred_at,
                evidence_lifecycle_event_table.c.id,
            )
        )
        try:
            version_rows = connection.execute(versions_statement).mappings().all()
            artifact_row = connection.execute(artifact_statement).mappings().one_or_none()
            event_rows = connection.execute(events_statement).mappings().all()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if artifact_row is None or not version_rows:
            raise PersistenceDataError("Persisted evidence history is incomplete.")
        try:
            artifact = artifact_from_values(cast(Mapping[str, object], artifact_row))
            versions = tuple(
                evidence_from_values(cast(Mapping[str, object], row)) for row in version_rows
            )
            events = tuple(
                lifecycle_event_from_values(cast(Mapping[str, object], row)) for row in event_rows
            )
            return EvidenceHistory(artifact=artifact, versions=versions, events=events)
        except (DomainError, ValueError) as error:
            raise PersistenceDataError("Persisted evidence history is invalid.") from error

    def get_history_by_command(
        self, workspace_id: WorkspaceId, command_id: EvidenceCommandId
    ) -> EvidenceHistory | None:
        connection = self._transaction_guard.require_active()
        evidence_statement = sa.select(evidence_table.c.id).where(
            evidence_table.c.workspace_id == workspace_id.value,
            evidence_table.c.command_id == command_id.value,
        )
        event_statement = sa.select(evidence_lifecycle_event_table.c.evidence_id).where(
            evidence_lifecycle_event_table.c.workspace_id == workspace_id.value,
            evidence_lifecycle_event_table.c.command_id == command_id.value,
        )
        try:
            evidence_id = connection.execute(evidence_statement).scalar_one_or_none()
            event_evidence_id = connection.execute(event_statement).scalar_one_or_none()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if evidence_id is None and event_evidence_id is None:
            return None
        first_id = EvidenceId(
            cast(UUID, evidence_id if evidence_id is not None else event_evidence_id)
        )
        history = self.get_history(workspace_id, first_id)
        if history is None:
            raise PersistenceDataError("Persisted evidence command history is missing.")
        if evidence_id is not None and event_evidence_id is not None:
            evidence_ids = {item.id.value for item in history.versions}
            if evidence_id not in evidence_ids or event_evidence_id not in evidence_ids:
                raise PersistenceDataError("Persisted evidence command spans different histories.")
        return history


__all__ = ["PostgreSQLEvidenceRepository"]
