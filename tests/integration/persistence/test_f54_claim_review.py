"""F5.4 PostgreSQL happy path over the controlled F5.3 trust root."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier, Event
from typing import Literal, Self

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import AuditActionCode
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.claim_evidence_policy import (
    ClaimEvidenceEligibilityPolicyV1,
    ControlledEvidenceAnchorV1,
    build_manifest,
    locator_digest,
)
from intelligence.application.claim_review import ClaimReviewOperationResult, DecideClaimReview
from intelligence.application.claims import CorrectClaim, ProposedClaimEvidenceLink
from intelligence.application.errors import (
    ClaimReviewPredecessorError,
    InvalidClaimReviewError,
    PersistenceConflictError,
)
from intelligence.application.evidence import EvidenceOperationResult
from intelligence.application.ports.unit_of_work import UnitOfWorkFactory
from intelligence.application.services.claim_review import ClaimReviewService
from intelligence.application.services.claims import ClaimService
from intelligence.application.services.evidence import EvidenceService
from intelligence.application.services.evidence_admissibility import EvidenceAdmissibilityService
from intelligence.claims.models import Claim, ClaimCorrectionReason, ClaimHistory
from intelligence.claims.review import (
    ClaimReviewDecision,
    ClaimReviewReason,
    ClaimReviewRequestedAction,
    EffectiveClaimReviewStatus,
)
from intelligence.domain.audit import AuditEvent, AuditOutcome
from intelligence.domain.identifiers import (
    ClaimCommandId,
    ClaimId,
    ClaimReviewCommandId,
    WorkspaceId,
)
from intelligence.evidence.models import Evidence, EvidenceHistory, EvidenceLifecycleEvent
from intelligence.infrastructure.persistence.postgresql.claim_repository import (
    PostgreSQLClaimRepository,
)
from intelligence.infrastructure.persistence.postgresql.claim_review_repository import (
    PostgreSQLClaimReviewDecisionRepository,
)
from intelligence.infrastructure.persistence.postgresql.claim_review_tables import (
    claim_review_decision_table,
)
from intelligence.infrastructure.persistence.postgresql.evidence_repository import (
    PostgreSQLEvidenceRepository,
)
from intelligence.infrastructure.persistence.postgresql.repositories import (
    PostgreSQLAuditEventRepository,
)
from intelligence.infrastructure.persistence.postgresql.tables import audit_event_table
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
from tests.integration.persistence.test_f51_evidence import (
    NOW,
)
from tests.integration.persistence.test_f51_evidence import _register_command as evidence_command
from tests.integration.persistence.test_f51_evidence import _seed_collecting as f53_seed_collecting
from tests.integration.persistence.test_f52_claims import _command as claim_command
from tests.integration.persistence.test_f53_evidence_admissibility import (
    _add_second_owner,
    _admit,
    _alembic_config,
)
from tests.integration.persistence.test_f53_evidence_admissibility import (
    _correct as f53_correct,
)
from tests.integration.persistence.test_f53_evidence_admissibility import (
    _reject as f53_reject,
)
from tests.integration.persistence.test_f53_evidence_admissibility import (
    _revoke as f53_revoke,
)
from tests.integration.persistence.test_f53_evidence_admissibility import (
    clean_database as f53_clean_database,
)
from tests.integration.persistence.test_f53_evidence_admissibility import (
    engine as f53_engine,
)
from tests.unit.application.fakes import FakeClock

_PREVIOUS_HEAD = "20260822_13"
_MUTATION_TIME = NOW + timedelta(seconds=1)
_DECISION_TIME = NOW + timedelta(seconds=2)
_INVALIDATION_TIME = NOW + timedelta(seconds=3)
_READMISSION_TIME = NOW + timedelta(seconds=4)
_SUPERSESSION_TIME = NOW + timedelta(seconds=5)


class _PausingClaimReadRepository(PostgreSQLClaimRepository):
    """Pause once after read discovery, before F5.4 obtains dependency locks."""

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

    def get_history(self, workspace_id: WorkspaceId, claim_id: ClaimId) -> ClaimHistory | None:
        history = super().get_history(workspace_id, claim_id)
        if not self._paused:
            self._paused = True
            self._observed.set()
            if not self._release.wait(timeout=20):
                raise RuntimeError("Timed out waiting to release Claim-review read discovery.")
        return history


class _PausingClaimLockRepository(PostgreSQLClaimRepository):
    """Hold the global Claim lock after acquisition for a deterministic contender."""

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

    def acquire_history_lock(self, workspace_id: WorkspaceId, claim_id: ClaimId) -> None:
        super().acquire_history_lock(workspace_id, claim_id)
        self._observed.set()
        if not self._release.wait(timeout=20):
            raise RuntimeError("Timed out waiting to release Claim lock.")


class _SignalingClaimLockRepository(PostgreSQLClaimRepository):
    """Signal a contender immediately before it waits for the Claim lock."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard, *, attempting: Event) -> None:
        super().__init__(transaction_guard)
        self._attempting = attempting

    def acquire_history_lock(self, workspace_id: WorkspaceId, claim_id: ClaimId) -> None:
        self._attempting.set()
        super().acquire_history_lock(workspace_id, claim_id)


