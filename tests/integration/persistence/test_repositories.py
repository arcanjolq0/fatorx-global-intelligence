"""Repository and Unit of Work integration tests against real PostgreSQL."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from intelligence.application.errors import (
    PersistenceConflictError,
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
    company_id: CompanyId | None = None,
    *,
    investigation_id: InvestigationId | None = None,
) -> Investigation:
    return Investigation(
        id=investigation_id or InvestigationId.new(),
        workspace_id=workspace_id,
        requested_by=UserId.new(),
        profile_code="  SUPPLIER_STANDARD  ",
        country_code=CountryCode("br"),
        confirmed_company_id=company_id,
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
        confirmed_company_id=company_id,
        budget=Money(Decimal("1000.00000000000000000001"), CurrencyCode("BRL")),
        deadline_at=CREATED_AT + timedelta(days=2),
        started_at=CREATED_AT + timedelta(minutes=1),
        completed_at=CREATED_AT + timedelta(minutes=2) if terminal else None,
        created_at=CREATED_AT,
    )


def test_commit_persists_round_trip_for_all_three_entities(engine: Engine) -> None:
    workspace = _workspace()
    company = _company(workspace.id)
    investigation = _created_investigation(workspace.id, company.id)

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
    assert restored.trade_name == "Empresa Global"
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
    investigation = _persisted_investigation(
        workspace.id,
        state=InvestigationState.WAITING_FOR_REVIEW,
    )

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
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
    investigation = _persisted_investigation(workspace.id, state=state)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
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
        unit_of_work.workspaces.add(workspace)
        assert unit_of_work.workspaces.get(workspace.id) == workspace
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
    investigation = _created_investigation(workspace.id, company.id)

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
    investigation = _created_investigation(investigation_workspace.id, company.id)

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
    investigation = _created_investigation(workspace.id, company.id)

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

    with pytest.raises(PersistenceStateError, match="connection is closed"):
        repository.get(workspace.id)


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
    invalid_investigation = _created_investigation(second_workspace.id, company.id)

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
