"""F4.2 real PostgreSQL atomicity, tenant isolation, replay, and concurrency."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
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
    PersistenceDataError,
    PersistenceError,
)
from intelligence.application.investigation_lifecycle import RequestEntityConfirmation
from intelligence.application.services.investigations import InvestigationService
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CorrelationId,
    EntityCandidateBatchId,
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
from intelligence.entity_resolution.contracts import (
    CandidateIdentitySnapshot,
    CandidateOriginSnapshot,
    CandidateSubmissionBatch,
    EntityCandidateInput,
)
from intelligence.entity_resolution.policy import INITIAL_MATCH_POLICY
from intelligence.infrastructure.persistence.postgresql.engine import create_postgresql_engine
from intelligence.infrastructure.persistence.postgresql.tables import (
    audit_event_table,
    entity_candidate_batch_table,
    entity_candidate_dimension_score_table,
    entity_candidate_table,
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
NOW = datetime(2026, 7, 29, 20, tzinfo=UTC)


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
                "entity_candidate_dimension_score, entity_candidate, entity_candidate_batch, "
                "workspace_membership, user_account, investigation, company, workspace CASCADE"
            )
        )


def _text(value: str) -> OriginalAndNormalizedText:
    return OriginalAndNormalizedText(original_value=value, normalized_value=value.casefold())


def _input() -> IdentificationInput:
    return IdentificationInput(legal_name=_text("Empresa Exemplo S.A."))


def _seed(engine: Engine, label: str = "tenant-a") -> tuple[ActorContext, Investigation]:
    workspace_id = WorkspaceId.new()
    user_id = UserId.new()
    actor = ActorContext(
        user_id=user_id,
        workspace_id=workspace_id,
        correlation_id=CorrelationId.new(),
    )
    created_at = NOW - timedelta(days=1)
    investigation = Investigation.reconstitute(
        id=InvestigationId.new(),
        workspace_id=workspace_id,
        requested_by=user_id,
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


def _candidate(key: str = "candidate-1") -> EntityCandidateInput:
    return EntityCandidateInput(
        candidate_key=key,
        identity=CandidateIdentitySnapshot(
            legal_name=_text("Empresa Exemplo S.A."),
            country_code=CountryCode("BR"),
        ),
        origin=CandidateOriginSnapshot(
            source_id="SYNTHETIC_SOURCE",
            connector_id="synthetic.source",
            connector_version="1.0.0",
            source_candidate_reference=f"opaque-{key}",
            collected_at=NOW - timedelta(minutes=1),
        ),
    )


def _command(
    investigation: Investigation,
    *,
    command_id: InvestigationCommandId | None = None,
    candidate_key: str = "candidate-1",
) -> RequestEntityConfirmation:
    assert investigation.identification_input is not None
    return RequestEntityConfirmation(
        command_id=command_id or InvestigationCommandId.new(),
        investigation_id=investigation.id,
        expected_state_version=2,
        candidate_batch=CandidateSubmissionBatch(
            input_digest=investigation.identification_input.digest,
            candidates=(_candidate(candidate_key),),
        ),
        matching_policy=INITIAL_MATCH_POLICY,
    )


def _service(
    engine: Engine,
    factory: Callable[[], PostgreSQLUnitOfWork] | None = None,
) -> InvestigationService:
    return InvestigationService(
        factory or PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW),
    )


def test_round_trip_replay_tenant_isolation_and_append_only_shape(engine: Engine) -> None:
    actor, investigation = _seed(engine)
    other_actor, _ = _seed(engine, "tenant-b")
    command = _command(investigation)

    first = _service(engine).request_entity_confirmation(actor, command)
    replay = _service(engine).request_entity_confirmation(actor, command)

    assert not first.replayed and replay.replayed
    assert first.candidate_batch_id == replay.candidate_batch_id
    assert first.candidate_batch_id is not None
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        restored_investigation = unit_of_work.investigations.get(
            actor.workspace_id, investigation.id
        )
        restored_batch = unit_of_work.entity_candidate_batches.get(
            actor.workspace_id, first.candidate_batch_id
        )
        alien_batch = unit_of_work.entity_candidate_batches.get(
            other_actor.workspace_id, first.candidate_batch_id
        )
        unit_of_work.commit()
    assert restored_investigation is not None
    assert restored_investigation.state is InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION
    assert restored_investigation.active_candidate_batch_id == first.candidate_batch_id
    assert restored_batch is not None and alien_batch is None
    assert restored_batch.policy_snapshot == INITIAL_MATCH_POLICY.to_canonical_json()
    assert len(restored_batch.candidates) == 1
    assert len(restored_batch.candidates[0].dimensions) == 7
    assert restored_batch.candidates[0].decision.value == "PENDING_REVIEW"

    with engine.connect() as connection:
        counts = tuple(
            connection.scalar(sa.select(sa.func.count()).select_from(table))
            for table in (
                entity_candidate_batch_table,
                entity_candidate_table,
                entity_candidate_dimension_score_table,
                investigation_transition_table,
                audit_event_table,
            )
        )
    assert counts == (1, 1, 7, 1, 1)


class FailingCommitUnitOfWork(PostgreSQLUnitOfWork):
    def commit(self) -> None:
        raise PersistenceError("Injected commit failure.")


def test_commit_failure_rolls_back_state_batch_candidates_scores_ledger_and_audit(
    engine: Engine,
) -> None:
    actor, investigation = _seed(engine)

    with pytest.raises(PersistenceError, match="Injected"):
        _service(engine, lambda: FailingCommitUnitOfWork(engine)).request_entity_confirmation(
            actor,
            _command(investigation),
        )

    with engine.connect() as connection:
        state = connection.execute(
            sa.select(
                investigation_table.c.state,
                investigation_table.c.state_version,
                investigation_table.c.active_candidate_batch_id,
            ).where(investigation_table.c.id == investigation.id.value)
        ).one()
        counts = tuple(
            connection.scalar(sa.select(sa.func.count()).select_from(table))
            for table in (
                entity_candidate_batch_table,
                entity_candidate_table,
                entity_candidate_dimension_score_table,
                investigation_transition_table,
                audit_event_table,
            )
        )
    assert state == (InvestigationState.IDENTIFYING.value, 2, None)
    assert counts == (0, 0, 0, 0, 0)


def test_two_distinct_commands_for_same_version_leave_one_batch_and_no_orphan(
    engine: Engine,
) -> None:
    actor, investigation = _seed(engine)
    commands = (
        _command(investigation, candidate_key="candidate-a"),
        _command(investigation, candidate_key="candidate-b"),
    )
    barrier = Barrier(2)

    def execute(item: RequestEntityConfirmation) -> str:
        barrier.wait()
        try:
            _service(engine).request_entity_confirmation(actor, item)
        except ConcurrentInvestigationUpdateError:
            return "conflict"
        return "success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(execute, commands))

    assert sorted(outcomes) == ["conflict", "success"]
    with engine.connect() as connection:
        batch_count = connection.scalar(
            sa.select(sa.func.count()).select_from(entity_candidate_batch_table)
        )
        candidate_count = connection.scalar(
            sa.select(sa.func.count()).select_from(entity_candidate_table)
        )
        transition_count = connection.scalar(
            sa.select(sa.func.count()).select_from(investigation_transition_table)
        )
    assert batch_count == candidate_count == transition_count == 1


def test_same_command_concurrently_has_one_effect_and_one_durable_replay(
    engine: Engine,
) -> None:
    actor, investigation = _seed(engine)
    command = _command(investigation)
    barrier = Barrier(2)

    def execute() -> tuple[bool, EntityCandidateBatchId | None]:
        barrier.wait()
        result = _service(engine).request_entity_confirmation(actor, command)
        return result.replayed, result.candidate_batch_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(execute) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]

    assert sorted(replayed for replayed, _ in results) == [False, True]
    assert results[0][1] == results[1][1]
    with engine.connect() as connection:
        counts = tuple(
            connection.scalar(sa.select(sa.func.count()).select_from(table))
            for table in (
                entity_candidate_batch_table,
                entity_candidate_table,
                investigation_transition_table,
                audit_event_table,
            )
        )
    assert counts == (1, 1, 1, 1)


@pytest.mark.parametrize(
    "scenario",
    [
        "total_score",
        "coverage",
        "candidate_evaluation_digest",
        "submission_digest",
        "batch_evaluation_digest",
        "dimension_explanation",
        "dimension_weight",
        "dimension_contribution",
        "classification",
        "rank",
        "policy_snapshot",
        "normalization_version",
        "policy_digest",
        "policy_version",
        "policy_id",
        "input_digest",
        "candidate_identity",
        "candidate_origin",
        "candidate_key",
    ],
)
def test_direct_row_tampering_fails_closed_on_load(engine: Engine, scenario: str) -> None:
    actor, investigation = _seed(engine)
    result = _service(engine).request_entity_confirmation(actor, _command(investigation))
    assert result.candidate_batch_id is not None

    with engine.connect() as connection:
        batch = dict(
            connection.execute(
                sa.select(entity_candidate_batch_table).where(
                    entity_candidate_batch_table.c.id == result.candidate_batch_id.value
                )
            )
            .mappings()
            .one()
        )
        candidate = dict(
            connection.execute(
                sa.select(entity_candidate_table).where(
                    entity_candidate_table.c.batch_id == result.candidate_batch_id.value
                )
            )
            .mappings()
            .one()
        )
        name_dimension = dict(
            connection.execute(
                sa.select(entity_candidate_dimension_score_table).where(
                    entity_candidate_dimension_score_table.c.candidate_id == candidate["id"],
                    entity_candidate_dimension_score_table.c.dimension == "NAME",
                )
            )
            .mappings()
            .one()
        )
        domain_dimension = dict(
            connection.execute(
                sa.select(entity_candidate_dimension_score_table).where(
                    entity_candidate_dimension_score_table.c.candidate_id == candidate["id"],
                    entity_candidate_dimension_score_table.c.dimension == "DOMAIN",
                )
            )
            .mappings()
            .one()
        )

    table = entity_candidate_batch_table
    where = table.c.id == batch["id"]
    changes: dict[str, object]
    if scenario == "total_score":
        table, where = entity_candidate_table, entity_candidate_table.c.id == candidate["id"]
        changes = {"total_score": int(candidate["total_score"]) + 1}
    elif scenario == "coverage":
        table, where = entity_candidate_table, entity_candidate_table.c.id == candidate["id"]
        changes = {"coverage": int(candidate["coverage"]) - 1}
    elif scenario == "candidate_evaluation_digest":
        table, where = entity_candidate_table, entity_candidate_table.c.id == candidate["id"]
        changes = {"evaluation_digest": "0" * 64}
    elif scenario == "submission_digest":
        changes = {"submission_digest": "0" * 64}
    elif scenario == "batch_evaluation_digest":
        changes = {"evaluation_digest": "0" * 64}
    elif scenario == "dimension_explanation":
        table = entity_candidate_dimension_score_table
        where = sa.and_(table.c.candidate_id == candidate["id"], table.c.dimension == "NAME")
        changes = {"explanation_code": "NAME_TRADE_EXACT"}
    elif scenario == "dimension_weight":
        table = entity_candidate_dimension_score_table
        where = sa.and_(table.c.candidate_id == candidate["id"], table.c.dimension == "DOMAIN")
        changes = {"weight": int(domain_dimension["weight"]) + 1}
    elif scenario == "dimension_contribution":
        table = entity_candidate_dimension_score_table
        where = sa.and_(table.c.candidate_id == candidate["id"], table.c.dimension == "NAME")
        changes = {"score": 9_996, "contribution": 2_499}
    elif scenario == "classification":
        table, where = entity_candidate_table, entity_candidate_table.c.id == candidate["id"]
        changes = {"classification": "MEDIUM"}
    elif scenario == "rank":
        table, where = entity_candidate_table, entity_candidate_table.c.id == candidate["id"]
        changes = {"rank": 2}
    elif scenario in {"policy_snapshot", "normalization_version"}:
        policy_snapshot = dict(batch["policy_snapshot"])
        if scenario == "policy_snapshot":
            policy_snapshot["version"] = 2
        else:
            policy_snapshot["normalization_version"] = "NAME_NORMALIZATION_V2"
        changes = {"policy_snapshot": policy_snapshot}
    elif scenario == "policy_digest":
        changes = {"policy_digest": "0" * 64}
    elif scenario == "policy_version":
        changes = {"policy_version": int(batch["policy_version"]) + 1}
    elif scenario == "policy_id":
        changes = {"policy_id": "ENTITY_MATCH_OTHER"}
    elif scenario == "input_digest":
        changes = {"input_digest": "0" * 64}
    elif scenario == "candidate_identity":
        table, where = entity_candidate_table, entity_candidate_table.c.id == candidate["id"]
        snapshot = json.loads(json.dumps(candidate["identity_snapshot"]))
        snapshot["legal_name"] = {
            "normalized_value": "other company",
            "original_value": "Other Company",
        }
        serialized = json.dumps(
            snapshot,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        changes = {
            "identity_snapshot": snapshot,
            "identity_digest": sha256(serialized.encode("utf-8")).hexdigest(),
        }
    elif scenario == "candidate_origin":
        table, where = entity_candidate_table, entity_candidate_table.c.id == candidate["id"]
        snapshot = json.loads(json.dumps(candidate["origin_snapshot"]))
        snapshot["source_candidate_reference"] = "opaque-tampered"
        serialized = json.dumps(
            snapshot,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        changes = {
            "origin_snapshot": snapshot,
            "origin_digest": sha256(serialized.encode("utf-8")).hexdigest(),
        }
    else:
        table, where = entity_candidate_table, entity_candidate_table.c.id == candidate["id"]
        changes = {"candidate_key": "candidate-tampered"}

    original_source = (
        name_dimension
        if scenario in {"dimension_explanation", "dimension_contribution"}
        else domain_dimension
        if scenario == "dimension_weight"
        else candidate
        if table is entity_candidate_table
        else batch
    )
    original = {field_name: original_source[field_name] for field_name in changes}
    try:
        with engine.begin() as connection:
            connection.execute(table.update().where(where).values(**changes))
        with pytest.raises(PersistenceDataError), PostgreSQLUnitOfWork(engine) as unit_of_work:
            unit_of_work.entity_candidate_batches.get(
                actor.workspace_id,
                result.candidate_batch_id,
            )
    finally:
        with engine.begin() as connection:
            connection.execute(table.update().where(where).values(**original))