class _PausingEvidenceAppendRepository(PostgreSQLEvidenceRepository):
    """Pause after Evidence mutation validation, before its append becomes visible."""

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

    def _pause(self) -> None:
        self._observed.set()
        if not self._release.wait(timeout=20):
            raise RuntimeError("Timed out waiting to release Evidence mutation append.")

    def add_correction(self, evidence: Evidence, event: EvidenceLifecycleEvent) -> None:
        self._pause()
        super().add_correction(evidence, event)

    def add_lifecycle_event(self, event: EvidenceLifecycleEvent) -> None:
        self._pause()
        super().add_lifecycle_event(event)


class _DuplicateDecisionAppendRepository(PostgreSQLClaimReviewDecisionRepository):
    """Force a real PostgreSQL uniqueness failure after appending a decision."""

    def add_initial(self, decision: ClaimReviewDecision) -> None:
        super().add_initial(decision)
        super().add_initial(decision)


class _DuplicateAuditAppendRepository(PostgreSQLAuditEventRepository):
    """Force a real PostgreSQL uniqueness failure after the success audit write."""

    def add(self, event: AuditEvent) -> None:
        super().add(event)
        super().add(event)


class _F54InstrumentedUnitOfWork(PostgreSQLUnitOfWork):
    def __init__(
        self,
        engine: Engine,
        *,
        mode: Literal[
            "claim_read",
            "claim_lock",
            "claim_signal",
            "evidence_append",
            "decision_duplicate",
            "audit_duplicate",
        ],
        observed: Event,
        release: Event | None,
    ) -> None:
        super().__init__(engine)
        self._mode = mode
        self._observed = observed
        self._release = release

    def __enter__(self) -> Self:
        super().__enter__()
        guard = self._transaction_guard
        if guard is None:
            raise RuntimeError("Transaction guard was not initialized.")
        if self._mode == "claim_read":
            if self._release is None:
                raise RuntimeError("Claim read instrumentation requires a release Event.")
            self._claims = _PausingClaimReadRepository(
                guard, observed=self._observed, release=self._release
            )
        elif self._mode == "claim_lock":
            if self._release is None:
                raise RuntimeError("Claim lock instrumentation requires a release Event.")
            self._claims = _PausingClaimLockRepository(
                guard, observed=self._observed, release=self._release
            )
        elif self._mode == "claim_signal":
            self._claims = _SignalingClaimLockRepository(guard, attempting=self._observed)
        elif self._mode == "evidence_append":
            if self._release is None:
                raise RuntimeError("Evidence append instrumentation requires a release Event.")
            self._evidence = _PausingEvidenceAppendRepository(
                guard, observed=self._observed, release=self._release
            )
        elif self._mode == "decision_duplicate":
            self._claim_reviews = _DuplicateDecisionAppendRepository(guard)
        else:
            self._audit_events = _DuplicateAuditAppendRepository(guard)
        return self


class _F54InstrumentedUnitOfWorkFactory:
    def __init__(
        self,
        engine: Engine,
        *,
        mode: Literal[
            "claim_read",
            "claim_lock",
            "claim_signal",
            "evidence_append",
            "decision_duplicate",
            "audit_duplicate",
        ],
        observed: Event,
        release: Event | None = None,
    ) -> None:
        self._engine = engine
        self._mode = mode
        self._observed = observed
        self._release = release

    def __call__(self) -> PostgreSQLUnitOfWork:
        return _F54InstrumentedUnitOfWork(
            self._engine,
            mode=self._mode,
            observed=self._observed,
            release=self._release,
        )


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    """Reuse the F5.3 controlled PostgreSQL lifecycle."""

    yield from f53_engine.__wrapped__()  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def clean_database(engine: Engine) -> Iterator[None]:
    """Reuse F5.3 cleanup, including the F5.4 dependent relation."""

    yield from f53_clean_database.__wrapped__(engine)  # type: ignore[attr-defined]


def _accepted_review_inputs(
    engine: Engine,
) -> tuple[ActorContext, Claim, EvidenceHistory, ClaimReviewService, DecideClaimReview]:
    """Create only the controlled F5.3/F5.2 inputs required by an F5.4 decision."""

    creator = f53_seed_collecting(engine, owner=True)
    evidence = (
        EvidenceService(PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW))
        .register(
            creator,
            replace(
                evidence_command(engine, creator),
                original_content=SYNTHETIC_ARTIFACT_BYTES,
                locator=synthetic_locator(),
                located_content=SYNTHETIC_LOCATED_BYTES,
                content_original=SYNTHETIC_LOCATED_BYTES.decode(),
            ),
        )
        .history
    )
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE investigation SET state = 'VERIFYING', "
                "state_version = state_version + 1 WHERE id = :id"
            ),
            {"id": evidence.latest.investigation_id.value},
        )
    reviewer = _add_second_owner(engine, creator)
    EvidenceAdmissibilityService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).decide(reviewer, _admit(evidence))
    anchor = ControlledEvidenceAnchorV1(
        artifact_original_sha256=evidence.artifact.original_content_sha256,
        evidence_content_sha256=evidence.latest.content_sha256,
        evidence_kind=evidence.latest.kind,
        locator_type=evidence.latest.locator.type,
        locator_digest=locator_digest(evidence.latest.locator),
    )
    claim = (
        ClaimService(
            PostgreSQLUnitOfWorkFactory(engine),
            ContextualAuthorizer(),
            FakeClock(NOW),
            ClaimEvidenceEligibilityPolicyV1(build_manifest((anchor,))),
        )
        .register(creator, claim_command(evidence))
        .history.latest
    )
    service = ClaimReviewService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )
    command = DecideClaimReview(
        command_id=ClaimReviewCommandId.new(),
        investigation_id=claim.investigation_id,
        claim_id=claim.id,
        expected_claim_digest=claim.claim_digest,
        expected_previous_decision_digest=None,
        requested_action=ClaimReviewRequestedAction.ACCEPT,
        reason_code=ClaimReviewReason.FACTUAL_BASIS_ACCEPTED,
    )
    return reviewer, claim, evidence, service, command


