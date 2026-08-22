"""F5.2 Claim service lifecycle, policy, authorization, and idempotency tests."""

from dataclasses import replace

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import AuditReasonCode
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.claim_evidence_policy import (
    ClaimEvidenceEligibilityPolicyV1,
    ControlledEvidenceAnchorV1,
    build_manifest,
    locator_digest,
)
from intelligence.application.claims import (
    CorrectClaim,
    ProposedClaimEvidenceLink,
    RegisterClaim,
)
from intelligence.application.errors import (
    AuthorizationDeniedError,
    ClaimCommandCollisionError,
    ClaimVersionConflictError,
    InvalidClaimContextError,
)
from intelligence.application.services.claims import ClaimService
from intelligence.claims.models import (
    ClaimAssessmentOutcome,
    ClaimCorrectionReason,
    ClaimCreationMethod,
    ClaimCriticality,
    ClaimEvidenceRole,
    ClaimPredicate,
    RegistrationStatus,
    RegistrationStatusClaimValue,
    TemporalAbsenceReason,
    TextClaimValue,
    UndatedClaimTemporal,
)
from intelligence.domain.identifiers import ClaimCommandId
from intelligence.domain.identities import MembershipRole
from intelligence.domain.investigations import InvestigationState
from tests.unit.application.fakes import FakeClock, FakeDatabase, FakeUnitOfWorkFactory
from tests.unit.application.test_entity_confirmation import _later_investigation
from tests.unit.application.test_evidence_service import (
    NOW,
)
from tests.unit.application.test_evidence_service import (
    _register_command as evidence_command,
)
from tests.unit.application.test_evidence_service import _setup as evidence_setup


def _setup(
    *, role: MembershipRole = MembershipRole.OWNER
) -> tuple[ActorContext, FakeDatabase, FakeUnitOfWorkFactory, ClaimService]:
    actor, database, _, evidence_service = evidence_setup(role=role)
    evidence_result = evidence_service.register(actor, evidence_command(database))
    evidence = evidence_result.history.latest
    artifact = evidence_result.history.artifact
    collecting = database.investigations[(actor.workspace_id, evidence.investigation_id)]
    verifying = _later_investigation(
        collecting,
        state=InvestigationState.VERIFYING,
        state_version=collecting.state_version + 1,
    )
    database.investigations[(actor.workspace_id, verifying.id)] = verifying
    database.audit_events.clear()
    anchor = ControlledEvidenceAnchorV1(
        artifact_original_sha256=artifact.original_content_sha256,
        evidence_content_sha256=evidence.content_sha256,
        evidence_kind=evidence.kind,
        locator_type=evidence.locator.type,
        locator_digest=locator_digest(evidence.locator),
    )
    factory = FakeUnitOfWorkFactory(database)
    service = ClaimService(
        factory,
        ContextualAuthorizer(),
        FakeClock(NOW),
        ClaimEvidenceEligibilityPolicyV1(build_manifest((anchor,))),
    )
    return actor, database, factory, service


def _register(database: FakeDatabase, *, command_id: ClaimCommandId | None = None) -> RegisterClaim:
    evidence = next(iter(database.evidence_histories.values())).latest
    return RegisterClaim(
        command_id=command_id or ClaimCommandId.new(),
        investigation_id=evidence.investigation_id,
        predicate_code=ClaimPredicate.LEGAL_NAME,
        predicate_version=1,
        value=TextClaimValue("Empresa Exemplo S.A."),
        temporal=UndatedClaimTemporal(TemporalAbsenceReason.NOT_PROVIDED),
        criticality=ClaimCriticality.STANDARD,
        creation_method=ClaimCreationMethod.MANUAL,
        creation_method_version=1,
        links=(
            ProposedClaimEvidenceLink(
                evidence.id,
                evidence.evidence_digest,
                ClaimEvidenceRole.SUPPORTS,
            ),
        ),
    )


