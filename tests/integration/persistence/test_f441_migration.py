"""F4.4.1 audit-cost constraint migration tests on PostgreSQL."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from tests.support.destructive_database import require_safe_destructive_database_url

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])

REPOSITORY_ROOT = Path(__file__).parents[3]
F44_REVISION = "20260801_06"
F441_REVISION = "20260801_07"
NOW = datetime(2026, 8, 2, 12, tzinfo=UTC)
CONSTRAINT_NAME = "ck_audit_event_investigation_planning_cost_consistency"


@dataclass(frozen=True, slots=True)
class DatabaseHarness:
    url: str
    config: Config

    def upgrade(self, revision: str = F441_REVISION) -> None:
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


def _seed_actor(connection: sa.Connection) -> tuple[object, object]:
    workspace_id, user_id = uuid4(), uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO workspace "
            "(id, name, status, retention_policy_version, created_at, updated_at) "
            "VALUES (:id, 'F4.4.1', 'ACTIVE', '2026-01', :now, :now)"
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


def _audit_values(workspace_id: object, user_id: object) -> dict[str, object]:
    return {
        "id": uuid4(),
        "workspace_id": workspace_id,
        "actor_user_id": user_id,
        "action_code": "INVESTIGATION_PLAN_CREATED",
        "resource_type": "INVESTIGATION",
        "resource_id": uuid4(),
        "outcome": "SUCCESS",
        "correlation_id": uuid4(),
        "occurred_at": NOW,
    }


def _planning_values(kind: str) -> dict[str, object]:
    return {
        "planning_command_id": uuid4(),
        "investigation_plan_id": uuid4(),
        "planned_capability_count": 10,
        "planned_connector_option_count": 2,
        "planning_policy_id": "INVESTIGATION_PLANNING_V1",
        "planning_policy_version": 1,
        "planning_maximum_estimated_cost_kind": kind,
    }


def _insert_audit(connection: sa.Connection, values: dict[str, object]) -> None:
    audit_event = sa.Table("audit_event", sa.MetaData(), autoload_with=connection)
    connection.execute(audit_event.insert().values(**values))


def _constraint_sql(engine: Engine) -> str:
    return next(
        value["sqltext"]
        for value in sa.inspect(engine).get_check_constraints("audit_event")
        if value["name"] == CONSTRAINT_NAME
    )


def test_head_rejects_partial_cost_metadata_and_accepts_complete_typed_sets(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    engine = database.engine()
    try:
        with engine.begin() as connection:
            workspace_id, user_id = _seed_actor(connection)
        partial_combinations = (
            {"planning_command_id": uuid4()},
            {"planning_maximum_estimated_cost_kind": "UNKNOWN"},
            {"planning_maximum_estimated_cost_amount": 1},
            {"planning_maximum_estimated_cost_currency": "BRL"},
            {
                "planning_maximum_estimated_cost_amount": 1,
                "planning_maximum_estimated_cost_currency": "BRL",
            },
            _planning_values("KNOWN"),
            _planning_values("KNOWN") | {"planning_maximum_estimated_cost_amount": 1},
            _planning_values("KNOWN") | {"planning_maximum_estimated_cost_currency": "BRL"},
            _planning_values("UNKNOWN")
            | {
                "planning_maximum_estimated_cost_amount": 1,
                "planning_maximum_estimated_cost_currency": "BRL",
            },
        )
        for partial in partial_combinations:
            with pytest.raises(IntegrityError), engine.begin() as connection:
                _insert_audit(
                    connection,
                    _audit_values(workspace_id, user_id) | partial,
                )

        with engine.begin() as connection:
            _insert_audit(connection, _audit_values(workspace_id, user_id))
            _insert_audit(
                connection,
                _audit_values(workspace_id, user_id) | _planning_values("UNKNOWN"),
            )
            _insert_audit(
                connection,
                _audit_values(workspace_id, user_id)
                | _planning_values("KNOWN")
                | {
                    "planning_maximum_estimated_cost_amount": 1,
                    "planning_maximum_estimated_cost_currency": "BRL",
                },
            )
    finally:
        engine.dispose()


def test_new_constraint_downgrades_to_f44_and_reupgrades(database: DatabaseHarness) -> None:
    database.upgrade()
    engine = database.engine()
    try:
        assert "planning_command_id IS NULL" in _constraint_sql(engine)
    finally:
        engine.dispose()

    database.downgrade(F44_REVISION)
    engine = database.engine()
    try:
        assert "planning_command_id IS NULL" not in _constraint_sql(engine)
    finally:
        engine.dispose()

    database.upgrade()
    engine = database.engine()
    try:
        assert "planning_command_id IS NULL" in _constraint_sql(engine)
    finally:
        engine.dispose()


def test_alembic_check_reports_metadata_at_f441_head(database: DatabaseHarness) -> None:
    database.upgrade("head")
    command.check(database.config)