def test_repository_returns_typed_absence_for_unknown_history_and_command(engine: Engine) -> None:
    """Absent tenant-scoped Claim-review rows never reconstruct a history."""

    creator = f53_seed_collecting(engine, owner=True)
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert unit_of_work.claim_reviews.get_history(creator.workspace_id, ClaimId.new()) is None
        assert (
            unit_of_work.claim_reviews.get_history_by_command(
                creator.workspace_id, ClaimReviewCommandId.new()
            )
            is None
        )


def _claim_correction(claim: Claim, evidence: EvidenceHistory) -> CorrectClaim:
    """Create a fresh exact-version F5.2 correction for the controlled Claim."""

    original = claim_command(evidence)
    return CorrectClaim(
        command_id=ClaimCommandId.new(),
        claim_id=claim.id,
        expected_claim_digest=claim.claim_digest,
        predicate_code=original.predicate_code,
        predicate_version=original.predicate_version,
        value=original.value,
        temporal=original.temporal,
        criticality=original.criticality,
        creation_method=original.creation_method,
        creation_method_version=original.creation_method_version,
        correction_reason=ClaimCorrectionReason.VALUE_CORRECTION,
        links=original.links,
    )


def _claim_service(
    engine: Engine, evidence: EvidenceHistory, factory: UnitOfWorkFactory
) -> ClaimService:
    anchor = ControlledEvidenceAnchorV1(
        artifact_original_sha256=evidence.artifact.original_content_sha256,
        evidence_content_sha256=evidence.latest.content_sha256,
        evidence_kind=evidence.latest.kind,
        locator_type=evidence.latest.locator.type,
        locator_digest=locator_digest(evidence.latest.locator),
    )
    return ClaimService(
        factory,
        ContextualAuthorizer(),
        FakeClock(_MUTATION_TIME),
        ClaimEvidenceEligibilityPolicyV1(build_manifest((anchor,))),
    )


def _set_investigation_state(engine: Engine, evidence: EvidenceHistory, state: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE investigation SET state = :state, state_version = state_version + 1 "
                "WHERE id = :id"
            ),
            {"id": evidence.latest.investigation_id.value, "state": state},
        )


def test_concurrent_initial_reviews_serialize_without_fork_or_duplicate_audit(
    engine: Engine,
) -> None:
    """The command and Claim-review history locks serialize contenders deterministically."""

    reviewer, claim, _, service, command = _accepted_review_inputs(engine)
    commands = (command, replace(command, command_id=ClaimReviewCommandId.new()))
    barrier = Barrier(len(commands))

    def decide(candidate: DecideClaimReview) -> str:
        barrier.wait(timeout=20)
        try:
            service.decide(reviewer, candidate)
        except ClaimReviewPredecessorError:
            return "STALE"
        return "SUCCESS"

    with ThreadPoolExecutor(max_workers=len(commands)) as executor:
        futures = [executor.submit(decide, item) for item in commands]
        outcomes = [future.result(timeout=30) for future in futures]

    assert sorted(outcomes) == ["STALE", "SUCCESS"]
    with engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(claim_review_decision_table))
            == 1
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(audit_event_table)
                .where(
                    audit_event_table.c.action_code == AuditActionCode.CLAIM_REVIEW_DECIDED.value
                )
                .where(audit_event_table.c.outcome == AuditOutcome.SUCCESS.value)
            )
            == 1
        )
    assert service.read(reviewer, claim.id, as_of=NOW).effective.status.value == "ACCEPTED"


def test_replay_stays_idempotent_during_concurrent_evidence_correction(engine: Engine) -> None:
    """A replay is resolved by command lock before a dependency mutation can append it."""

    reviewer, claim, evidence, service, command = _accepted_review_inputs(engine)
    first = service.decide(reviewer, command)
    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE investigation SET state = 'COLLECTING' WHERE id = :id"),
            {"id": claim.investigation_id.value},
        )
    barrier = Barrier(2)
    mutation_service = EvidenceService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_MUTATION_TIME)
    )

    def replay() -> ClaimReviewOperationResult:
        barrier.wait(timeout=20)
        return service.decide(reviewer, command)

    def correct() -> EvidenceOperationResult:
        barrier.wait(timeout=20)
        return mutation_service.correct(reviewer, f53_correct(evidence))

    with ThreadPoolExecutor(max_workers=2) as executor:
        replay_future = executor.submit(replay)
        correction_future = executor.submit(correct)
        replayed = replay_future.result(timeout=30)
        correction_future.result(timeout=30)

    assert replayed.replayed
    assert replayed.history.latest.id == first.history.latest.id
    with engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(claim_review_decision_table))
            == 1
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(audit_event_table)
                .where(
                    audit_event_table.c.action_code == AuditActionCode.CLAIM_REVIEW_DECIDED.value
                )
            )
            == 1
        )


