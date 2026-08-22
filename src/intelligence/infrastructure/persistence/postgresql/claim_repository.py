"""PostgreSQL adapter for append-only F5.2 Claim histories."""

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
from intelligence.claims.models import Claim, ClaimEvidenceLink, ClaimHistory
from intelligence.domain.errors import DomainError
from intelligence.domain.identifiers import ClaimCommandId, ClaimId, WorkspaceId
from intelligence.infrastructure.persistence.postgresql.claim_mappers import (
    claim_from_values,
    claim_link_from_values,
    claim_link_to_values,
    claim_to_values,
)
from intelligence.infrastructure.persistence.postgresql.claim_tables import (
    claim_evidence_link_table,
    claim_table,
)
from intelligence.infrastructure.persistence.postgresql.transaction_guard import (
    PostgreSQLTransactionGuard,
)


class PostgreSQLClaimRepository:
    """Append and reconstitute complete Claim series with fail-closed validation."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def acquire_command_lock(self, workspace_id: WorkspaceId, command_id: ClaimCommandId) -> None:
        self._acquire_advisory_lock(f"CLAIM:{workspace_id.value}:{command_id.value}")

    def acquire_history_lock(self, workspace_id: WorkspaceId, claim_id: ClaimId) -> None:
        self._acquire_advisory_lock(f"CLAIM_HISTORY:{workspace_id.value}:{claim_id.value}")

    def _acquire_advisory_lock(self, key: str) -> None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(
            sa.func.pg_advisory_xact_lock(
                sa.func.hashtextextended(sa.bindparam("claim_lock_key"), 0)
            )
        )
        try:
            connection.execute(statement, {"claim_lock_key": key}).scalar_one()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def add_initial(self, claim: Claim, links: tuple[ClaimEvidenceLink, ...]) -> None:
        self._append(claim, links)

    def add_correction(self, claim: Claim, links: tuple[ClaimEvidenceLink, ...]) -> None:
        self._append(claim, links)

    def _append(self, claim: Claim, links: tuple[ClaimEvidenceLink, ...]) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(sa.insert(claim_table).values(**claim_to_values(claim)))
            connection.execute(
                sa.insert(claim_evidence_link_table),
                [claim_link_to_values(link) for link in links],
            )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get_history(self, workspace_id: WorkspaceId, claim_id: ClaimId) -> ClaimHistory | None:
        connection = self._transaction_guard.require_active()
        root_statement = sa.select(claim_table.c.series_id).where(
            claim_table.c.workspace_id == workspace_id.value,
            claim_table.c.id == claim_id.value,
        )
        try:
            series_id = connection.execute(root_statement).scalar_one_or_none()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if series_id is None:
            return None
        versions_statement = (
            sa.select(claim_table)
            .where(
                claim_table.c.workspace_id == workspace_id.value,
                claim_table.c.series_id == series_id,
            )
            .order_by(claim_table.c.version)
        )
        links_statement = (
            sa.select(claim_evidence_link_table)
            .select_from(
                claim_evidence_link_table.join(
                    claim_table,
                    sa.and_(
                        claim_evidence_link_table.c.claim_id == claim_table.c.id,
                        claim_evidence_link_table.c.workspace_id == claim_table.c.workspace_id,
                    ),
                )
            )
            .where(
                claim_table.c.workspace_id == workspace_id.value,
                claim_table.c.series_id == series_id,
            )
            .order_by(claim_table.c.version, claim_evidence_link_table.c.evidence_id)
        )
        try:
            version_rows = connection.execute(versions_statement).mappings().all()
            link_rows = connection.execute(links_statement).mappings().all()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if not version_rows or not link_rows:
            raise PersistenceDataError("Persisted Claim history is incomplete.")
        try:
            versions = tuple(
                claim_from_values(cast(Mapping[str, object], row)) for row in version_rows
            )
            links = tuple(
                claim_link_from_values(cast(Mapping[str, object], row)) for row in link_rows
            )
            return ClaimHistory(versions=versions, links=links)
        except (DomainError, ValueError) as error:
            raise PersistenceDataError("Persisted Claim history is invalid.") from error

    def get_history_by_command(
        self, workspace_id: WorkspaceId, command_id: ClaimCommandId
    ) -> ClaimHistory | None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(claim_table.c.id).where(
            claim_table.c.workspace_id == workspace_id.value,
            claim_table.c.command_id == command_id.value,
        )
        try:
            claim_id = connection.execute(statement).scalar_one_or_none()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if claim_id is None:
            return None
        history = self.get_history(workspace_id, ClaimId(cast(UUID, claim_id)))
        if history is None:
            raise PersistenceDataError("Persisted Claim command history is missing.")
        return history


__all__ = ["PostgreSQLClaimRepository"]
