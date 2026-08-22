"""F5.3 PostgreSQL decision round-trip, constraints, tamper, and downgrade tests."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import (
    EvidenceAdmissibilityPredecessorError,
    PersistenceDataError,
)
from intelligence.application.evidence_admissibility import DecideEvidenceAdmissibility
from intelligence.application.services.evidence import EvidenceService
from intelligence.application.services.evidence_admissibility import (
    EvidenceAdmissibilityService,
)
from intelligence.domain.identifiers import EvidenceAdmissibilityCommandId
from intelligence.evidence.admissibility import (
    EffectiveEvidenceAdmissibilityStatus,
    EvidenceAdmissibilityReason,
    EvidenceAdmissibilityRequestedAction,
)
from intelligence.evidence.models import EvidenceHistory
from intelligence.infrastructure.persistence.postgresql.engine import create_postgresql_engine
from intelligence.infrastructure.persistence.postgresql.evidence_admissibility_repository import (
    PostgreSQLEvidenceAdmissibilityDecisionRepository,
)
from intelligence.infrastructure.persistence.postgresql.evidence_admissibility_tables import (
    evidence_admissibility_decision_table,
)
from intelligence.infrastructure.persistence.postgresql.evidence_tables import evidence_table
from intelligence.infrastructure.persistence.postgresql.tables import investigation_table
from intelligence.infrastructure.persistence.postgresql.transaction_guard import (
    PostgreSQLTransactionGuard,
)
from intelligence.infrastructure.persistence.postgresql.unit_of_work import (
    PostgreSQLUnitOfWorkFactory,
)
from tests.integration.persistence.test_f51_evidence import NOW, _seed_collecting
from tests.integration.persistence.test_f51_evidence import (
    _register_command as evidence_command,
)
from tests.support.destructive_database import require_safe_destructive_database_url
from tests.unit.application.fakes import FakeClock

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])
REPOSITORY_ROOT = Path(__file__).parents[3]
PREVIOUS_HEAD = "20260821_12"


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    database_url = require_safe_destructive_database_url()
    config = _alembic_config()
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
                "TRUNCATE TABLE evidence_admissibility_decision, claim_evidence_link, claim, "
                "evidence_lifecycle_event, evidence, evidence_artifact, "
                "entity_resolution_decision, investigation_transition, audit_event, "
                "entity_candidate_dimension_score, entity_candidate, entity_candidate_batch, "
                "workspace_membership, user_account, investigation, company, workspace CASCADE"
            )
        )


def _alembic_config() -> Config:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    return config


def _seed_verifying(
    engine: Engine,
) -> tuple[ActorContext, EvidenceHistory, EvidenceAdmissibilityService]:
    actor = _seed_collecting(engine, owner=True)
    evidence = (
        EvidenceService(PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW))
        .register(actor, evidence_command(engine, actor))
        .history
    )
    with engine.begin() as connection:
        connection.execute(
            sa.update(investigation_table)
            .where(investigation_table.c.id == evidence.latest.investigation_id.value)
            .values(state="VERIFYING", state_version=investigation_table.c.state_version + 1)
        )
    service = EvidenceAdmissibilityService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )
    return actor, evidence, service


def _restrict(
    evidence: EvidenceHistory,
    *,
    command_id: EvidenceAdmissibilityCommandId | None = None,
    previous: str | None = None,
) -> DecideEvidenceAdmissibility:
    return DecideEvidenceAdmissibility(
        command_id=command_id or EvidenceAdmissibilityCommandId.new(),
        investigation_id=evidence.latest.investigation_id,
        evidence_id=evidence.latest.id,
        expected_evidence_digest=evidence.latest.evidence_digest,
        expected_previous_decision_digest=previous,
        requested_action=EvidenceAdmissibilityRequestedAction.RESTRICT,
        reason_code=EvidenceAdmissibilityReason.POLICY_OR_VERIFIABILITY_RESTRICTED,
    )


def test_round_trip_replay_full_binding_and_pending_evidence(engine: Engine) -> None:
    actor, evidence, service = _seed_verifying(engine)
    command = _restrict(evidence)
    result = service.decide(actor, command)
    replay = service.decide(actor, command)
    assert replay.replayed and replay.history == result.history
    assert result.effective.status is EffectiveEvidenceAdmissibilityStatus.RESTRICTED
    with engine.connect() as connection:
        row = connection.execute(sa.select(evidence_admissibility_decision_table)).mappings().one()
        assert row["evidence_id"] == evidence.latest.id.value
        assert row["evidence_series_id"] == evidence.latest.series_id.value
        assert row["evidence_version"] == evidence.latest.version
        assert row["workspace_id"] == actor.workspace_id.value
        assert row["evidence_digest"] == evidence.latest.evidence_digest
        assert connection.scalar(sa.select(evidence_table.c.admissibility_status)) == "PENDING"


def test_schema_fk_binds_full_evidence_version_and_tenant_context(engine: Engine) -> None:
    inspector = sa.inspect(engine)
    exact_fk = next(
        item
        for item in inspector.get_foreign_keys("evidence_admissibility_decision")
        if item["name"] == "fk_admissibility_exact_evidence_scope"
    )
    assert exact_fk["constrained_columns"] == [
        "evidence_id",
        "evidence_series_id",
        "evidence_version",
        "workspace_id",
        "investigation_id",
        "subject_company_id",
        "entity_resolution_decision_id",
    ]
    unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("evidence")}
    assert (
        "id",
        "series_id",
        "version",
        "workspace_id",
        "investigation_id",
        "subject_company_id",
        "entity_resolution_decision_id",
    ) in unique
    indexes = {
        item["name"]: tuple(item["column_names"])
        for item in inspector.get_indexes("evidence_admissibility_decision")
    }
    assert indexes["ix_admissibility_workspace_investigation_decided_at"] == (
        "workspace_id",
        "investigation_id",
        "decided_at",
    )
    assert indexes["ix_admissibility_workspace_predecessor"] == (
        "workspace_id",
        "supersedes_decision_id",
    )
    assert indexes["ix_admissibility_workspace_actor"] == (
        "workspace_id",
        "decided_by",
    )


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("policy_id", "F5_3_OTHER_POLICY_V1"),
        ("purpose", "OTHER_PURPOSE"),
        ("admission_basis", "OTHER_BASIS"),
        ("controlled_trust_root_id", "F5_2_CONTROLLED_CORPUS_MANIFEST_V1"),
        ("controlled_trust_root_digest", "0" * 64),
        ("schema_version", 2),
        ("decision_digest", "A" * 64),
    ],
)
def test_closed_policy_snapshot_and_digest_checks_reject_tamper(
    engine: Engine, field: str, invalid: object
) -> None:
    actor, evidence, service = _seed_verifying(engine)
    service.decide(actor, _restrict(evidence))
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            sa.update(evidence_admissibility_decision_table).values({field: invalid})
        )


def test_superseding_predecessor_fk_and_mapper_tamper_fail_closed(engine: Engine) -> None:
    actor, evidence, service = _seed_verifying(engine)
    first = service.decide(actor, _restrict(evidence))
    service.decide(
        actor,
        _restrict(evidence, previous=first.history.latest.decision_digest),
    )
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            sa.insert(evidence_admissibility_decision_table).values(
                **{
                    **connection.execute(sa.select(evidence_admissibility_decision_table).limit(1))
                    .mappings()
                    .one(),
                    "id": EvidenceAdmissibilityCommandId.new().value,
                    "command_id": EvidenceAdmissibilityCommandId.new().value,
                    "decision_sequence": 3,
                    "supersedes_decision_id": EvidenceAdmissibilityCommandId.new().value,
                }
            )
        )
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            sa.update(evidence_admissibility_decision_table)
            .where(evidence_admissibility_decision_table.c.decision_sequence == 1)
            .values(evidence_digest="0" * 64)
        )
        guard = PostgreSQLTransactionGuard(connection, transaction)
        repository = PostgreSQLEvidenceAdmissibilityDecisionRepository(guard)
        with pytest.raises(PersistenceDataError):
            repository.get_history(actor.workspace_id, evidence.latest.id)
        transaction.rollback()


def test_command_collision_constraint_and_protected_downgrade(engine: Engine) -> None:
    actor, evidence, service = _seed_verifying(engine)
    command = _restrict(evidence)
    result = service.decide(actor, command)
    row = result.history.latest
    with engine.begin() as connection:
        values = dict(
            connection.execute(sa.select(evidence_admissibility_decision_table)).mappings().one()
        )
        values.update(
            id=EvidenceAdmissibilityCommandId.new().value,
            decision_sequence=2,
            supersedes_decision_id=row.id.value,
        )
        with pytest.raises(IntegrityError):
            connection.execute(sa.insert(evidence_admissibility_decision_table).values(**values))
    with pytest.raises(RuntimeError, match="admissibility history exists"):
        alembic_command.downgrade(_alembic_config(), PREVIOUS_HEAD)


def test_concurrent_initial_and_superseding_decisions_serialize_without_deadlock(
    engine: Engine,
) -> None:
    actor, evidence, service = _seed_verifying(engine)

    def race(commands: tuple[DecideEvidenceAdmissibility, ...]) -> list[str]:
        barrier = Barrier(len(commands))

        def decide(command: DecideEvidenceAdmissibility) -> str:
            barrier.wait(timeout=20)
            try:
                service.decide(actor, command)
            except EvidenceAdmissibilityPredecessorError:
                return "STALE"
            return "SUCCESS"

        with ThreadPoolExecutor(max_workers=len(commands)) as executor:
            futures = [executor.submit(decide, command) for command in commands]
            return [future.result(timeout=30) for future in futures]

    assert sorted(race((_restrict(evidence), _restrict(evidence)))) == ["STALE", "SUCCESS"]
    first = service.read(actor, evidence.latest.id, as_of=NOW).decision_histories[0].latest
    superseding = (
        _restrict(evidence, previous=first.decision_digest),
        _restrict(evidence, previous=first.decision_digest),
    )
    assert sorted(race(superseding)) == ["STALE", "SUCCESS"]
    with engine.connect() as connection:
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(evidence_admissibility_decision_table)
            )
            == 2
        )


def test_empty_downgrade_and_reupgrade(engine: Engine) -> None:
    del engine
    config = _alembic_config()
    alembic_command.downgrade(config, PREVIOUS_HEAD)
    alembic_command.upgrade(config, "head")