def test_review_and_f53_supersession_have_only_serializable_outcomes(engine: Engine) -> None:
    """F5.4 locks the F5.3 history before it derives a positive factual basis."""

    reviewer, _, evidence, service, command = _accepted_review_inputs(engine)
    admissibility = EvidenceAdmissibilityService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )
    prior = admissibility.read(reviewer, evidence.latest.id, as_of=NOW).decision_histories[0].latest
    barrier = Barrier(2)

    def review() -> str:
        barrier.wait(timeout=20)
        try:
            service.decide(reviewer, command)
        except InvalidClaimReviewError:
            return "BLOCKED"
        return "ACCEPTED"

    def supersede() -> None:
        barrier.wait(timeout=20)
        admissibility.decide(reviewer, f53_reject(evidence, previous=prior.decision_digest))

    with ThreadPoolExecutor(max_workers=2) as executor:
        review_future = executor.submit(review)
        supersede_future = executor.submit(supersede)
        outcome = review_future.result(timeout=30)
        supersede_future.result(timeout=30)

    assert outcome in {"ACCEPTED", "BLOCKED"}
    with engine.connect() as connection:
        review_count = connection.scalar(
            sa.select(sa.func.count()).select_from(claim_review_decision_table)
        )
        assert review_count in {0, 1}
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(audit_event_table)
                .where(
                    audit_event_table.c.action_code == AuditActionCode.CLAIM_REVIEW_DECIDED.value
                )
                .where(audit_event_table.c.outcome == AuditOutcome.SUCCESS.value)
            )
            == review_count
        )


def test_review_fails_closed_when_claim_correction_wins_the_claim_lock(engine: Engine) -> None:
    """A review for the replaced Claim version cannot append an ACCEPT decision."""

    reviewer, claim, evidence, service, command = _accepted_review_inputs(engine)
    locked = Event()
    release = Event()
    attempting = Event()
    correction_service = _claim_service(
        engine,
        evidence,
        _F54InstrumentedUnitOfWorkFactory(
            engine, mode="claim_lock", observed=locked, release=release
        ),
    )
    competing_review = ClaimReviewService(
        _F54InstrumentedUnitOfWorkFactory(engine, mode="claim_signal", observed=attempting),
        ContextualAuthorizer(),
        FakeClock(_MUTATION_TIME),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        correction_future = executor.submit(
            correction_service.correct, reviewer, _claim_correction(claim, evidence)
        )
        assert locked.wait(timeout=10)
        review_future = executor.submit(competing_review.decide, reviewer, command)
        assert attempting.wait(timeout=10)
        release.set()
        corrected = correction_future.result(timeout=30)
        with pytest.raises(InvalidClaimReviewError):
            review_future.result(timeout=30)

    assert corrected.history.latest.version == 2
    result = service.read(reviewer, claim.id, as_of=_MUTATION_TIME)
    assert result.history is None
    assert result.effective.status is EffectiveClaimReviewStatus.PENDING
    with engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(claim_review_decision_table))
            == 0
        )


@pytest.mark.parametrize("operation", ["correction", "revoke"])
def test_review_fails_closed_when_evidence_mutation_commits_first(
    engine: Engine, operation: str
) -> None:
    """A held Evidence append cannot yield an ACCEPT from an obsolete F5.3 basis."""

    reviewer, claim, evidence, service, command = _accepted_review_inputs(engine)
    _set_investigation_state(engine, evidence, "COLLECTING")
    observed = Event()
    release = Event()
    mutation_service = EvidenceService(
        _F54InstrumentedUnitOfWorkFactory(
            engine, mode="evidence_append", observed=observed, release=release
        ),
        ContextualAuthorizer(),
        FakeClock(_MUTATION_TIME),
    )
    review_service = ClaimReviewService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_MUTATION_TIME)
    )

    def mutate() -> object:
        if operation == "correction":
            return mutation_service.correct(reviewer, f53_correct(evidence))
        return mutation_service.revoke(reviewer, f53_revoke(evidence))

    with ThreadPoolExecutor(max_workers=2) as executor:
        mutation_future = executor.submit(mutate)
        assert observed.wait(timeout=10)
        _set_investigation_state(engine, evidence, "VERIFYING")
        review_future = executor.submit(review_service.decide, reviewer, command)
        release.set()
        mutation_future.result(timeout=30)
        with pytest.raises(InvalidClaimReviewError):
            review_future.result(timeout=30)

    result = service.read(reviewer, claim.id, as_of=_MUTATION_TIME)
    assert result.history is None
    assert result.effective.status is EffectiveClaimReviewStatus.PENDING
    with engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(claim_review_decision_table))
            == 0
        )


