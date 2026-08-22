"""F5.3 PostgreSQL decision round-trip, constraints, tamper, and downgrade tests."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from threading import Barrier, Event
from typing import Self

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
    InvalidEvidenceAdmissibilityError,
    InvalidEvidenceContextError,
    PersistenceDataError,
)
from intelligence.application.evidence import CorrectEvidence, RevokeEvidence
from intelligence.application.evidence_admissibility import DecideEvidenceAdmissibility
from intelligence.application.evidence_admissibility_policy import (
    F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1,
)
from intelligence.application.services.evidence import EvidenceService
from intelligence.application.services.evidence_admissibility import (
    EvidenceAdmissibilityService,
)
from intelligence.domain.identifiers import (
    EvidenceAdmissibilityCommandId,
    EvidenceAdmissibilityDecisionId,
    EvidenceCommandId,
    EvidenceId,
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
from intelligence.evidence.admissibility import (
    EffectiveEvidenceAdmissibilityStatus,
    EvidenceAdmissibilityDecisionOutcome,
    EvidenceAdmissibilityHistory,
    EvidenceAdmissibilityPurpose,
    EvidenceAdmissibilityReason,
    EvidenceAdmissibilityRequestedAction,
    EvidenceAdmissionBasis,
    build_evidence_admissibility_decision,
)
from intelligence.evidence.models import (
    ArtifactStorageMode,
    EvidenceHistory,
    EvidenceLifecycleReason,
)
from intelligence.infrastructure.persistence.postgresql.engine import create_postgresql_engine
from intelligence.infrastructure.persistence.postgresql.evidence_admissibility_mappers import (
    evidence_admissibility_decision_to_values,
)
from intelligence.infrastructure.persistence.postgresql.evidence_admissibility_repository import (
    PostgreSQLEvidenceAdmissibilityDecisionRepository,
)
from intelligence.infrastructure.persistence.postgresql.evidence_admissibility_tables import (
    evidence_admissibility_decision_table,
)
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
from tests.claims.synthetic_fixtures import (
    SYNTHETIC_ARTIFACT_BYTES,
    SYNTHETIC_LOCATED_BYTES,
    synthetic_locator,
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
MUTATION_TIME = NOW + timedelta(seconds=1)
REVOCATION_TIME = NOW + timedelta(seconds=2)


class _PausingReadEvidenceRepository(PostgreSQLEvidenceRepository):
    def __init__(
        self,
        transaction_guard: PostgreSQLTransactionGuard,
        *,
        observed: Event,
        release: Event,
    ) -> None:
        super().__init__(transaction_guard)
        self._observed = observed
        self._release = release
        self._paused = False

    def get_history(
        self, workspace_id: WorkspaceId, evidence_id: EvidenceId
    ) -> EvidenceHistory | None:
        history = super().get_history(workspace_id, evidence_id)
        if not self._paused:
            self._paused = True
            self._observed.set()
            if not self._release.wait(timeout=20):
                raise RuntimeError("Timed out waiting to release the deterministic read.")
        return history


class _PausingLockEvidenceRepository(PostgreSQLEvidenceRepository):
    def __init__(
        self,
        transaction_guard: PostgreSQLTransactionGuard,
        *,
        locked: Event,
        release: Event,
    ) -> None:
        super().__init__(transaction_guard)
        self._locked = locked
        self._release = release

    def acquire_history_lock(self, workspace_id: WorkspaceId, evidence_id: EvidenceId) -> None:
        super().acquire_history_lock(workspace_id, evidence_id)
        self._locked.set()
        if not self._release.wait(timeout=20):
            raise RuntimeError("Timed out waiting to release the deterministic mutation.")


class _SignalingLockEvidenceRepository(PostgreSQLEvidenceRepository):
    def __init__(
        self,
        transaction_guard: PostgreSQLTransactionGuard,
        *,
        attempting: Event,
    ) -> None:
        super().__init__(transaction_guard)
        self._attempting = attempting

    def acquire_history_lock(self, workspace_id: WorkspaceId, evidence_id: EvidenceId) -> None:
        self._attempting.set()
        super().acquire_history_lock(workspace_id, evidence_id)


class _InstrumentedUnitOfWork(PostgreSQLUnitOfWork):
    def __init__(
        self,
        engine: Engine,
        *,
        observed: Event,
        release: Event,
        pause_read: bool,
    ) -> None:
        super().__init__(engine)
        self._observed_event = observed
        self._release_event = release
        self._pause_read = pause_read

    def __enter__(self) -> Self:
        super().__enter__()
        guard = self._transaction_guard
        if guard is None:
            raise RuntimeError("Transaction guard was not initialized.")
        if self._pause_read:
            self._evidence = _PausingReadEvidenceRepository(
                guard,
                observed=self._observed_event,
                release=self._release_event,
            )
        else:
            self._evidence = _PausingLockEvidenceRepository(
                guard,
                locked=self._observed_event,
                release=self._release_event,
            )
        return self


class _InstrumentedUnitOfWorkFactory:
    def __init__(
        self,
        engine: Engine,
        observed: Event,
        release: Event,
        *,
        pause_read: bool,
    ) -> None:
        self._engine = engine
        self._observed = observed
        self._release = release
        self._pause_read = pause_read

    def __call__(self) -> PostgreSQLUnitOfWork:
        return _InstrumentedUnitOfWork(
            self._engine,
            observed=self._observed,
            release=self._release,
            pause_read=self._pause_read,
        )


class _SignalingUnitOfWork(PostgreSQLUnitOfWork):
    def __init__(self, engine: Engine, attempting: Event) -> None:
        super().__init__(engine)
        self._attempting = attempting

    def __enter__(self) -> Self:
        super().__enter__()
        guard = self._transaction_guard
        if guard is None:
            raise RuntimeError("Transaction guard was not initialized.")
        self._evidence = _SignalingLockEvidenceRepository(
            guard,
            attempting=self._attempting,
        )
        return self


class _SignalingUnitOfWorkFactory:
    def __init__(self, engine: Engine, attempting: Event) -> None:
        self._engine = engine
        self._attempting = attempting

    def __call__(self) -> PostgreSQLUnitOfWork:
        return _SignalingUnitOfWork(self._engine, self._attempting)


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


def _reject(
    evidence: EvidenceHistory,
    *,
    previous: str,
) -> DecideEvidenceAdmissibility:
    return replace(
        _restrict(evidence, previous=previous),
        requested_action=EvidenceAdmissibilityRequestedAction.REJECT,
        reason_code=EvidenceAdmissibilityReason.CONTENT_OR_CONTEXT_REJECTED,
    )


def _admit(evidence: EvidenceHistory) -> DecideEvidenceAdmissibility:
    return replace(
        _restrict(evidence),
        requested_action=EvidenceAdmissibilityRequestedAction.ADMIT,
        reason_code=EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED,
    )


def _correct(evidence: EvidenceHistory) -> CorrectEvidence:
    content_original = evidence.latest.content_original
    assert content_original is not None
    return CorrectEvidence(
        command_id=EvidenceCommandId.new(),
        evidence_id=evidence.latest.id,
        expected_evidence_digest=evidence.latest.evidence_digest,
        kind=evidence.latest.kind,
        language=evidence.latest.language,
        locator=evidence.latest.locator,
        located_content=content_original.encode(),
        content_original=content_original,
        extraction_method="F5_3_REVIEW_CORRECTION",
        extraction_method_version="1",
    )


def _revoke(evidence: EvidenceHistory) -> RevokeEvidence:
    return RevokeEvidence(
        command_id=EvidenceCommandId.new(),
        evidence_id=evidence.latest.id,
        expected_evidence_digest=evidence.latest.evidence_digest,
        reason=EvidenceLifecycleReason.CONTENT_INVALID,
    )


def _set_investigation_state(engine: Engine, evidence: EvidenceHistory, state: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.update(investigation_table)
            .where(investigation_table.c.id == evidence.latest.investigation_id.value)
            .values(state=state, state_version=investigation_table.c.state_version + 1)
        )


def _add_second_owner(engine: Engine, actor: ActorContext) -> ActorContext:
    user_id = UserId.from_value("50000000-0000-4000-8000-000000000053")
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.users.add(
            UserAccount(
                id=user_id,
                email=EmailAddress("f53-independent-reviewer@example.test"),
                display_name="F5.3 Independent Reviewer",
                status=UserAccountStatus.ACTIVE,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        unit_of_work.memberships.add(
            WorkspaceMembership(
                id=MembershipId.new(),
                workspace_id=actor.workspace_id,
                user_id=user_id,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        unit_of_work.commit()
    return ActorContext(
        user_id=user_id,
        workspace_id=actor.workspace_id,
        correlation_id=actor.correlation_id,
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


@pytest.mark.parametrize("case", ["self_approval", "trust_laundering", "storage_policy"])
def test_semantically_forged_persisted_admissible_fails_closed(
    engine: Engine,
    case: str,
) -> None:
    actor = _seed_collecting(engine, owner=True)
    registration = replace(
        evidence_command(engine, actor),
        original_content=SYNTHETIC_ARTIFACT_BYTES,
        locator=synthetic_locator(),
        located_content=SYNTHETIC_LOCATED_BYTES,
        content_original=SYNTHETIC_LOCATED_BYTES.decode(),
    )
    if case == "trust_laundering":
        registration = replace(
            registration,
            located_content=b"Different controlled text",
            content_original="Different controlled text",
        )
    elif case == "storage_policy":
        registration = replace(
            registration,
            storage_mode=ArtifactStorageMode.OBJECT,
            storage_reference=f"workspace/{actor.workspace_id}/f53-review/object",
        )
    evidence = (
        EvidenceService(PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW))
        .register(actor, registration)
        .history
    )
    _set_investigation_state(engine, evidence, "VERIFYING")
    reviewer = _add_second_owner(engine, actor)
    decided_by = actor.user_id if case == "self_approval" else reviewer.user_id
    forged = build_evidence_admissibility_decision(
        decision_id=EvidenceAdmissibilityDecisionId.new(),
        evidence=evidence.latest,
        decision_sequence=1,
        supersedes_decision_id=None,
        outcome=EvidenceAdmissibilityDecisionOutcome.ADMISSIBLE,
        reason_code=EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED,
        policy_id="F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1",
        policy_version=1,
        purpose=EvidenceAdmissibilityPurpose.INTERNAL_FACTUAL_EVIDENCE_USE,
        admission_basis=EvidenceAdmissionBasis.CONTROLLED_TEST_EVIDENCE,
        controlled_trust_root_id=F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.manifest_id,
        controlled_trust_root_version=F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.version,
        controlled_trust_root_digest=F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.digest,
        valid_until=None,
        command_id=EvidenceAdmissibilityCommandId.new(),
        command_digest=sha256(f"forged-{case}".encode()).hexdigest(),
        decided_by=decided_by,
        decided_at=NOW,
    )
    with engine.begin() as connection:
        connection.execute(
            sa.insert(evidence_admissibility_decision_table).values(
                **evidence_admissibility_decision_to_values(forged)
            )
        )
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        structurally_valid = unit_of_work.evidence_admissibility.get_history(
            actor.workspace_id, evidence.latest.id
        )
        unit_of_work.commit()
    assert structurally_valid == EvidenceAdmissibilityHistory(decisions=(forged,))

    service = EvidenceAdmissibilityService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(NOW),
    )
    with pytest.raises(InvalidEvidenceAdmissibilityError):
        service.read(actor, evidence.latest.id, as_of=NOW)


def test_historical_admission_remains_reproducible_after_correction_and_revocation(
    engine: Engine,
) -> None:
    actor = _seed_collecting(engine, owner=True)
    registration = replace(
        evidence_command(engine, actor),
        original_content=SYNTHETIC_ARTIFACT_BYTES,
        locator=synthetic_locator(),
        located_content=SYNTHETIC_LOCATED_BYTES,
        content_original=SYNTHETIC_LOCATED_BYTES.decode(),
    )
    original = (
        EvidenceService(PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW))
        .register(actor, registration)
        .history
    )
    _set_investigation_state(engine, original, "VERIFYING")
    reviewer = _add_second_owner(engine, actor)
    service = EvidenceAdmissibilityService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )
    admitted = service.decide(reviewer, _admit(original))
    assert admitted.effective.status is EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE

    _set_investigation_state(engine, original, "COLLECTING")
    evidence_service = EvidenceService(
        PostgreSQLUnitOfWorkFactory(engine),
        ContextualAuthorizer(),
        FakeClock(MUTATION_TIME),
    )
    corrected = evidence_service.correct(actor, _correct(original)).history
    revoked = (
        EvidenceService(
            PostgreSQLUnitOfWorkFactory(engine),
            ContextualAuthorizer(),
            FakeClock(REVOCATION_TIME),
        )
        .revoke(actor, _revoke(corrected))
        .history
    )
    _set_investigation_state(engine, revoked, "VERIFYING")

    historical = service.read(reviewer, original.latest.id, as_of=NOW)
    at_correction = service.read(reviewer, original.latest.id, as_of=MUTATION_TIME)
    at_revocation = service.read(reviewer, original.latest.id, as_of=REVOCATION_TIME)
    assert historical.effective.status is EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE
    assert historical.effective.evidence_id == original.latest.id
    assert at_correction.effective.status is EffectiveEvidenceAdmissibilityStatus.PENDING
    assert at_correction.effective.evidence_id == corrected.latest.id
    assert at_revocation.effective.status is EffectiveEvidenceAdmissibilityStatus.REVOKED


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


@pytest.mark.parametrize(
    "operation",
    ["initial_decision", "superseding_decision", "correction", "revoke"],
)
def test_read_stabilizes_against_concurrent_commits_without_sleep(
    engine: Engine,
    operation: str,
) -> None:
    actor, evidence, decision_service = _seed_verifying(engine)
    if operation == "superseding_decision":
        first = decision_service.decide(actor, _restrict(evidence)).history.latest
    else:
        first = None
    observed = Event()
    release = Event()
    read_service = EvidenceAdmissibilityService(
        _InstrumentedUnitOfWorkFactory(
            engine,
            observed,
            release,
            pause_read=True,
        ),
        ContextualAuthorizer(),
        FakeClock(MUTATION_TIME),
    )
    cutoff = MUTATION_TIME if operation in {"correction", "revoke"} else NOW

    with ThreadPoolExecutor(max_workers=2) as executor:
        read_future = executor.submit(
            read_service.read,
            actor,
            evidence.latest.id,
            as_of=cutoff,
        )
        assert observed.wait(timeout=10)
        try:
            if operation == "initial_decision":
                decision_service.decide(actor, _restrict(evidence))
            elif operation == "superseding_decision":
                assert first is not None
                decision_service.decide(
                    actor,
                    _reject(evidence, previous=first.decision_digest),
                )
            else:
                _set_investigation_state(engine, evidence, "COLLECTING")
                mutation_service = EvidenceService(
                    PostgreSQLUnitOfWorkFactory(engine),
                    ContextualAuthorizer(),
                    FakeClock(MUTATION_TIME),
                )
                if operation == "correction":
                    mutation_service.correct(actor, _correct(evidence))
                else:
                    mutation_service.revoke(actor, _revoke(evidence))
                _set_investigation_state(engine, evidence, "VERIFYING")
        finally:
            release.set()
        result = read_future.result(timeout=30)

    if operation == "initial_decision":
        assert result.effective.status is EffectiveEvidenceAdmissibilityStatus.RESTRICTED
        assert result.decision_histories[0].latest.decision_sequence == 1
    elif operation == "superseding_decision":
        assert result.effective.status is EffectiveEvidenceAdmissibilityStatus.REJECTED
        assert result.decision_histories[0].latest.decision_sequence == 2
    elif operation == "correction":
        assert result.effective.status is EffectiveEvidenceAdmissibilityStatus.PENDING
        assert result.evidence_history.latest.version == 2
        assert result.effective.evidence_id == result.evidence_history.latest.id
    else:
        assert result.effective.status is EffectiveEvidenceAdmissibilityStatus.REVOKED
        assert result.evidence_history.is_revoked


@pytest.mark.parametrize("operation", ["correction", "revoke"])
def test_decision_serializes_against_evidence_mutation_without_sleep(
    engine: Engine,
    operation: str,
) -> None:
    actor, evidence, _ = _seed_verifying(engine)
    _set_investigation_state(engine, evidence, "COLLECTING")
    locked = Event()
    release = Event()
    attempting = Event()
    mutation_service = EvidenceService(
        _InstrumentedUnitOfWorkFactory(
            engine,
            locked,
            release,
            pause_read=False,
        ),
        ContextualAuthorizer(),
        FakeClock(MUTATION_TIME),
    )
    decision_service = EvidenceAdmissibilityService(
        _SignalingUnitOfWorkFactory(engine, attempting),
        ContextualAuthorizer(),
        FakeClock(MUTATION_TIME),
    )

    def mutate() -> None:
        if operation == "correction":
            mutation_service.correct(actor, _correct(evidence))
        else:
            mutation_service.revoke(actor, _revoke(evidence))

    with ThreadPoolExecutor(max_workers=2) as executor:
        mutation_future = executor.submit(mutate)
        assert locked.wait(timeout=10)
        _set_investigation_state(engine, evidence, "VERIFYING")
        decision_future = executor.submit(decision_service.decide, actor, _restrict(evidence))
        assert attempting.wait(timeout=10)
        release.set()
        if operation == "correction":
            with pytest.raises(InvalidEvidenceContextError):
                mutation_future.result(timeout=30)
            decision = decision_future.result(timeout=30)
            assert decision.effective.status is EffectiveEvidenceAdmissibilityStatus.RESTRICTED
        else:
            mutation_future.result(timeout=30)
            with pytest.raises(InvalidEvidenceAdmissibilityError):
                decision_future.result(timeout=30)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        persisted_evidence = unit_of_work.evidence.get_history(
            actor.workspace_id, evidence.latest.id
        )
        persisted_decision = unit_of_work.evidence_admissibility.get_history(
            actor.workspace_id, evidence.latest.id
        )
        unit_of_work.commit()
    assert persisted_evidence is not None
    if operation == "correction":
        assert persisted_evidence == evidence
        assert persisted_decision is not None
    else:
        assert persisted_evidence.is_revoked
        assert persisted_decision is None


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
