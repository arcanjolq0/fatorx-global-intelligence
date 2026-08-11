"""Atomic F4.2 entity-candidate review application tests."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import AuditActionCode, AuditReasonCode
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import (
    AuthorizationDeniedError,
    CandidateInputDigestMismatchError,
    ConcurrentInvestigationUpdateError,
    InvestigationCommandCollisionError,
    InvestigationTransitionError,
    PersistenceError,
    ResourceNotFoundError,
)
from intelligence.application.investigation_lifecycle import (
    InvestigationCommandType,
    RequestEntityConfirmation,
)
from intelligence.application.services.investigations import InvestigationService
from intelligence.domain.audit import AuditOutcome
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
    IdentificationInput,
    OriginalAndNormalizedText,
)
from intelligence.domain.investigations import Investigation, InvestigationState
from intelligence.entity_resolution.contracts import (
    CandidateIdentitySnapshot,
    CandidateOriginSnapshot,
    CandidateSubmissionBatch,
    EntityCandidateInput,
)
from intelligence.entity_resolution.policy import INITIAL_MATCH_POLICY, MatchClassification
from tests.unit.application.fakes import FakeDatabase, FakeUnitOfWorkFactory

NOW = datetime(2026, 7, 29, 18, tzinfo=UTC)


def _text(value: str) -> OriginalAndNormalizedText:
    return OriginalAndNormalizedText(original_value=value, normalized_value=value.casefold())


def _input(name: str = "Empresa Exemplo S.A.") -> IdentificationInput:
    return IdentificationInput(legal_name=_text(name))


def _candidate(
    key: str = "candidate-1", name: str = "Empresa Exemplo S.A."
) -> EntityCandidateInput:
    return EntityCandidateInput(
        candidate_key=key,
        identity=CandidateIdentitySnapshot(
            legal_name=_text(name),
            country_code=CountryCode("BR"),
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
    role: MembershipRole = MembershipRole.OWNER,
    *,
    include_resource: bool = True,
    force_cas_conflict: bool = False,
    fail_candidate_batch_add: bool = False,
    fail_transition_add: bool = False,
    fail_audit: bool = False,
    fail_commit: bool = False,
) -> tuple[
    ActorContext,
    Investigation,
    FakeDatabase,
    FakeUnitOfWorkFactory,
    CountingClock,
    InvestigationService,
]:
    actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )
    source = _input()
    investigation = Investigation.reconstitute(
        id=InvestigationId.new(),
        workspace_id=actor.workspace_id,
        requested_by=actor.user_id,
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        created_at=NOW - timedelta(minutes=5),
        state=InvestigationState.IDENTIFYING,
        state_version=2,
        started_at=NOW - timedelta(minutes=4),
        identification_input=source,
    )
    user = UserAccount(
        id=actor.user_id,
        email=EmailAddress(f"{actor.user_id.value}@example.test"),
        display_name="Actor",
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
        investigations=(
            {(actor.workspace_id, investigation.id): investigation} if include_resource else {}
        ),
        users={actor.user_id: user},
        memberships={(actor.workspace_id, actor.user_id): membership},
    )
    factory = FakeUnitOfWorkFactory(
        database,
        force_cas_conflict=force_cas_conflict,
        fail_candidate_batch_add=fail_candidate_batch_add,
        fail_transition_add=fail_transition_add,
        fail_audit=fail_audit,
        fail_commit=fail_commit,
    )
    clock = CountingClock(NOW)
    service = InvestigationService(factory, ContextualAuthorizer(), clock)
    return actor, investigation, database, factory, clock, service


def _command(
    investigation: Investigation,
    *,
    command_id: InvestigationCommandId | None = None,
    input_digest: str | None = None,
    name: str = "Empresa Exemplo S.A.",
) -> RequestEntityConfirmation:
    assert investigation.identification_input is not None
    return RequestEntityConfirmation(
        command_id=command_id or InvestigationCommandId.new(),
        investigation_id=investigation.id,
        expected_state_version=2,
        candidate_batch=CandidateSubmissionBatch(
            input_digest=input_digest or investigation.identification_input.digest,
            candidates=(_candidate(name=name),),
        ),
        matching_policy=INITIAL_MATCH_POLICY,
    )


@pytest.mark.parametrize(
    "role",
    [MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.ANALYST],
)
def test_authorized_roles_persist_ranked_batch_pause_ledger_and_safe_audit(
    role: MembershipRole,
) -> None:
    actor, investigation, database, factory, clock, service = _setup(role)
    command = _command(investigation)

    result = service.request_entity_confirmation(actor, command)

    assert result.state is InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION
    assert result.state_version == 3
    assert result.candidate_batch_id is not None
    assert result.candidate_count == 1
    assert result.top_classification is MatchClassification.LOW
    assert not result.replayed
    persisted = database.investigations[(actor.workspace_id, investigation.id)]
    assert persisted.active_candidate_batch_id == result.candidate_batch_id
    assert persisted.confirmed_company_id is None
    assert persisted.started_at == investigation.started_at
    assert persisted.completed_at is None
    batch = database.entity_candidate_batches[(actor.workspace_id, result.candidate_batch_id)]
    assert batch.policy_snapshot == INITIAL_MATCH_POLICY.to_canonical_json()
    assert batch.candidates[0].decision.value == "PENDING_REVIEW"
    assert len(batch.candidates[0].dimensions) == 7
    record = next(iter(database.investigation_transitions.values()))
    assert record.command_type is InvestigationCommandType.REQUEST_ENTITY_CONFIRMATION
    assert record.candidate_batch_id == batch.id
    audit = database.audit_events[-1]
    assert audit.action_code == AuditActionCode.INVESTIGATION_ENTITY_CONFIRMATION_REQUESTED.value
    assert audit.command_id == command.command_id
    assert audit.candidate_count == 1
    assert "Empresa Exemplo" not in repr(audit)
    assert factory.created[0].commit_calls == 1
    assert clock.calls == [NOW]


def test_exact_replay_returns_persisted_result_without_matching_clock_or_second_effect() -> None:
    actor, investigation, database, factory, clock, service = _setup()
    command = _command(investigation)

    first = service.request_entity_confirmation(actor, command)
    second = service.request_entity_confirmation(actor, command)

    assert not first.replayed and second.replayed
    assert second.candidate_batch_id == first.candidate_batch_id
    assert second.top_classification == first.top_classification
    assert len(database.entity_candidate_batches) == 1
    assert len(database.investigation_transitions) == 1
    assert len(database.audit_events) == 1
    assert clock.calls == [NOW]
    assert factory.created[1].investigations.get_calls == []


def test_same_command_with_changed_candidate_collides_without_new_batch() -> None:
    actor, investigation, database, _, _, service = _setup()
    command_id = InvestigationCommandId.new()
    service.request_entity_confirmation(
        actor,
        _command(investigation, command_id=command_id),
    )

    with pytest.raises(InvestigationCommandCollisionError):
        service.request_entity_confirmation(
            actor,
            _command(investigation, command_id=command_id, name="Different Company"),
        )

    assert len(database.entity_candidate_batches) == 1
    assert len(database.investigation_transitions) == 1
    assert database.audit_events[-1].reason_code == AuditReasonCode.COMMAND_ID_COLLISION.value


def test_viewer_is_denied_before_command_or_resource_lookup() -> None:
    actor, investigation, database, factory, _, service = _setup(MembershipRole.VIEWER)

    with pytest.raises(AuthorizationDeniedError):
        service.request_entity_confirmation(actor, _command(investigation))

    assert database.entity_candidate_batches == {}
    assert factory.created[0].investigations.get_calls == []
    assert factory.created[0].investigation_transitions.get_calls == []
    assert database.audit_events[-1].outcome is AuditOutcome.DENIED


def test_missing_or_cross_tenant_resource_is_safe_absence() -> None:
    actor, investigation, database, factory, _, service = _setup(include_resource=False)

    with pytest.raises(ResourceNotFoundError):
        service.request_entity_confirmation(actor, _command(investigation))

    assert factory.created[0].investigations.get_calls == [(actor.workspace_id, investigation.id)]
    assert database.entity_candidate_batches == {}
    assert database.audit_events[-1].resource_id is None


def test_input_digest_mismatch_is_typed_and_never_attempts_cas() -> None:
    actor, investigation, database, factory, _, service = _setup()

    with pytest.raises(CandidateInputDigestMismatchError):
        service.request_entity_confirmation(
            actor,
            _command(investigation, input_digest="0" * 64),
        )

    assert factory.created[0].investigations.cas_calls == []
    assert database.entity_candidate_batches == {}
    assert database.audit_events[-1].reason_code == AuditReasonCode.INPUT_DIGEST_MISMATCH.value


def test_stale_version_and_cas_conflict_leave_no_orphan_batch() -> None:
    actor, investigation, database, factory, _, service = _setup()
    stale = replace(_command(investigation), expected_state_version=1)
    with pytest.raises(ConcurrentInvestigationUpdateError):
        service.request_entity_confirmation(actor, stale)
    assert factory.created[0].investigations.cas_calls == []
    assert database.entity_candidate_batches == {}

    actor, investigation, database, factory, _, service = _setup(force_cas_conflict=True)
    with pytest.raises(ConcurrentInvestigationUpdateError):
        service.request_entity_confirmation(actor, _command(investigation))
    assert len(factory.created[0].investigations.cas_calls) == 1
    assert database.entity_candidate_batches == {}
    assert database.investigation_transitions == {}


def test_invalid_source_state_is_typed_and_persists_no_batch() -> None:
    actor, investigation, database, _, _, service = _setup()
    database.investigations[(actor.workspace_id, investigation.id)] = Investigation.reconstitute(
        id=investigation.id,
        workspace_id=investigation.workspace_id,
        requested_by=investigation.requested_by,
        profile_code=investigation.profile_code,
        country_code=investigation.country_code,
        created_at=investigation.created_at,
        state=InvestigationState.PLANNING,
        state_version=2,
        started_at=investigation.started_at,
        identification_input=investigation.identification_input,
        confirmed_company_id=CompanyId.new(),
    )

    with pytest.raises(InvestigationTransitionError):
        service.request_entity_confirmation(actor, _command(investigation))

    assert database.entity_candidate_batches == {}
    assert database.audit_events[-1].reason_code == AuditReasonCode.INVALID_TRANSITION.value


@pytest.mark.parametrize("failure", ["batch", "ledger", "audit", "commit"])
def test_batch_ledger_audit_or_commit_failure_rolls_back_every_effect(failure: str) -> None:
    actor, investigation, database, _, _, service = _setup(
        fail_candidate_batch_add=failure == "batch",
        fail_transition_add=failure == "ledger",
        fail_audit=failure == "audit",
        fail_commit=failure == "commit",
    )

    with pytest.raises(PersistenceError):
        service.request_entity_confirmation(actor, _command(investigation))

    assert database.investigations[(actor.workspace_id, investigation.id)] == investigation
    assert database.entity_candidate_batches == {}
    assert database.investigation_transitions == {}
    assert database.audit_events == []
