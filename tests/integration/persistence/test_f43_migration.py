"""F4.3 PostgreSQL migration constraints and fail-safe reversibility."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from tests.support.destructive_database import require_safe_destructive_database_url

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])

REPOSITORY_ROOT = Path(__file__).parents[3]
F42_REVISION = "20260729_04"
F43_REVISION = "20260801_05"
NOW = datetime(2026, 8, 1, 15, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class DatabaseHarness:
    url: str
    config: Config

    def upgrade(self, revision: str = F43_REVISION) -> None:
        command.upgrade(self.config, revision)

    def downgrade(self, revision: str = "base") -> None:
        command.downgrade(self.config, revision)

    def engine(self) -> Engine:
        return sa.create_engine(self.url)


@pytest.fixture()
def database() -> Iterator[DatabaseHarness]:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    harness = DatabaseHarness(require_safe_destructive_database_url(), config)
    harness.downgrade()
    yield harness
    harness.downgrade()


def _names(items: Iterable[Mapping[str, object]]) -> set[str]:
    return {name for item in items if isinstance((name := item.get("name")), str)}


def _seed_workspace(connection: sa.Connection) -> tuple[object, object]:
    workspace_id, user_id = uuid4(), uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO workspace "
            "(id, name, status, retention_policy_version, created_at, updated_at) "
            "VALUES (:id, 'F4.3', 'ACTIVE', '2026-01', :now, :now)"
        ),
        {"id": workspace_id, "now": NOW},
    )
    connection.execute(
        sa.text(
            "INSERT INTO user_account "
            "(id, email, display_name, status, created_at, updated_at) "
            "VALUES (:id, :email, 'Reviewer', 'ACTIVE', :now, :now)"
        ),
        {"id": user_id, "email": f"{user_id}@example.test", "now": NOW},
    )
    return workspace_id, user_id


def test_schema_has_decision_constraints_tenant_fks_and_typed_snapshot(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    engine = database.engine()
    inspector = sa.inspect(engine)
    try:
        assert "entity_resolution_decision" in inspector.get_table_names()
        columns = {
            value["name"]: value for value in inspector.get_columns("entity_resolution_decision")
        }
        assert isinstance(columns["materialization_policy_snapshot"]["type"], postgresql.JSONB)
        assert isinstance(columns["candidate_rank"]["type"], sa.SmallInteger)
        assert _names(inspector.get_foreign_keys("entity_resolution_decision")) == {
            "fk_entity_resolution_decision_workspace",
            "fk_entity_resolution_decision_investigation_scope",
            "fk_entity_resolution_decision_batch_scope",
            "fk_entity_resolution_decision_candidate_scope",
            "fk_entity_resolution_decision_company_scope",
            "fk_entity_resolution_decision_reviewer",
        }
        unique_columns = {
            tuple(value["column_names"])
            for value in inspector.get_unique_constraints("entity_resolution_decision")
        }
        assert ("workspace_id", "investigation_id") in unique_columns
        assert ("workspace_id", "command_id") in unique_columns
        assert ("workspace_id", "company_id") in unique_columns
        transition_fks = _names(inspector.get_foreign_keys("investigation_transition"))
        assert "fk_investigation_transition_confirmation_decision" in transition_fks
    finally:
        engine.dispose()


def test_unknown_company_blocks_downgrade_without_silent_conversion(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    engine = database.engine()
    company_id = uuid4()
    try:
        with engine.begin() as connection:
            workspace_id, _ = _seed_workspace(connection)
            connection.execute(
                sa.text(
                    "INSERT INTO company "
                    "(id, workspace_id, legal_name, country_code, status, created_at, updated_at) "
                    "VALUES (:id, :workspace_id, 'Unknown Entity', 'BR', 'UNKNOWN', :now, :now)"
                ),
                {"id": company_id, "workspace_id": workspace_id, "now": NOW},
            )
        with pytest.raises(RuntimeError, match="Company rows use UNKNOWN status"):
            database.downgrade(F42_REVISION)
        with engine.begin() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT status FROM company WHERE id = :id"),
                    {"id": company_id},
                )
                == "UNKNOWN"
            )
            connection.execute(
                sa.text("DELETE FROM company WHERE id = :id"),
                {"id": company_id},
            )
    finally:
        engine.dispose()
    database.downgrade(F42_REVISION)


def test_compatible_downgrade_and_reupgrade(database: DatabaseHarness) -> None:
    database.upgrade()
    database.downgrade(F42_REVISION)
    engine = database.engine()
    try:
        inspector = sa.inspect(engine)
        assert "entity_resolution_decision" not in inspector.get_table_names()
        assert "UNKNOWN" not in next(
            value["sqltext"]
            for value in inspector.get_check_constraints("company")
            if value["name"] == "ck_company_status_allowed"
        )
    finally:
        engine.dispose()
    database.upgrade()
    engine = database.engine()
    try:
        assert "entity_resolution_decision" in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_new_planning_write_without_company_is_rejected(database: DatabaseHarness) -> None:
    database.upgrade()
    engine = database.engine()
    try:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            workspace_id, user_id = _seed_workspace(connection)
            connection.execute(
                sa.text(
                    "INSERT INTO investigation "
                    "(id, workspace_id, requested_by, profile_code, country_code, state, "
                    "state_version, created_at) VALUES "
                    "(:id, :workspace_id, :user_id, 'SUPPLIER_STANDARD', 'BR', "
                    "'PLANNING', 4, :now)"
                ),
                {
                    "id": uuid4(),
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "now": NOW,
                },
            )
    finally:
        engine.dispose()


def test_alembic_check_reports_metadata_at_f43_head(database: DatabaseHarness) -> None:
    database.upgrade("head")
    command.check(database.config)
