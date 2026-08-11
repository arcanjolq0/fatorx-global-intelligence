"""F4.1 lifecycle atomicity, durable replay, CAS, and real concurrency."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy.engine import Engine

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import (
    ConcurrentInvestigationUpdateError,
    PersistenceError,
    ResourceNotFoundError,
)
from intelligence.application.investigation_lifecycle import (
    StartIdentification,
)
from intelligence.application.services.investigations import InvestigationService
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
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
from intelligence.domain.investigations import Investigation, InvestigationState
from intelligence.domain.workspaces import Workspace, WorkspaceStatus
from intelligence.infrastructure.persistence.postgresql.engine import (
    create_postgresql_engine,
)
from intelligence.infrastructure.persistence.postgresql.tables import (
    audit_event_table,
    investigation_table,
    investigation_transition_table,
)
from intelligence.infrastructure.persistence.postgresql.unit_of_work import (
    PostgreSQLUnitOfWork,
    PostgreSQLUnitOfWorkFactory,
)
from tests.support.destructive_database import require_safe_destructive_database_url
from tests.unit.application.fakes import FakeClock

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])

REPOSITORY_ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 7, 29, 18, tzinfo=UTC)


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
                "TRUNCATE TABLE investigation_transition, audit_event, "
                "workspace_membership, user_account, investigation, company, workspace CASCADE"
            )
        )


def _input(name: str = "Empresa Exemplo S.A.") -> IdentificationInput:
    return IdentificationInput(
        legal_name=OriginalAndNormalizedText(
            original_value=name,
            normalized_value=name.casefold(),
        )
    )


def _seed(
    engine: Engine,
    *,
    label: str = "tenant-a",
) -> tuple[ActorContext, Investigation]:
    workspace_id = WorkspaceId.new()
    user_id = UserId.new()
    actor = ActorContext(
        user_id=user_id,
        workspace_id=workspace_id,
        correlation_id=CorrelationId.new(),
    )
    created_at = NOW - timedelta(days=1)
    investigation = Investigation(
        id=InvestigationId.new(),
        workspace_id=workspace_id,
        requested_by=user_id,
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        created_at=created_at,
    )
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(
            Workspace(
                id=workspace_id,
                name=label,
                status=WorkspaceStatus.ACTIVE,
                retention_policy_version="2026-01",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        unit_of_work.users.add(
            UserAccount(
                id=user_id,
                email=EmailAddress(f"{user_id.value}@example.test"),
                display_name=label,
                status=UserAccountStatus.ACTIVE,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        unit_of_work.memberships.add(
            WorkspaceMembership(
                id=MembershipId.new(),
                workspace_id=workspace_id,
                user_id=user_id,
                role=MembershipRole.ANALYST,
                status=MembershipStatus.ACTIVE,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        unit_of_work.investigations.add(investigation)
        unit_of_work.commit()
    return actor, investigation


def _service(
    engine: Engine,
    factory: Callable[[], PostgreSQLUnitOfWork] | None = None,
) -> InvestigationService:
    return InvestigationService(
        factory or PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW),
    )


def _command(
    investigation: Investigation,
    *,
    command_id: InvestigationCommandId | None = None,
    name: str = "Empresa Exemplo S.A.",
) -> StartIdentification:
    return StartIdentification(
        command_id=command_id or InvestigationCommandId.new(),
        investigation_id=investigation.id,
        expected_state_version=1,
        identification_input=_input(name),
    )


def test_start_round_trip_and_replay_are_durable_and_redacted(engine: Engine) -> None:
    actor, investigation = _seed(engine)
    command = _command(investigation)

    first = _service(engine).start_identification(actor, command)
    replay = _service(engine).start_identification(actor, command)

    assert not first.replayed and replay.replayed
    assert replay.state is InvestigationState.IDENTIFYING
    assert replay.state_version == first.state_version == 2
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        restored = unit_of_work.investigations.get(actor.workspace_id, investigation.id)
        record = unit_of_work.investigation_transitions.get_by_command(
            actor.workspace_id,
            command.command_id,
        )
        unit_of_work.commit()
    assert restored is not None
    assert restored.identification_input == command.identification_input
    assert restored.started_at == NOW and restored.completed_at is None
    assert record is not None and record.version_after == 2

    with engine.connect() as connection:
        audits = list(connection.execute(sa.select(audit_event_table)).mappings())
        persisted_snapshot = connection.execute(
            sa.select(investigation_table.c.input_snapshot).where(
                investigation_table.c.id == investigation.id.value
            )
        ).scalar_one()
    assert len(audits) == 1
    assert persisted_snapshot["legal_name"]["original_value"] == "Empresa Exemplo S.A."
    assert "Empresa Exemplo" not in repr(audits[0])


def test_cross_tenant_command_lookup_and_resource_access_are_isolated(engine: Engine) -> None:
    actor, investigation = _seed(engine, label="tenant-owner")
    other_actor, _ = _seed(engine, label="tenant-other")
    command = _command(investigation)
    _service(engine).start_identification(actor, command)

    with pytest.raises(ResourceNotFoundError):
        _service(engine).start_identification(other_actor, command)

    with engine.connect() as connection:
        rows = list(connection.execute(sa.select(investigation_transition_table)).mappings())
    assert len(rows) == 1
    assert rows[0]["workspace_id"] == actor.workspace_id.value


def test_repository_compare_and_swap_rejects_stale_and_cross_tenant_versions(
    engine: Engine,
) -> None:
    actor, investigation = _seed(engine)
    transitioned = investigation.start_identification(
        identification_input=_input(),
        occurred_at=NOW,
    ).investigation

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert unit_of_work.investigations.update_if_version(
            transitioned,
            expected_state_version=1,
        )
        unit_of_work.commit()
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert not unit_of_work.investigations.update_if_version(
            transitioned,
            expected_state_version=1,
        )
        unit_of_work.rollback()

    alien = Investigation.reconstitute(
        id=transitioned.id,
        workspace_id=WorkspaceId.new(),
        requested_by=transitioned.requested_by,
        profile_code=transitioned.profile_code,
        country_code=transitioned.country_code,
        state=transitioned.state,
        state_version=transitioned.state_version,
        identification_input=transitioned.identification_input,
        confirmed_company_id=transitioned.confirmed_company_id,
        budget=transitioned.budget,
        deadline_at=transitioned.deadline_at,
        started_at=transitioned.started_at,
        completed_at=transitioned.completed_at,
        created_at=transitioned.created_at,
    )
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert not unit_of_work.investigations.update_if_version(
            alien,
            expected_state_version=1,
        )
        unit_of_work.rollback()
    assert actor.workspace_id != alien.workspace_id


class FailingCommitUnitOfWork(PostgreSQLUnitOfWork):
    """Inject failure after CAS, ledger, and audit have been staged."""

    def commit(self) -> None:
        raise PersistenceError("Injected commit failure.")


def test_commit_failure_rolls_back_state_ledger_and_audit(engine: Engine) -> None:
    actor, investigation = _seed(engine)

    with pytest.raises(PersistenceError, match="Injected"):
        _service(engine, lambda: FailingCommitUnitOfWork(engine)).start_identification(
            actor,
            _command(investigation),
        )

    with engine.connect() as connection:
        row = connection.execute(
            sa.select(investigation_table.c.state, investigation_table.c.state_version).where(
                investigation_table.c.id == investigation.id.value
            )
        ).one()
        transition_count = connection.scalar(
            sa.select(sa.func.count()).select_from(investigation_transition_table)
        )
        audit_count = connection.scalar(sa.select(sa.func.count()).select_from(audit_event_table))
    assert row == (InvestigationState.CREATED.value, 1)
    assert transition_count == audit_count == 0


def test_two_distinct_commands_for_same_version_have_one_real_winner(engine: Engine) -> None:
    actor, investigation = _seed(engine)
    commands = (
        _command(investigation, name="Empresa Um"),
        _command(investigation, name="Empresa Dois"),
    )
    barrier = Barrier(2)

    def execute(item: StartIdentification) -> str:
        barrier.wait()
        try:
            _service(engine).start_identification(actor, item)
        except ConcurrentInvestigationUpdateError:
            return "conflict"
        return "success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(execute, commands))

    assert sorted(outcomes) == ["conflict", "success"]
    with engine.connect() as connection:
        state_version = connection.scalar(
            sa.select(investigation_table.c.state_version).where(
                investigation_table.c.id == investigation.id.value
            )
        )
        transition_count = connection.scalar(
            sa.select(sa.func.count()).select_from(investigation_transition_table)
        )
    assert state_version == 2
    assert transition_count == 1


def test_same_command_concurrently_has_one_effect_and_one_replay(engine: Engine) -> None:
    actor, investigation = _seed(engine)
    command = _command(investigation)
    barrier = Barrier(2)

    def execute() -> bool:
        barrier.wait()
        return _service(engine).start_identification(actor, command).replayed

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(execute) for _ in range(2)]
        replay_flags = [future.result(timeout=20) for future in futures]

    assert sorted(replay_flags) == [False, True]
    with engine.connect() as connection:
        transition_count = connection.scalar(
            sa.select(sa.func.count()).select_from(investigation_transition_table)
        )
        success_audit_count = connection.scalar(
            sa.select(sa.func.count()).select_from(audit_event_table)
        )
    assert transition_count == success_audit_count == 1