def test_register_is_supported_atomic_pending_and_replayable() -> None:
    actor, database, factory, service = _setup()
    command = _register(database)

    result = service.register(actor, command)
    replay = service.register(actor, command)

    assert result.assessment.outcome is ClaimAssessmentOutcome.SUPPORTED
    assert not result.replayed and replay.replayed
    assert replay.history == result.history
    assert len(database.claim_histories) == 1
    evidence_status = next(
        iter(database.evidence_histories.values())
    ).latest.admissibility_status.value
    assert evidence_status == "PENDING"
    assert factory.created[0].claims.add_initial_calls
    assert factory.created[0].evidence.history_lock_calls
    assert "Empresa Exemplo" not in repr(command)


def test_command_collision_fails_without_second_append() -> None:
    actor, database, _, service = _setup()
    command_id = ClaimCommandId.new()
    service.register(actor, _register(database, command_id=command_id))

    with pytest.raises(ClaimCommandCollisionError):
        service.register(
            actor,
            replace(
                _register(database, command_id=command_id),
                value=TextClaimValue("Different value"),
            ),
        )

    assert len(database.claim_histories) == 1
    assert database.audit_events[-1].reason_code == AuditReasonCode.COMMAND_ID_COLLISION.value


def test_correction_appends_and_predicate_change_is_rejected() -> None:
    actor, database, _, service = _setup()
    registered = service.register(actor, _register(database))
    latest = registered.history.latest
    evidence = next(iter(database.evidence_histories.values())).latest
    corrected = service.correct(
        actor,
        CorrectClaim(
            command_id=ClaimCommandId.new(),
            claim_id=latest.id,
            expected_claim_digest=latest.claim_digest,
            predicate_code=latest.predicate_code,
            predicate_version=latest.predicate_version,
            value=TextClaimValue("Empresa Exemplo Corrigida S.A."),
            temporal=latest.temporal,
            criticality=latest.criticality,
            creation_method=latest.creation_method,
            creation_method_version=latest.creation_method_version,
            correction_reason=ClaimCorrectionReason.VALUE_CORRECTION,
            links=(
                ProposedClaimEvidenceLink(
                    evidence.id,
                    evidence.evidence_digest,
                    ClaimEvidenceRole.SUPPORTS,
                ),
            ),
        ),
    )
    assert len(corrected.history.versions) == 2
    assert corrected.history.latest.supersedes_claim_id == latest.id

    with pytest.raises(ClaimVersionConflictError):
        service.correct(
            actor,
            CorrectClaim(
                command_id=ClaimCommandId.new(),
                claim_id=corrected.history.latest.id,
                expected_claim_digest=corrected.history.latest.claim_digest,
                predicate_code=ClaimPredicate.REGISTRATION_STATUS,
                predicate_version=1,
                value=RegistrationStatusClaimValue(RegistrationStatus.ACTIVE),
                temporal=corrected.history.latest.temporal,
                criticality=corrected.history.latest.criticality,
                creation_method=corrected.history.latest.creation_method,
                creation_method_version=1,
                correction_reason=ClaimCorrectionReason.VALUE_CORRECTION,
                links=(
                    ProposedClaimEvidenceLink(
                        evidence.id,
                        evidence.evidence_digest,
                        ClaimEvidenceRole.SUPPORTS,
                    ),
                ),
            ),
        )


def test_collecting_and_analyst_mutation_fail_closed() -> None:
    actor, database, _, service = _setup()
    verifying = next(iter(database.investigations.values()))
    database.investigations[(actor.workspace_id, verifying.id)] = _later_investigation(
        verifying,
        state=InvestigationState.COLLECTING,
        state_version=verifying.state_version + 1,
    )
    with pytest.raises(InvalidClaimContextError):
        service.register(actor, _register(database))
    assert database.audit_events[-1].reason_code == AuditReasonCode.CLAIM_CONTEXT_INVALID.value

    analyst, analyst_database, _, analyst_service = _setup(role=MembershipRole.ANALYST)
    with pytest.raises(AuthorizationDeniedError):
        analyst_service.register(analyst, _register(analyst_database))