def test_read_stabilizes_against_claim_correction_without_mixed_snapshot(engine: Engine) -> None:
    """Read waits behind Claim correction, then projects the new version as PENDING."""

    reviewer, claim, evidence, _, _ = _accepted_review_inputs(engine)
    locked = Event()
    release = Event()
    attempting = Event()
    correction_service = _claim_service(
        engine,
        evidence,
        _F54InstrumentedUnitOfWorkFactory(
            engine, mode="claim_lock", observed=locked, release=release
        ),
    )
    read_service = ClaimReviewService(
        _F54InstrumentedUnitOfWorkFactory(engine, mode="claim_signal", observed=attempting),
        ContextualAuthorizer(),
        FakeClock(_MUTATION_TIME),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        correction_future = executor.submit(
            correction_service.correct, reviewer, _claim_correction(claim, evidence)
        )
        assert locked.wait(timeout=10)
        read_future = executor.submit(read_service.read, reviewer, claim.id, as_of=_MUTATION_TIME)
        assert attempting.wait(timeout=10)
        release.set()
        corrected = correction_future.result(timeout=30)
        result = read_future.result(timeout=30)

    assert corrected.history.latest.version == 2
    assert result.history is None
    assert result.effective.claim_id == corrected.history.latest.id
    assert result.effective.status is EffectiveClaimReviewStatus.PENDING


@pytest.mark.parametrize("operation", ["correction", "revoke"])
def test_read_stabilizes_against_evidence_mutation_without_mixed_snapshot(
    engine: Engine, operation: str
) -> None:
    """The reread after ordered Evidence locks sees one complete incompatible mutation."""

    reviewer, claim, evidence, service, command = _accepted_review_inputs(engine)
    service.decide(reviewer, command)
    observed = Event()
    release = Event()
    read_service = ClaimReviewService(
        _F54InstrumentedUnitOfWorkFactory(
            engine, mode="claim_read", observed=observed, release=release
        ),
        ContextualAuthorizer(),
        FakeClock(_MUTATION_TIME),
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        read_future = executor.submit(read_service.read, reviewer, claim.id, as_of=_MUTATION_TIME)
        assert observed.wait(timeout=10)
        _set_investigation_state(engine, evidence, "COLLECTING")
        mutation_service = EvidenceService(
            PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_MUTATION_TIME)
        )
        if operation == "correction":
            mutation_service.correct(reviewer, f53_correct(evidence))
        else:
            mutation_service.revoke(reviewer, f53_revoke(evidence))
        _set_investigation_state(engine, evidence, "VERIFYING")
        release.set()
        result = read_future.result(timeout=30)

    assert result.history is not None
    assert result.history.latest.decision_sequence == 1
    assert result.history.latest.supersedes_decision_id is None
    assert result.effective.status is EffectiveClaimReviewStatus.INVALIDATED


def test_read_stabilizes_against_f53_supersession_without_mixed_snapshot(engine: Engine) -> None:
    """F5.3 supersession committed between discovery and locks invalidates the projection."""

    reviewer, claim, evidence, service, command = _accepted_review_inputs(engine)
    initial = service.decide(reviewer, command).history.latest
    prior = (
        EvidenceAdmissibilityService(
            PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
        )
        .read(reviewer, evidence.latest.id, as_of=NOW)
        .decision_histories[0]
        .latest
    )
    observed = Event()
    release = Event()
    read_service = ClaimReviewService(
        _F54InstrumentedUnitOfWorkFactory(
            engine, mode="claim_read", observed=observed, release=release
        ),
        ContextualAuthorizer(),
        FakeClock(_MUTATION_TIME),
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        read_future = executor.submit(read_service.read, reviewer, claim.id, as_of=_MUTATION_TIME)
        assert observed.wait(timeout=10)
        EvidenceAdmissibilityService(
            PostgreSQLUnitOfWorkFactory(engine),
            ContextualAuthorizer(),
            FakeClock(_MUTATION_TIME),
        ).decide(reviewer, f53_reject(evidence, previous=prior.decision_digest))
        release.set()
        result = read_future.result(timeout=30)

    assert result.history is not None
    assert result.history.latest.id == initial.id
    assert result.effective.status is EffectiveClaimReviewStatus.INVALIDATED


def test_read_stabilizes_against_claim_review_append_without_mixed_snapshot(engine: Engine) -> None:
    """Read waits behind the same Claim lock and observes the complete review history."""

    reviewer, claim, _, _, command = _accepted_review_inputs(engine)
    locked = Event()
    release = Event()
    attempting = Event()
    deciding_service = ClaimReviewService(
        _F54InstrumentedUnitOfWorkFactory(
            engine, mode="claim_lock", observed=locked, release=release
        ),
        ContextualAuthorizer(),
        FakeClock(NOW),
    )
    read_service = ClaimReviewService(
        _F54InstrumentedUnitOfWorkFactory(engine, mode="claim_signal", observed=attempting),
        ContextualAuthorizer(),
        FakeClock(NOW),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        decision_future = executor.submit(deciding_service.decide, reviewer, command)
        assert locked.wait(timeout=10)
        read_future = executor.submit(read_service.read, reviewer, claim.id, as_of=NOW)
        assert attempting.wait(timeout=10)
        release.set()
        decided = decision_future.result(timeout=30)
        result = read_future.result(timeout=30)

    assert result.history is not None
    assert result.history.latest.id == decided.history.latest.id
    assert result.history.latest.decision_sequence == 1
    assert result.history.latest.supersedes_decision_id is None
    assert result.effective.status is EffectiveClaimReviewStatus.ACCEPTED


def test_temporal_projection_is_nonretroactive_monotonic_and_allows_a_new_epoch(
    engine: Engine,
) -> None:
    """A persisted invalidation cannot change old cutoffs or revive the old ACCEPT."""

    reviewer, claim, evidence, _, command = _accepted_review_inputs(engine)
    decision_service = ClaimReviewService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_DECISION_TIME)
    )
    before = decision_service.read(reviewer, claim.id, as_of=NOW)
    accepted = decision_service.decide(reviewer, command)
    assert before.effective.status is EffectiveClaimReviewStatus.PENDING
    assert accepted.history.latest.decided_at == _DECISION_TIME
    assert decision_service.read(reviewer, claim.id, as_of=_DECISION_TIME).effective.status is (
        EffectiveClaimReviewStatus.ACCEPTED
    )

    admissibility = EvidenceAdmissibilityService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_INVALIDATION_TIME)
    )
    prior = (
        admissibility.read(reviewer, evidence.latest.id, as_of=_DECISION_TIME)
        .decision_histories[0]
        .latest
    )
    restricted = admissibility.decide(
        reviewer, f53_reject(evidence, previous=prior.decision_digest)
    )
    assert decision_service.read(reviewer, claim.id, as_of=_DECISION_TIME).effective.status is (
        EffectiveClaimReviewStatus.ACCEPTED
    )
    invalidated = decision_service.read(reviewer, claim.id, as_of=_INVALIDATION_TIME)
    assert invalidated.history is not None
    assert invalidated.history.latest.id == accepted.history.latest.id
    assert invalidated.effective.status is EffectiveClaimReviewStatus.INVALIDATED

    readmitted = EvidenceAdmissibilityService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_READMISSION_TIME)
    ).decide(
        reviewer,
        replace(
            _admit(evidence),
            expected_previous_decision_digest=restricted.history.latest.decision_digest,
        ),
    )
    assert readmitted.effective.status.value == "ADMISSIBLE"
    # The implementation scans the whole interval, not merely its endpoints:
    # the transient F5.3 rejection permanently invalidates this review epoch.
    assert decision_service.read(reviewer, claim.id, as_of=_READMISSION_TIME).effective.status is (
        EffectiveClaimReviewStatus.INVALIDATED
    )

    renewed = ClaimReviewService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_SUPERSESSION_TIME)
    ).decide(
        reviewer,
        replace(
            command,
            command_id=ClaimReviewCommandId.new(),
            expected_previous_decision_digest=accepted.history.latest.decision_digest,
        ),
    )
    assert [item.decision_sequence for item in renewed.history.decisions] == [1, 2]
    assert renewed.history.latest.supersedes_decision_id == accepted.history.latest.id
    assert renewed.effective.status is EffectiveClaimReviewStatus.ACCEPTED


