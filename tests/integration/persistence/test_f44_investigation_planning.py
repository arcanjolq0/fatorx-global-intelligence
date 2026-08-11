"""F4.4 PostgreSQL round-trip, replay, tamper detection, and concurrency."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy.engine import Engine

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import (
    InvestigationPlanAlreadyExistsError,
    PersistenceDataError,
)
from intelligence.application.investigation_planning import CreateInvestigationPlan
from intelligence.application.services.investigation_planning import (
    InvestigationPlanningService,
)
from intelligence.connectors.registry import ConnectorRegistry
from intelligence.connectors.simulated.business_registry import (
    SimulatedBusinessRegistryConnector,
)
from intelligence.connectors.simulated.scenarios import BusinessRegistryScenario
from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CompanyId,
    CorrelationId,
    InvestigationCommandId,
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
from intelligence.domain.investigation_inputs import (
    IdentificationInput,
    OriginalAndNormalizedText,
)
from intelligence.domain.investigations import (
    TERMINAL_INVESTIGATION_STATES,
    Investigation,
    InvestigationState,
)
from intelligence.domain.workspaces import Workspace, WorkspaceStatus
from intelligence.infrastructure.persistence.postgresql.engine import create_postgresql_engine
from intelligence.infrastructure.persistence.postgresql.tables import (
    audit_event_table,
    entity_candidate_batch_table,
    investigation_plan_table,
    investigation_table,
    planned_capability_table,
    planned_connector_option_table,
)
from intelligence.infrastructure.persistence.postgresql.unit_of_work import (
    PostgreSQLUnitOfWork,
    PostgreSQLUnitOfWorkFactory,
)
from intelligence.orchestration.planning import INVESTIGATION_PLANNING_V1
from tests.support.destructive_database import require_safe_destructive_database_url
from tests.unit.application.fakes import FakeClock

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])

REPOSITORY_ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 8, 1, 20, tzinfo=UTC)


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    database_url = require_safe_destructive_database_url()
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    alembic_command.downgrade(config, "base")
    alembic_command.upgrade(config, "head")
    database_engine = create_postgresql_engine({"DATABASE_URL": database_url})
    try:
        yield database_engine
    finally:
        database_engine.dispose()
        alembic_command.downgrade(config, "base")


@pytest.fixture(autouse=True)
def clean_database(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE TABLE planned_connector_option, planned_capability, "
                "investigation_plan, entity_resolution_decision, investigation_transition, "
                "audit_event, entity_candidate_dimension_score, entity_candidate, "
                "entity_candidate_batch, workspace_membership, user_account, investigation, "
                "company, workspace CASCADE"
            )
        )


def _registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register(SimulatedBusinessRegistryConnector(BusinessRegistryScenario.SUCCESS))
    return registry


def _seed_planning(engine: Engine, label: str = "tenant-a") -> tuple[ActorContext, Investigation]:
    actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )
    created_at = NOW - timedelta(days=1)
    company = Company(
        id=CompanyId.new(),
        workspace_id=actor.workspace_id,
        legal_name="Empresa Exemplo S.A.",
        country_code=CountryCode("BR"),
        status=CompanyStatus.ACTIVE,
        created_at=created_at,
        updated_at=created_at,
    )
    investigation = Investigation.reconstitute(
        id=InvestigationId.new(),
        workspace_id=actor.workspace_id,
        requested_by=actor.user_id,
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        created_at=created_at,
        state=InvestigationState.PLANNING,
        state_version=4,
        confirmed_company_id=company.id,
        deadline_at=NOW + timedelta(hours=3),
        started_at=created_at + timedelta(minutes=1),
        identification_input=IdentificationInput(
            legal_name=OriginalAndNormalizedText(
                original_value="Empresa Exemplo S.A.",
                normalized_value="empresa exemplo s.a.",
            )
        ),
    )
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(
            Workspace(
                id=actor.workspace_id,
                name=label,
                status=WorkspaceStatus.ACTIVE,
                retention_policy_version="2026-01",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        unit_of_work.users.add(
            UserAccount(
                id=actor.user_id,
                email=EmailAddress(f"{actor.user_id.value}@example.test"),
                display_name="Planner",
                status=UserAccountStatus.ACTIVE,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        unit_of_work.memberships.add(
            WorkspaceMembership(
                id=MembershipId.new(),
                workspace_id=actor.workspace_id,
                user_id=actor.user_id,
                role=MembershipRole.ANALYST,
                status=MembershipStatus.ACTIVE,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        unit_of_work.companies.add(company)
        unit_of_work.investigations.add(investigation)
        unit_of_work.commit()
    return actor, investigation


def _command(
    investigation: Investigation,
    command_id: InvestigationCommandId | None = None,
) -> CreateInvestigationPlan:
    return CreateInvestigationPlan(
        command_id=command_id or InvestigationCommandId.new(),
        investigation_id=investigation.id,
        expected_state_version=investigation.state_version,
        planning_policy=INVESTIGATION_PLANNING_V1,
    )


def _service(engine: Engine) -> InvestigationPlanningService:
    return InvestigationPlanningService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW),
        _registry(),
    )


def test_complete_plan_round_trip_replay_and_tenant_isolation(engine: Engine) -> None:
    actor, investigation = _seed_planning(engine)
    command = _command(investigation)
    first = _service(engine).create_investigation_plan(actor, command)
    replay = _service(engine).create_investigation_plan(actor, command)

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.plan == first.plan
    assert len(first.plan.capabilities) == 10
    assert sum(len(item.connector_options) for item in first.plan.capabilities) == 2
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert (
            unit_of_work.investigation_plans.get_by_id(actor.workspace_id, first.plan.id)
            == first.plan
        )
        assert (
            unit_of_work.investigation_plans.get_by_investigation(
                actor.workspace_id, investigation.id
            )
            == first.plan
        )
        assert (
            unit_of_work.investigation_plans.get_by_command(actor.workspace_id, command.command_id)
            == first.plan
        )
        assert unit_of_work.investigation_plans.get_by_id(WorkspaceId.new(), first.plan.id) is None
    with engine.connect() as connection:
        state = connection.execute(
            sa.select(investigation_table.c.state, investigation_table.c.state_version).where(
                investigation_table.c.id == investigation.id.value
            )
        ).one()
        assert state == (InvestigationState.PLANNING.value, 4)
        assert connection.scalar(sa.select(sa.func.count()).select_from(audit_event_table)) == 1


@pytest.mark.parametrize(
    "state",
    [
        InvestigationState.PLANNING,
        InvestigationState.COLLECTING,
        InvestigationState.NORMALIZING,
        InvestigationState.VERIFYING,
        InvestigationState.ANALYZING,
        InvestigationState.WAITING_FOR_REVIEW,
        InvestigationState.COMPLETED,
        InvestigationState.PARTIALLY_COMPLETED,
        InvestigationState.FAILED,
        InvestigationState.CANCELLED,
    ],
)
def test_all_repository_reads_and_command_replay_survive_lifecycle_advancement(
    engine: Engine,
    state: InvestigationState,
) -> None:
    actor, investigation = _seed_planning(engine, f"advanced-{state.value.lower()}")
    command = _command(investigation)
    created = _service(engine).create_investigation_plan(actor, command)
    completed_at = NOW if state in TERMINAL_INVESTIGATION_STATES else None
    with engine.begin() as connection:
        connection.execute(
            sa.update(investigation_table)
            .where(investigation_table.c.id == investigation.id.value)
            .values(state=state.value, state_version=5, completed_at=completed_at)
        )

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        repository = unit_of_work.investigation_plans
        assert repository.get_by_id(actor.workspace_id, created.plan.id) == created.plan
        assert repository.get_by_investigation(actor.workspace_id, investigation.id) == created.plan
        assert repository.get_by_command(actor.workspace_id, command.command_id) == created.plan

    replay = _service(engine).create_investigation_plan(actor, command)
    assert replay.replayed is True
    assert replay.plan == created.plan
    with engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(audit_event_table)) == 1


@pytest.mark.parametrize(
    ("state", "state_version", "confirmed_company_id"),
    [
        (InvestigationState.IDENTIFYING, 5, None),
        (InvestigationState.PLANNING, 3, "original"),
    ],
)
def test_repository_rejects_earlier_state_or_version_regression(
    engine: Engine,
    state: InvestigationState,
    state_version: int,
    confirmed_company_id: str | None,
) -> None:
    actor, investigation = _seed_planning(engine, f"invalid-{state.value.lower()}")
    created = _service(engine).create_investigation_plan(actor, _command(investigation))
    persisted_company_id = (
        investigation.confirmed_company_id.value
        if confirmed_company_id == "original" and investigation.confirmed_company_id is not None
        else None
    )
    with engine.begin() as connection:
        connection.execute(
            sa.update(investigation_table)
            .where(investigation_table.c.id == investigation.id.value)
            .values(
                state=state.value,
                state_version=state_version,
                confirmed_company_id=persisted_company_id,
            )
        )

    with PostgreSQLUnitOfWork(engine) as unit_of_work, pytest.raises(PersistenceDataError):
        unit_of_work.investigation_plans.get_by_id(actor.workspace_id, created.plan.id)


def test_repository_rejects_confirmed_company_swap(engine: Engine) -> None:
    actor, investigation = _seed_planning(engine, "company-swap")
    created = _service(engine).create_investigation_plan(actor, _command(investigation))
    replacement = Company(
        id=CompanyId.new(),
        workspace_id=actor.workspace_id,
        legal_name="Empresa Diferente S.A.",
        country_code=CountryCode("BR"),
        status=CompanyStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.companies.add(replacement)
        unit_of_work.commit()
    with engine.begin() as connection:
        connection.execute(
            sa.update(investigation_table)
            .where(investigation_table.c.id == investigation.id.value)
            .values(
                state=InvestigationState.COLLECTING.value,
                state_version=5,
                confirmed_company_id=replacement.id.value,
            )
        )

    with PostgreSQLUnitOfWork(engine) as unit_of_work, pytest.raises(PersistenceDataError):
        unit_of_work.investigation_plans.get_by_id(actor.workspace_id, created.plan.id)


def test_repository_rejects_reintroduced_active_candidate_batch(engine: Engine) -> None:
    actor, investigation = _seed_planning(engine, "active-batch")
    created = _service(engine).create_investigation_plan(actor, _command(investigation))
    batch_id = uuid4()
    digest = "a" * 64
    with engine.begin() as connection:
        connection.execute(
            sa.insert(entity_candidate_batch_table).values(
                id=batch_id,
                workspace_id=actor.workspace_id.value,
                investigation_id=investigation.id.value,
                batch_version=1,
                input_digest=digest,
                policy_id="ENTITY_MATCHING_V1",
                policy_version=1,
                policy_digest=digest,
                policy_snapshot={},
                command_id=uuid4(),
                created_by=actor.user_id.value,
                created_at=NOW,
                submission_digest=digest,
                evaluation_digest=digest,
            )
        )
        connection.execute(
            sa.update(investigation_table)
            .where(investigation_table.c.id == investigation.id.value)
            .values(
                state=InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION.value,
                state_version=5,
                confirmed_company_id=None,
                active_candidate_batch_id=batch_id,
            )
        )

    with PostgreSQLUnitOfWork(engine) as unit_of_work, pytest.raises(PersistenceDataError):
        unit_of_work.investigation_plans.get_by_id(actor.workspace_id, created.plan.id)


@pytest.mark.parametrize(
    "target",
    ["policy", "digest", "capability", "dependency", "option", "cost"],
)
def test_repository_fails_closed_on_persisted_tampering(engine: Engine, target: str) -> None:
    actor, investigation = _seed_planning(engine, f"tamper-{target}")
    result = _service(engine).create_investigation_plan(actor, _command(investigation))
    with engine.begin() as connection:
        if target == "policy":
            connection.execute(
                sa.update(investigation_plan_table)
                .where(investigation_plan_table.c.id == result.plan.id.value)
                .values(planning_policy_snapshot="{}")
            )
        elif target == "digest":
            connection.execute(
                sa.update(investigation_plan_table)
                .where(investigation_plan_table.c.id == result.plan.id.value)
                .values(plan_digest="b" * 64)
            )
        elif target == "capability":
            connection.execute(
                sa.update(planned_capability_table)
                .where(
                    planned_capability_table.c.plan_id == result.plan.id.value,
                    planned_capability_table.c.capability == "DOCUMENTS",
                )
                .values(priority=101)
            )
        elif target == "dependency":
            connection.execute(
                sa.update(planned_capability_table)
                .where(
                    planned_capability_table.c.plan_id == result.plan.id.value,
                    planned_capability_table.c.capability == "OWNERSHIP",
                )
                .values(dependencies=[])
            )
        elif target == "option":
            connection.execute(
                sa.update(planned_connector_option_table)
                .where(planned_connector_option_table.c.plan_id == result.plan.id.value)
                .values(connector_version="1.3.0")
            )
        else:
            connection.execute(
                sa.update(planned_connector_option_table)
                .where(planned_connector_option_table.c.plan_id == result.plan.id.value)
                .values(
                    estimated_cost_kind="KNOWN",
                    estimated_cost_amount=1,
                    estimated_cost_currency="BRL",
                )
            )
    with PostgreSQLUnitOfWork(engine) as unit_of_work, pytest.raises(PersistenceDataError):
        unit_of_work.investigation_plans.get_by_id(actor.workspace_id, result.plan.id)


def test_distinct_concurrent_commands_create_exactly_one_plan(engine: Engine) -> None:
    actor, investigation = _seed_planning(engine, "concurrent")
    barrier = Barrier(2)

    def invoke() -> object:
        barrier.wait()
        return _service(engine).create_investigation_plan(actor, _command(investigation))

    outcomes: list[object] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(invoke) for _ in range(2)]
        for future in futures:
            try:
                outcomes.append(future.result(timeout=20))
            except InvestigationPlanAlreadyExistsError as error:
                outcomes.append(error)

    assert sum(not isinstance(value, Exception) for value in outcomes) == 1
    assert sum(isinstance(value, InvestigationPlanAlreadyExistsError) for value in outcomes) == 1
    with engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(investigation_plan_table)) == 1
        )
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(planned_capability_table))
            == 10
        )
