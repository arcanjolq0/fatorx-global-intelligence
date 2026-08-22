"""F5.2 PostgreSQL Claim round-trip, constraints, tamper, and migration tests."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import Self

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.claim_evidence_policy import (
    ClaimEvidenceEligibilityPolicyV1,
    ControlledEvidenceAnchorV1,
    build_manifest,
    locator_digest,
)
from intelligence.application.claims import ProposedClaimEvidenceLink, RegisterClaim
from intelligence.application.errors import (
    InvalidClaimEvidenceError,
    InvalidEvidenceContextError,
    PersistenceDataError,
)
from intelligence.application.evidence import CorrectEvidence, RevokeEvidence
from intelligence.application.services.claims import ClaimService
from intelligence.application.services.evidence import EvidenceService
from intelligence.claims.models import (
    ClaimAssessmentOutcome,
    ClaimCreationMethod,
    ClaimCriticality,
    ClaimEvidenceRole,
    ClaimPredicate,
    TemporalAbsenceReason,
    TextClaimValue,
    UndatedClaimTemporal,
)
from intelligence.domain.identifiers import (
    ClaimCommandId,
    EvidenceCommandId,
    EvidenceId,
    WorkspaceId,
)
from intelligence.evidence.models import EvidenceHistory, EvidenceLifecycleReason
from intelligence.infrastructure.persistence.postgresql.claim_tables import (
    claim_evidence_link_table,
    claim_table,
)
from intelligence.infrastructure.persistence.postgresql.engine import create_postgresql_engine
from intelligence.infrastructure.persistence.postgresql.evidence_repository import (
    PostgreSQLEvidenceRepository,
)
from intelligence.infrastructure.persistence.postgresql.evidence_tables import evidence_table
from intelligence.infrastructure.persistence.postgresql.tables import investigation_table
from intelligence.infrastructure.persistence.postgresql.transaction_guard import (
    PostgreSQLTransactionGuard,
)
from intelligence.infrastructure.persistence.postgresql.unit_of_work import (
    PostgreSQLUnitOfWork,
    PostgreSQLUnitOfWorkFactory,
)
from tests.integration.persistence.test_f51_evidence import (
    NOW,
    _seed_collecting,
)
from tests.integration.persistence.test_f51_evidence import (
    _register_command as evidence_command,
)
from tests.support.destructive_database import require_safe_destructive_database_url
from tests.unit.application.fakes import FakeClock

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])
REPOSITORY_ROOT = Path(__file__).parents[3]
PREVIOUS_HEAD = "20260814_11"


class _PausingEvidenceRepository(PostgreSQLEvidenceRepository):
    def __init__(
        self, transaction_guard: PostgreSQLTransactionGuard, *, locked: Event, release: Event
    ) -> None:
        super().__init__(transaction_guard)
        self._locked = locked
        self._release = release

    def acquire_history_lock(self, workspace_id: WorkspaceId, evidence_id: EvidenceId) -> None:
        super().acquire_history_lock(workspace_id, evidence_id)
        self._locked.set()
        if not self._release.wait(timeout=20):
            raise RuntimeError("Timed out waiting for the deterministic concurrency release.")


class _PausingUnitOfWork(PostgreSQLUnitOfWork):
    def __init__(self, engine: Engine, locked: Event, release: Event) -> None:
        super().__init__(engine)
        self._locked_event = locked
        self._release_event = release

    def __enter__(self) -> Self:
        super().__enter__()
        guard = self._transaction_guard
        if guard is None:
            raise RuntimeError("Transaction guard was not initialized.")
        self._evidence = _PausingEvidenceRepository(
            guard,
            locked=self._locked_event,
            release=self._release_event,
        )
        return self


class _PausingUnitOfWorkFactory:
    def __init__(self, engine: Engine, locked: Event, release: Event) -> None:
        self._engine = engine
        self._locked = locked
        self._release = release

    def __call__(self) -> PostgreSQLUnitOfWork:
        return _PausingUnitOfWork(self._engine, self._locked, self._release)


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
                "TRUNCATE TABLE claim_evidence_link, claim, evidence_lifecycle_event, "
                "evidence, evidence_artifact, entity_resolution_decision, "
                "investigation_transition, audit_event, entity_candidate_dimension_score, "
                "entity_candidate, entity_candidate_batch, workspace_membership, user_account, "
                "investigation, company, workspace CASCADE"
            )
        )


def _alembic_config() -> Config:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    return config


def _seed_verifying(engine: Engine) -> tuple[ActorContext, EvidenceHistory, ClaimService]:
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
    anchor = ControlledEvidenceAnchorV1(
        artifact_original_sha256=evidence.artifact.original_content_sha256,
        evidence_content_sha256=evidence.latest.content_sha256,
        evidence_kind=evidence.latest.kind,
        locator_type=evidence.latest.locator.type,
        locator_digest=locator_digest(evidence.latest.locator),
    )
    service = ClaimService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW),
        ClaimEvidenceEligibilityPolicyV1(build_manifest((anchor,))),
    )
    return actor, evidence, service


def _command(evidence: EvidenceHistory) -> RegisterClaim:
    latest = evidence.latest
    return RegisterClaim(
        command_id=ClaimCommandId.new(),
        investigation_id=latest.investigation_id,
        predicate_code=ClaimPredicate.LEGAL_NAME,
        predicate_version=1,
        value=TextClaimValue("Empresa Exemplo S.A."),
        temporal=UndatedClaimTemporal(TemporalAbsenceReason.NOT_PROVIDED),
        criticality=ClaimCriticality.STANDARD,
        creation_method=ClaimCreationMethod.MANUAL,
        creation_method_version=1,
        links=(
            ProposedClaimEvidenceLink(
                latest.id,
                latest.evidence_digest,
                ClaimEvidenceRole.SUPPORTS,
            ),
        ),
    )


def test_round_trip_replay_pending_and_atomic_policy_rejection(engine: Engine) -> None:
    actor, evidence, service = _seed_verifying(engine)
    command = _command(evidence)
    result = service.register(actor, command)
    replay = service.register(actor, command)

    assert result.assessment.outcome is ClaimAssessmentOutcome.SUPPORTED
    assert replay.replayed and replay.history == result.history
    with engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(claim_table)) == 1
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(claim_evidence_link_table))
            == 1
        )
        assert connection.scalar(sa.select(evidence_table.c.admissibility_status)) == "PENDING"

    invalid = replace(
        _command(evidence),
        links=(
            replace(
                _command(evidence).links[0],
                expected_evidence_digest="0" * 64,
            ),
        ),
    )
    with pytest.raises(InvalidClaimEvidenceError):
        service.register(actor, invalid)
    with engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(claim_table)) == 1


def test_database_scope_constraints_and_mapper_tamper_fail_closed(engine: Engine) -> None:
    actor, evidence, service = _seed_verifying(engine)
    result = service.register(actor, _command(evidence))
    claim = result.history.latest

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.update(claim_evidence_link_table)
            .where(claim_evidence_link_table.c.claim_id == claim.id.value)
            .values(claim_version=claim.version + 1)
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.update(claim_table)
            .where(claim_table.c.id == claim.id.value)
            .values(predicate_code="UNSAFE_DYNAMIC_PREDICATE")
        )
    with engine.begin() as connection:
        connection.execute(
            sa.update(claim_table)
            .where(claim_table.c.id == claim.id.value)
            .values(claim_digest="0" * 64)
        )
    with pytest.raises(PersistenceDataError), PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.claims.get_history(actor.workspace_id, claim.id)


@pytest.mark.parametrize("operation", ["correct", "revoke"])
def test_claim_serializes_against_evidence_mutation_without_sleep(
    engine: Engine, operation: str
) -> None:
    actor = _seed_collecting(engine, owner=True)
    evidence = (
        EvidenceService(PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW))
        .register(actor, evidence_command(engine, actor))
        .history
    )
    anchor = ControlledEvidenceAnchorV1(
        artifact_original_sha256=evidence.artifact.original_content_sha256,
        evidence_content_sha256=evidence.latest.content_sha256,
        evidence_kind=evidence.latest.kind,
        locator_type=evidence.latest.locator.type,
        locator_digest=locator_digest(evidence.latest.locator),
    )
    claim_service = ClaimService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW),
        ClaimEvidenceEligibilityPolicyV1(build_manifest((anchor,))),
    )
    locked = Event()
    release = Event()
    mutation_service = EvidenceService(
        _PausingUnitOfWorkFactory(engine, locked, release),
        ContextualAuthorizer(),
        FakeClock(NOW),
    )
    mutation_command: CorrectEvidence | RevokeEvidence
    if operation == "correct":
        content_original = evidence.latest.content_original
        assert content_original is not None
        mutation_command = CorrectEvidence(
            command_id=EvidenceCommandId.new(),
            evidence_id=evidence.latest.id,
            expected_evidence_digest=evidence.latest.evidence_digest,
            kind=evidence.latest.kind,
            language=evidence.latest.language,
            locator=evidence.latest.locator,
            located_content=content_original.encode(),
            content_original=content_original,
            extraction_method="SYNTHETIC_CORRECTION",
            extraction_method_version="1",
        )
    else:
        mutation_command = RevokeEvidence(
            command_id=EvidenceCommandId.new(),
            evidence_id=evidence.latest.id,
            expected_evidence_digest=evidence.latest.evidence_digest,
            reason=EvidenceLifecycleReason.CONTENT_INVALID,
        )

    def mutate() -> None:
        if isinstance(mutation_command, CorrectEvidence):
            mutation_service.correct(actor, mutation_command)
        else:
            mutation_service.revoke(actor, mutation_command)

    with ThreadPoolExecutor(max_workers=2) as executor:
        mutation_future = executor.submit(mutate)
        assert locked.wait(timeout=10)
        with engine.begin() as connection:
            connection.execute(
                sa.update(investigation_table)
                .where(investigation_table.c.id == evidence.latest.investigation_id.value)
                .values(state="VERIFYING", state_version=investigation_table.c.state_version + 1)
            )
        claim_future = executor.submit(claim_service.register, actor, _command(evidence))
        release.set()
        if operation == "correct":
            with pytest.raises(InvalidEvidenceContextError):
                mutation_future.result(timeout=20)
            claim_result = claim_future.result(timeout=20)
            assert claim_result.assessment.outcome is ClaimAssessmentOutcome.SUPPORTED
        else:
            mutation_future.result(timeout=20)
            with pytest.raises(InvalidClaimEvidenceError):
                claim_future.result(timeout=20)
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        current = unit_of_work.evidence.get_history(actor.workspace_id, evidence.latest.id)
        unit_of_work.commit()
    assert current is not None
    if operation == "correct":
        assert current == evidence
    else:
        assert current.is_revoked


def test_migration_preserves_f51_and_refuses_destructive_downgrade(engine: Engine) -> None:
    config = _alembic_config()
    alembic_command.downgrade(config, PREVIOUS_HEAD)
    actor = _seed_collecting(engine, owner=True)
    evidence = (
        EvidenceService(PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW))
        .register(actor, evidence_command(engine, actor))
        .history
    )
    alembic_command.upgrade(config, "head")

    with engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(evidence_table)) == len(
            evidence.versions
        )
    with engine.begin() as connection:
        connection.execute(
            sa.update(investigation_table)
            .where(investigation_table.c.id == evidence.latest.investigation_id.value)
            .values(state="VERIFYING", state_version=investigation_table.c.state_version + 1)
        )
    anchor = ControlledEvidenceAnchorV1(
        artifact_original_sha256=evidence.artifact.original_content_sha256,
        evidence_content_sha256=evidence.latest.content_sha256,
        evidence_kind=evidence.latest.kind,
        locator_type=evidence.latest.locator.type,
        locator_digest=locator_digest(evidence.latest.locator),
    )
    ClaimService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW),
        ClaimEvidenceEligibilityPolicyV1(build_manifest((anchor,))),
    ).register(actor, _command(evidence))
    with pytest.raises(RuntimeError, match=r"Cannot downgrade F5\.2"):
        alembic_command.downgrade(config, PREVIOUS_HEAD)
    alembic_command.check(config)
