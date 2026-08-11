"""F2.4.1 migration tests against an explicitly approved real PostgreSQL database."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from intelligence.infrastructure.persistence.postgresql.tables import (
    audit_event_table,
    user_account_table,
    workspace_membership_table,
    workspace_table,
)
from tests.support.destructive_database import require_safe_destructive_database_url

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])

REPOSITORY_ROOT = Path(__file__).parents[3]
PREVIOUS_REVISION = "20260728_01"
F241_REVISION = "20260728_02"
CORE_TABLES = {"workspace", "company", "investigation"}
F241_TABLES = {"user_account", "workspace_membership", "audit_event"}
MANAGED_TABLES = CORE_TABLES | F241_TABLES
CREATED_AT = datetime(2026, 7, 28, 12, 0, 0, 123456, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class DatabaseHarness:
    """Alembic commands and engines for one explicitly safe test database."""

    url: str
    config: Config

    def upgrade(self, revision: str = F241_REVISION) -> None:
        command.upgrade(self.config, revision)

    def downgrade(self, revision: str = "base") -> None:
        command.downgrade(self.config, revision)

    def engine(self) -> Engine:
        return sa.create_engine(self.url)


def _alembic_config() -> Config:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    return config


@pytest.fixture()
def database() -> Iterator[DatabaseHarness]:
    harness = DatabaseHarness(
        url=require_safe_destructive_database_url(),
        config=_alembic_config(),
    )
    harness.downgrade()
    yield harness
    harness.downgrade()


def _table_names(engine: Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def _workspace_values(workspace_id: UUID) -> dict[str, object]:
    return {
        "id": workspace_id,
        "name": "Workspace F2.4.1",
        "status": "ACTIVE",
        "retention_policy_version": "2026-01",
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }


def _user_values(
    user_id: UUID,
    *,
    email: str = "analyst@example.test",
    status: str = "ACTIVE",
) -> dict[str, object]:
    return {
        "id": user_id,
        "email": email,
        "display_name": "Analista F2.4.1",
        "status": status,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }


def _membership_values(
    membership_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    *,
    role: str = "ANALYST",
    status: str = "ACTIVE",
    deactivated_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "id": membership_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "role": role,
        "status": status,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
        "deactivated_at": deactivated_at,
    }


def _audit_values(
    event_id: UUID,
    workspace_id: UUID,
    user_id: UUID,
    *,
    outcome: str = "SUCCESS",
) -> dict[str, object]:
    return {
        "id": event_id,
        "workspace_id": workspace_id,
        "actor_user_id": user_id,
        "action_code": "MEMBERSHIP.READ",
        "resource_type": "MEMBERSHIP",
        "resource_id": None,
        "outcome": outcome,
        "reason_code": None,
        "correlation_id": uuid4(),
        "occurred_at": CREATED_AT,
    }


def _insert_identity_prerequisites(engine: Engine) -> tuple[UUID, UUID]:
    workspace_id = uuid4()
    user_id = uuid4()
    with engine.begin() as connection:
        connection.execute(workspace_table.insert(), _workspace_values(workspace_id))
        connection.execute(user_account_table.insert(), _user_values(user_id))
    return workspace_id, user_id


def _assert_rejected(engine: Engine, statement: sa.Executable) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(statement)


def _constraint_names(
    constraints: Iterable[Mapping[str, object]],
) -> set[str]:
    return {name for constraint in constraints if isinstance((name := constraint.get("name")), str)}


def _column_names_by_index(
    indexes: Iterable[Mapping[str, object]],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for index in indexes:
        if index.get("duplicates_constraint") is not None:
            continue
        name = index.get("name")
        columns = index.get("column_names")
        if (
            isinstance(name, str)
            and isinstance(columns, list)
            and all(isinstance(column, str) for column in columns)
        ):
            result[name] = columns
    return result


def test_empty_database_upgrades_to_head_with_only_approved_tables(
    database: DatabaseHarness,
) -> None:
    engine = database.engine()
    try:
        assert MANAGED_TABLES.isdisjoint(_table_names(engine))
    finally:
        engine.dispose()

    database.upgrade()
    engine = database.engine()
    try:
        assert _table_names(engine) == MANAGED_TABLES | {"alembic_version"}
    finally:
        engine.dispose()


def test_upgrade_from_previous_revision_preserves_orphan_requested_by_without_fk(
    database: DatabaseHarness,
) -> None:
    database.upgrade(PREVIOUS_REVISION)
    engine = database.engine()
    workspace_id = uuid4()
    investigation_id = uuid4()
    orphan_requested_by = uuid4()
    try:
        reflected = sa.MetaData()
        workspace = sa.Table("workspace", reflected, autoload_with=engine)
        investigation = sa.Table("investigation", reflected, autoload_with=engine)
        with engine.begin() as connection:
            connection.execute(workspace.insert(), _workspace_values(workspace_id))
            connection.execute(
                investigation.insert(),
                {
                    "id": investigation_id,
                    "workspace_id": workspace_id,
                    "requested_by": orphan_requested_by,
                    "profile_code": "SUPPLIER_STANDARD",
                    "country_code": "BR",
                    "state": "CREATED",
                    "state_version": 1,
                    "confirmed_company_id": None,
                    "budget_amount": None,
                    "budget_currency": None,
                    "deadline_at": None,
                    "started_at": None,
                    "completed_at": None,
                    "created_at": CREATED_AT,
                },
            )
    finally:
        engine.dispose()

    database.upgrade()
    engine = database.engine()
    try:
        inspector = sa.inspect(engine)
        with engine.connect() as connection:
            persisted_requested_by = connection.execute(
                sa.text("SELECT requested_by FROM investigation WHERE id = :id"),
                {"id": investigation_id},
            ).scalar_one()
            user_count = connection.execute(
                sa.text("SELECT count(*) FROM user_account")
            ).scalar_one()
        assert persisted_requested_by == orphan_requested_by
        assert user_count == 0
        assert "requested_by" not in {
            column
            for foreign_key in inspector.get_foreign_keys("investigation")
            for column in foreign_key["constrained_columns"]
        }
        assert _table_names(engine) >= F241_TABLES
    finally:
        engine.dispose()


def test_f241_columns_use_required_types_and_nullability(database: DatabaseHarness) -> None:
    database.upgrade()
    engine = database.engine()
    inspector = sa.inspect(engine)
    try:
        users = {column["name"]: column for column in inspector.get_columns("user_account")}
        memberships = {
            column["name"]: column for column in inspector.get_columns("workspace_membership")
        }
        events = {column["name"]: column for column in inspector.get_columns("audit_event")}

        for columns, uuid_names in (
            (users, {"id"}),
            (memberships, {"id", "workspace_id", "user_id"}),
            (
                events,
                {"id", "workspace_id", "actor_user_id", "resource_id", "correlation_id"},
            ),
        ):
            for column_name in uuid_names:
                assert isinstance(columns[column_name]["type"], postgresql.UUID)
        assert isinstance(users["email"]["type"], sa.String)
        assert users["email"]["type"].length == 254
        for columns, timestamp_names in (
            (users, {"created_at", "updated_at"}),
            (memberships, {"created_at", "updated_at", "deactivated_at"}),
            (events, {"occurred_at"}),
        ):
            for column_name in timestamp_names:
                column_type = columns[column_name]["type"]
                assert isinstance(column_type, sa.DateTime)
                assert column_type.timezone is True
        assert memberships["deactivated_at"]["nullable"] is True
        assert events["resource_id"]["nullable"] is True
        assert events["reason_code"]["nullable"] is True
    finally:
        engine.dispose()


def test_primary_foreign_unique_constraints_and_indexes_are_exact(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    engine = database.engine()
    inspector = sa.inspect(engine)
    try:
        for table_name in F241_TABLES:
            primary_key = inspector.get_pk_constraint(table_name)
            assert primary_key["name"] == f"pk_{table_name}"
            assert primary_key["constrained_columns"] == ["id"]

        membership_foreign_keys = inspector.get_foreign_keys("workspace_membership")
        audit_foreign_keys = inspector.get_foreign_keys("audit_event")
        assert _constraint_names(membership_foreign_keys) == {
            "fk_workspace_membership_workspace",
            "fk_workspace_membership_user_account",
        }
        assert _constraint_names(audit_foreign_keys) == {
            "fk_audit_event_workspace",
            "fk_audit_event_actor_user_account",
        }
        for foreign_key in membership_foreign_keys + audit_foreign_keys:
            assert foreign_key["options"].get("ondelete") == "RESTRICT"

        user_uniques = inspector.get_unique_constraints("user_account")
        membership_uniques = inspector.get_unique_constraints("workspace_membership")
        assert {
            tuple(constraint["column_names"]): constraint["name"] for constraint in user_uniques
        } == {("email",): "uq_user_account_email"}
        assert {
            tuple(constraint["column_names"]): constraint["name"]
            for constraint in membership_uniques
        } == {("workspace_id", "user_id"): "uq_workspace_membership_workspace_id_user_id"}

        assert _column_names_by_index(inspector.get_indexes("workspace_membership")) == {
            "ix_workspace_membership_user_id_workspace_id": ["user_id", "workspace_id"],
            "ix_workspace_membership_workspace_id_status": ["workspace_id", "status"],
        }
        assert _column_names_by_index(inspector.get_indexes("audit_event")) == {
            "ix_audit_event_correlation_id": ["correlation_id"],
            "ix_audit_event_workspace_id_occurred_at": ["workspace_id", "occurred_at"],
        }
    finally:
        engine.dispose()


def test_duplicate_email_is_rejected(database: DatabaseHarness) -> None:
    database.upgrade()
    engine = database.engine()
    try:
        with engine.begin() as connection:
            connection.execute(user_account_table.insert(), _user_values(uuid4()))
        _assert_rejected(
            engine,
            user_account_table.insert().values(**_user_values(uuid4())),
        )
    finally:
        engine.dispose()


def test_duplicate_membership_is_rejected(database: DatabaseHarness) -> None:
    database.upgrade()
    engine = database.engine()
    try:
        workspace_id, user_id = _insert_identity_prerequisites(engine)
        with engine.begin() as connection:
            connection.execute(
                workspace_membership_table.insert(),
                _membership_values(uuid4(), workspace_id, user_id),
            )
        _assert_rejected(
            engine,
            workspace_membership_table.insert().values(
                **_membership_values(uuid4(), workspace_id, user_id, role="VIEWER")
            ),
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("overrides",),
    [
        ({"role": "SUPERUSER"},),
        ({"status": "UNKNOWN"},),
        ({"status": "ACTIVE", "deactivated_at": CREATED_AT + timedelta(minutes=1)},),
        ({"status": "INACTIVE", "deactivated_at": None},),
    ],
    ids=["invalid-role", "invalid-status", "active-deactivated", "inactive-active-shape"],
)
def test_membership_constraints_reject_invalid_snapshots(
    database: DatabaseHarness,
    overrides: Mapping[str, object],
) -> None:
    database.upgrade()
    engine = database.engine()
    try:
        workspace_id, user_id = _insert_identity_prerequisites(engine)
        values = _membership_values(uuid4(), workspace_id, user_id)
        values.update(overrides)
        _assert_rejected(
            engine,
            workspace_membership_table.insert().values(**values),
        )
    finally:
        engine.dispose()


def test_audit_invalid_outcome_is_rejected(database: DatabaseHarness) -> None:
    database.upgrade()
    engine = database.engine()
    try:
        workspace_id, user_id = _insert_identity_prerequisites(engine)
        _assert_rejected(
            engine,
            audit_event_table.insert().values(
                **_audit_values(uuid4(), workspace_id, user_id, outcome="UNKNOWN")
            ),
        )
    finally:
        engine.dispose()


def test_downgrade_one_revision_preserves_core_and_removes_only_f241(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    engine = database.engine()
    workspace_id = uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(workspace_table.insert(), _workspace_values(workspace_id))
    finally:
        engine.dispose()

    database.downgrade("-1")
    engine = database.engine()
    try:
        assert _table_names(engine) == CORE_TABLES | {"alembic_version"}
        with engine.connect() as connection:
            assert (
                connection.execute(
                    sa.text("SELECT count(*) FROM workspace WHERE id = :id"),
                    {"id": workspace_id},
                ).scalar_one()
                == 1
            )
    finally:
        engine.dispose()


def test_reupgrade_after_one_revision_downgrade_recreates_f241(
    database: DatabaseHarness,
) -> None:
    database.upgrade()
    database.downgrade("-1")
    database.upgrade()
    engine = database.engine()
    try:
        assert _table_names(engine) == MANAGED_TABLES | {"alembic_version"}
    finally:
        engine.dispose()


def test_alembic_check_reports_metadata_at_head(database: DatabaseHarness) -> None:
    database.upgrade("head")

    command.check(database.config)
