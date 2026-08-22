"""F5.3 service authorization, append, supersession, replay, and read tests."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import (
    AuthorizationDeniedError,
    EvidenceAdmissibilityCommandCollisionError,
    EvidenceAdmissibilityPredecessorError,
    InvalidEvidenceAdmissibilityError,
    ResourceNotFoundError,
)
from intelligence.application.evidence_admissibility import DecideEvidenceAdmissibility
from intelligence.application.evidence_admissibility_policy import (
    ControlledTestEvidenceAnchorV1,
    EvidenceAdmissibilityPolicyV1,
    build_manifest,
    locator_digest,
)
from intelligence.application.services.evidence_admissibility import (
    EvidenceAdmissibilityService,
)
from intelligence.domain.identifiers import (
    CorrelationId,
    EvidenceAdmissibilityCommandId,
    EvidenceId,
    MembershipId,
    UserId,
)
from intelligence.domain.identities import (
    EmailAddress,
    MembershipRole,
    MembershipStatus,
    UserAccount,
    UserAccountStatus,
    WorkspaceMembership,
)
from intelligence.domain.investigations import InvestigationState
from intelligence.evidence.admissibility import (
    EffectiveEvidenceAdmissibilityStatus,
    EvidenceAdmissibilityReason,
    EvidenceAdmissibilityRequestedAction,
)
from intelligence.evidence.models import EvidenceHistory
from tests.unit.application.fakes import FakeClock, FakeDatabase, FakeUnitOfWorkFactory
from tests.unit.application.test_entity_confirmation import _later_investigation
from tests.unit.application.test_evidence_service import (
    NOW,
    _register_command,
)
from tests.unit.application.test_evidence_service import (
    _setup as evidence_setup,
)


def _service_setup(
    *, role: MembershipRole = MembershipRole.OWNER
) -> tuple[
    ActorContext,
    FakeDatabase,
    FakeUnitOfWorkFactory,
    EvidenceAdmissibilityService,
    EvidenceHistory,
]:
    actor, database, _, evidence_service = evidence_setup(role=role)
    evidence_history = evidence_service.register(actor, _register_command(database)).history
    collecting = database.investigations[
        (actor.workspace_id, evidence_history.latest.investigation_id)
    ]
    database.investigations[(actor.workspace_id, collecting.id)] = _later_investigation(
        collecting,
        state=InvestigationState.VERIFYING,
        state_version=collecting.state_version + 1,
    )
    database.audit_events.clear()
    evidence = evidence_history.latest
    anchor = ControlledTestEvidenceAnchorV1(
        artifact_original_sha256=evidence_history.artifact.original_content_sha256,
        evidence_content_sha256=evidence.content_sha256,
        evidence_kind=evidence.kind,
        locator_type=evidence.locator.type,
        locator_digest=locator_digest(evidence.locator),
    )
    factory = FakeUnitOfWorkFactory(database)
    service = EvidenceAdmissibilityService(
        factory,
        ContextualAuthorizer(),
        FakeClock(NOW),
        EvidenceAdmissibilityPolicyV1(build_manifest((anchor,))),
    )
    return actor, database, factory, service, evidence_history


def _command(
    evidence_history: EvidenceHistory,
    *,
    action: EvidenceAdmissibilityRequestedAction = (EvidenceAdmissibilityRequestedAction.RESTRICT),
    command_id: EvidenceAdmissibilityCommandId | None = None,
    previous: str | None = None,
    valid_until: datetime | None = None,
) -> DecideEvidenceAdmissibility:
    reason = {
        EvidenceAdmissibilityRequestedAction.ADMIT: (
            EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED
        ),
        EvidenceAdmissibilityRequestedAction.RESTRICT: (
            EvidenceAdmissibilityReason.POLICY_OR_VERIFIABILITY_RESTRICTED
        ),
        EvidenceAdmissibilityRequestedAction.REJECT: (
            EvidenceAdmissibilityReason.CONTENT_OR_CONTEXT_REJECTED
        ),
    }[action]
    evidence = evidence_history.latest
    return DecideEvidenceAdmissibility(
        command_id=command_id or EvidenceAdmissibilityCommandId.new(),
        investigation_id=evidence.investigation_id,
        evidence_id=evidence.id,
        expected_evidence_digest=evidence.evidence_digest,
        expected_previous_decision_digest=previous,
        requested_action=action,
        reason_code=reason,
        requested_valid_until=valid_until,
    )


def _second_owner(actor: ActorContext, database: FakeDatabase) -> ActorContext:
    user_id = UserId.from_value("50000000-0000-4000-8000-000000000001")
    database.users[user_id] = UserAccount(
        id=user_id,
        email=EmailAddress("second-owner@example.test"),
        display_name="Second Owner",
        status=UserAccountStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    database.memberships[(actor.workspace_id, user_id)] = WorkspaceMembership(
        id=MembershipId.new(),
        workspace_id=actor.workspace_id,
        user_id=user_id,
        role=MembershipRole.OWNER,
        status=MembershipStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    return ActorContext(
        user_id=user_id,
        workspace_id=actor.workspace_id,
        correlation_id=CorrelationId.new(),
    )


def test_negative_initial_supersession_and_historical_replay_are_append_only() -> None:
    actor, database, factory, service, evidence = _service_setup()
    first_command = _command(evidence)
    first = service.decide(actor, first_command)
    second = service.decide(
        actor,
        _command(
            evidence,
            action=EvidenceAdmissibilityRequestedAction.REJECT,
            previous=first.history.latest.decision_digest,
        ),
    )
    replay = service.decide(actor, first_command)
    assert first.effective.status is EffectiveEvidenceAdmissibilityStatus.RESTRICTED
    assert second.effective.status is EffectiveEvidenceAdmissibilityStatus.REJECTED
    assert replay.replayed and replay.history == first.history
    assert len(next(iter(database.evidence_admissibility_histories.values())).decisions) == 2
    assert len(database.audit_events) == 2
    assert factory.created[0].evidence.history_lock_calls
    assert factory.created[0].evidence_admissibility.history_lock_calls


def test_admit_separation_of_duties_expiration_and_replay_use_persisted_time() -> None:
    creator, database, _, service, evidence = _service_setup()
    command = _command(
        evidence,
        action=EvidenceAdmissibilityRequestedAction.ADMIT,
        valid_until=NOW + timedelta(hours=1),
    )
    with pytest.raises(InvalidEvidenceAdmissibilityError):
        service.decide(creator, command)
    reviewer = _second_owner(creator, database)
    admitted = service.decide(
        reviewer, replace(command, command_id=EvidenceAdmissibilityCommandId.new())
    )
    replay = service.decide(
        reviewer, replace(command, command_id=admitted.history.latest.command_id)
    )
    current = service.read(reviewer, evidence.latest.id, as_of=NOW + timedelta(hours=2))
    assert admitted.effective.status is EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE
    assert replay.replayed
    assert replay.effective.as_of == admitted.history.latest.decided_at
    assert replay.effective.status is EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE
    assert current.effective.status is EffectiveEvidenceAdmissibilityStatus.EXPIRED


def test_stale_predecessor_collision_and_analyst_mutation_fail_closed() -> None:
    actor, database, _, service, evidence = _service_setup()
    first = service.decide(actor, _command(evidence))
    with pytest.raises(EvidenceAdmissibilityPredecessorError):
        service.decide(
            actor,
            _command(
                evidence,
                action=EvidenceAdmissibilityRequestedAction.REJECT,
                previous="0" * 64,
            ),
        )
    reused = first.history.latest.command_id
    with pytest.raises(EvidenceAdmissibilityCommandCollisionError):
        service.decide(
            actor,
            _command(
                evidence,
                command_id=reused,
                action=EvidenceAdmissibilityRequestedAction.REJECT,
            ),
        )

    analyst, analyst_database, _, analyst_service, analyst_evidence = _service_setup(
        role=MembershipRole.ANALYST
    )
    with pytest.raises(AuthorizationDeniedError):
        analyst_service.decide(analyst, _command(analyst_evidence))
    read = analyst_service.read(analyst, analyst_evidence.latest.id, as_of=NOW)
    assert read.effective.status is EffectiveEvidenceAdmissibilityStatus.PENDING
    assert database.audit_events
    assert analyst_database.audit_events


def test_type_missing_resource_context_and_generic_policy_failures_are_closed() -> None:
    actor, database, _, service, evidence = _service_setup()
    with pytest.raises(TypeError):
        service.decide(actor, object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        service.read(actor, object(), as_of=NOW)  # type: ignore[arg-type]
    missing = replace(_command(evidence), evidence_id=EvidenceId.new())
    with pytest.raises(ResourceNotFoundError):
        service.decide(actor, missing)
    with pytest.raises(ResourceNotFoundError):
        service.read(actor, EvidenceId.new(), as_of=NOW)

    current = database.investigations[(actor.workspace_id, evidence.latest.investigation_id)]
    database.investigations[(actor.workspace_id, current.id)] = _later_investigation(
        current,
        state=InvestigationState.COLLECTING,
        state_version=current.state_version + 1,
    )
    with pytest.raises(InvalidEvidenceAdmissibilityError):
        service.decide(actor, _command(evidence))
    database.investigations[(actor.workspace_id, current.id)] = current

    incompatible = replace(
        _command(evidence, action=EvidenceAdmissibilityRequestedAction.ADMIT),
        reason_code=EvidenceAdmissibilityReason.CONTENT_OR_CONTEXT_REJECTED,
    )
    reviewer = _second_owner(actor, database)
    with pytest.raises(InvalidEvidenceAdmissibilityError):
        service.decide(reviewer, incompatible)


def test_replay_fails_closed_if_its_evidence_history_disappears() -> None:
    actor, database, _, service, evidence = _service_setup()
    command = _command(evidence)
    service.decide(actor, command)
    database.evidence_histories.clear()
    with pytest.raises(InvalidEvidenceAdmissibilityError):
        service.decide(actor, command)
