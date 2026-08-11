"""F4.4 migration shape, reversibility, and metadata convergence."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine

from tests.integration.persistence.test_f44_investigation_planning import (
    _command,
    _seed_planning,
    _service,
)
from tests.support.destructive_database import require_safe_destructive_database_url

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])

REPOSITORY_ROOT = Path(__file__).parents[3]
F43_REVISION = "20260801_05"
F44_REVISION = "20260801_06"


@dataclass(frozen=True, slots=True)
class DatabaseHarness:
    url: str
    config: Config

    def upgrade(self, revision: str = F44_REVISION) -> None:
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


def test_schema_has_three_typed_tables_tenant_fks_and_closed_constraints(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    engine = database.engine()
    try:
        inspector = sa.inspect(engine)
        assert {"investigation_plan", "planned_capability", "planned_connector_option"} <= set(
            inspector.get_table_names()
        )
        plan_columns = {
            value["name"]: value for value in inspector.get_columns("investigation_plan")
        }
        capability_columns = {
            value["name"]: value for value in inspector.get_columns("planned_capability")
        }
        option_columns = {
            value["name"]: value for value in inspector.get_columns("planned_connector_option")
        }
        assert isinstance(plan_columns["planning_policy_snapshot"]["type"], sa.Text)
        assert isinstance(capability_columns["dependencies"]["type"], postgresql.ARRAY)
        assert isinstance(option_columns["operations"]["type"], postgresql.ARRAY)
        assert _names(inspector.get_foreign_keys("investigation_plan")) == {
            "fk_investigation_plan_investigation_scope",
            "fk_investigation_plan_company_scope",
            "fk_investigation_plan_created_by",
        }
        assert _names(inspector.get_foreign_keys("planned_capability")) == {
            "fk_planned_capability_plan_scope"
        }
        assert _names(inspector.get_foreign_keys("planned_connector_option")) == {
            "fk_planned_connector_option_capability_scope"
        }
        assert {
            "ck_investigation_plan_budget_finite",
            "ck_investigation_plan_maximum_cost_finite",
        } <= _names(inspector.get_check_constraints("investigation_plan"))
        assert "ck_planned_capability_estimated_cost_finite" in _names(
            inspector.get_check_constraints("planned_capability")
        )
        assert "ck_planned_connector_option_estimated_cost_finite" in _names(
            inspector.get_check_constraints("planned_connector_option")
        )
        unique_columns = {
            tuple(value["column_names"])
            for value in inspector.get_unique_constraints("investigation_plan")
        }
        assert ("workspace_id", "investigation_id") in unique_columns
        assert ("workspace_id", "command_id") in unique_columns
    finally:
        engine.dispose()


def test_empty_downgrade_and_reupgrade_are_reversible(database: DatabaseHarness) -> None:
    database.upgrade()
    database.downgrade(F43_REVISION)
    engine = database.engine()
    try:
        assert "investigation_plan" not in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()
    database.upgrade()


def test_downgrade_refuses_to_erase_an_immutable_plan(database: DatabaseHarness) -> None:
    database.upgrade("head")
    engine = database.engine()
    actor, investigation = _seed_planning(engine, "migration-refusal")
    _service(engine).create_investigation_plan(actor, _command(investigation))
    engine.dispose()

    with pytest.raises(RuntimeError, match="investigation plans exist"):
        database.downgrade(F43_REVISION)

    engine = database.engine()
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("TRUNCATE TABLE investigation_plan CASCADE"))
    finally:
        engine.dispose()
    database.downgrade(F43_REVISION)


def test_alembic_check_reports_metadata_at_f44_head(database: DatabaseHarness) -> None:
    database.upgrade("head")
    command.check(database.config)
