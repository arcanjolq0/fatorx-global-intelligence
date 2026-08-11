"""F4.1 migration compatibility, integrity, and reversibility on PostgreSQL."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

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
PREVIOUS_REVISION = "20260728_02"
F41_REVISION = "20260729_03"
OCCURRED_AT = datetime(2026, 7, 29, 18, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class DatabaseHarness:
    url: str
    config: Config

    def upgrade(self, revision: str = F41_REVISION) -> None:
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


def _workspace(workspace_id: UUID, name: str = "Workspace F4.1") -> dict[str, object]:
    return {
        "id": workspace_id,
        "name": name,
        "status": "ACTIVE",
        "retention_policy_version": "2026-01",
        "created_at": OCCURRED_AT,
        "updated_at": OCCURRED_AT,
    }


def _user(user_id: UUID) -> dict[str, object]:
    return {
        "id": user_id,
        "email": f"{user_id}@example.test",
        "display_name": "Actor F4.1",
        "status": "ACTIVE",
        "created_at": OCCURRED_AT,
        "updated_at": OCCURRED_AT,
    }


def _investigation(
    investigation_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    *,
    state: str = "CREATED",
    version: int = 1,
) -> dict[str, object]:
    return {
        "id": investigation_id,
        "workspace_id": workspace_id,
        "requested_by": user_id,
        "profile_code": "SUPPLIER_STANDARD",
        "country_code": "BR",
        "state": state,
        "state_version": version,
        "confirmed_company_id": None,
        "budget_amount": None,
        "budget_currency": None,
        "deadline_at": None,
        "started_at": OCCURRED_AT if state != "CREATED" else None,
        "completed_at": None,
        "created_at": OCCURRED_AT,
    }


def _input_snapshot() -> tuple[dict[str, object], str]:
    value: dict[str, object] = {
        "address": None,
        "corporate_domain": None,
        "identifiers": [],
        "legal_name": {
            "normalized_value": "empresa exemplo s.a.",
            "original_value": "Empresa Exemplo S.A.",
        },
        "original_language": None,
        "schema_version": 1,
        "trade_name": None,
    }
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return value, sha256(canonical.encode()).hexdigest()


def _constraint_names(items: Iterable[Mapping[str, object]]) -> set[str]:
    return {name for item in items if isinstance((name := item.get("name")), str)}


def test_upgrade_preserves_legacy_rows_and_enforces_new_writes(
    database: DatabaseHarness,
) -> None:
    database.upgrade(PREVIOUS_REVISION)
    engine = database.engine()
    workspace_id, user_id = uuid4(), uuid4()
    created_id, historical_started_id = uuid4(), uuid4()
    try:
        metadata = sa.MetaData()
        workspace = sa.Table("workspace", metadata, autoload_with=engine)
        user = sa.Table("user_account", metadata, autoload_with=engine)
        investigation = sa.Table("investigation", metadata, autoload_with=engine)
        with engine.begin() as connection:
            connection.execute(workspace.insert(), _workspace(workspace_id))
            connection.execute(user.insert(), _user(user_id))
            connection.execute(
                investigation.insert(),
                [
                    _investigation(created_id, workspace_id, user_id),
                    _investigation(
                        historical_started_id,
                        workspace_id,
                        user_id,
                        state="IDENTIFYING",
                        version=2,
                    ),
                ],
            )
    finally:
        engine.dispose()

    database.upgrade()
    engine = database.engine()
    try:
        with engine.connect() as connection:
            rows = list(
                connection.execute(
                    sa.text(
                        "SELECT id, input_snapshot FROM investigation "
                        "WHERE workspace_id = :workspace_id ORDER BY id"
                    ),
                    {"workspace_id": workspace_id},
                )
            )
        assert {row.id for row in rows} == {created_id, historical_started_id}
        assert all(row.input_snapshot is None for row in rows)

        reflected = sa.MetaData()
        investigation = sa.Table("investigation", reflected, autoload_with=engine)
        invalid = _investigation(uuid4(), workspace_id, user_id, state="IDENTIFYING", version=2)
        invalid.update({"input_snapshot": None, "input_schema_version": None, "input_digest": None})
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(investigation.insert(), invalid)
    finally:
        engine.dispose()


def test_schema_has_typed_snapshot_ledger_constraints_and_indexes(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    engine = database.engine()
    inspector = sa.inspect(engine)
    try:
        columns = {item["name"]: item for item in inspector.get_columns("investigation_transition")}
        investigation_columns = {
            item["name"]: item for item in inspector.get_columns("investigation")
        }
        assert isinstance(investigation_columns["input_snapshot"]["type"], postgresql.JSONB)
        assert isinstance(investigation_columns["input_schema_version"]["type"], sa.SmallInteger)
        assert isinstance(columns["occurred_at"]["type"], sa.DateTime)
        assert columns["occurred_at"]["type"].timezone is True
        for name in {
            "id",
            "workspace_id",
            "investigation_id",
            "command_id",
            "actor_user_id",
            "correlation_id",
        }:
            assert isinstance(columns[name]["type"], postgresql.UUID)

        assert _constraint_names(inspector.get_foreign_keys("investigation_transition")) == {
            "fk_investigation_transition_actor_user_account",
            "fk_investigation_transition_investigation_workspace",
            "fk_investigation_transition_workspace",
        }
        assert {
            tuple(item["column_names"]): item["name"]
            for item in inspector.get_unique_constraints("investigation_transition")
        } == {
            ("workspace_id", "command_id"): ("uq_investigation_transition_workspace_id_command_id")
        }
        indexes = {
            item["name"]: item["column_names"]
            for item in inspector.get_indexes("investigation_transition")
            if item.get("duplicates_constraint") is None
        }
        assert indexes == {
            "ix_investigation_transition_workspace_investigation_version": [
                "workspace_id",
                "investigation_id",
                "version_after",
            ],
            "ix_investigation_transition_workspace_occurred_at": [
                "workspace_id",
                "occurred_at",
            ],
        }
    finally:
        engine.dispose()


def test_ledger_rejects_duplicate_command_invalid_shape_and_cross_tenant_fk(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    engine = database.engine()
    workspace_id, other_workspace_id, user_id = uuid4(), uuid4(), uuid4()
    investigation_id, command_id = uuid4(), uuid4()
    snapshot, digest = _input_snapshot()
    metadata = sa.MetaData()
    workspace = sa.Table("workspace", metadata, autoload_with=engine)
    user = sa.Table("user_account", metadata, autoload_with=engine)
    investigation = sa.Table("investigation", metadata, autoload_with=engine)
    transition = sa.Table("investigation_transition", metadata, autoload_with=engine)
    record = {
        "id": uuid4(),
        "workspace_id": workspace_id,
        "investigation_id": investigation_id,
        "command_id": command_id,
        "command_type": "START_IDENTIFICATION",
        "state_before": "CREATED",
        "version_before": 1,
        "state_after": "IDENTIFYING",
        "version_after": 2,
        "actor_user_id": user_id,
        "reason_code": None,
        "occurred_at": OCCURRED_AT,
        "command_digest": digest,
        "correlation_id": uuid4(),
    }
    try:
        values = _investigation(
            investigation_id,
            workspace_id,
            user_id,
            state="IDENTIFYING",
            version=2,
        )
        values.update(
            {
                "input_snapshot": snapshot,
                "input_schema_version": 1,
                "input_digest": digest,
            }
        )
        with engine.begin() as connection:
            connection.execute(
                workspace.insert(),
                [_workspace(workspace_id), _workspace(other_workspace_id, "Other")],
            )
            connection.execute(user.insert(), _user(user_id))
            connection.execute(investigation.insert(), values)
            connection.execute(transition.insert(), record)

        duplicate = {**record, "id": uuid4()}
        invalid_shape = {
            **record,
            "id": uuid4(),
            "command_id": uuid4(),
            "version_after": 3,
        }
        cross_tenant = {
            **record,
            "id": uuid4(),
            "workspace_id": other_workspace_id,
            "command_id": uuid4(),
        }
        for invalid in (duplicate, invalid_shape, cross_tenant):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(transition.insert(), invalid)
    finally:
        engine.dispose()


def test_downgrade_and_reupgrade_preserve_investigation_without_f41_artifacts(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    engine = database.engine()
    workspace_id, user_id, investigation_id = uuid4(), uuid4(), uuid4()
    try:
        metadata = sa.MetaData()
        workspace = sa.Table("workspace", metadata, autoload_with=engine)
        user = sa.Table("user_account", metadata, autoload_with=engine)
        investigation = sa.Table("investigation", metadata, autoload_with=engine)
        with engine.begin() as connection:
            connection.execute(workspace.insert(), _workspace(workspace_id))
            connection.execute(user.insert(), _user(user_id))
            connection.execute(
                investigation.insert(),
                _investigation(investigation_id, workspace_id, user_id),
            )
    finally:
        engine.dispose()

    database.downgrade("-1")
    engine = database.engine()
    try:
        inspector = sa.inspect(engine)
        assert "investigation_transition" not in inspector.get_table_names()
        assert "input_snapshot" not in {
            item["name"] for item in inspector.get_columns("investigation")
        }
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT count(*) FROM investigation WHERE id = :id"),
                    {"id": investigation_id},
                )
                == 1
            )
    finally:
        engine.dispose()

    database.upgrade()
    engine = database.engine()
    try:
        assert "investigation_transition" in sa.inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT count(*) FROM investigation WHERE id = :id"),
                    {"id": investigation_id},
                )
                == 1
            )
    finally:
        engine.dispose()


def test_alembic_check_reports_metadata_at_head(database: DatabaseHarness) -> None:
    database.upgrade("head")
    command.check(database.config)
