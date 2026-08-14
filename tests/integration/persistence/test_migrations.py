"""Integration tests for the initial schema against a real PostgreSQL server."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
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

from intelligence.infrastructure.persistence.postgresql.configuration import (
    DatabaseConfigurationError,
    require_database_url,
)
from intelligence.infrastructure.persistence.postgresql.tables import (
    company_table,
    investigation_table,
    workspace_table,
)
from tests.support.destructive_database import require_safe_destructive_database_url

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])

REPOSITORY_ROOT = Path(__file__).parents[3]
DOMAIN_TABLES = {
    "workspace",
    "company",
    "investigation",
    "user_account",
    "workspace_membership",
    "audit_event",
    "investigation_transition",
    "entity_candidate_batch",
    "entity_candidate",
    "entity_candidate_dimension_score",
    "entity_resolution_decision",
    "investigation_plan",
    "planned_capability",
    "planned_connector_option",
    "collection_run",
    "collection_operation",
    "collection_operation_dependency",
    "collection_operation_execution",
    "collection_operation_execution_result",
}
CREATED_AT = datetime(2026, 7, 28, 12, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class DatabaseHarness:
    """Alembic commands and engines for one explicitly safe test database."""

    url: str
    config: Config

    def upgrade(self) -> None:
        command.upgrade(self.config, "head")

    def downgrade(self) -> None:
        command.downgrade(self.config, "base")

    def engine(self) -> Engine:
        return sa.create_engine(self.url)


def _safe_test_database_url() -> str:
    return require_safe_destructive_database_url()


def _alembic_config() -> Config:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    return config


@pytest.fixture()
def database() -> Iterator[DatabaseHarness]:
    """Reset all managed objects before and after each migration scenario."""

    harness = DatabaseHarness(url=_safe_test_database_url(), config=_alembic_config())
    harness.downgrade()
    yield harness
    harness.downgrade()


def _upgrade_engine(database: DatabaseHarness) -> Engine:
    database.upgrade()
    return database.engine()


def _workspace_values(workspace_id: UUID, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "id": workspace_id,
        "name": "Workspace de teste",
        "status": "ACTIVE",
        "retention_policy_version": "2026-01",
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return values


def _company_values(
    company_id: UUID,
    workspace_id: UUID,
    **overrides: object,
) -> dict[str, object]:
    values: dict[str, object] = {
        "id": company_id,
        "workspace_id": workspace_id,
        "legal_name": "Empresa de teste Ltda.",
        "trade_name": None,
        "country_code": "BR",
        "legal_form": None,
        "status": "ACTIVE",
        "incorporated_on": date(2020, 1, 1),
        "dissolved_on": None,
        "official_domain": "example.test",
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return values


def _investigation_values(
    investigation_id: UUID,
    workspace_id: UUID,
    **overrides: object,
) -> dict[str, object]:
    values: dict[str, object] = {
        "id": investigation_id,
        "workspace_id": workspace_id,
        "requested_by": uuid4(),
        "profile_code": "SUPPLIER_STANDARD",
        "country_code": "BR",
        "state": "CREATED",
        "state_version": 1,
        "input_snapshot": None,
        "input_schema_version": None,
        "input_digest": None,
        "confirmed_company_id": None,
        "budget_amount": None,
        "budget_currency": None,
        "deadline_at": None,
        "started_at": None,
        "completed_at": None,
        "created_at": CREATED_AT,
    }
    values.update(overrides)
    if (
        values["state"]
        not in {
            "CREATED",
            "CANCELLED",
            "UNKNOWN",
        }
        and values["confirmed_company_id"] is None
        and values["input_snapshot"] is None
    ):
        snapshot: dict[str, object] = {
            "address": None,
            "corporate_domain": None,
            "identifiers": [],
            "legal_name": {
                "normalized_value": "empresa de teste",
                "original_value": "Empresa de teste",
            },
            "original_language": "pt-BR",
            "schema_version": 1,
            "trade_name": None,
        }
        canonical = json.dumps(
            snapshot,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        values["input_snapshot"] = snapshot
        values["input_schema_version"] = 1
        values["input_digest"] = sha256(canonical.encode("utf-8")).hexdigest()
    return values


def _insert_prerequisites(
    engine: Engine,
    *,
    workspace_id: UUID,
    company_id: UUID | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(workspace_table.insert(), _workspace_values(workspace_id))
        if company_id is not None:
            connection.execute(
                company_table.insert(),
                _company_values(company_id, workspace_id),
            )


def _assert_rejected(engine: Engine, statement: sa.Executable) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(statement)


def test_database_configuration_is_required_and_redacted() -> None:
    with pytest.raises(DatabaseConfigurationError):
        require_database_url({})

    sensitive_value = "must-not-appear"
    with pytest.raises(DatabaseConfigurationError) as captured:
        require_database_url(
            {"DATABASE_URL": f"sqlite://user:{sensitive_value}@localhost/fatorx_test"}
        )

    assert sensitive_value not in str(captured.value)


def test_empty_database_upgrades_to_head_and_reupgrade_is_safe(
    database: DatabaseHarness,
) -> None:
    engine = database.engine()
    try:
        assert DOMAIN_TABLES.isdisjoint(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    database.upgrade()
    database.upgrade()
    engine = database.engine()
    try:
        assert set(sa.inspect(engine).get_table_names()) >= DOMAIN_TABLES
    finally:
        engine.dispose()


def test_schema_creates_only_approved_domain_tables(database: DatabaseHarness) -> None:
    engine = _upgrade_engine(database)
    try:
        assert set(sa.inspect(engine).get_table_names()) == DOMAIN_TABLES | {"alembic_version"}
    finally:
        engine.dispose()


def test_migration_matches_declared_metadata(database: DatabaseHarness) -> None:
    database.upgrade()

    command.check(database.config)


def test_columns_use_native_uuid_numeric_and_timezone_types(
    database: DatabaseHarness,
) -> None:
    engine = _upgrade_engine(database)
    inspector = sa.inspect(engine)
    try:
        workspace_columns = {
            column["name"]: column for column in inspector.get_columns("workspace")
        }
        investigation_columns = {
            column["name"]: column for column in inspector.get_columns("investigation")
        }

        assert isinstance(workspace_columns["id"]["type"], postgresql.UUID)
        assert isinstance(investigation_columns["budget_amount"]["type"], sa.Numeric)
        assert investigation_columns["budget_amount"]["type"].precision is None
        assert investigation_columns["budget_amount"]["type"].scale is None
        for column_name in ("created_at", "deadline_at", "started_at", "completed_at"):
            timestamp_type = investigation_columns[column_name]["type"]
            assert isinstance(timestamp_type, sa.DateTime)
            assert timestamp_type.timezone is True
    finally:
        engine.dispose()


def test_primary_keys_have_stable_names(database: DatabaseHarness) -> None:
    engine = _upgrade_engine(database)
    inspector = sa.inspect(engine)
    try:
        composite_primary_keys = {
            "entity_candidate_dimension_score": ["candidate_id", "dimension"],
            "collection_operation_dependency": [
                "collection_run_id",
                "operation_id",
                "depends_on_operation_id",
            ],
            "collection_operation_execution": ["command_id"],
            "collection_operation_execution_result": ["command_id"],
        }
        for table_name in DOMAIN_TABLES - composite_primary_keys.keys():
            primary_key = inspector.get_pk_constraint(table_name)
            assert primary_key["name"] == f"pk_{table_name}"
            assert primary_key["constrained_columns"] == ["id"]
        for table_name, columns in composite_primary_keys.items():
            primary_key = inspector.get_pk_constraint(table_name)
            assert primary_key["name"] == f"pk_{table_name}"
            assert primary_key["constrained_columns"] == columns
    finally:
        engine.dispose()


def test_foreign_keys_and_workspace_first_indexes_exist(database: DatabaseHarness) -> None:
    engine = _upgrade_engine(database)
    inspector = sa.inspect(engine)
    try:
        company_foreign_keys = inspector.get_foreign_keys("company")
        investigation_foreign_keys = inspector.get_foreign_keys("investigation")
        investigation_indexes = inspector.get_indexes("investigation")
        company_indexes = inspector.get_indexes("company")

        assert {foreign_key["name"] for foreign_key in company_foreign_keys} == {
            "fk_company_workspace"
        }
        assert {foreign_key["name"] for foreign_key in investigation_foreign_keys} == {
            "fk_investigation_workspace",
            "fk_investigation_confirmed_company_workspace",
            "fk_investigation_active_candidate_batch_scope",
        }
        composite_foreign_key = next(
            foreign_key
            for foreign_key in investigation_foreign_keys
            if foreign_key["name"] == "fk_investigation_confirmed_company_workspace"
        )
        assert composite_foreign_key["constrained_columns"] == [
            "confirmed_company_id",
            "workspace_id",
        ]
        assert composite_foreign_key["referred_columns"] == ["id", "workspace_id"]
        assert (
            next(
                index
                for index in investigation_indexes
                if index["name"] == "ix_investigation_workspace_id_state"
            )["column_names"][0]
            == "workspace_id"
        )
        assert (
            next(
                index for index in company_indexes if index["name"] == "ix_company_workspace_id_id"
            )["column_names"][0]
            == "workspace_id"
        )
    finally:
        engine.dispose()


def test_workspace_rejects_invalid_status_and_timestamp_order(
    database: DatabaseHarness,
) -> None:
    engine = _upgrade_engine(database)
    try:
        _assert_rejected(
            engine,
            workspace_table.insert().values(**_workspace_values(uuid4(), status="UNKNOWN")),
        )
        _assert_rejected(
            engine,
            workspace_table.insert().values(
                **_workspace_values(
                    uuid4(),
                    updated_at=CREATED_AT - timedelta(seconds=1),
                )
            ),
        )
    finally:
        engine.dispose()


def test_company_rejects_invalid_dates_status_country_and_domain(
    database: DatabaseHarness,
) -> None:
    engine = _upgrade_engine(database)
    workspace_id = uuid4()
    _insert_prerequisites(engine, workspace_id=workspace_id)
    invalid_companies = (
        _company_values(uuid4(), workspace_id, country_code="br"),
        _company_values(uuid4(), workspace_id, status="PENDING"),
        _company_values(uuid4(), workspace_id, official_domain="UPPER.example"),
        _company_values(
            uuid4(),
            workspace_id,
            updated_at=CREATED_AT - timedelta(seconds=1),
        ),
        _company_values(
            uuid4(),
            workspace_id,
            status="DISSOLVED",
            dissolved_on=None,
        ),
        _company_values(
            uuid4(),
            workspace_id,
            status="DISSOLVED",
            incorporated_on=date(2025, 1, 1),
            dissolved_on=date(2024, 1, 1),
        ),
    )
    try:
        for values in invalid_companies:
            _assert_rejected(engine, company_table.insert().values(**values))
    finally:
        engine.dispose()


def test_investigation_rejects_invalid_state_and_timestamps(
    database: DatabaseHarness,
) -> None:
    engine = _upgrade_engine(database)
    workspace_id = uuid4()
    _insert_prerequisites(engine, workspace_id=workspace_id)
    invalid_investigations = (
        _investigation_values(uuid4(), workspace_id, state="UNKNOWN"),
        _investigation_values(uuid4(), workspace_id, state_version=0),
        _investigation_values(
            uuid4(),
            workspace_id,
            deadline_at=CREATED_AT - timedelta(seconds=1),
        ),
        _investigation_values(
            uuid4(),
            workspace_id,
            state="IDENTIFYING",
            started_at=CREATED_AT + timedelta(seconds=2),
            completed_at=CREATED_AT + timedelta(seconds=1),
        ),
    )
    try:
        for values in invalid_investigations:
            _assert_rejected(engine, investigation_table.insert().values(**values))
    finally:
        engine.dispose()


def test_identifying_without_started_at_is_rejected(database: DatabaseHarness) -> None:
    engine = _upgrade_engine(database)
    workspace_id = uuid4()
    _insert_prerequisites(engine, workspace_id=workspace_id)
    try:
        _assert_rejected(
            engine,
            investigation_table.insert().values(
                **_investigation_values(
                    uuid4(),
                    workspace_id,
                    state="IDENTIFYING",
                )
            ),
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize("terminal_state", ["COMPLETED", "FAILED"])
def test_terminal_state_without_completed_at_is_rejected(
    database: DatabaseHarness,
    terminal_state: str,
) -> None:
    engine = _upgrade_engine(database)
    workspace_id = uuid4()
    company_id = uuid4() if terminal_state == "COMPLETED" else None
    _insert_prerequisites(engine, workspace_id=workspace_id, company_id=company_id)
    try:
        _assert_rejected(
            engine,
            investigation_table.insert().values(
                **_investigation_values(
                    uuid4(),
                    workspace_id,
                    state=terminal_state,
                    confirmed_company_id=company_id,
                    started_at=CREATED_AT + timedelta(seconds=1),
                )
            ),
        )
    finally:
        engine.dispose()


def test_non_terminal_state_with_completed_at_is_rejected(
    database: DatabaseHarness,
) -> None:
    engine = _upgrade_engine(database)
    workspace_id = uuid4()
    _insert_prerequisites(engine, workspace_id=workspace_id)
    try:
        _assert_rejected(
            engine,
            investigation_table.insert().values(
                **_investigation_values(
                    uuid4(),
                    workspace_id,
                    state="IDENTIFYING",
                    started_at=CREATED_AT + timedelta(seconds=1),
                    completed_at=CREATED_AT + timedelta(seconds=2),
                )
            ),
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "terminal_state",
    ["COMPLETED", "PARTIALLY_COMPLETED", "FAILED", "CANCELLED"],
)
def test_terminal_state_with_valid_timestamps_is_accepted(
    database: DatabaseHarness,
    terminal_state: str,
) -> None:
    engine = _upgrade_engine(database)
    workspace_id = uuid4()
    company_id = uuid4() if terminal_state in {"COMPLETED", "PARTIALLY_COMPLETED"} else None
    _insert_prerequisites(engine, workspace_id=workspace_id, company_id=company_id)
    try:
        with engine.begin() as connection:
            connection.execute(
                investigation_table.insert(),
                _investigation_values(
                    uuid4(),
                    workspace_id,
                    state=terminal_state,
                    confirmed_company_id=company_id,
                    started_at=CREATED_AT + timedelta(seconds=1),
                    completed_at=CREATED_AT + timedelta(seconds=2),
                ),
            )
    finally:
        engine.dispose()


def test_created_without_timestamps_is_accepted(database: DatabaseHarness) -> None:
    engine = _upgrade_engine(database)
    workspace_id = uuid4()
    _insert_prerequisites(engine, workspace_id=workspace_id)
    try:
        with engine.begin() as connection:
            connection.execute(
                investigation_table.insert(),
                _investigation_values(uuid4(), workspace_id),
            )
    finally:
        engine.dispose()


def test_created_with_started_at_is_rejected(database: DatabaseHarness) -> None:
    engine = _upgrade_engine(database)
    workspace_id = uuid4()
    _insert_prerequisites(engine, workspace_id=workspace_id)
    try:
        _assert_rejected(
            engine,
            investigation_table.insert().values(
                **_investigation_values(
                    uuid4(),
                    workspace_id,
                    started_at=CREATED_AT + timedelta(seconds=1),
                )
            ),
        )
    finally:
        engine.dispose()


def test_direct_created_cancellation_uses_one_terminal_timestamp(
    database: DatabaseHarness,
) -> None:
    engine = _upgrade_engine(database)
    workspace_id = uuid4()
    _insert_prerequisites(engine, workspace_id=workspace_id)
    cancelled_at = CREATED_AT + timedelta(seconds=1)
    try:
        with engine.begin() as connection:
            connection.execute(
                investigation_table.insert(),
                _investigation_values(
                    uuid4(),
                    workspace_id,
                    state="CANCELLED",
                    started_at=cancelled_at,
                    completed_at=cancelled_at,
                ),
            )
    finally:
        engine.dispose()


def test_investigation_rejects_partial_budget_and_invalid_codes(
    database: DatabaseHarness,
) -> None:
    engine = _upgrade_engine(database)
    workspace_id = uuid4()
    _insert_prerequisites(engine, workspace_id=workspace_id)
    invalid_investigations = (
        _investigation_values(uuid4(), workspace_id, budget_amount=Decimal("10")),
        _investigation_values(uuid4(), workspace_id, budget_currency="BRL"),
        _investigation_values(
            uuid4(),
            workspace_id,
            budget_amount=Decimal("NaN"),
            budget_currency="BRL",
        ),
        _investigation_values(
            uuid4(),
            workspace_id,
            budget_amount=Decimal("Infinity"),
            budget_currency="BRL",
        ),
        _investigation_values(
            uuid4(),
            workspace_id,
            budget_amount=Decimal("10"),
            budget_currency="brl",
        ),
        _investigation_values(uuid4(), workspace_id, country_code="B1"),
    )
    try:
        for values in invalid_investigations:
            _assert_rejected(engine, investigation_table.insert().values(**values))
    finally:
        engine.dispose()


def test_cross_workspace_company_reference_is_rejected(
    database: DatabaseHarness,
) -> None:
    engine = _upgrade_engine(database)
    company_workspace_id = uuid4()
    investigation_workspace_id = uuid4()
    company_id = uuid4()
    try:
        _insert_prerequisites(
            engine,
            workspace_id=company_workspace_id,
            company_id=company_id,
        )
        _insert_prerequisites(engine, workspace_id=investigation_workspace_id)
        _assert_rejected(
            engine,
            investigation_table.insert().values(
                **_investigation_values(
                    uuid4(),
                    investigation_workspace_id,
                    confirmed_company_id=company_id,
                )
            ),
        )
    finally:
        engine.dispose()


def test_created_investigation_with_confirmed_company_is_rejected(
    database: DatabaseHarness,
) -> None:
    engine = _upgrade_engine(database)
    workspace_id = uuid4()
    company_id = uuid4()
    try:
        _insert_prerequisites(
            engine,
            workspace_id=workspace_id,
            company_id=company_id,
        )
        _assert_rejected(
            engine,
            investigation_table.insert().values(
                **_investigation_values(
                    uuid4(),
                    workspace_id,
                    confirmed_company_id=company_id,
                )
            ),
        )
    finally:
        engine.dispose()


def test_downgrade_returns_to_base(database: DatabaseHarness) -> None:
    database.upgrade()
    database.downgrade()
    engine = database.engine()
    try:
        assert DOMAIN_TABLES.isdisjoint(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_after_downgrade_recreates_schema(database: DatabaseHarness) -> None:
    database.upgrade()
    database.downgrade()
    database.upgrade()
    engine = database.engine()
    try:
        assert set(sa.inspect(engine).get_table_names()) >= DOMAIN_TABLES
    finally:
        engine.dispose()
