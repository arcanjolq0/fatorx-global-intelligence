"""F4.5/F4.5.1 migration shape, reversibility, refusal, and metadata convergence."""

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

from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.collection_activation import StartInvestigationCollection
from intelligence.application.services.collection_activation import CollectionActivationService
from intelligence.domain.identifiers import InvestigationCommandId
from intelligence.infrastructure.persistence.postgresql.unit_of_work import (
    PostgreSQLUnitOfWorkFactory,
)
from intelligence.orchestration.collection_activation import COLLECTION_ACTIVATION_V1
from tests.integration.persistence.test_f44_investigation_planning import (
    NOW,
    _seed_planning,
)
from tests.integration.persistence.test_f44_investigation_planning import (
    _command as planning_command,
)
from tests.integration.persistence.test_f44_investigation_planning import (
    _service as planning_service,
)
from tests.support.destructive_database import require_safe_destructive_database_url
from tests.unit.application.fakes import FakeClock

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])
REPOSITORY_ROOT = Path(__file__).parents[3]
F441_REVISION = "20260801_07"
F45_REVISION = "20260802_09"


@dataclass(frozen=True, slots=True)
class DatabaseHarness:
    url: str
    config: Config

    def upgrade(self, revision: str = F45_REVISION) -> None:
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


def test_schema_has_manifest_tables_scoped_fks_arrays_and_closed_checks(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    engine = database.engine()
    try:
        inspector = sa.inspect(engine)
        assert {
            "collection_run",
            "collection_operation",
            "collection_operation_dependency",
        } <= set(inspector.get_table_names())
        operation_columns = {
            item["name"]: item for item in inspector.get_columns("collection_operation")
        }
        assert isinstance(operation_columns["connector_operations"]["type"], postgresql.ARRAY)
        assert {
            "fk_collection_operation_run_scope",
            "fk_collection_operation_capability_scope",
            "fk_collection_operation_option_scope",
        } == _names(inspector.get_foreign_keys("collection_operation"))
        assert {
            "ck_collection_run_digests_format",
            "ck_collection_run_status_allowed",
            "ck_collection_run_maximum_cost_valid",
        } <= _names(inspector.get_check_constraints("collection_run"))
        assert {
            "ck_collection_operation_initial_state_valid",
            "ck_collection_operation_digest_format",
        } <= _names(inspector.get_check_constraints("collection_operation"))
        transition_columns = {
            item["name"] for item in inspector.get_columns("investigation_transition")
        }
        assert {"collection_company_id", "collection_plan_id"} <= transition_columns
        assert "fk_investigation_transition_collection_run_scope" in _names(
            inspector.get_foreign_keys("investigation_transition")
        )
    finally:
        engine.dispose()


def test_empty_downgrade_and_reupgrade_are_reversible(database: DatabaseHarness) -> None:
    database.upgrade()
    database.downgrade(F441_REVISION)
    engine = database.engine()
    try:
        assert "collection_run" not in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()
    database.upgrade()


def test_downgrade_refuses_to_erase_immutable_collection_history(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    engine = database.engine()
    actor, investigation = _seed_planning(engine, "f4.5-migration-refusal")
    plan = (
        planning_service(engine)
        .create_investigation_plan(actor, planning_command(investigation))
        .plan
    )
    CollectionActivationService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).start_investigation_collection(
        actor,
        StartInvestigationCollection(
            command_id=InvestigationCommandId.new(),
            investigation_id=investigation.id,
            plan_id=plan.id,
            expected_state_version=investigation.state_version,
            activation_policy=COLLECTION_ACTIVATION_V1,
        ),
    )
    engine.dispose()
    with pytest.raises(RuntimeError, match="collection runs exist"):
        database.downgrade(F441_REVISION)
    engine = database.engine()
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("TRUNCATE TABLE collection_run, investigation_plan CASCADE"))
    finally:
        engine.dispose()
    database.downgrade(F441_REVISION)


def test_alembic_check_reports_metadata_at_f45_head(database: DatabaseHarness) -> None:
    database.upgrade("head")
    command.check(database.config)
