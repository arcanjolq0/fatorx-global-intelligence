"""F5.1 evidence service tenancy, idempotency, correction, and revocation tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import (
    AuthorizationDeniedError,
    EvidenceAlreadyRevokedError,
    EvidenceCommandCollisionError,
    EvidenceVersionConflictError,
    InvalidEvidenceContextError,
    ResourceNotFoundError,
)
from intelligence.application.evidence import CorrectEvidence, RegisterEvidence, RevokeEvidence
from intelligence.application.services.evidence import EvidenceService
from intelligence.domain.audit import AuditOutcome
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import EvidenceCommandId
from intelligence.domain.identities import MembershipRole
from intelligence.domain.investigations import InvestigationState
from intelligence.evidence.models import (
    ArtifactOriginType,
    ArtifactStorageMode,
    EvidenceDisplayMode,
    EvidenceKind,
    EvidenceLifecycleEventType,
    EvidenceLifecycleReason,
    JsonPointerLocator,
    PublicationAbsenceReason,
    RetentionMode,
    SensitivityClassification,
)
from tests.unit.application.fakes import FakeClock, FakeDatabase, FakeUnitOfWorkFactory
from tests.unit.application.test_entity_confirmation import (
    _command as confirmation_command,
)
from tests.unit.application.test_entity_confirmation import (
    _later_investigation,
)
from tests.unit.application.test_entity_confirmation import (
    _setup as confirmation_setup,
)

NOW = datetime(2026, 8, 14, 14, tzinfo=UTC)
ORIGINAL = b'{"company":{"name":"Empresa Exemplo S.A."}}'
LOCATED = b"Empresa Exemplo S.A."


def _setup(
    *, role: MembershipRole = MembershipRole.ANALYST
) -> tuple[ActorContext, FakeDatabase, FakeUnitOfWorkFactory, EvidenceService]:
    actor, waiting, database, _, _, confirmation_service = confirmation_setup(role=role)
    confirmation_service.confirm_entity_candidate(actor, confirmation_command(waiting, database))
    planning = database.investigations[(actor.workspace_id, waiting.id)]
    collecting = _later_investigation(
        planning,
        state=InvestigationState.COLLECTING,
        state_version=planning.state_version + 1,
    )
    database.investigations[(actor.workspace_id, collecting.id)] = collecting
    database.audit_events.clear()
    decision = next(iter(database.entity_resolution_decisions.values()))
    factory = FakeUnitOfWorkFactory(database)
    service = EvidenceService(factory, ContextualAuthorizer(), FakeClock(NOW))
    assert decision.investigation_id == collecting.id
    return actor, database, factory, service


def _register_command(
    database: FakeDatabase,
    *,
    command_id: EvidenceCommandId | None = None,
    located_content: bytes = LOCATED,
    content_original: str | None = LOCATED.decode(),
) -> RegisterEvidence:
    decision = next(iter(database.entity_resolution_decisions.values()))
    return RegisterEvidence(
        command_id=command_id or EvidenceCommandId.new(),
        investigation_id=decision.investigation_id,
        entity_resolution_decision_id=decision.id,
        source_id="SYNTHETIC_REGISTRY",
        source_policy_version="SYNTHETIC_POLICY_V1",
        origin_type=ArtifactOriginType.FILE_IMPORT,
        origin_reference="fixture/company.json",
        origin_fingerprint=sha256(b"synthetic-origin").hexdigest(),
        acquisition_method="SYNTHETIC_IMPORT",
        acquisition_method_version="1.0.0",
        retrieved_at=NOW - timedelta(minutes=1),
        published_at=None,
        publication_absence_reason=PublicationAbsenceReason.NOT_PROVIDED,
        media_type="application/json",
        original_content=ORIGINAL,
        storage_mode=ArtifactStorageMode.EXCERPT_ONLY,
        storage_reference=None,
        retention_mode=RetentionMode.INDEFINITE,
        retention_until=None,
        display_mode=EvidenceDisplayMode.FULL,
        sensitivity=SensitivityClassification.INTERNAL,
        evidence_kind=EvidenceKind.STRUCTURED_DATA,
        language="pt-BR",
        locator=JsonPointerLocator(
            pointer="/company/name", response_sha256=sha256(ORIGINAL).hexdigest()
        ),
        located_content=located_content,
        content_original=content_original,
        extraction_method="JSON_POINTER",
        extraction_method_version="1.0.0",
    )


def test_register_is_atomic_tenant_scoped_pending_and_replayable() -> None:
    actor, database, factory, service = _setup()
    command = _register_command(database)

    result = service.register(actor, command)
    replay = service.register(actor, command)

    assert not result.replayed
    assert replay.replayed
    assert replay.history == result.history
    assert (
        result.history.latest.subject_company_id
        == next(iter(database.entity_resolution_decisions.values())).company_id
    )
    assert result.history.latest.admissibility_status.value == "PENDING"
    assert result.history.artifact.original_content_sha256 == sha256(ORIGINAL).hexdigest()
    assert len(database.evidence_histories) == 1
    assert len(database.audit_events) == 1
    assert database.audit_events[0].outcome is AuditOutcome.SUCCESS
    assert factory.created[0].evidence.lock_calls == [(actor.workspace_id, command.command_id)]
    assert "Empresa Exemplo" not in repr(command)


def test_command_collision_is_fail_closed_without_duplicate_history() -> None:
    actor, database, _, service = _setup()
    command_id = EvidenceCommandId.new()
    service.register(actor, _register_command(database, command_id=command_id))

    with pytest.raises(EvidenceCommandCollisionError):
        service.register(
            actor,
            _register_command(
                database,
                command_id=command_id,
                located_content=b"Different",
                content_original="Different",
            ),
        )

    assert len(database.evidence_histories) == 1


def test_commands_reject_untyped_boundary_vocabulary() -> None:
    _, database, _, _ = _setup()
    with pytest.raises(InvariantViolationError):
        replace(
            _register_command(database),
            evidence_kind=cast(EvidenceKind, "STRUCTURED_DATA"),
        )


def test_correction_appends_version_and_supersession_without_mutating_artifact() -> None:
    actor, database, factory, service = _setup()
    registered = service.register(actor, _register_command(database))
    original_artifact = registered.history.artifact
    command = CorrectEvidence(
        command_id=EvidenceCommandId.new(),
        evidence_id=registered.history.latest.id,
        expected_evidence_digest=registered.history.latest.evidence_digest,
        kind=EvidenceKind.STRUCTURED_DATA,
        language="pt-BR",
        locator=JsonPointerLocator(
            pointer="/company/legal_name", response_sha256=sha256(ORIGINAL).hexdigest()
        ),
        located_content=b"Empresa Exemplo Ltda.",
        content_original="Empresa Exemplo Ltda.",
        extraction_method="HUMAN_CORRECTION",
        extraction_method_version="1.0.0",
    )

    result = service.correct(actor, command)
    replay = service.correct(actor, command)

    assert not result.replayed and replay.replayed
    assert result.history.artifact == original_artifact
    assert tuple(item.version for item in result.history.versions) == (1, 2)
    assert result.history.events[0].event_type is EvidenceLifecycleEventType.SUPERSEDED
    assert result.history.events[0].related_evidence_id == result.history.latest.id
    assert factory.created[1].evidence.history_lock_calls == [
        (actor.workspace_id, registered.history.latest.id)
    ]


def test_stale_correction_and_revocation_are_rejected() -> None:
    actor, database, _, service = _setup(role=MembershipRole.OWNER)
    registered = service.register(actor, _register_command(database))
    with pytest.raises(EvidenceVersionConflictError):
        service.correct(
            actor,
            CorrectEvidence(
                command_id=EvidenceCommandId.new(),
                evidence_id=registered.history.latest.id,
                expected_evidence_digest="0" * 64,
                kind=EvidenceKind.TEXT,
                language="pt-BR",
                locator=registered.history.latest.locator,
                located_content=b"changed",
                content_original="changed",
                extraction_method="HUMAN_CORRECTION",
                extraction_method_version="1.0.0",
            ),
        )


def test_only_owner_or_admin_can_revoke_and_revocation_is_terminal() -> None:
    analyst, analyst_database, _, analyst_service = _setup()
    analyst_history = analyst_service.register(analyst, _register_command(analyst_database)).history
    analyst_revoke = RevokeEvidence(
        command_id=EvidenceCommandId.new(),
        evidence_id=analyst_history.latest.id,
        expected_evidence_digest=analyst_history.latest.evidence_digest,
        reason=EvidenceLifecycleReason.CONTENT_INVALID,
    )
    with pytest.raises(AuthorizationDeniedError):
        analyst_service.revoke(analyst, analyst_revoke)

    owner, owner_database, owner_factory, owner_service = _setup(role=MembershipRole.OWNER)
    history = owner_service.register(owner, _register_command(owner_database)).history
    revoke = RevokeEvidence(
        command_id=EvidenceCommandId.new(),
        evidence_id=history.latest.id,
        expected_evidence_digest=history.latest.evidence_digest,
        reason=EvidenceLifecycleReason.SOURCE_WITHDRAWN,
    )
    result = owner_service.revoke(owner, revoke)
    replay = owner_service.revoke(owner, revoke)

    assert result.history.is_revoked and replay.replayed
    assert owner_factory.created[1].evidence.history_lock_calls == [
        (owner.workspace_id, history.latest.id)
    ]
    with pytest.raises(EvidenceAlreadyRevokedError):
        owner_service.revoke(owner, replace(revoke, command_id=EvidenceCommandId.new()))


def test_read_is_tenant_scoped_and_viewer_authorized() -> None:
    actor, database, _, service = _setup()
    history = service.register(actor, _register_command(database)).history
    membership_key = (actor.workspace_id, actor.user_id)
    database.memberships[membership_key] = replace(
        database.memberships[membership_key], role=MembershipRole.VIEWER
    )
    viewer_service = EvidenceService(
        FakeUnitOfWorkFactory(database), ContextualAuthorizer(), FakeClock(NOW)
    )
    assert viewer_service.get_history(actor, history.latest.id) == history

    other_actor, other_database, _, _ = _setup()
    other_membership_key = (other_actor.workspace_id, other_actor.user_id)
    other_database.memberships[other_membership_key] = replace(
        other_database.memberships[other_membership_key], role=MembershipRole.VIEWER
    )
    other_service = EvidenceService(
        FakeUnitOfWorkFactory(other_database), ContextualAuthorizer(), FakeClock(NOW)
    )
    with pytest.raises(ResourceNotFoundError):
        other_service.get_history(other_actor, history.latest.id)


def test_registration_requires_collecting_and_matching_confirmed_decision() -> None:
    actor, database, _, service = _setup()
    current = next(iter(database.investigations.values()))
    database.investigations[(actor.workspace_id, current.id)] = _later_investigation(
        current,
        state=InvestigationState.VERIFYING,
        state_version=current.state_version + 1,
    )

    with pytest.raises(InvalidEvidenceContextError):
        service.register(actor, _register_command(database))
