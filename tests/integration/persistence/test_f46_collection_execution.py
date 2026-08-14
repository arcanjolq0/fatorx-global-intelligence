"""F4.6 PostgreSQL ownership/completion round-trip and immutable-history tests."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.collection_execution import (
    CollectionExecutionResultRecord,
    ExecuteCollectionSearchOperation,
)
from intelligence.application.errors import PersistenceDataError
from intelligence.application.services.collection_execution import CollectionExecutionService
from intelligence.connectors.context import LocaleTag, MonotonicDeadline
from intelligence.connectors.enums import ConnectorCapability, ConnectorOutcomeStatus
from intelligence.connectors.simulated import (
    SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID,
    BusinessRegistryScenario,
    SimulatedBusinessRegistryConnector,
)
from intelligence.connectors.versions import SourcePolicyVersion
from intelligence.domain.identifiers import (
    InvestigationCommandId,
    WorkspaceId,
)
from intelligence.infrastructure.persistence.postgresql.engine import create_postgresql_engine
from intelligence.infrastructure.persistence.postgresql.unit_of_work import (
    PostgreSQLUnitOfWork,
    PostgreSQLUnitOfWorkFactory,
)
from intelligence.orchestration.collection_activation import CollectionRun
from tests.connectors.execution.doubles import (
    MutableCancellationSignal,
    execution_policy,
    operation_runner,
    run_async,
)
from tests.integration.persistence.test_f44_investigation_planning import NOW
from tests.integration.persistence.test_f45_collection_activation import (
    _command as activation_command,
)
from tests.integration.persistence.test_f45_collection_activation import (
    _seed_plan,
)
from tests.integration.persistence.test_f45_collection_activation import (
    _service as activation_service,
)
from tests.support.destructive_database import require_safe_destructive_database_url
from tests.unit.application.fakes import FakeClock

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])
REPOSITORY_ROOT = Path(__file__).parents[3]
F45_REVISION = "20260802_09"


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
                "TRUNCATE TABLE collection_operation_execution_result, "
                "collection_operation_execution, collection_operation_dependency, "
                "collection_operation, collection_run, planned_connector_option, "
                "planned_capability, investigation_plan, entity_resolution_decision, "
                "investigation_transition, audit_event, entity_candidate_dimension_score, "
                "entity_candidate, entity_candidate_batch, workspace_membership, "
                "user_account, investigation, company, workspace CASCADE"
            )
        )


def _seed_run(engine: Engine) -> tuple[ActorContext, CollectionRun]:
    actor, investigation, plan = _seed_plan(engine)
    run = (
        activation_service(engine)
        .start_investigation_collection(actor, activation_command(investigation, plan))
        .collection_run
    )
    return actor, run


def _execution_command(run: CollectionRun) -> ExecuteCollectionSearchOperation:
    operation = next(
        item for item in run.operations if item.capability is ConnectorCapability.COMPANY_REGISTRY
    )
    return ExecuteCollectionSearchOperation(
        command_id=InvestigationCommandId.new(),
        collection_run_id=run.id,
        collection_operation_id=operation.id,
        expected_run_digest=run.run_digest,
        expected_operation_digest=operation.operation_digest,
        source_policy_version=SourcePolicyVersion("synthetic-source-policy-1"),
        accepted_locales=(LocaleTag("pt-BR"),),
        execution_policy=execution_policy(estimated_attempt_cost=None),
    )


def _execute(
    engine: Engine,
    actor: ActorContext,
    command: ExecuteCollectionSearchOperation,
) -> CollectionExecutionResultRecord:
    connector = SimulatedBusinessRegistryConnector(BusinessRegistryScenario.SUCCESS)
    service = CollectionExecutionService(
        unit_of_work_factory=PostgreSQLUnitOfWorkFactory(engine),
        authorizer=ContextualAuthorizer(),
        clock=FakeClock(NOW),
        runner=operation_runner(),
        admitted_connector_ids=frozenset({SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID}),
    )
    return run_async(
        service.execute_search(
            actor,
            command,
            connector=connector,
            monotonic_deadline=MonotonicDeadline(1_000.0),
            cancellation_signal=MutableCancellationSignal(),
        )
    )


def _constraint_names(items: Iterable[Mapping[str, object]]) -> set[str]:
    return {name for item in items if isinstance((name := item.get("name")), str)}


def test_round_trip_replay_tenant_scope_and_redacted_schema(engine: Engine) -> None:
    actor, run = _seed_run(engine)
    command = _execution_command(run)

    first = _execute(engine, actor, command)
    replay = _execute(engine, actor, command)

    assert replay == first
    assert first.outcome_status is ConnectorOutcomeStatus.SUCCEEDED
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert (
            unit_of_work.collection_executions.get_result_by_command(
                actor.workspace_id, command.command_id
            )
            == first
        )
        assert (
            unit_of_work.collection_executions.get_result_by_command(
                WorkspaceId.new(), command.command_id
            )
            is None
        )
        unit_of_work.commit()
    inspector = sa.inspect(engine)
    result_columns = {
        item["name"] for item in inspector.get_columns("collection_operation_execution_result")
    }
    assert not {"items", "payload", "observations", "artifacts"} & result_columns
    with engine.connect() as connection:
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM collection_operation_execution")) == 1
        )
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM collection_operation_execution_result"))
            == 1
        )


def test_result_digest_tampering_fails_closed(engine: Engine) -> None:
    actor, run = _seed_run(engine)
    command = _execution_command(run)
    _execute(engine, actor, command)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE collection_operation_execution_result "
                "SET result_digest = :digest WHERE command_id = :command_id"
            ),
            {"digest": "f" * 64, "command_id": command.command_id.value},
        )

    with pytest.raises(PersistenceDataError), PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.collection_executions.get_result_by_command(
            actor.workspace_id, command.command_id
        )


def test_schema_constraints_and_downgrade_refusal(engine: Engine) -> None:
    inspector = sa.inspect(engine)
    assert {
        "ck_collection_operation_execution_digests_format",
        "ck_collection_operation_execution_schema_version_supported",
    } <= _constraint_names(inspector.get_check_constraints("collection_operation_execution"))
    assert {
        "ck_collection_operation_execution_result_digests_format",
        "ck_collection_operation_execution_result_usage_cost_valid",
    } <= _constraint_names(inspector.get_check_constraints("collection_operation_execution_result"))
    actor, run = _seed_run(engine)
    _execute(engine, actor, _execution_command(run))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE collection_operation_execution SET accepted_locales = ARRAY[]::varchar[]"
            )
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE collection_operation_execution_result "
                "SET usage_cost_amount = 'NaN'::numeric, "
                "usage_cost_currency = 'USD', usage_cost_kind = 'KNOWN'"
            )
        )
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))

    with pytest.raises(RuntimeError, match="collection executions exist"):
        alembic_command.downgrade(config, F45_REVISION)
