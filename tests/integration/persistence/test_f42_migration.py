"""F4.2 PostgreSQL migration compatibility, integrity, and reversibility."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
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
F41_REVISION = "20260729_03"
F42_REVISION = "20260729_04"
NOW = datetime(2026, 7, 29, 20, tzinfo=UTC)
F42_TABLES = {
    "entity_candidate_batch",
    "entity_candidate",
    "entity_candidate_dimension_score",
}


@dataclass(frozen=True, slots=True)
class DatabaseHarness:
    url: str
    config: Config

    def upgrade(self, revision: str = F42_REVISION) -> None:
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


def _input_snapshot() -> tuple[dict[str, object], str]:
    snapshot: dict[str, object] = {
        "address": None,
        "corporate_domain": None,
        "identifiers": [],
        "legal_name": {
            "normalized_value": "empresa exemplo",
            "original_value": "Empresa Exemplo",
        },
        "original_language": None,
        "schema_version": 1,
        "trade_name": None,
    }
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return snapshot, sha256(canonical.encode()).hexdigest()


def _constraint_names(items: Iterable[Mapping[str, object]]) -> set[str]:
    return {name for item in items if isinstance((name := item.get("name")), str)}


def test_upgrade_preserves_historical_waiting_row_but_rejects_new_row_without_batch(
    database: DatabaseHarness,
) -> None:
    database.upgrade(F41_REVISION)
    engine = database.engine()
    workspace_id, user_id, investigation_id = uuid4(), uuid4(), uuid4()
    snapshot, digest = _input_snapshot()
    try:
        metadata = sa.MetaData()
        workspace = sa.Table("workspace", metadata, autoload_with=engine)
        user = sa.Table("user_account", metadata, autoload_with=engine)
        investigation = sa.Table("investigation", metadata, autoload_with=engine)
        with engine.begin() as connection:
            connection.execute(
                workspace.insert(),
                {
                    "id": workspace_id,
                    "name": "Historical",
                    "status": "ACTIVE",
                    "retention_policy_version": "2026-01",
                    "created_at": NOW,
                    "updated_at": NOW,
                },
            )
            connection.execute(
                user.insert(),
                {
                    "id": user_id,
                    "email": f"{user_id}@example.test",
                    "display_name": "Historical Actor",
                    "status": "ACTIVE",
                    "created_at": NOW,
                    "updated_at": NOW,
                },
            )
            connection.execute(
                investigation.insert(),
                {
                    "id": investigation_id,
                    "workspace_id": workspace_id,
                    "requested_by": user_id,
                    "profile_code": "SUPPLIER_STANDARD",
                    "country_code": "BR",
                    "state": "WAITING_FOR_ENTITY_CONFIRMATION",
                    "state_version": 3,
                    "input_snapshot": snapshot,
                    "input_schema_version": 1,
                    "input_digest": digest,
                    "confirmed_company_id": None,
                    "budget_amount": None,
                    "budget_currency": None,
                    "deadline_at": None,
                    "started_at": NOW,
                    "completed_at": None,
                    "created_at": NOW,
                },
            )
    finally:
        engine.dispose()

    database.upgrade()
    engine = database.engine()
    try:
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT count(*) FROM investigation WHERE id = :id"),
                    {"id": investigation_id},
                )
                == 1
            )
        investigation = sa.Table("investigation", sa.MetaData(), autoload_with=engine)
        invalid = {
            "id": uuid4(),
            "workspace_id": workspace_id,
            "requested_by": user_id,
            "profile_code": "SUPPLIER_STANDARD",
            "country_code": "BR",
            "state": "WAITING_FOR_ENTITY_CONFIRMATION",
            "state_version": 3,
            "input_snapshot": snapshot,
            "input_schema_version": 1,
            "input_digest": digest,
            "confirmed_company_id": None,
            "budget_amount": None,
            "budget_currency": None,
            "deadline_at": None,
            "started_at": NOW,
            "completed_at": None,
            "created_at": NOW,
            "active_candidate_batch_id": None,
        }
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(investigation.insert(), invalid)
    finally:
        engine.dispose()


def test_schema_has_tenant_scoped_tables_constraints_and_typed_columns(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    engine = database.engine()
    inspector = sa.inspect(engine)
    try:
        assert set(inspector.get_table_names()) >= F42_TABLES
        batch_columns = {
            value["name"]: value for value in inspector.get_columns("entity_candidate_batch")
        }
        candidate_columns = {
            value["name"]: value for value in inspector.get_columns("entity_candidate")
        }
        dimension_columns = {
            value["name"]: value
            for value in inspector.get_columns("entity_candidate_dimension_score")
        }
        assert isinstance(batch_columns["policy_snapshot"]["type"], postgresql.JSONB)
        assert isinstance(candidate_columns["identity_snapshot"]["type"], postgresql.JSONB)
        assert isinstance(candidate_columns["origin_snapshot"]["type"], postgresql.JSONB)
        assert isinstance(dimension_columns["score"]["type"], sa.SmallInteger)
        assert _constraint_names(inspector.get_foreign_keys("entity_candidate_batch")) == {
            "fk_entity_candidate_batch_created_by",
            "fk_entity_candidate_batch_investigation_scope",
        }
        assert _constraint_names(inspector.get_foreign_keys("entity_candidate")) == {
            "fk_entity_candidate_batch_scope"
        }
        assert _constraint_names(
            inspector.get_foreign_keys("entity_candidate_dimension_score")
        ) == {"fk_entity_candidate_dimension_candidate_scope"}
        assert "fk_investigation_active_candidate_batch_scope" in _constraint_names(
            inspector.get_foreign_keys("investigation")
        )
        batch_unique = {
            tuple(value["column_names"])
            for value in inspector.get_unique_constraints("entity_candidate_batch")
        }
        assert ("workspace_id", "investigation_id") in batch_unique
        assert ("workspace_id", "command_id") in batch_unique
        candidate_unique = {
            tuple(value["column_names"])
            for value in inspector.get_unique_constraints("entity_candidate")
        }
        assert ("batch_id", "candidate_key") in candidate_unique
        assert ("batch_id", "rank") in candidate_unique
    finally:
        engine.dispose()


def test_downgrade_and_reupgrade_remove_only_f42_artifacts(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    database.downgrade(F41_REVISION)
    engine = database.engine()
    try:
        inspector = sa.inspect(engine)
        assert F42_TABLES.isdisjoint(inspector.get_table_names())
        assert "active_candidate_batch_id" not in {
            value["name"] for value in inspector.get_columns("investigation")
        }
        assert "candidate_batch_id" not in {
            value["name"] for value in inspector.get_columns("investigation_transition")
        }
    finally:
        engine.dispose()

    database.upgrade()
    engine = database.engine()
    try:
        assert set(sa.inspect(engine).get_table_names()) >= F42_TABLES
    finally:
        engine.dispose()


def test_alembic_check_reports_metadata_at_f42_head(database: DatabaseHarness) -> None:
    database.upgrade("head")
    command.check(database.config)