@pytest.mark.parametrize(
    ("requested_action", "reason_code", "expected"),
    [
        (
            ClaimReviewRequestedAction.REJECT,
            ClaimReviewReason.INTERNAL_FACTUAL_USE_REJECTED,
            EffectiveClaimReviewStatus.REJECTED,
        ),
        (
            ClaimReviewRequestedAction.RETURN_FOR_CORRECTION,
            ClaimReviewReason.CLAIM_CORRECTION_REQUIRED,
            EffectiveClaimReviewStatus.NEEDS_CORRECTION,
        ),
    ],
)
def test_negative_reviews_remain_stable_after_f53_dependency_supersession(
    engine: Engine,
    requested_action: ClaimReviewRequestedAction,
    reason_code: ClaimReviewReason,
    expected: EffectiveClaimReviewStatus,
) -> None:
    """Only positive review epochs are invalidated by later dependency changes."""

    reviewer, claim, evidence, _, command = _accepted_review_inputs(engine)
    service = ClaimReviewService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_DECISION_TIME)
    )
    negative = service.decide(
        reviewer,
        replace(command, requested_action=requested_action, reason_code=reason_code),
    )
    prior = (
        EvidenceAdmissibilityService(
            PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_DECISION_TIME)
        )
        .read(reviewer, evidence.latest.id, as_of=_DECISION_TIME)
        .decision_histories[0]
        .latest
    )
    EvidenceAdmissibilityService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_INVALIDATION_TIME)
    ).decide(reviewer, f53_reject(evidence, previous=prior.decision_digest))
    result = service.read(reviewer, claim.id, as_of=_INVALIDATION_TIME)
    assert result.history is not None
    assert result.history.latest.id == negative.history.latest.id
    assert result.effective.status is expected


