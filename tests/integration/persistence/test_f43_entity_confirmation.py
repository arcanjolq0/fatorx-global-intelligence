"""F4.3 real PostgreSQL round-trip, replay, integrity, and tenant isolation."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from typing import cast

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.entity_confirmation import (
    ConfirmEntityCandidate,
    EntityConfirmationReason,
)
from intelligence.application.errors import (
    ConcurrentInvestigationUpdateError,
    PersistenceDataError,
    PersistenceError,
)
from intelligence.application.investigation_lifecycle import (
    CancelInvestigation,
    InvestigationCancellationReason,
    RequestEntityConfirmation,
)
from intelligence.application.ports.unit_of_work import UnitOfWork
from intelligence.application.services.entity_confirmation import EntityConfirmationService
from intelligence.application.services.investigations import InvestigationService
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
    CorporateDomainInput,
    IdentificationInput,
    OriginalAndNormalizedText,
)
from intelligence.domain.investigations import Investigation, InvestigationState
from intelligence.domain.workspaces import Workspace, WorkspaceStatus
from intelligence.entity_resolution.contracts import (
    CandidateIdentitySnapshot,
    CandidateOriginSnapshot,
    CandidateSubmissionBatch,
    EntityCandidateInput,
    SourceRegistrationStatus,
)
from intelligence.entity_resolution.materialization import COMPANY_MATERIALIZATION_V1
from intelligence.entity_resolution.policy import INITIAL_MATCH_POLICY
from intelligence.infrastructure.persistence.postgresql.engine import create_postgresql_engine
from intelligence.infrastructure.persistence.postgresql.tables import (
    audit_event_table,
    company_table,
    entity_resolution_decision_table,
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
NOW = datetime(2026, 8, 1, 15, tzinfo=UTC)


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
                "TRUNCATE TABLE entity_resolution_decision, investigation_transition, "
                "audit_event, entity_candidate_dimension_score, entity_candidate, "
                "entity_candidate_batch, workspace_membership, user_account, investigation, "
                "company, workspace CASCADE"
            )
        )


def _text(value: str) -> OriginalAndNormalizedText:
    return OriginalAndNormalizedText(original_value=value, normalized_value=value.casefold())


def _input() -> IdentificationInput:
    return IdentificationInput(legal_name=_text("Empresa Exemplo S.A."))


def _candidate() -> EntityCandidateInput:
    return EntityCandidateInput(
        candidate_key="candidate-1",
        identity=CandidateIdentitySnapshot(
            legal_name=_text("Empresa Exemplo S.A."),
            trade_name=_text("Empresa Exemplo"),
            country_code=CountryCode("BR"),
            corporate_domain=CorporateDomainInput(
                original_value="EXAMPLE.COM",
                normalized_value="example.com",
            ),
            registry_status=SourceRegistrationStatus.ACTIVE,
        ),
        origin=CandidateOriginSnapshot(
            source_id="SYNTHETIC_SOURCE",
            connector_id="synthetic.source",
            connector_version="1.0.0",
            source_candidate_reference="opaque-candidate-1",
            collected_at=NOW - timedelta(minutes=2),
        ),
    )


def _seed_waiting(engine: Engine, label: str = "tenant-a") -> tuple[ActorContext, Investigation]:
    actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )
    created_at = NOW - timedelta(days=1)
    identifying = Investigation.reconstitute(
        id=InvestigationId.new(),
        workspace_id=actor.workspace_id,
        requested_by=actor.user_id,
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        created_at=created_at,
        state=InvestigationState.IDENTIFYING,
        state_version=2,
        started_at=created_at + timedelta(minutes=1),
        identification_input=_input(),
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
                display_name=label,
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
        unit_of_work.investigations.add(identifying)
        unit_of_work.commit()
    identification_input = identifying.identification_input
    assert identification_input is not None
    request = RequestEntityConfirmation(
        command_id=InvestigationCommandId.new(),
        investigation_id=identifying.id,
        expected_state_version=2,
        candidate_batch=CandidateSubmissionBatch(
            input_digest=identification_input.digest,
            candidates=(_candidate(),),
        ),
        matching_policy=INITIAL_MATCH_POLICY,
    )
    InvestigationService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW - timedelta(minutes=1)),
    ).request_entity_confirmation(actor, request)
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        waiting = unit_of_work.investigations.get(actor.workspace_id, identifying.id)
        unit_of_work.commit()
    assert waiting is not None
    return actor, waiting


def _command(
    engine: Engine,
    actor: ActorContext,
    waiting: Investigation,
    *,
    command_id: InvestigationCommandId | None = None,
) -> ConfirmEntityCandidate:
    assert waiting.active_candidate_batch_id is not None
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        batch = unit_of_work.entity_candidate_batches.get(
            actor.workspace_id,
            waiting.active_candidate_batch_id,
        )
        unit_of_work.commit()
    assert batch is not None
    return ConfirmEntityCandidate(
        command_id=command_id or InvestigationCommandId.new(),
        investigation_id=waiting.id,
        expected_state_version=waiting.state_version,
        candidate_batch_id=batch.id,
        candidate_id=batch.candidates[0].id,
        review_reason=EntityConfirmationReason.MANUAL_OVERRIDE,
        materialization_policy=COMPANY_MATERIALIZATION_V1,
    )


def test_round_trip_atomic_confirmation_and_durable_replay(engine: Engine) -> None:
    actor, waiting = _seed_waiting(engine)
    command = _command(engine, actor, waiting)
    clock = FakeClock(NOW)
    service = EntityConfirmationService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), clock
    )

    result = service.confirm_entity_candidate(actor, command)
    replay = EntityConfirmationService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        _FailingClock(),
    ).confirm_entity_candidate(actor, command)

    assert not result.replayed
    assert replay.replayed
    assert replay.company == result.company
    assert replay.decision == result.decision
    assert result.company.legal_name == "Empresa Exemplo S.A."
    assert result.company.trade_name == "Empresa Exemplo"
    assert result.company.official_domain == "example.com"
    with engine.connect() as connection:
        investigation = (
            connection.execute(
                sa.select(investigation_table).where(investigation_table.c.id == waiting.id.value)
            )
            .mappings()
            .one()
        )
        assert investigation["state"] == "PLANNING"
        assert investigation["state_version"] == waiting.state_version + 1
        assert investigation["confirmed_company_id"] == result.company.id.value
        assert investigation["active_candidate_batch_id"] is None
        assert connection.scalar(sa.select(sa.func.count()).select_from(company_table)) == 1
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(entity_resolution_decision_table)
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(investigation_transition_table)
            )
            == 2
        )
        confirmation_audits = (
            connection.execute(
                sa.select(audit_event_table.c.outcome, audit_event_table.c.reason_code).where(
                    audit_event_table.c.action_code == "INVESTIGATION_ENTITY_CANDIDATE_CONFIRMED"
                )
            )
            .mappings()
            .all()
        )
        assert sum(item["outcome"] == "SUCCESS" for item in confirmation_audits) == 1
        failure_audits = [item for item in confirmation_audits if item["outcome"] == "FAILURE"]
        assert len(failure_audits) <= 1
        if failure_audits:
            assert failure_audits[0]["reason_code"] == "STATE_VERSION_CONFLICT"


def test_cancelled_confirmation_remains_loadable_and_replayable(engine: Engine) -> None:
    actor, waiting = _seed_waiting(engine)
    command = _command(engine, actor, waiting)
    result = EntityConfirmationService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).confirm_entity_candidate(actor, command)
    cancellation = InvestigationService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW + timedelta(minutes=1)),
    ).cancel_investigation(
        actor,
        CancelInvestigation(
            command_id=InvestigationCommandId.new(),
            investigation_id=waiting.id,
            expected_state_version=waiting.state_version + 1,
            reason=InvestigationCancellationReason.USER_REQUESTED,
        ),
    )

    replay = EntityConfirmationService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        _FailingClock(),
    ).confirm_entity_candidate(actor, command)

    assert cancellation.state is InvestigationState.CANCELLED
    assert cancellation.state_version == waiting.state_version + 2
    assert replay.replayed and replay.decision == result.decision
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        by_command = unit_of_work.entity_resolution_decisions.get_by_command(
            actor.workspace_id,
            command.command_id,
        )
        by_investigation = unit_of_work.entity_resolution_decisions.get_by_investigation(
            actor.workspace_id,
            waiting.id,
        )
        by_id = unit_of_work.entity_resolution_decisions.get_by_id(
            actor.workspace_id,
            result.decision.id,
        )
        current = unit_of_work.investigations.get(actor.workspace_id, waiting.id)
        unit_of_work.commit()
    assert by_command == by_investigation == by_id == result.decision
    assert current is not None
    assert current.state is InvestigationState.CANCELLED
    assert current.state_version == waiting.state_version + 2
    assert current.confirmed_company_id == result.company.id
    assert current.active_candidate_batch_id is None
    with engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(company_table)) == 1
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(entity_resolution_decision_table)
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(investigation_transition_table)
            )
            == 3
        )
        assert connection.scalar(sa.select(sa.func.count()).select_from(audit_event_table)) == 3


@pytest.mark.parametrize(
    "state",
    [
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
def test_decision_repository_accepts_every_later_persisted_state(
    engine: Engine,
    state: InvestigationState,
) -> None:
    actor, waiting = _seed_waiting(engine)
    command = _command(engine, actor, waiting)
    result = EntityConfirmationService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).confirm_entity_candidate(actor, command)
    terminal = state in {
        InvestigationState.COMPLETED,
        InvestigationState.PARTIALLY_COMPLETED,
        InvestigationState.FAILED,
        InvestigationState.CANCELLED,
    }
    with engine.begin() as connection:
        connection.execute(
            sa.update(investigation_table)
            .where(investigation_table.c.id == waiting.id.value)
            .values(
                state=state.value,
                state_version=waiting.state_version + 2,
                completed_at=NOW + timedelta(minutes=1) if terminal else None,
            )
        )

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        restored = unit_of_work.entity_resolution_decisions.get_by_command(
            actor.workspace_id,
            command.command_id,
        )
        unit_of_work.commit()
    assert restored == result.decision


def test_decision_repository_rejects_regression_company_swap_and_active_batch(
    engine: Engine,
) -> None:
    actor, waiting = _seed_waiting(engine)
    command = _command(engine, actor, waiting)
    result = EntityConfirmationService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).confirm_entity_candidate(actor, command)

    with engine.begin() as connection:
        connection.execute(
            sa.update(investigation_table)
            .where(investigation_table.c.id == waiting.id.value)
            .values(state_version=waiting.state_version)
        )
    with pytest.raises(PersistenceDataError), PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.entity_resolution_decisions.get_by_command(
            actor.workspace_id,
            command.command_id,
        )

    with engine.begin() as connection:
        connection.execute(
            sa.update(investigation_table)
            .where(investigation_table.c.id == waiting.id.value)
            .values(
                state=InvestigationState.COLLECTING.value,
                state_version=waiting.state_version + 1,
            )
        )
    with pytest.raises(PersistenceDataError), PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.entity_resolution_decisions.get_by_id(
            actor.workspace_id,
            result.decision.id,
        )

    other_company = replace(result.company, id=CompanyId.new())
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.companies.add(other_company)
        unit_of_work.commit()
    with engine.begin() as connection:
        connection.execute(
            sa.update(investigation_table)
            .where(investigation_table.c.id == waiting.id.value)
            .values(
                state=InvestigationState.PLANNING.value,
                state_version=waiting.state_version + 1,
                confirmed_company_id=other_company.id.value,
            )
        )
    with pytest.raises(PersistenceDataError), PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.entity_resolution_decisions.get_by_investigation(
            actor.workspace_id,
            waiting.id,
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.update(investigation_table)
            .where(investigation_table.c.id == waiting.id.value)
            .values(active_candidate_batch_id=command.candidate_batch_id.value)
        )


def test_decision_reads_fail_closed_without_historical_transition(engine: Engine) -> None:
    actor, waiting = _seed_waiting(engine)
    command = _command(engine, actor, waiting)
    result = EntityConfirmationService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).confirm_entity_candidate(actor, command)
    with engine.begin() as connection:
        connection.execute(
            sa.delete(investigation_transition_table).where(
                investigation_transition_table.c.command_id == command.command_id.value
            )
        )

    lookups: tuple[Callable[[UnitOfWork], object], ...] = (
        lambda unit_of_work: unit_of_work.entity_resolution_decisions.get_by_command(
            actor.workspace_id,
            command.command_id,
        ),
        lambda unit_of_work: unit_of_work.entity_resolution_decisions.get_by_investigation(
            actor.workspace_id,
            waiting.id,
        ),
        lambda unit_of_work: unit_of_work.entity_resolution_decisions.get_by_id(
            actor.workspace_id,
            result.decision.id,
        ),
    )
    for lookup in lookups:
        with pytest.raises(PersistenceDataError), PostgreSQLUnitOfWork(engine) as unit_of_work:
            lookup(unit_of_work)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("decision_digest", "0" * 64),
        ("company_snapshot_digest", "1" * 64),
        ("materialization_policy_snapshot", {"policy_id": "TAMPERED"}),
    ],
)
def test_decision_reconstitution_fails_closed_after_tampering(
    engine: Engine,
    column: str,
    value: object,
) -> None:
    actor, waiting = _seed_waiting(engine)
    command = _command(engine, actor, waiting)
    result = EntityConfirmationService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).confirm_entity_candidate(actor, command)
    with engine.begin() as connection:
        connection.execute(
            sa.update(entity_resolution_decision_table)
            .where(entity_resolution_decision_table.c.id == result.decision.id.value)
            .values({column: value})
        )
    with pytest.raises(PersistenceDataError), PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.entity_resolution_decisions.get_by_command(
            actor.workspace_id,
            command.command_id,
        )


def test_decision_and_candidate_reads_are_tenant_scoped(engine: Engine) -> None:
    actor, waiting = _seed_waiting(engine, "tenant-a")
    other_actor, _ = _seed_waiting(engine, "tenant-b")
    command = _command(engine, actor, waiting)
    result = EntityConfirmationService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).confirm_entity_candidate(actor, command)
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert (
            unit_of_work.entity_resolution_decisions.get_by_id(
                other_actor.workspace_id,
                result.decision.id,
            )
            is None
        )
        assert unit_of_work.companies.get(other_actor.workspace_id, result.company.id) is None
        unit_of_work.commit()


@pytest.mark.parametrize("reference_kind", ["candidate", "batch", "company"])
def test_decision_foreign_keys_reject_cross_tenant_references(
    engine: Engine,
    reference_kind: str,
) -> None:
    actor, waiting = _seed_waiting(engine, "tenant-a")
    other_actor, other_waiting = _seed_waiting(engine, "tenant-b")
    result = EntityConfirmationService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).confirm_entity_candidate(actor, _command(engine, actor, waiting))
    other_result = EntityConfirmationService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).confirm_entity_candidate(
        other_actor,
        _command(engine, other_actor, other_waiting),
    )
    updates_by_reference: dict[str, dict[str, object]] = {
        "candidate": {"candidate_id": other_result.decision.candidate_id.value},
        "batch": {
            "candidate_batch_id": other_result.decision.candidate_batch_id.value,
            "candidate_id": other_result.decision.candidate_id.value,
        },
        "company": {"company_id": other_result.company.id.value},
    }
    expected_constraints = {
        "candidate": {"fk_entity_resolution_decision_candidate_scope"},
        "batch": {
            "fk_entity_resolution_decision_batch_scope",
            "fk_entity_resolution_decision_candidate_scope",
        },
        "company": {"fk_entity_resolution_decision_company_scope"},
    }

    with pytest.raises(IntegrityError) as caught, engine.begin() as connection:
        connection.execute(
            sa.update(entity_resolution_decision_table)
            .where(entity_resolution_decision_table.c.id == result.decision.id.value)
            .values(updates_by_reference[reference_kind])
        )

    diagnostic = getattr(caught.value.orig, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    assert constraint_name in expected_constraints[reference_kind]


def test_downgrade_refuses_to_erase_append_only_confirmation(engine: Engine) -> None:
    actor, waiting = _seed_waiting(engine)
    command = _command(engine, actor, waiting)
    EntityConfirmationService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).confirm_entity_candidate(actor, command)
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    with pytest.raises(RuntimeError, match="entity confirmation records exist"):
        alembic_command.downgrade(config, "20260729_04")
    assert "entity_resolution_decision" in sa.inspect(engine).get_table_names()


class _FailingCommitUnitOfWork(PostgreSQLUnitOfWork):
    def commit(self) -> None:
        raise PersistenceError("Injected commit failure.")


class _FailingUnitOfWorkFactory:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def __call__(self) -> UnitOfWork:
        return cast(UnitOfWork, _FailingCommitUnitOfWork(self._engine))


def test_commit_failure_rolls_back_company_decision_state_ledger_and_audit(
    engine: Engine,
) -> None:
    actor, waiting = _seed_waiting(engine)
    command = _command(engine, actor, waiting)
    service = EntityConfirmationService(
        _FailingUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW),
    )
    with pytest.raises(PersistenceError, match="Injected"):
        service.confirm_entity_candidate(actor, command)
    assert waiting.active_candidate_batch_id is not None
    with engine.connect() as connection:
        state = connection.execute(
            sa.select(
                investigation_table.c.state,
                investigation_table.c.state_version,
                investigation_table.c.confirmed_company_id,
                investigation_table.c.active_candidate_batch_id,
            ).where(investigation_table.c.id == waiting.id.value)
        ).one()
        assert state == (
            "WAITING_FOR_ENTITY_CONFIRMATION",
            waiting.state_version,
            None,
            waiting.active_candidate_batch_id.value,
        )
        assert connection.scalar(sa.select(sa.func.count()).select_from(company_table)) == 0
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(entity_resolution_decision_table)
            )
            == 0
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(investigation_transition_table)
            )
            == 1
        )
        assert connection.scalar(sa.select(sa.func.count()).select_from(audit_event_table)) == 1


def test_distinct_commands_same_version_leave_one_company_and_decision(
    engine: Engine,
) -> None:
    actor, waiting = _seed_waiting(engine)
    commands = (
        _command(engine, actor, waiting),
        _command(engine, actor, waiting),
    )
    barrier = Barrier(2)

    def execute(item: ConfirmEntityCandidate) -> str:
        barrier.wait()
        try:
            EntityConfirmationService(
                PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
            ).confirm_entity_candidate(actor, item)
        except ConcurrentInvestigationUpdateError:
            return "conflict"
        return "success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(execute, commands))

    assert sorted(outcomes) == ["conflict", "success"]
    with engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(company_table)) == 1
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(entity_resolution_decision_table)
            )
            == 1
        )
        investigation = (
            connection.execute(
                sa.select(
                    investigation_table.c.state,
                    investigation_table.c.state_version,
                    investigation_table.c.confirmed_company_id,
                    investigation_table.c.active_candidate_batch_id,
                ).where(investigation_table.c.id == waiting.id.value)
            )
            .mappings()
            .one()
        )
        assert investigation["state"] == InvestigationState.PLANNING.value
        assert investigation["state_version"] == waiting.state_version + 1
        assert investigation["confirmed_company_id"] is not None
        assert investigation["active_candidate_batch_id"] is None
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(investigation_transition_table)
            )
            == 2
        )
        assert connection.scalar(sa.select(sa.func.count()).select_from(audit_event_table)) == 2


def test_same_command_concurrently_has_one_effect_and_one_replay(engine: Engine) -> None:
    actor, waiting = _seed_waiting(engine)
    command = _command(engine, actor, waiting)
    barrier = Barrier(2)

    def execute() -> bool:
        barrier.wait()
        return (
            EntityConfirmationService(
                PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
            )
            .confirm_entity_candidate(actor, command)
            .replayed
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(execute) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]

    assert sorted(results) == [False, True]
    with engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(company_table)) == 1
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(entity_resolution_decision_table)
            )
            == 1
        )
        investigation = (
            connection.execute(
                sa.select(
                    investigation_table.c.state,
                    investigation_table.c.state_version,
                    investigation_table.c.confirmed_company_id,
                    investigation_table.c.active_candidate_batch_id,
                ).where(investigation_table.c.id == waiting.id.value)
            )
            .mappings()
            .one()
        )
        assert investigation["state"] == InvestigationState.PLANNING.value
        assert investigation["state_version"] == waiting.state_version + 1
        assert investigation["confirmed_company_id"] is not None
        assert investigation["active_candidate_batch_id"] is None
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(investigation_transition_table)
            )
            == 2
        )
        assert connection.scalar(sa.select(sa.func.count()).select_from(audit_event_table)) == 2


class _FailingClock:
    def now(self) -> datetime:
        raise AssertionError("Replay must not read the clock.")
