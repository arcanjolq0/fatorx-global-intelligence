"""F4.3 command, decision integrity, service replay, and rollback tests."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.entity_candidate_review import build_candidate_batch_record
from intelligence.application.entity_confirmation import (
    ConfirmEntityCandidate,
    EntityConfirmationReason,
    EntityResolutionDecisionRecord,
    build_entity_resolution_decision_record,
    digest_entity_confirmation_command,
    validate_entity_resolution_decision_context,
)
from intelligence.application.errors import (
    AuthorizationDeniedError,
    CandidateExcludedError,
    CandidateNotInBatchError,
    ConcurrentInvestigationUpdateError,
    EntityConfirmationReasonError,
    InactiveCandidateBatchError,
    InvalidMaterializationPolicyError,
    InvestigationCommandCollisionError,
    InvestigationTransitionError,
    PersistenceDataError,
    PersistenceError,
    ResourceNotFoundError,
)
from intelligence.application.investigation_lifecycle import (
    InvestigationCommandDigest,
    InvestigationCommandType,
    InvestigationTransitionRecord,
)
from intelligence.application.services.entity_confirmation import EntityConfirmationService
from intelligence.domain.audit import AuditOutcome
from intelligence.domain.companies import CompanyStatus
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CompanyId,
    CorrelationId,
    EntityCandidateBatchId,
    EntityCandidateId,
    EntityResolutionDecisionId,
    InvestigationCommandId,
    InvestigationId,
    InvestigationTransitionId,
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
from intelligence.domain.investigation_inputs import IdentificationInput, OriginalAndNormalizedText
from intelligence.domain.investigations import Investigation, InvestigationState
from intelligence.entity_resolution.contracts import (
    CandidateIdentitySnapshot,
    CandidateOriginSnapshot,
    CandidateSubmissionBatch,
    EntityCandidateInput,
)
from intelligence.entity_resolution.matching import evaluate_candidate_batch
from intelligence.entity_resolution.materialization import (
    COMPANY_MATERIALIZATION_V1,
    materialize_company,
)
from intelligence.entity_resolution.policy import INITIAL_MATCH_POLICY, MatchPolicy
from intelligence.infrastructure.persistence.postgresql.mappers import (
    entity_resolution_decision_from_values,
    entity_resolution_decision_to_values,
)
from tests.unit.application.fakes import FakeDatabase, FakeUnitOfWorkFactory

NOW = datetime(2026, 8, 1, 15, tzinfo=UTC)


def _text(value: str) -> OriginalAndNormalizedText:
    return OriginalAndNormalizedText(original_value=value, normalized_value=value.casefold())


def _candidate(key: str, *, country: str = "BR") -> EntityCandidateInput:
    return EntityCandidateInput(
        candidate_key=key,
        identity=CandidateIdentitySnapshot(
            legal_name=_text("Empresa Exemplo S.A."),
            country_code=CountryCode(country),
        ),
        origin=CandidateOriginSnapshot(
            source_id="SYNTHETIC_SOURCE",
            connector_id="synthetic.source",
            connector_version="1.0.0",
            source_candidate_reference=f"opaque-{key}",
            collected_at=NOW - timedelta(minutes=2),
        ),
    )


@dataclass(slots=True)
class CountingClock:
    instant: datetime
    calls: list[datetime] = field(default_factory=list)

    def now(self) -> datetime:
        self.calls.append(self.instant)
        return self.instant


def _setup(
    *,
    role: MembershipRole = MembershipRole.ANALYST,
    policy: MatchPolicy = INITIAL_MATCH_POLICY,
    candidates: tuple[EntityCandidateInput, ...] | None = None,
    **factory_options: bool,
) -> tuple[
    ActorContext,
    Investigation,
    FakeDatabase,
    FakeUnitOfWorkFactory,
    CountingClock,
    EntityConfirmationService,
]:
    actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )
    identification_input = IdentificationInput(legal_name=_text("Empresa Exemplo S.A."))
    identifying = Investigation.reconstitute(
        id=InvestigationId.new(),
        workspace_id=actor.workspace_id,
        requested_by=actor.user_id,
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        created_at=NOW - timedelta(minutes=10),
        state=InvestigationState.IDENTIFYING,
        state_version=2,
        started_at=NOW - timedelta(minutes=9),
        identification_input=identification_input,
    )
    submission = CandidateSubmissionBatch(
        input_digest=identification_input.digest,
        candidates=candidates or (_candidate("candidate-1"),),
    )
    evaluation = evaluate_candidate_batch(
        investigation_country_code=identifying.country_code,
        identification_input=identification_input,
        batch=submission,
        policy=policy,
    )
    batch_id = EntityCandidateBatchId.new()
    batch = build_candidate_batch_record(
        batch_id=batch_id,
        workspace_id=actor.workspace_id,
        investigation_id=identifying.id,
        command_id=InvestigationCommandId.new(),
        created_by=actor.user_id,
        created_at=NOW - timedelta(minutes=1),
        submission=submission,
        policy=policy,
        evaluation=evaluation,
    )
    waiting = identifying.request_entity_confirmation(
        candidate_batch_id=batch_id,
        occurred_at=NOW - timedelta(minutes=1),
    ).investigation
    user = UserAccount(
        id=actor.user_id,
        email=EmailAddress(f"{actor.user_id.value}@example.test"),
        display_name="Reviewer",
        status=UserAccountStatus.ACTIVE,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )
    membership = WorkspaceMembership(
        id=MembershipId.new(),
        workspace_id=actor.workspace_id,
        user_id=actor.user_id,
        role=role,
        status=MembershipStatus.ACTIVE,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )
    database = FakeDatabase(
        investigations={(actor.workspace_id, waiting.id): waiting},
        entity_candidate_batches={(actor.workspace_id, batch.id): batch},
        users={actor.user_id: user},
        memberships={(actor.workspace_id, actor.user_id): membership},
    )
    factory = FakeUnitOfWorkFactory(database, **factory_options)
    clock = CountingClock(NOW)
    service = EntityConfirmationService(factory, ContextualAuthorizer(), clock)
    return actor, waiting, database, factory, clock, service


def _command(
    investigation: Investigation,
    database: FakeDatabase,
    *,
    candidate_index: int = 0,
    command_id: InvestigationCommandId | None = None,
    reason: EntityConfirmationReason = EntityConfirmationReason.MANUAL_OVERRIDE,
) -> ConfirmEntityCandidate:
    assert investigation.active_candidate_batch_id is not None
    batch = database.entity_candidate_batches[
        (investigation.workspace_id, investigation.active_candidate_batch_id)
    ]
    return ConfirmEntityCandidate(
        command_id=command_id or InvestigationCommandId.new(),
        investigation_id=investigation.id,
        expected_state_version=investigation.state_version,
        candidate_batch_id=batch.id,
        candidate_id=batch.candidates[candidate_index].id,
        review_reason=reason,
        materialization_policy=COMPANY_MATERIALIZATION_V1,
    )


def _confirmation_transition(
    actor: ActorContext,
    command: ConfirmEntityCandidate,
    decision: EntityResolutionDecisionRecord,
) -> InvestigationTransitionRecord:
    return InvestigationTransitionRecord(
        id=InvestigationTransitionId.new(),
        workspace_id=actor.workspace_id,
        investigation_id=command.investigation_id,
        command_id=command.command_id,
        command_type=InvestigationCommandType.CONFIRM_ENTITY_CANDIDATE,
        state_before=InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION,
        version_before=command.expected_state_version,
        state_after=InvestigationState.PLANNING,
        version_after=command.expected_state_version + 1,
        actor_user_id=actor.user_id,
        reason=None,
        occurred_at=decision.decided_at,
        command_digest=decision.command_digest,
        correlation_id=actor.correlation_id,
        confirmation_decision_id=decision.id,
        confirmed_company_id=decision.company_id,
        confirmed_candidate_batch_id=decision.candidate_batch_id,
        confirmed_candidate_id=decision.candidate_id,
        confirmation_reason_code=decision.review_reason.value,
        confirmed_candidate_classification=decision.candidate_classification,
        confirmed_candidate_rank=decision.candidate_rank,
        matching_policy_id=decision.matching_policy_id,
        matching_policy_version=decision.matching_policy_version,
        materialization_policy_id=decision.materialization_policy_id,
        materialization_policy_version=decision.materialization_policy_version,
    )


def _later_investigation(
    planning: Investigation,
    *,
    state: InvestigationState,
    state_version: int,
    confirmed_company_id: CompanyId | None = None,
) -> Investigation:
    terminal = state in {
        InvestigationState.COMPLETED,
        InvestigationState.PARTIALLY_COMPLETED,
        InvestigationState.FAILED,
        InvestigationState.CANCELLED,
    }
    return Investigation.reconstitute(
        id=planning.id,
        workspace_id=planning.workspace_id,
        requested_by=planning.requested_by,
        profile_code=planning.profile_code,
        country_code=planning.country_code,
        created_at=planning.created_at,
        state=state,
        state_version=state_version,
        confirmed_company_id=confirmed_company_id or planning.confirmed_company_id,
        budget=planning.budget,
        deadline_at=planning.deadline_at,
        started_at=planning.started_at,
        completed_at=NOW + timedelta(minutes=1) if terminal else None,
        identification_input=planning.identification_input,
        active_candidate_batch_id=None,
    )


@pytest.mark.parametrize(
    "role",
    [MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.ANALYST],
)
def test_authorized_roles_materialize_company_decision_transition_and_safe_audit(
    role: MembershipRole,
) -> None:
    actor, investigation, database, factory, clock, service = _setup(role=role)
    command = _command(investigation, database)

    result = service.confirm_entity_candidate(actor, command)

    assert not result.replayed
    assert result.company.status is CompanyStatus.UNKNOWN
    assert result.company.workspace_id == actor.workspace_id
    assert result.decision.company_id == result.company.id
    persisted = database.investigations[(actor.workspace_id, investigation.id)]
    assert persisted.state is InvestigationState.PLANNING
    assert persisted.state_version == investigation.state_version + 1
    assert persisted.confirmed_company_id == result.company.id
    assert persisted.active_candidate_batch_id is None
    transition = database.investigation_transitions[(actor.workspace_id, command.command_id)]
    assert transition.command_type is InvestigationCommandType.CONFIRM_ENTITY_CANDIDATE
    assert transition.confirmation_decision_id == result.decision.id
    audit = database.audit_events[-1]
    assert audit.outcome is AuditOutcome.SUCCESS
    assert audit.entity_resolution_decision_id == result.decision.id
    assert audit.confirmed_candidate_id == command.candidate_id
    assert "Empresa Exemplo" not in repr(audit)
    assert "Empresa Exemplo" not in repr(result)
    assert factory.created[0].commit_calls == 1
    assert clock.calls == [NOW]


def test_exact_replay_returns_same_records_without_clock_or_rematerialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, investigation, database, _, clock, service = _setup()
    command = _command(investigation, database)

    first = service.confirm_entity_candidate(actor, command)

    def fail_materialization(**_: object) -> None:
        raise AssertionError("replay must not recalculate Company materialization")

    def fail_identifier_generation(_: type[object]) -> None:
        raise AssertionError("replay must not generate identifiers")

    monkeypatch.setattr(
        "intelligence.application.services.entity_confirmation.materialize_company",
        fail_materialization,
    )
    monkeypatch.setattr(
        "intelligence.entity_resolution.materialization.materialize_company",
        fail_materialization,
    )
    for identifier_type in (CompanyId, EntityResolutionDecisionId, InvestigationTransitionId):
        monkeypatch.setattr(identifier_type, "new", classmethod(fail_identifier_generation))
    replay = service.confirm_entity_candidate(actor, command)

    assert not first.replayed and replay.replayed
    assert replay.company == first.company
    assert replay.decision == first.decision
    assert len(database.companies) == 1
    assert len(database.entity_resolution_decisions) == 1
    assert len(database.investigation_transitions) == 1
    assert len(database.audit_events) == 1
    assert clock.calls == [NOW]

    replay_clock = CountingClock(NOW + timedelta(days=1))
    replay_service = EntityConfirmationService(
        FakeUnitOfWorkFactory(database),
        ContextualAuthorizer(),
        replay_clock,
    )
    process_replay = replay_service.confirm_entity_candidate(actor, command)
    assert process_replay.replayed
    assert process_replay.decision == first.decision
    assert replay_clock.calls == []


def test_replay_after_cancellation_preserves_current_state_and_has_no_new_effect() -> None:
    actor, waiting, database, _, _, service = _setup()
    command = _command(waiting, database)
    first = service.confirm_entity_candidate(actor, command)
    planning = database.investigations[(actor.workspace_id, waiting.id)]
    cancelled = planning.cancel(occurred_at=NOW + timedelta(minutes=1)).investigation
    database.investigations[(actor.workspace_id, waiting.id)] = cancelled
    replay_clock = CountingClock(NOW + timedelta(days=1))
    replay_factory = FakeUnitOfWorkFactory(database)

    replay = EntityConfirmationService(
        replay_factory,
        ContextualAuthorizer(),
        replay_clock,
    ).confirm_entity_candidate(actor, command)

    assert replay.replayed and replay.decision == first.decision
    assert database.investigations[(actor.workspace_id, waiting.id)] == cancelled
    assert replay_factory.created[0].investigations.cas_calls == []
    assert len(database.companies) == len(database.entity_resolution_decisions) == 1
    assert len(database.investigation_transitions) == len(database.audit_events) == 1
    assert replay_clock.calls == []


def test_partial_confirmation_records_are_corruption_but_other_digest_is_collision() -> None:
    actor, waiting, database, _, _, service = _setup()
    command = _command(waiting, database)
    result = service.confirm_entity_candidate(actor, command)
    transition_key = (actor.workspace_id, command.command_id)
    decision_key = (actor.workspace_id, result.decision.id)
    transition = database.investigation_transitions.pop(transition_key)

    with pytest.raises(PersistenceDataError):
        service.confirm_entity_candidate(actor, command)

    database.investigation_transitions[transition_key] = transition
    decision = database.entity_resolution_decisions.pop(decision_key)
    with pytest.raises(PersistenceDataError):
        service.confirm_entity_candidate(actor, command)

    database.investigation_transitions[transition_key] = replace(
        transition,
        command_digest=InvestigationCommandDigest("f" * 64),
    )
    with pytest.raises(InvestigationCommandCollisionError):
        service.confirm_entity_candidate(actor, command)

    database.entity_resolution_decisions[decision_key] = decision
    with pytest.raises(PersistenceDataError):
        service.confirm_entity_candidate(actor, command)


def test_viewer_is_denied_without_loading_or_persisting_confirmation() -> None:
    actor, investigation, database, factory, _, service = _setup(role=MembershipRole.VIEWER)

    with pytest.raises(AuthorizationDeniedError):
        service.confirm_entity_candidate(actor, _command(investigation, database))

    assert database.companies == {}
    assert database.entity_resolution_decisions == {}
    assert factory.created[0].investigation_transitions.lock_calls == []
    assert database.audit_events[-1].outcome is AuditOutcome.DENIED


def test_missing_candidate_inactive_batch_and_cross_tenant_investigation_are_typed() -> None:
    actor, investigation, database, _, _, service = _setup()
    with pytest.raises(CandidateNotInBatchError):
        service.confirm_entity_candidate(
            actor,
            replace(_command(investigation, database), candidate_id=EntityCandidateId.new()),
        )

    actor, investigation, database, _, _, service = _setup()
    with pytest.raises(InactiveCandidateBatchError):
        service.confirm_entity_candidate(
            actor,
            replace(
                _command(investigation, database),
                candidate_batch_id=EntityCandidateBatchId.new(),
            ),
        )

    actor, investigation, database, _, _, service = _setup()
    with pytest.raises(ResourceNotFoundError):
        service.confirm_entity_candidate(
            actor,
            replace(_command(investigation, database), investigation_id=InvestigationId.new()),
        )


def test_invalid_version_state_missing_batch_and_policy_are_typed() -> None:
    actor, investigation, database, _, _, service = _setup()
    with pytest.raises(ConcurrentInvestigationUpdateError):
        service.confirm_entity_candidate(
            actor,
            replace(
                _command(investigation, database),
                expected_state_version=investigation.state_version + 1,
            ),
        )

    actor, investigation, database, _, _, service = _setup()
    cancelled = investigation.cancel(occurred_at=NOW).investigation
    database.investigations[(actor.workspace_id, investigation.id)] = cancelled
    with pytest.raises(InvestigationTransitionError):
        service.confirm_entity_candidate(
            actor,
            replace(
                _command(investigation, database), expected_state_version=cancelled.state_version
            ),
        )

    actor, investigation, database, _, _, service = _setup()
    assert investigation.active_candidate_batch_id is not None
    database.entity_candidate_batches.pop(
        (actor.workspace_id, investigation.active_candidate_batch_id)
    )
    command = ConfirmEntityCandidate(
        command_id=InvestigationCommandId.new(),
        investigation_id=investigation.id,
        expected_state_version=investigation.state_version,
        candidate_batch_id=investigation.active_candidate_batch_id,
        candidate_id=EntityCandidateId.new(),
        review_reason=EntityConfirmationReason.MANUAL_OVERRIDE,
        materialization_policy=COMPANY_MATERIALIZATION_V1,
    )
    with pytest.raises(InactiveCandidateBatchError):
        service.confirm_entity_candidate(actor, command)

    actor, investigation, database, _, _, service = _setup()
    with pytest.raises(InvalidMaterializationPolicyError):
        service.confirm_entity_candidate(
            actor,
            replace(
                _command(investigation, database),
                materialization_policy=replace(COMPANY_MATERIALIZATION_V1, version=2),
            ),
        )


def test_service_rejects_untyped_command() -> None:
    actor, _, _, _, _, service = _setup()
    with pytest.raises(TypeError):
        service.confirm_entity_candidate(actor, cast(Any, "command"))


def test_replay_rejects_inconsistent_or_missing_persisted_context() -> None:
    actor, investigation, database, _, _, service = _setup()
    command = _command(investigation, database)
    result = service.confirm_entity_candidate(actor, command)
    key = (actor.workspace_id, command.command_id)
    database.investigation_transitions[key] = replace(
        database.investigation_transitions[key],
        confirmed_candidate_id=EntityCandidateId.new(),
    )
    with pytest.raises(PersistenceDataError):
        service.confirm_entity_candidate(actor, command)

    database.investigation_transitions[key] = replace(
        database.investigation_transitions[key],
        confirmed_candidate_id=result.decision.candidate_id,
    )
    database.companies.clear()
    with pytest.raises(PersistenceDataError):
        service.confirm_entity_candidate(actor, command)

    database.companies[(actor.workspace_id, result.company.id)] = result.company
    database.investigation_transitions[key] = replace(
        database.investigation_transitions[key],
        confirmation_reason_code=EntityConfirmationReason.IDENTIFIERS_REVIEWED.value,
    )
    with pytest.raises(PersistenceDataError):
        service.confirm_entity_candidate(actor, command)


@pytest.mark.parametrize("changed_field", ["candidate", "policy", "version"])
def test_same_command_collides_when_any_confirmation_semantic_changes(
    changed_field: str,
) -> None:
    actor, investigation, database, _, _, service = _setup(
        candidates=(_candidate("candidate-a"), _candidate("candidate-b"))
    )
    command_id = InvestigationCommandId.new()
    original = _command(investigation, database, command_id=command_id)
    service.confirm_entity_candidate(actor, original)
    if changed_field == "candidate":
        changed = _command(
            investigation,
            database,
            candidate_index=1,
            command_id=command_id,
        )
    elif changed_field == "policy":
        changed = replace(
            original,
            materialization_policy=replace(COMPANY_MATERIALIZATION_V1, version=2),
        )
    else:
        changed = replace(original, expected_state_version=original.expected_state_version + 1)

    with pytest.raises(InvestigationCommandCollisionError):
        service.confirm_entity_candidate(actor, changed)


def test_same_command_with_different_reason_collides() -> None:
    actor, investigation, database, _, _, service = _setup()
    command_id = InvestigationCommandId.new()
    service.confirm_entity_candidate(
        actor,
        _command(investigation, database, command_id=command_id),
    )

    with pytest.raises(InvestigationCommandCollisionError):
        service.confirm_entity_candidate(
            actor,
            _command(
                investigation,
                database,
                command_id=command_id,
                reason=EntityConfirmationReason.IDENTIFIERS_REVIEWED,
            ),
        )

    assert len(database.companies) == len(database.entity_resolution_decisions) == 1


def test_low_and_non_leading_candidates_require_override_and_excluded_is_blocked() -> None:
    actor, investigation, database, _, _, service = _setup()
    with pytest.raises(EntityConfirmationReasonError):
        service.confirm_entity_candidate(
            actor,
            _command(
                investigation,
                database,
                reason=EntityConfirmationReason.IDENTIFIERS_REVIEWED,
            ),
        )

    actor, investigation, database, _, _, service = _setup(
        candidates=(_candidate("candidate-a"), _candidate("candidate-b"))
    )
    with pytest.raises(EntityConfirmationReasonError):
        service.confirm_entity_candidate(
            actor,
            _command(
                investigation,
                database,
                candidate_index=1,
                reason=EntityConfirmationReason.CORPORATE_DATA_REVIEWED,
            ),
        )

    actor, investigation, database, _, _, service = _setup(
        candidates=(_candidate("candidate-excluded", country="US"),)
    )
    with pytest.raises(CandidateExcludedError):
        service.confirm_entity_candidate(actor, _command(investigation, database))


@pytest.mark.parametrize(
    "policy",
    [
        replace(INITIAL_MATCH_POLICY, high_threshold=3_000, medium_threshold=2_000),
        replace(INITIAL_MATCH_POLICY, high_threshold=4_000, medium_threshold=3_000),
    ],
)
def test_rank_one_high_or_medium_accepts_non_override_reason(policy: MatchPolicy) -> None:
    actor, investigation, database, _, _, service = _setup(policy=policy)

    result = service.confirm_entity_candidate(
        actor,
        _command(
            investigation,
            database,
            reason=EntityConfirmationReason.SOURCE_REFERENCE_REVIEWED,
        ),
    )

    assert result.decision.review_reason is EntityConfirmationReason.SOURCE_REFERENCE_REVIEWED


@pytest.mark.parametrize(
    "failure_option",
    [
        "fail_company_add",
        "fail_decision_add",
        "force_cas_conflict",
        "fail_transition_add",
        "fail_audit",
        "fail_commit",
    ],
)
def test_failures_roll_back_company_decision_state_ledger_and_success_audit(
    failure_option: str,
) -> None:
    expected_error = (
        ConcurrentInvestigationUpdateError
        if failure_option == "force_cas_conflict"
        else PersistenceError
    )
    actor, investigation, database, _, _, service = _setup(**cast(Any, {failure_option: True}))

    with pytest.raises(expected_error):
        service.confirm_entity_candidate(actor, _command(investigation, database))

    assert database.investigations[(actor.workspace_id, investigation.id)] == investigation
    assert database.companies == {}
    assert database.entity_resolution_decisions == {}
    assert database.investigation_transitions == {}
    assert database.audit_events == []


def test_decision_digest_and_context_detect_tampering() -> None:
    actor, investigation, database, _, _, _ = _setup()
    command = _command(investigation, database)
    batch = database.entity_candidate_batches[(actor.workspace_id, command.candidate_batch_id)]
    candidate = batch.candidates[0]
    company = materialize_company(
        policy=COMPANY_MATERIALIZATION_V1,
        company_id=CompanyId.new(),
        workspace_id=actor.workspace_id,
        candidate_identity=candidate.identity,
        occurred_at=NOW,
    )
    decision = build_entity_resolution_decision_record(
        decision_id=EntityResolutionDecisionId.new(),
        actor=actor,
        command=command,
        command_digest=digest_entity_confirmation_command(actor, command),
        batch=batch,
        candidate=candidate,
        company=company,
        decided_at=NOW,
    )
    planning = investigation.confirm_entity(
        company_id=company.id,
        candidate_batch_id=batch.id,
        occurred_at=NOW,
    ).investigation
    transition = _confirmation_transition(actor, command, decision)

    values = entity_resolution_decision_to_values(decision)
    assert entity_resolution_decision_from_values(values) == decision
    with pytest.raises(PersistenceDataError):
        entity_resolution_decision_from_values({**values, "decision_digest": "0" * 64})

    validate_entity_resolution_decision_context(
        decision,
        transition=transition,
        investigation=planning,
        batch=batch,
        company=company,
    )
    with pytest.raises(InvariantViolationError):
        replace(decision, decision_digest="0" * 64)
    with pytest.raises(InvariantViolationError):
        validate_entity_resolution_decision_context(
            decision,
            transition=transition,
            investigation=planning,
            batch=batch,
            company=replace(company, legal_name="Tampered"),
        )

    different_input = IdentificationInput(legal_name=_text("Outra Empresa"))
    with pytest.raises(InvariantViolationError):
        validate_entity_resolution_decision_context(
            decision,
            transition=transition,
            investigation=replace(planning, identification_input=different_input),
            batch=batch,
            company=company,
        )

    non_override_command = replace(
        command,
        review_reason=EntityConfirmationReason.IDENTIFIERS_REVIEWED,
    )
    with pytest.raises(InvariantViolationError):
        build_entity_resolution_decision_record(
            decision_id=EntityResolutionDecisionId.new(),
            actor=actor,
            command=non_override_command,
            command_digest=digest_entity_confirmation_command(actor, non_override_command),
            batch=batch,
            candidate=candidate,
            company=company,
            decided_at=NOW,
        )


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
def test_decision_context_accepts_every_later_compatible_state(
    state: InvestigationState,
) -> None:
    actor, waiting, database, _, _, service = _setup()
    command = _command(waiting, database)
    result = service.confirm_entity_candidate(actor, command)
    transition = database.investigation_transitions[(actor.workspace_id, command.command_id)]
    planning = database.investigations[(actor.workspace_id, waiting.id)]
    batch = database.entity_candidate_batches[(actor.workspace_id, command.candidate_batch_id)]
    current = _later_investigation(
        planning,
        state=state,
        state_version=transition.version_after + 1,
    )

    validate_entity_resolution_decision_context(
        result.decision,
        transition=transition,
        investigation=current,
        batch=batch,
        company=result.company,
    )


def test_decision_context_rejects_prior_or_regressive_current_snapshots() -> None:
    actor, waiting, database, _, _, service = _setup()
    command = _command(waiting, database)
    result = service.confirm_entity_candidate(actor, command)
    transition = database.investigation_transitions[(actor.workspace_id, command.command_id)]
    planning = database.investigations[(actor.workspace_id, waiting.id)]
    batch = database.entity_candidate_batches[(actor.workspace_id, command.candidate_batch_id)]
    identifying = Investigation.reconstitute(
        id=waiting.id,
        workspace_id=waiting.workspace_id,
        requested_by=waiting.requested_by,
        profile_code=waiting.profile_code,
        country_code=waiting.country_code,
        created_at=waiting.created_at,
        state=InvestigationState.IDENTIFYING,
        state_version=transition.version_before - 1,
        budget=waiting.budget,
        deadline_at=waiting.deadline_at,
        started_at=waiting.started_at,
        completed_at=None,
        identification_input=waiting.identification_input,
        active_candidate_batch_id=None,
    )
    created = Investigation(
        id=waiting.id,
        workspace_id=waiting.workspace_id,
        requested_by=waiting.requested_by,
        profile_code=waiting.profile_code,
        country_code=waiting.country_code,
        created_at=waiting.created_at,
        budget=waiting.budget,
        deadline_at=waiting.deadline_at,
    )
    equal_version_collecting = _later_investigation(
        planning,
        state=InvestigationState.COLLECTING,
        state_version=transition.version_after,
    )
    lower_version = _later_investigation(
        planning,
        state=InvestigationState.PLANNING,
        state_version=transition.version_after - 1,
    )
    changed_company = _later_investigation(
        planning,
        state=InvestigationState.PLANNING,
        state_version=transition.version_after,
        confirmed_company_id=CompanyId.new(),
    )
    reintroduced_batch = _later_investigation(
        planning,
        state=InvestigationState.PLANNING,
        state_version=transition.version_after,
    )
    object.__setattr__(reintroduced_batch, "active_candidate_batch_id", batch.id)

    for invalid in (
        created,
        identifying,
        waiting,
        equal_version_collecting,
        lower_version,
        changed_company,
        reintroduced_batch,
    ):
        with pytest.raises(InvariantViolationError):
            validate_entity_resolution_decision_context(
                result.decision,
                transition=transition,
                investigation=invalid,
                batch=batch,
                company=result.company,
            )
