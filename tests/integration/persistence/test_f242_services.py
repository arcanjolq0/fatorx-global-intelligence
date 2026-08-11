"""F2.4.2 service isolation and audit atomicity against real PostgreSQL."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import AuditActionCode, AuditReasonCode
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import (
    AuthorizationDeniedError,
    InvalidOperationError,
    PersistenceError,
    PersistenceStateError,
    ResourceNotFoundError,
)
from intelligence.application.services.companies import CompanyService
from intelligence.application.services.investigations import InvestigationService
from intelligence.domain.audit import AuditOutcome
from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CompanyId,
    CorrelationId,
    InvestigationId,
    MembershipId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.identities import (
    EmailAddress,
    MembershipRole,
    MembershipStatus,
    UserAccount,
    UserAccountStatus,
    WorkspaceMembership,
)
from intelligence.domain.investigations import Investigation
from intelligence.domain.workspaces import Workspace, WorkspaceStatus
from intelligence.infrastructure.persistence.postgresql.engine import create_postgresql_engine
from intelligence.infrastructure.persistence.postgresql.tables import (
    audit_event_table,
    company_table,
    investigation_table,
)
from intelligence.infrastructure.persistence.postgresql.unit_of_work import (
    PostgreSQLUnitOfWork,
    PostgreSQLUnitOfWorkFactory,
)
from tests.support.destructive_database import require_safe_destructive_database_url
from tests.unit.application.fakes import FakeClock

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])

REPOSITORY_ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 7, 28, 15, tzinfo=UTC)


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
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


@pytest.fixture(autouse=True)
def clean_database(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE TABLE audit_event, workspace_membership, user_account, "
                "investigation, company, workspace CASCADE"
            )
        )


def _workspace(name: str) -> Workspace:
    return Workspace(
        id=WorkspaceId.new(),
        name=name,
        status=WorkspaceStatus.ACTIVE,
        retention_policy_version="2026-01",
        created_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(days=2),
    )


def _user(user_id: UserId, label: str) -> UserAccount:
    return UserAccount(
        id=user_id,
        email=EmailAddress(f"{label}-{user_id.value}@example.test"),
        display_name=label,
        status=UserAccountStatus.ACTIVE,
        created_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(days=2),
    )


def _membership(
    workspace_id: WorkspaceId,
    user_id: UserId,
    role: MembershipRole,
) -> WorkspaceMembership:
    return WorkspaceMembership(
        id=MembershipId.new(),
        workspace_id=workspace_id,
        user_id=user_id,
        role=role,
        status=MembershipStatus.ACTIVE,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )


def _seed_workspace_with_actor(
    engine: Engine,
    *,
    name: str,
    role: MembershipRole,
) -> tuple[Workspace, ActorContext]:
    workspace = _workspace(name)
    user_id = UserId.new()
    actor = ActorContext(
        user_id=user_id,
        workspace_id=workspace.id,
        correlation_id=CorrelationId.new(),
    )
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        unit_of_work.users.add(_user(user_id, name))
        unit_of_work.memberships.add(_membership(workspace.id, user_id, role))
        unit_of_work.commit()
    return workspace, actor


def _company(workspace_id: WorkspaceId) -> Company:
    return Company(
        id=CompanyId.new(),
        workspace_id=workspace_id,
        legal_name="Other Workspace Company",
        country_code=CountryCode("BR"),
        status=CompanyStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


def _investigation(actor: ActorContext) -> Investigation:
    return Investigation(
        id=InvestigationId.new(),
        workspace_id=actor.workspace_id,
        requested_by=actor.user_id,
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        created_at=NOW,
    )


def _audit_rows(engine: Engine) -> list[sa.RowMapping]:
    statement = sa.select(
        audit_event_table.c.workspace_id,
        audit_event_table.c.actor_user_id,
        audit_event_table.c.action_code,
        audit_event_table.c.resource_id,
        audit_event_table.c.outcome,
        audit_event_table.c.reason_code,
        audit_event_table.c.correlation_id,
    ).order_by(audit_event_table.c.occurred_at, audit_event_table.c.id)
    with engine.connect() as connection:
        return list(connection.execute(statement).mappings())


class TrackingFactory:
    def __init__(self, engine: Engine) -> None:
        self._factory = PostgreSQLUnitOfWorkFactory(engine)
        self.created: list[PostgreSQLUnitOfWork] = []

    def __call__(self) -> PostgreSQLUnitOfWork:
        unit_of_work = self._factory()
        self.created.append(unit_of_work)
        return unit_of_work


class TerminatingUnitOfWork(PostgreSQLUnitOfWork):
    def __init__(self, engine: Engine) -> None:
        super().__init__(engine)
        self._controller_engine = engine

    def __enter__(self) -> TerminatingUnitOfWork:
        super().__enter__()
        return self

    def commit(self) -> None:
        connection = self._connection
        assert connection is not None
        backend_pid = connection.execute(sa.text("SELECT pg_backend_pid() ")).scalar_one()
        with self._controller_engine.begin() as controller:
            assert controller.execute(
                sa.text("SELECT pg_terminate_backend(:backend_pid)"),
                {"backend_pid": backend_pid},
            ).scalar_one()
        super().commit()


class TerminatingFactory:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self.created: list[TerminatingUnitOfWork] = []

    def __call__(self) -> TerminatingUnitOfWork:
        unit_of_work = TerminatingUnitOfWork(self._engine)
        self.created.append(unit_of_work)
        return unit_of_work


def test_services_isolate_company_and_investigation_and_audit_safe_absence(
    engine: Engine,
) -> None:
    _, actor_a = _seed_workspace_with_actor(
        engine,
        name="workspace-a",
        role=MembershipRole.OWNER,
    )
    _, actor_b = _seed_workspace_with_actor(
        engine,
        name="workspace-b",
        role=MembershipRole.OWNER,
    )
    company_b = _company(actor_b.workspace_id)
    investigation_b = _investigation(actor_b)
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.companies.add(company_b)
        unit_of_work.investigations.add(investigation_b)
        unit_of_work.commit()

    factory = TrackingFactory(engine)
    company_service = CompanyService(factory, ContextualAuthorizer(), FakeClock(NOW))
    investigation_service = InvestigationService(
        factory,
        ContextualAuthorizer(),
        FakeClock(NOW),
    )

    with pytest.raises(ResourceNotFoundError):
        company_service.get_company(actor_a, company_id=company_b.id)
    with pytest.raises(ResourceNotFoundError):
        investigation_service.get_investigation(
            actor_a,
            investigation_id=investigation_b.id,
        )

    assert len(factory.created) == 2
    rows = _audit_rows(engine)
    assert {row["action_code"] for row in rows} == {
        AuditActionCode.COMPANY_READ_DENIED.value,
        AuditActionCode.INVESTIGATION_READ_DENIED.value,
    }
    assert all(row["outcome"] == AuditOutcome.DENIED.value for row in rows)
    assert all(row["reason_code"] == AuditReasonCode.RESOURCE_NOT_FOUND.value for row in rows)
    assert all(row["resource_id"] is None for row in rows)


def test_membership_in_another_workspace_does_not_authorize_actor_context(
    engine: Engine,
) -> None:
    workspace_a, _ = _seed_workspace_with_actor(
        engine,
        name="workspace-a",
        role=MembershipRole.OWNER,
    )
    workspace_b, _ = _seed_workspace_with_actor(
        engine,
        name="workspace-b",
        role=MembershipRole.OWNER,
    )
    user_id = UserId.new()
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.users.add(_user(user_id, "cross-scope"))
        unit_of_work.memberships.add(_membership(workspace_b.id, user_id, MembershipRole.OWNER))
        unit_of_work.commit()
    actor = ActorContext(
        user_id=user_id,
        workspace_id=workspace_a.id,
        correlation_id=CorrelationId.new(),
    )
    service = CompanyService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW),
    )

    with pytest.raises(AuthorizationDeniedError):
        service.create_company(
            actor,
            legal_name="Must Not Exist",
            country_code=CountryCode("BR"),
        )

    rows = _audit_rows(engine)
    assert len(rows) == 1
    assert rows[0]["workspace_id"] == workspace_a.id.value
    assert rows[0]["reason_code"] == AuditReasonCode.ACTOR_MEMBERSHIP_NOT_FOUND.value
    with engine.connect() as connection:
        assert (
            connection.execute(sa.select(sa.func.count()).select_from(company_table)).scalar_one()
            == 0
        )


def test_missing_actor_preserves_denial_when_audit_foreign_key_rejects_event(
    engine: Engine,
) -> None:
    workspace = _workspace("workspace-without-actor")
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        unit_of_work.commit()
    actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=workspace.id,
        correlation_id=CorrelationId.new(),
    )
    service = CompanyService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW),
    )

    with pytest.raises(AuthorizationDeniedError) as captured:
        service.create_company(
            actor,
            legal_name="Must Not Exist",
            country_code=CountryCode("BR"),
        )

    assert str(captured.value) == "Operation is not authorized."
    with engine.connect() as connection:
        assert (
            connection.execute(sa.select(sa.func.count()).select_from(company_table)).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(audit_event_table)
            ).scalar_one()
            == 0
        )


def test_creations_use_actor_scope_requester_and_atomic_success_audit(engine: Engine) -> None:
    _, actor = _seed_workspace_with_actor(
        engine,
        name="workspace-owner",
        role=MembershipRole.OWNER,
    )
    factory = TrackingFactory(engine)
    company_service = CompanyService(factory, ContextualAuthorizer(), FakeClock(NOW))
    investigation_service = InvestigationService(
        factory,
        ContextualAuthorizer(),
        FakeClock(NOW),
    )

    company = company_service.create_company(
        actor,
        legal_name="Scoped Company",
        country_code=CountryCode("BR"),
    )
    investigation = investigation_service.create_investigation(
        actor,
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
    )

    assert company.workspace_id == actor.workspace_id
    assert investigation.workspace_id == actor.workspace_id
    assert investigation.requested_by == actor.user_id
    assert investigation.confirmed_company_id is None
    assert len(factory.created) == 2
    assert all(unit_of_work.is_closed for unit_of_work in factory.created)
    rows = _audit_rows(engine)
    assert {row["action_code"] for row in rows} == {
        AuditActionCode.COMPANY_CREATED.value,
        AuditActionCode.INVESTIGATION_CREATED.value,
    }
    assert all(row["outcome"] == AuditOutcome.SUCCESS.value for row in rows)
    assert all(row["correlation_id"] == actor.correlation_id.value for row in rows)


def test_denial_commits_event_without_company_mutation(engine: Engine) -> None:
    _, viewer = _seed_workspace_with_actor(
        engine,
        name="workspace-viewer",
        role=MembershipRole.VIEWER,
    )
    service = CompanyService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW),
    )

    with pytest.raises(AuthorizationDeniedError):
        service.create_company(
            viewer,
            legal_name="Denied Company",
            country_code=CountryCode("BR"),
        )

    with engine.connect() as connection:
        assert (
            connection.execute(sa.select(sa.func.count()).select_from(company_table)).scalar_one()
            == 0
        )
    rows = _audit_rows(engine)
    assert len(rows) == 1
    assert rows[0]["outcome"] == AuditOutcome.DENIED.value
    assert rows[0]["reason_code"] == AuditReasonCode.PERMISSION_DENIED.value


def test_known_validation_failure_never_records_success(engine: Engine) -> None:
    _, owner = _seed_workspace_with_actor(
        engine,
        name="workspace-owner",
        role=MembershipRole.OWNER,
    )
    service = CompanyService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW),
    )

    with pytest.raises(InvalidOperationError):
        service.create_company(
            owner,
            legal_name="   ",
            country_code=CountryCode("BR"),
        )

    rows = _audit_rows(engine)
    assert len(rows) == 1
    assert rows[0]["outcome"] == AuditOutcome.FAILURE.value
    assert rows[0]["reason_code"] == AuditReasonCode.VALIDATION_FAILURE.value
    assert all(row["outcome"] != AuditOutcome.SUCCESS.value for row in rows)


def test_failed_commit_rolls_back_mutation_and_audit_and_keeps_guard_terminal(
    engine: Engine,
) -> None:
    _, owner = _seed_workspace_with_actor(
        engine,
        name="workspace-owner",
        role=MembershipRole.OWNER,
    )
    factory = TerminatingFactory(engine)
    service = CompanyService(factory, ContextualAuthorizer(), FakeClock(NOW))

    with pytest.raises(PersistenceError, match="Unable to commit"):
        service.create_company(
            owner,
            legal_name="Uncertain Company",
            country_code=CountryCode("BR"),
        )

    unit_of_work = factory.created[0]
    repository = unit_of_work._companies
    guard = unit_of_work._transaction_guard
    assert repository is not None
    assert guard is not None and guard.is_invalidated
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        repository.get(owner.workspace_id, CompanyId.new())
    with engine.connect() as connection:
        assert (
            connection.execute(sa.select(sa.func.count()).select_from(company_table)).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(audit_event_table)
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(investigation_table)
            ).scalar_one()
            == 0
        )