def test_multiple_identical_trust_root_supports_invalidate_old_review_epoch(engine: Engine) -> None:
    """Two IDs may share the official F5.3 anchor; changing either invalidates the old basis."""

    creator = f53_seed_collecting(engine, owner=True)
    evidence_service = EvidenceService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )
    register = replace(
        evidence_command(engine, creator),
        original_content=SYNTHETIC_ARTIFACT_BYTES,
        locator=synthetic_locator(),
        located_content=SYNTHETIC_LOCATED_BYTES,
        content_original=SYNTHETIC_LOCATED_BYTES.decode(),
    )
    first = evidence_service.register(creator, register).history
    second = evidence_service.register(
        creator, replace(register, command_id=register.command_id.new())
    ).history
    _set_investigation_state(engine, first, "VERIFYING")
    reviewer = _add_second_owner(engine, creator)
    admissibility = EvidenceAdmissibilityService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )
    for evidence in (first, second):
        assert (
            admissibility.decide(reviewer, _admit(evidence)).effective.status.value == "ADMISSIBLE"
        )
    anchor = ControlledEvidenceAnchorV1(
        artifact_original_sha256=first.artifact.original_content_sha256,
        evidence_content_sha256=first.latest.content_sha256,
        evidence_kind=first.latest.kind,
        locator_type=first.latest.locator.type,
        locator_digest=locator_digest(first.latest.locator),
    )
    base = claim_command(first)
    claim = (
        ClaimService(
            PostgreSQLUnitOfWorkFactory(engine),
            ContextualAuthorizer(),
            FakeClock(NOW),
            ClaimEvidenceEligibilityPolicyV1(build_manifest((anchor,))),
        )
        .register(
            creator,
            replace(
                base,
                links=(
                    base.links[0],
                    ProposedClaimEvidenceLink(
                        evidence_id=second.latest.id,
                        expected_evidence_digest=second.latest.evidence_digest,
                        role=base.links[0].role,
                    ),
                ),
            ),
        )
        .history.latest
    )
    command = DecideClaimReview(
        command_id=ClaimReviewCommandId.new(),
        investigation_id=claim.investigation_id,
        claim_id=claim.id,
        expected_claim_digest=claim.claim_digest,
        expected_previous_decision_digest=None,
        requested_action=ClaimReviewRequestedAction.ACCEPT,
        reason_code=ClaimReviewReason.FACTUAL_BASIS_ACCEPTED,
    )
    review = ClaimReviewService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_DECISION_TIME)
    )
    original = review.decide(reviewer, command)
    prior = (
        admissibility.read(reviewer, first.latest.id, as_of=_DECISION_TIME)
        .decision_histories[0]
        .latest
    )
    EvidenceAdmissibilityService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_INVALIDATION_TIME)
    ).decide(reviewer, f53_reject(first, previous=prior.decision_digest))
    assert review.read(reviewer, claim.id, as_of=_INVALIDATION_TIME).effective.status is (
        EffectiveClaimReviewStatus.INVALIDATED
    )
    fresh = ClaimReviewService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_SUPERSESSION_TIME)
    ).decide(
        reviewer,
        replace(
            command,
            command_id=ClaimReviewCommandId.new(),
            expected_previous_decision_digest=original.history.latest.decision_digest,
        ),
    )
    assert fresh.effective.status is EffectiveClaimReviewStatus.ACCEPTED
    assert [item.decision_sequence for item in fresh.history.decisions] == [1, 2]


@pytest.mark.parametrize("mode", ["decision_duplicate", "audit_duplicate"])
def test_postgresql_uow_rolls_back_decision_and_audit_and_keeps_command_retryable(
    engine: Engine,
    mode: Literal["decision_duplicate", "audit_duplicate"],
) -> None:
    """PostgreSQL failures after decision persistence leave no decision, audit, or command ghost."""

    reviewer, _, _, _, command = _accepted_review_inputs(engine)
    failing = ClaimReviewService(
        _F54InstrumentedUnitOfWorkFactory(engine, mode=mode, observed=Event()),
        ContextualAuthorizer(),
        FakeClock(_DECISION_TIME),
    )
    with pytest.raises(PersistenceConflictError):
        failing.decide(reviewer, command)
    with engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(claim_review_decision_table))
            == 0
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(audit_event_table)
                .where(
                    audit_event_table.c.action_code == AuditActionCode.CLAIM_REVIEW_DECIDED.value
                )
            )
            == 0
        )
    retried = ClaimReviewService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_DECISION_TIME)
    ).decide(reviewer, command)
    assert retried.history.latest.decision_sequence == 1
    with engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(claim_review_decision_table))
            == 1
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(audit_event_table)
                .where(
                    audit_event_table.c.action_code == AuditActionCode.CLAIM_REVIEW_DECIDED.value
                )
                .where(audit_event_table.c.outcome == AuditOutcome.SUCCESS.value)
            )
            == 1
        )


def test_successful_atomic_commit_replay_and_audit_redaction(engine: Engine) -> None:
    """A committed review writes one minimal audit event; replay writes none."""

    reviewer, claim, evidence, _, command = _accepted_review_inputs(engine)
    service = ClaimReviewService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(_DECISION_TIME)
    )
    result = service.decide(reviewer, command)
    replay = service.decide(reviewer, command)
    assert replay.replayed
    with engine.connect() as connection:
        audit = (
            connection.execute(
                sa.select(audit_event_table)
                .where(
                    audit_event_table.c.action_code == AuditActionCode.CLAIM_REVIEW_DECIDED.value
                )
                .where(audit_event_table.c.outcome == AuditOutcome.SUCCESS.value)
            )
            .mappings()
            .one()
        )
    assert result.history.latest.decision_sequence == 1
    assert audit["reason_code"] is None
    assert audit["command_id"] is None
    assert audit["policy_id"] is None
    serialized = "|".join(str(value) for value in audit.values() if value is not None)
    forbidden = (
        SYNTHETIC_ARTIFACT_BYTES.decode(),
        SYNTHETIC_LOCATED_BYTES.decode(),
        evidence.latest.content_sha256,
        locator_digest(evidence.latest.locator),
        result.history.latest.review_basis_digest,
        repr(claim.value),
    )
    assert all(value not in serialized for value in forbidden)


