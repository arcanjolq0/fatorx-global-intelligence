"""F4.5 PostgreSQL manifest round-trip, replay, tamper, tenant, and concurrency."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
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
from intelligence.application.collection_activation import StartInvestigationCollection
from intelligence.application.errors import (
    CollectionActivationDeadlineError,
    ConcurrentInvestigationUpdateError,
    PersistenceDataError,
)
from intelligence.application.services.collection_activation import CollectionActivationService
from intelligence.domain.identifiers import CorrelationId, InvestigationCommandId, WorkspaceId
from intelligence.domain.investigations import Investigation, InvestigationState
from intelligence.infrastructure.persistence.postgresql.engine import create_postgresql_engine
from intelligence.infrastructure.persistence.postgresql.repositories import (
    PostgreSQLCollectionRunRepository,
)
from intelligence.infrastructure.persistence.postgresql.transaction_guard import (
    PostgreSQLTransactionGuard,
)
from intelligence.infrastructure.persistence.postgresql.unit_of_work import (
    PostgreSQLUnitOfWork,
    PostgreSQLUnitOfWorkFactory,
)
from intelligence.orchestration.collection_activation import (
    COLLECTION_ACTIVATION_V1,
    ready_operation_critical_path_seconds,
)
from intelligence.orchestration.planning import InvestigationPlan
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
                "TRUNCATE TABLE collection_operation_dependency, collection_operation, "
                "collection_run, planned_connector_option, planned_capability, "
                "investigation_plan, entity_resolution_decision, investigation_transition, "
                "audit_event, entity_candidate_dimension_score, entity_candidate, "
                "entity_candidate_batch, workspace_membership, user_account, investigation, "
                "company, workspace CASCADE"
            )
        )


def _seed_plan(engine: Engine) -> tuple[ActorContext, Investigation, InvestigationPlan]:
    actor, investigation = _seed_planning(engine, "f4.5")
    plan = (
        planning_service(engine)
        .create_investigation_plan(actor, planning_command(investigation))
        .plan
    )
    return actor, investigation, plan


def _command(
    investigation: Investigation,
    plan: InvestigationPlan,
    *,
    command_id: InvestigationCommandId | None = None,
) -> StartInvestigationCollection:
    return StartInvestigationCollection(
        command_id=command_id or InvestigationCommandId.new(),
        investigation_id=investigation.id,
        plan_id=plan.id,
        expected_state_version=investigation.state_version,
        activation_policy=COLLECTION_ACTIVATION_V1,
    )


def _service(engine: Engine) -> CollectionActivationService:
    return CollectionActivationService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW),
    )


def test_complete_manifest_round_trip_replay_and_tenant_isolation(engine: Engine) -> None:
    actor, investigation, plan = _seed_plan(engine)
    command = _command(investigation, plan)
    first = _service(engine).start_investigation_collection(actor, command)
    replay = _service(engine).start_investigation_collection(actor, command)

    assert replay.replayed
    assert replay.collection_run == first.collection_run
    assert len(first.collection_run.operations) == 2
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        current = unit_of_work.investigations.get(actor.workspace_id, investigation.id)
        assert current is not None
        assert current.state is InvestigationState.COLLECTING
        assert current.state_version == investigation.state_version + 1
        assert (
            unit_of_work.collection_runs.get_by_id(WorkspaceId.new(), first.collection_run.id)
            is None
        )
        assert (
            unit_of_work.collection_runs.get_by_command(actor.workspace_id, command.command_id)
            == first.collection_run
        )
        assert (
            unit_of_work.collection_runs.get_by_investigation(actor.workspace_id, investigation.id)
            == first.collection_run
        )
        assert (
            unit_of_work.collection_runs.get_by_id(actor.workspace_id, first.collection_run.id)
            == first.collection_run
        )
        unit_of_work.commit()
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT count(*) FROM collection_run")) == 1
        assert connection.scalar(sa.text("SELECT count(*) FROM collection_operation")) == 2
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM audit_event "
                    "WHERE action_code = 'INVESTIGATION_COLLECTION_STARTED'"
                )
            )
            == 1
        )


def test_persisted_digest_tampering_fails_closed(engine: Engine) -> None:
    actor, investigation, plan = _seed_plan(engine)
    run = (
        _service(engine)
        .start_investigation_collection(actor, _command(investigation, plan))
        .collection_run
    )
    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE collection_run SET run_digest = :digest WHERE id = :id"),
            {"digest": "f" * 64, "id": run.id.value},
        )
    with pytest.raises(PersistenceDataError), PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.collection_runs.get_by_id(actor.workspace_id, run.id)


@pytest.mark.parametrize(("remaining_delta", "succeeds"), [(1, True), (0, True), (-1, False)])
def test_activation_revalidates_remaining_deadline_in_postgresql(
    engine: Engine,
    remaining_delta: int,
    succeeds: bool,
) -> None:
    actor, investigation, plan = _seed_plan(engine)
    assert investigation.deadline_at is not None
    activated_at = investigation.deadline_at - timedelta(
        seconds=ready_operation_critical_path_seconds(plan) + remaining_delta
    )
    service = CollectionActivationService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(activated_at)
    )

    if succeeds:
        result = service.start_investigation_collection(actor, _command(investigation, plan))
        assert result.collection_run.created_at == activated_at
    else:
        with pytest.raises(CollectionActivationDeadlineError):
            service.start_investigation_collection(actor, _command(investigation, plan))
        with engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT count(*) FROM collection_run")) == 0
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM investigation_transition "
                        "WHERE command_type = 'START_COLLECTION'"
                    )
                )
                == 0
            )
            assert (
                connection.scalar(
                    sa.text("SELECT state FROM investigation WHERE id = :id"),
                    {"id": investigation.id.value},
                )
                == InvestigationState.PLANNING.value
            )


def test_run_without_transition_fails_all_public_reads(engine: Engine) -> None:
    actor, investigation, plan = _seed_plan(engine)
    command = _command(investigation, plan)
    run = _service(engine).start_investigation_collection(actor, command).collection_run
    with engine.begin() as connection:
        connection.execute(
            sa.text("DELETE FROM investigation_transition WHERE command_id = :command_id"),
            {"command_id": command.command_id.value},
        )

    with pytest.raises(PersistenceDataError), PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.collection_runs.get_by_command(actor.workspace_id, command.command_id)
    with pytest.raises(PersistenceDataError), PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.collection_runs.get_by_investigation(actor.workspace_id, investigation.id)
    with pytest.raises(PersistenceDataError), PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.collection_runs.get_by_id(actor.workspace_id, run.id)


def test_transition_without_run_fails_all_public_reads_inside_deferred_transaction(
    engine: Engine,
) -> None:
    actor, investigation, plan = _seed_plan(engine)
    command = _command(investigation, plan)
    run = _service(engine).start_investigation_collection(actor, command).collection_run
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            sa.text(
                "ALTER TABLE investigation_transition DROP CONSTRAINT "
                "fk_investigation_transition_collection_run_scope"
            )
        )
        connection.execute(sa.text("DELETE FROM collection_operation_dependency"))
        connection.execute(sa.text("DELETE FROM collection_operation"))
        connection.execute(
            sa.text("DELETE FROM collection_run WHERE id = :id"), {"id": run.id.value}
        )
        repository = PostgreSQLCollectionRunRepository(
            PostgreSQLTransactionGuard(connection, transaction)
        )
        with pytest.raises(PersistenceDataError):
            repository.get_by_command(actor.workspace_id, command.command_id)
        with pytest.raises(PersistenceDataError):
            repository.get_by_investigation(actor.workspace_id, investigation.id)
        with pytest.raises(PersistenceDataError):
            repository.get_by_id(actor.workspace_id, run.id)
        transaction.rollback()


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("occurred_at", None),
        ("run_id", uuid4()),
        ("company_id", uuid4()),
        ("plan_id", uuid4()),
        ("operation_count", None),
        ("policy_id", None),
        ("policy_version", None),
    ],
)
def test_historical_transition_divergence_fails_closed(
    engine: Engine,
    mutation: str,
    value: object | None,
) -> None:
    actor, investigation, plan = _seed_plan(engine)
    run = (
        _service(engine)
        .start_investigation_collection(actor, _command(investigation, plan))
        .collection_run
    )
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(sa.text("SET CONSTRAINTS ALL DEFERRED"))
        statements = {
            "occurred_at": sa.text(
                "UPDATE investigation_transition "
                "SET occurred_at = occurred_at + interval '1 second' "
                "WHERE collection_run_id = :run_id"
            ),
            "run_id": sa.text(
                "UPDATE investigation_transition SET collection_run_id = :value "
                "WHERE collection_run_id = :run_id"
            ),
            "company_id": sa.text(
                "UPDATE investigation_transition SET collection_company_id = :value "
                "WHERE collection_run_id = :run_id"
            ),
            "plan_id": sa.text(
                "UPDATE investigation_transition SET collection_plan_id = :value "
                "WHERE collection_run_id = :run_id"
            ),
            "operation_count": sa.text(
                "UPDATE investigation_transition "
                "SET collection_operation_count = collection_operation_count - 1 "
                "WHERE collection_run_id = :run_id"
            ),
            "policy_id": sa.text(
                "UPDATE investigation_transition "
                "SET collection_activation_policy_id = 'COLLECTION_ACTIVATION_V2' "
                "WHERE collection_run_id = :run_id"
            ),
            "policy_version": sa.text(
                "UPDATE investigation_transition SET collection_activation_policy_version = 2 "
                "WHERE collection_run_id = :run_id"
            ),
        }
        connection.execute(
            statements[mutation],
            {"run_id": run.id.value, "value": value},
        )
        repository = PostgreSQLCollectionRunRepository(
            PostgreSQLTransactionGuard(connection, transaction)
        )
        with pytest.raises(PersistenceDataError):
            repository.get_by_id(actor.workspace_id, run.id)
        transaction.rollback()


def test_historical_transition_actor_divergence_fails_closed(engine: Engine) -> None:
    actor, investigation, plan = _seed_plan(engine)
    other_actor, _ = _seed_planning(engine, "f4.5-other-actor")
    run = (
        _service(engine)
        .start_investigation_collection(actor, _command(investigation, plan))
        .collection_run
    )
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            sa.text(
                "UPDATE investigation_transition SET actor_user_id = :actor_id "
                "WHERE collection_run_id = :run_id"
            ),
            {"actor_id": other_actor.user_id.value, "run_id": run.id.value},
        )
        repository = PostgreSQLCollectionRunRepository(
            PostgreSQLTransactionGuard(connection, transaction)
        )
        with pytest.raises(PersistenceDataError):
            repository.get_by_id(actor.workspace_id, run.id)
        transaction.rollback()


def test_two_distinct_commands_for_one_version_have_exactly_one_winner(
    engine: Engine,
) -> None:
    actor, investigation, plan = _seed_plan(engine)
    commands = (_command(investigation, plan), _command(investigation, plan))
    barrier = Barrier(2)

    def activate(command: StartInvestigationCollection) -> str:
        barrier.wait()
        try:
            _service(engine).start_investigation_collection(actor, command)
            return "won"
        except ConcurrentInvestigationUpdateError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(activate, commands))
    assert sorted(outcomes) == ["conflict", "won"]
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT count(*) FROM collection_run")) == 1
        assert connection.scalar(sa.text("SELECT count(*) FROM collection_operation")) == 2


def test_same_plan_and_run_are_not_visible_to_another_workspace(engine: Engine) -> None:
    actor, investigation, plan = _seed_plan(engine)
    run = (
        _service(engine)
        .start_investigation_collection(actor, _command(investigation, plan))
        .collection_run
    )
    other_actor = ActorContext(
        user_id=actor.user_id,
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert unit_of_work.collection_runs.get_by_id(other_actor.workspace_id, run.id) is None
        unit_of_work.commit()
