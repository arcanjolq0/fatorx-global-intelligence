"""Repository and Unit of Work integration tests against real PostgreSQL."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from intelligence.application.errors import (
    PersistenceConflictError,
    PersistenceError,
    PersistenceStateError,
)
from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CompanyId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.investigation_inputs import (
    IdentificationInput,
    OriginalAndNormalizedText,
)
from intelligence.domain.investigations import (
    TERMINAL_INVESTIGATION_STATES,
    Investigation,
    InvestigationState,
)
from intelligence.domain.money import CurrencyCode, Money
from intelligence.domain.workspaces import Workspace, WorkspaceStatus
from intelligence.infrastructure.persistence.postgresql.engine import (
    create_postgresql_engine,
)
from intelligence.infrastructure.persistence.postgresql.unit_of_work import (
    PostgreSQLUnitOfWork,
)
from tests.support.destructive_database import require_safe_destructive_database_url

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])

REPOSITORY_ROOT = Path(__file__).parents[3]
CREATED_AT = datetime(2026, 7, 28, 12, tzinfo=UTC)


@pytest.fixture()
def engine() -> Iterator[Engine]:
    """Create the approved schema for one isolated persistence scenario."""

    database_url = require_safe_destructive_database_url()
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    database_engine = create_postgresql_engine({"DATABASE_URL": database_url})
    try:
        yield database_engine
    finally:
        with database_engine.begin() as connection:
            connection.execute(sa.text("TRUNCATE TABLE company CASCADE"))
        database_engine.dispose()
        command.downgrade(config, "base")


def _workspace(
    *,
    workspace_id: WorkspaceId | None = None,
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE,
) -> Workspace:
    return Workspace(
        id=workspace_id or WorkspaceId.new(),
        name="  Workspace internacional  ",
        status=status,
        retention_policy_version="  2026-01  ",
        created_at=CREATED_AT,
        updated_at=CREATED_AT + timedelta(minutes=1),
    )


def _company(
    workspace_id: WorkspaceId,
    *,
    company_id: CompanyId | None = None,
    status: CompanyStatus = CompanyStatus.ACTIVE,
) -> Company:
    dissolved_on = date(2025, 5, 1) if status is CompanyStatus.DISSOLVED else None
    return Company(
        id=company_id or CompanyId.new(),
        workspace_id=workspace_id,
        legal_name="  Empresa Global Ltda.  ",
        trade_name="  Empresa Global  ",
        country_code=CountryCode("br"),
        legal_form="  Limitada  ",
        status=status,
        incorporated_on=date(2020, 1, 1),
        dissolved_on=dissolved_on,
        official_domain="  EMPRESA.EXAMPLE  ",
        created_at=CREATED_AT,
        updated_at=CREATED_AT + timedelta(minutes=1),
    )


def _created_investigation(
    workspace_id: WorkspaceId,
    *,
    investigation_id: InvestigationId | None = None,
) -> Investigation:
    return Investigation(
        id=investigation_id or InvestigationId.new(),
        workspace_id=workspace_id,
        requested_by=UserId.new(),
        profile_code="  SUPPLIER_STANDARD  ",
        country_code=CountryCode("br"),
        budget=Money(
            Decimal("98765432109876543210.12345678901234567890"),
            CurrencyCode("brl"),
        ),
        deadline_at=CREATED_AT + timedelta(days=2),
        created_at=CREATED_AT,
    )


def _persisted_investigation(
    workspace_id: WorkspaceId,
    *,
    state: InvestigationState,
    company_id: CompanyId | None = None,
) -> Investigation:
    terminal = state in TERMINAL_INVESTIGATION_STATES
    return Investigation.reconstitute(
        id=InvestigationId.new(),
        workspace_id=workspace_id,
        requested_by=UserId.new(),
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        state=state,
        state_version=9,
        identification_input=IdentificationInput(
            legal_name=OriginalAndNormalizedText(
                original_value="Empresa Global Ltda.",
                normalized_value="empresa global ltda",
            )
        ),
        confirmed_company_id=company_id,
        budget=Money(Decimal("1000.00000000000000000001"), CurrencyCode("BRL")),
        deadline_at=CREATED_AT + timedelta(days=2),
        started_at=CREATED_AT + timedelta(minutes=1),
        completed_at=CREATED_AT + timedelta(minutes=2) if terminal else None,
        created_at=CREATED_AT,
    )


def _terminate_unit_of_work_backend(
    engine: Engine,
    unit_of_work: PostgreSQLUnitOfWork,
) -> None:
    connection = unit_of_work._connection
    assert connection is not None
    backend_pid = connection.execute(sa.text("SELECT pg_backend_pid()")).scalar_one()
    with engine.begin() as controller:
        terminated = controller.execute(
            sa.text("SELECT pg_terminate_backend(:backend_pid)"),
            {"backend_pid": backend_pid},
        ).scalar_one()
    assert terminated is True


def test_commit_persists_round_trip_for_all_three_entities(engine: Engine) -> None:
    workspace = _workspace()
    company = _company(workspace.id)
    investigation = _created_investigation(workspace.id)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        unit_of_work.companies.add(company)
        unit_of_work.investigations.add(investigation)
        unit_of_work.commit()

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert unit_of_work.workspaces.get(workspace.id) == workspace
        assert unit_of_work.companies.get(workspace.id, company.id) == company
        restored = unit_of_work.investigations.get(workspace.id, investigation.id)

    assert restored == investigation
    assert restored is not None
    assert restored.budget is not None
    assert restored.budget.amount == Decimal("98765432109876543210.12345678901234567890")


@pytest.mark.parametrize("status", list(WorkspaceStatus))
def test_workspace_round_trip_covers_every_status(
    engine: Engine,
    status: WorkspaceStatus,
) -> None:
    workspace = _workspace(status=status)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        unit_of_work.commit()
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        restored = unit_of_work.workspaces.get(workspace.id)

    assert restored == workspace
    assert restored is not None
    assert restored.created_at.tzinfo is UTC


@pytest.mark.parametrize("status", list(CompanyStatus))
def test_company_round_trip_covers_statuses_dates_and_optional_fields(
    engine: Engine,
    status: CompanyStatus,
) -> None:
    workspace = _workspace()
    company = _company(workspace.id, status=status)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        unit_of_work.companies.add(company)
        unit_of_work.commit()
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        restored = unit_of_work.companies.get(workspace.id, company.id)

    assert restored == company
    assert restored is not None
    assert restored.trade_name == "  Empresa Global  "
    assert restored.official_domain == "empresa.example"


def test_company_round_trip_preserves_absent_optional_fields(engine: Engine) -> None:
    workspace = _workspace()
    company = Company(
        id=CompanyId.new(),
        workspace_id=workspace.id,
        legal_name="Empresa mínima",
        country_code=CountryCode("BR"),
        status=CompanyStatus.INACTIVE,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        unit_of_work.companies.add(company)
        unit_of_work.commit()
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        restored = unit_of_work.companies.get(workspace.id, company.id)

    assert restored == company


def test_non_initial_investigation_snapshot_round_trip(engine: Engine) -> None:
    workspace = _workspace()
    company = _company(workspace.id)
    investigation = _persisted_investigation(
        workspace.id,
        state=InvestigationState.WAITING_FOR_REVIEW,
        company_id=company.id,
    )

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        unit_of_work.companies.add(company)
        unit_of_work.investigations.add(investigation)
        unit_of_work.commit()
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        restored = unit_of_work.investigations.get(workspace.id, investigation.id)

    assert restored == investigation
    assert restored is not None
    assert restored.state_version == 9


@pytest.mark.parametrize("state", sorted(TERMINAL_INVESTIGATION_STATES, key=str))
def test_terminal_investigation_snapshot_round_trip(
    engine: Engine,
    state: InvestigationState,
) -> None:
    workspace = _workspace()
    company = (
        _company(workspace.id)
        if state in {InvestigationState.COMPLETED, InvestigationState.PARTIALLY_COMPLETED}
        else None
    )
    investigation = _persisted_investigation(
        workspace.id,
        state=state,
        company_id=company.id if company is not None else None,
    )

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        if company is not None:
            unit_of_work.companies.add(company)
        unit_of_work.investigations.add(investigation)
        unit_of_work.commit()
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        restored = unit_of_work.investigations.get(workspace.id, investigation.id)

    assert restored == investigation
    assert restored is not None
    assert restored.completed_at == CREATED_AT + timedelta(minutes=2)


def test_exit_without_commit_rolls_back(engine: Engine) -> None:
    workspace = _workspace()

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert unit_of_work.workspaces.get(workspace.id) is None


def test_exception_inside_context_rolls_back(engine: Engine) -> None:
    workspace = _workspace()

    with (
        pytest.raises(RuntimeError, match="controlled failure"),
        PostgreSQLUnitOfWork(engine) as unit_of_work,
    ):
        unit_of_work.workspaces.add(workspace)
        raise RuntimeError("controlled failure")

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert unit_of_work.workspaces.get(workspace.id) is None


def test_repositories_share_one_uncommitted_transaction(engine: Engine) -> None:
    workspace = _workspace()

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        connection = unit_of_work._connection
        original_transaction = unit_of_work._transaction
        assert connection is not None
        assert original_transaction is not None
        assert connection.get_transaction() is original_transaction
        unit_of_work.workspaces.add(workspace)
        assert unit_of_work.workspaces.get(workspace.id) == workspace
        assert connection.get_transaction() is original_transaction
        with PostgreSQLUnitOfWork(engine) as separate_unit_of_work:
            assert separate_unit_of_work.workspaces.get(workspace.id) is None
        unit_of_work.commit()

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert unit_of_work.workspaces.get(workspace.id) == workspace


def test_company_and_investigation_insert_together_in_one_unit_of_work(
    engine: Engine,
) -> None:
    workspace = _workspace()
    company = _company(workspace.id)
    investigation = _created_investigation(workspace.id)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        unit_of_work.companies.add(company)
        unit_of_work.investigations.add(investigation)
        assert unit_of_work.companies.get(workspace.id, company.id) == company
        assert unit_of_work.investigations.get(workspace.id, investigation.id) == investigation
        unit_of_work.commit()


def test_key_conflict_is_translated_without_sensitive_details(engine: Engine) -> None:
    workspace = _workspace()

    with (
        pytest.raises(PersistenceConflictError) as captured,
        PostgreSQLUnitOfWork(engine) as unit_of_work,
    ):
        unit_of_work.workspaces.add(workspace)
        unit_of_work.workspaces.add(workspace)

    assert str(captured.value) == "Persistence constraint conflict."
    assert isinstance(captured.value.__cause__, IntegrityError)


def test_cross_workspace_company_conflict_remains_rejected(engine: Engine) -> None:
    company_workspace = _workspace()
    investigation_workspace = _workspace()
    company = _company(company_workspace.id)
    investigation = _persisted_investigation(
        investigation_workspace.id,
        state=InvestigationState.PLANNING,
        company_id=company.id,
    )

    with (
        pytest.raises(PersistenceConflictError),
        PostgreSQLUnitOfWork(engine) as unit_of_work,
    ):
        unit_of_work.workspaces.add(company_workspace)
        unit_of_work.workspaces.add(investigation_workspace)
        unit_of_work.companies.add(company)
        unit_of_work.investigations.add(investigation)


def test_wrong_workspace_queries_return_none(engine: Engine) -> None:
    workspace = _workspace()
    other_workspace = _workspace()
    company = _company(workspace.id)
    investigation = _created_investigation(workspace.id)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        unit_of_work.workspaces.add(other_workspace)
        unit_of_work.companies.add(company)
        unit_of_work.investigations.add(investigation)
        unit_of_work.commit()

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert unit_of_work.companies.get(other_workspace.id, company.id) is None
        assert unit_of_work.investigations.get(other_workspace.id, investigation.id) is None


def test_connection_closes_after_context(engine: Engine) -> None:
    unit_of_work = PostgreSQLUnitOfWork(engine)

    with unit_of_work:
        connection = unit_of_work._connection
        assert connection is not None
        assert not connection.closed

    assert unit_of_work.is_closed
    assert connection.closed


def test_repository_operation_after_context_fails_clearly(engine: Engine) -> None:
    workspace = _workspace()

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        repository = unit_of_work.workspaces

    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        repository.get(workspace.id)


def test_captured_repository_rejects_read_after_commit_without_autobegin(
    engine: Engine,
) -> None:
    workspace = _workspace()

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        repository = unit_of_work.workspaces
        connection = unit_of_work._connection
        original_transaction = unit_of_work._transaction
        assert connection is not None
        assert original_transaction is not None
        repository.add(workspace)
        unit_of_work.commit()

        assert not original_transaction.is_active
        assert connection.get_transaction() is None
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.get(workspace.id)
        assert connection.get_transaction() is None


def test_captured_repository_rejects_write_after_commit_without_autobegin(
    engine: Engine,
) -> None:
    persisted_workspace = _workspace()
    rejected_workspace = _workspace()

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        repository = unit_of_work.workspaces
        connection = unit_of_work._connection
        assert connection is not None
        repository.add(persisted_workspace)
        unit_of_work.commit()

        assert connection.get_transaction() is None
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.add(rejected_workspace)
        assert connection.get_transaction() is None

    with PostgreSQLUnitOfWork(engine) as observer:
        assert observer.workspaces.get(persisted_workspace.id) == persisted_workspace
        assert observer.workspaces.get(rejected_workspace.id) is None


def test_captured_repository_rejects_operations_after_rollback_without_autobegin(
    engine: Engine,
) -> None:
    rolled_back_workspace = _workspace()
    rejected_workspace = _workspace()

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        repository = unit_of_work.workspaces
        connection = unit_of_work._connection
        original_transaction = unit_of_work._transaction
        assert connection is not None
        assert original_transaction is not None
        repository.add(rolled_back_workspace)
        unit_of_work.rollback()

        assert not original_transaction.is_active
        assert connection.get_transaction() is None
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.get(rolled_back_workspace.id)
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.add(rejected_workspace)
        assert connection.get_transaction() is None

    with PostgreSQLUnitOfWork(engine) as observer:
        assert observer.workspaces.get(rolled_back_workspace.id) is None
        assert observer.workspaces.get(rejected_workspace.id) is None


def test_duplicate_commit_is_rejected_without_autobegin(engine: Engine) -> None:
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        connection = unit_of_work._connection
        assert connection is not None
        unit_of_work.commit()

        with pytest.raises(PersistenceStateError, match="already been committed"):
            unit_of_work.commit()
        assert connection.get_transaction() is None


def test_duplicate_rollback_is_rejected_without_autobegin(engine: Engine) -> None:
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        connection = unit_of_work._connection
        assert connection is not None
        unit_of_work.rollback()

        with pytest.raises(PersistenceStateError, match="already been rolled back"):
            unit_of_work.rollback()
        assert connection.get_transaction() is None


def test_real_postgresql_start_failure_is_translated_without_technical_details(
    engine: Engine,
) -> None:
    missing_database = "fatorx_missing_f232"
    unavailable_url = engine.url.set(database=missing_database).render_as_string(
        hide_password=False
    )
    unavailable_engine = create_postgresql_engine({"DATABASE_URL": unavailable_url})
    unit_of_work = PostgreSQLUnitOfWork(unavailable_engine)

    try:
        with pytest.raises(PersistenceError) as captured, unit_of_work:
            pytest.fail("The Unit of Work unexpectedly connected to a missing database.")
    finally:
        unavailable_engine.dispose()

    assert str(captured.value) == "Unable to start the persistence transaction."
    assert missing_database not in str(captured.value)
    assert unavailable_url not in str(captured.value)
    assert unit_of_work.is_closed
    with pytest.raises(PersistenceStateError, match="single-use"):
        unit_of_work.__enter__()


def test_real_postgresql_commit_failure_is_translated_without_technical_details(
    engine: Engine,
) -> None:
    unit_of_work = PostgreSQLUnitOfWork(engine)
    with (
        pytest.raises(PersistenceError) as captured,
        unit_of_work,
    ):
        repository = unit_of_work.workspaces
        guard = repository._transaction_guard
        _terminate_unit_of_work_backend(engine, unit_of_work)
        unit_of_work.commit()

    assert str(captured.value) == "Unable to commit the persistence transaction."
    assert "pg_terminate_backend" not in str(captured.value)
    assert engine.url.render_as_string(hide_password=False) not in str(captured.value)
    assert guard.is_invalidated
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        repository.get(WorkspaceId.new())
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        repository.add(_workspace())
    with pytest.raises(PersistenceStateError, match="finalization has already been attempted"):
        unit_of_work.commit()
    with pytest.raises(PersistenceStateError, match="finalization has already been attempted"):
        unit_of_work.rollback()


def test_real_postgresql_rollback_failure_is_translated_without_technical_details(
    engine: Engine,
) -> None:
    unit_of_work = PostgreSQLUnitOfWork(engine)
    with (
        pytest.raises(PersistenceError) as captured,
        unit_of_work,
    ):
        repository = unit_of_work.workspaces
        guard = repository._transaction_guard
        _terminate_unit_of_work_backend(engine, unit_of_work)
        unit_of_work.rollback()

    assert str(captured.value) == "Unable to roll back the persistence transaction."
    assert "pg_terminate_backend" not in str(captured.value)
    assert engine.url.render_as_string(hide_password=False) not in str(captured.value)
    assert guard.is_invalidated
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        repository.get(WorkspaceId.new())
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        repository.add(_workspace())
    with pytest.raises(PersistenceStateError, match="finalization has already been attempted"):
        unit_of_work.commit()
    with pytest.raises(PersistenceStateError, match="finalization has already been attempted"):
        unit_of_work.rollback()


def test_repository_does_not_commit_implicitly(engine: Engine) -> None:
    workspace = _workspace()

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        with PostgreSQLUnitOfWork(engine) as observer:
            assert observer.workspaces.get(workspace.id) is None

    with PostgreSQLUnitOfWork(engine) as observer:
        assert observer.workspaces.get(workspace.id) is None


def test_rollback_leaves_no_partial_data_after_constraint_failure(engine: Engine) -> None:
    first_workspace = _workspace()
    second_workspace = _workspace()
    company = _company(first_workspace.id)
    invalid_investigation = _persisted_investigation(
        second_workspace.id,
        state=InvestigationState.PLANNING,
        company_id=company.id,
    )

    with (
        pytest.raises(PersistenceConflictError),
        PostgreSQLUnitOfWork(engine) as unit_of_work,
    ):
        unit_of_work.workspaces.add(first_workspace)
        unit_of_work.workspaces.add(second_workspace)
        unit_of_work.companies.add(company)
        unit_of_work.investigations.add(invalid_investigation)

    with PostgreSQLUnitOfWork(engine) as observer:
        assert observer.workspaces.get(first_workspace.id) is None
        assert observer.workspaces.get(second_workspace.id) is None
        assert observer.companies.get(first_workspace.id, company.id) is None