def test_controlled_f53_admissible_evidence_enables_persisted_f54_accept(
    engine: Engine, clean_database: None
) -> None:
    creator = f53_seed_collecting(engine, owner=True)
    evidence = (
        EvidenceService(PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW))
        .register(
            creator,
            replace(
                evidence_command(engine, creator),
                original_content=SYNTHETIC_ARTIFACT_BYTES,
                locator=synthetic_locator(),
                located_content=SYNTHETIC_LOCATED_BYTES,
                content_original=SYNTHETIC_LOCATED_BYTES.decode(),
            ),
        )
        .history
    )
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE investigation SET state = 'VERIFYING', "
                "state_version = state_version + 1 WHERE id = :id"
            ),
            {"id": evidence.latest.investigation_id.value},
        )
    reviewer = _add_second_owner(engine, creator)
    admitted = EvidenceAdmissibilityService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    ).decide(reviewer, _admit(evidence))
    anchor = ControlledEvidenceAnchorV1(
        artifact_original_sha256=evidence.artifact.original_content_sha256,
        evidence_content_sha256=evidence.latest.content_sha256,
        evidence_kind=evidence.latest.kind,
        locator_type=evidence.latest.locator.type,
        locator_digest=locator_digest(evidence.latest.locator),
    )
    claim = (
        ClaimService(
            PostgreSQLUnitOfWorkFactory(engine),
            ContextualAuthorizer(),
            FakeClock(NOW),
            ClaimEvidenceEligibilityPolicyV1(build_manifest((anchor,))),
        )
        .register(creator, claim_command(evidence))
        .history.latest
    )
    service = ClaimReviewService(
        PostgreSQLUnitOfWorkFactory(engine), ContextualAuthorizer(), FakeClock(NOW)
    )
    command = DecideClaimReview(
        command_id=ClaimReviewCommandId.new(),
        investigation_id=claim.investigation_id,
        claim_id=claim.id,
        expected_claim_digest=claim.claim_digest,
        expected_previous_decision_digest=None,
        requested_action=ClaimReviewRequestedAction.ACCEPT,
        reason_code=ClaimReviewReason.FACTUAL_BASIS_ACCEPTED,
    )
    result = service.decide(reviewer, command)
    replay = service.decide(reviewer, command)
    superseding = service.decide(
        reviewer,
        replace(
            command,
            command_id=ClaimReviewCommandId.new(),
            expected_previous_decision_digest=result.history.latest.decision_digest,
            requested_action=ClaimReviewRequestedAction.REJECT,
            reason_code=ClaimReviewReason.INTERNAL_FACTUAL_USE_REJECTED,
        ),
    )
    assert admitted.effective.status.value == "ADMISSIBLE"
    assert result.effective.status.value == "ACCEPTED" and replay.replayed
    assert len(superseding.history.decisions) == 2
    with engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(claim_review_decision_table))
            == 2
        )
        actions = (
            connection.execute(
                sa.select(audit_event_table.c.action_code)
                .where(audit_event_table.c.workspace_id == reviewer.workspace_id.value)
                .where(
                    audit_event_table.c.action_code.in_(
                        (
                            AuditActionCode.CLAIM_REVIEW_DECIDED.value,
                            AuditActionCode.CLAIM_REVIEW_SUPERSEDED.value,
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        assert sorted(actions) == [
            AuditActionCode.CLAIM_REVIEW_DECIDED.value,
            AuditActionCode.CLAIM_REVIEW_SUPERSEDED.value,
        ]
    with pytest.raises(RuntimeError, match=r"Cannot downgrade F5\.4"):
        alembic_command.downgrade(_alembic_config(), _PREVIOUS_HEAD)
    protected_column_updates = (
        {"outcome": "UNSUPPORTED_OUTCOME"},
        {"purpose": "UNSUPPORTED_PURPOSE"},
        {"policy_version": 99},
        {"schema_version": 99},
        {"decision_sequence": 0},
        {"supersedes_decision_id": result.history.latest.id.value},
        {"claim_version": 999},
        {"workspace_id": ClaimReviewCommandId.new().value},
    )
    for values in protected_column_updates:
        with engine.connect() as connection:
            transaction = connection.begin()
            with pytest.raises(IntegrityError):
                connection.execute(
                    sa.update(claim_review_decision_table)
                    .where(claim_review_decision_table.c.id == result.history.latest.id.value)
                    .values(**values)
                )
            transaction.rollback()
    with engine.begin() as connection:
        connection.execute(
            sa.update(claim_review_decision_table)
            .where(claim_review_decision_table.c.id == result.history.latest.id.value)
            .values(review_basis_digest="0" * 64)
        )
    with pytest.raises(InvalidClaimReviewError):
        service.read(reviewer, claim.id, as_of=NOW)
    with engine.begin() as connection:
        connection.execute(
            sa.update(claim_review_decision_table)
            .where(claim_review_decision_table.c.id == result.history.latest.id.value)
            .values(decision_digest="0" * 64)
        )
    with pytest.raises(InvalidClaimReviewError):
        service.read(reviewer, claim.id, as_of=NOW)


def test_empty_f54_downgrade_reupgrade_and_metadata_check(engine: Engine) -> None:
    """The protected migration remains reversible only before history exists."""

    config = _alembic_config()
    alembic_command.downgrade(config, _PREVIOUS_HEAD)
    alembic_command.upgrade(config, "head")
    alembic_command.check(config)
    with engine.connect() as connection:
        assert (
            connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == "20260825_14"
        )
