"""Atomic F5.1 canonical evidence registration, correction, revocation, and reading."""

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import (
    AuditActionCode,
    append_audit_event,
    commit_standalone_outcome,
)
from intelligence.application.authorization import ContextualAuthorizer, Permission
from intelligence.application.entity_confirmation import EntityResolutionDecisionRecord
from intelligence.application.errors import (
    AuthorizationDeniedError,
    EvidenceAlreadyRevokedError,
    EvidenceCommandCollisionError,
    EvidenceVersionConflictError,
    InvalidEvidenceContextError,
    ResourceNotFoundError,
)
from intelligence.application.evidence import (
    CorrectEvidence,
    EvidenceOperationResult,
    RegisterEvidence,
    RevokeEvidence,
    digest_correct_evidence,
    digest_register_evidence,
    digest_revoke_evidence,
)
from intelligence.application.ports.clock import Clock
from intelligence.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from intelligence.domain.audit import AuditOutcome, AuditResourceType
from intelligence.domain.identifiers import (
    ArtifactId,
    EntityResolutionDecisionId,
    EvidenceCommandId,
    EvidenceId,
    EvidenceLifecycleEventId,
    InvestigationId,
)
from intelligence.domain.investigations import InvestigationState
from intelligence.evidence.models import (
    ArtifactStorageMode,
    EvidenceHistory,
    EvidenceLifecycleEventType,
    EvidenceLifecycleReason,
    build_artifact,
    build_evidence,
    build_lifecycle_event,
)


class EvidenceService:
    """Coordinate evidence invariants through tenant-scoped application ports."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        authorizer: ContextualAuthorizer,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authorizer = authorizer
        self._clock = clock

    def register(self, actor: ActorContext, command: RegisterEvidence) -> EvidenceOperationResult:
        """Append an artifact and its first PENDING evidence version."""

        if not isinstance(command, RegisterEvidence):
            raise TypeError("command must be a RegisterEvidence")
        command_digest = digest_register_evidence(actor, command)
        action = AuditActionCode.EVIDENCE_REGISTERED
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, Permission.EVIDENCE_REGISTER, action)
            unit_of_work.evidence.acquire_command_lock(actor.workspace_id, command.command_id)
            existing = unit_of_work.evidence.get_history_by_command(
                actor.workspace_id, command.command_id
            )
            if existing is not None:
                return self._replay(unit_of_work, existing, command.command_id, command_digest)
            decision = self._validated_context(
                unit_of_work,
                actor=actor,
                investigation_id=command.investigation_id,
                decision_id=command.entity_resolution_decision_id,
            )
            occurred_at = self._clock.now()
            artifact = build_artifact(
                artifact_id=ArtifactId.new(),
                workspace_id=actor.workspace_id,
                investigation_id=command.investigation_id,
                source_id=command.source_id,
                source_policy_version=command.source_policy_version,
                origin_type=command.origin_type,
                origin_reference=command.origin_reference,
                origin_fingerprint=command.origin_fingerprint,
                acquisition_method=command.acquisition_method,
                acquisition_method_version=command.acquisition_method_version,
                acquired_by=actor.user_id,
                retrieved_at=command.retrieved_at,
                published_at=command.published_at,
                publication_absence_reason=command.publication_absence_reason,
                media_type=command.media_type,
                original_content=command.original_content,
                storage_mode=command.storage_mode,
                storage_reference=command.storage_reference,
                retention_mode=command.retention_mode,
                retention_until=command.retention_until,
                display_mode=command.display_mode,
                sensitivity=command.sensitivity,
                created_at=occurred_at,
            )
            evidence_id = EvidenceId.new()
            evidence = build_evidence(
                evidence_id=evidence_id,
                series_id=evidence_id,
                version=1,
                supersedes_evidence_id=None,
                workspace_id=actor.workspace_id,
                investigation_id=command.investigation_id,
                subject_company_id=decision.company_id,
                entity_resolution_decision_id=decision.id,
                artifact_id=artifact.id,
                command_id=command.command_id,
                command_digest=command_digest,
                kind=command.evidence_kind,
                language=command.language,
                locator=command.locator,
                located_content=command.located_content,
                content_original=command.content_original,
                extraction_method=command.extraction_method,
                extraction_method_version=command.extraction_method_version,
                matching_policy_id=decision.matching_policy_id,
                matching_policy_version=decision.matching_policy_version,
                created_by=actor.user_id,
                created_at=occurred_at,
            )
            unit_of_work.evidence.add_initial(artifact, evidence)
            append_audit_event(
                unit_of_work,
                actor=actor,
                action=action,
                resource_type=AuditResourceType.INVESTIGATION,
                resource_id=command.investigation_id,
                outcome=AuditOutcome.SUCCESS,
                reason=None,
                occurred_at=occurred_at,
            )
            unit_of_work.commit()
            return EvidenceOperationResult(
                history=EvidenceHistory(artifact=artifact, versions=(evidence,), events=()),
                replayed=False,
            )

    def correct(self, actor: ActorContext, command: CorrectEvidence) -> EvidenceOperationResult:
        """Append a corrected version without modifying the artifact or prior evidence."""

        if not isinstance(command, CorrectEvidence):
            raise TypeError("command must be a CorrectEvidence")
        command_digest = digest_correct_evidence(actor, command)
        action = AuditActionCode.EVIDENCE_CORRECTED
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, Permission.EVIDENCE_CORRECT, action)
            unit_of_work.evidence.acquire_command_lock(actor.workspace_id, command.command_id)
            existing = unit_of_work.evidence.get_history_by_command(
                actor.workspace_id, command.command_id
            )
            if existing is not None:
                return self._replay(unit_of_work, existing, command.command_id, command_digest)
            unit_of_work.evidence.acquire_history_lock(actor.workspace_id, command.evidence_id)
            history = unit_of_work.evidence.get_history(actor.workspace_id, command.evidence_id)
            if history is None:
                raise ResourceNotFoundError()
            self._validate_current_version(
                history, command.evidence_id, command.expected_evidence_digest
            )
            if history.is_revoked:
                raise EvidenceAlreadyRevokedError()
            self._validated_context(
                unit_of_work,
                actor=actor,
                investigation_id=history.latest.investigation_id,
                decision_id=history.latest.entity_resolution_decision_id,
            )
            if (
                history.artifact.storage_mode
                in {
                    ArtifactStorageMode.REFERENCE_ONLY,
                    ArtifactStorageMode.EPHEMERAL_PROCESSING,
                }
                and command.content_original is not None
            ):
                raise InvalidEvidenceContextError()
            occurred_at = self._clock.now()
            corrected = build_evidence(
                evidence_id=EvidenceId.new(),
                series_id=history.latest.series_id,
                version=history.latest.version + 1,
                supersedes_evidence_id=history.latest.id,
                workspace_id=history.latest.workspace_id,
                investigation_id=history.latest.investigation_id,
                subject_company_id=history.latest.subject_company_id,
                entity_resolution_decision_id=history.latest.entity_resolution_decision_id,
                artifact_id=history.latest.artifact_id,
                command_id=command.command_id,
                command_digest=command_digest,
                kind=command.kind,
                language=command.language,
                locator=command.locator,
                located_content=command.located_content,
                content_original=command.content_original,
                extraction_method=command.extraction_method,
                extraction_method_version=command.extraction_method_version,
                matching_policy_id=history.latest.matching_policy_id,
                matching_policy_version=history.latest.matching_policy_version,
                created_by=actor.user_id,
                created_at=occurred_at,
            )
            event = build_lifecycle_event(
                event_id=EvidenceLifecycleEventId.new(),
                workspace_id=history.latest.workspace_id,
                investigation_id=history.latest.investigation_id,
                evidence_id=history.latest.id,
                command_id=command.command_id,
                command_digest=command_digest,
                event_type=EvidenceLifecycleEventType.SUPERSEDED,
                reason=EvidenceLifecycleReason.CORRECTION,
                actor_user_id=actor.user_id,
                related_evidence_id=corrected.id,
                occurred_at=occurred_at,
            )
            unit_of_work.evidence.add_correction(corrected, event)
            append_audit_event(
                unit_of_work,
                actor=actor,
                action=action,
                resource_type=AuditResourceType.INVESTIGATION,
                resource_id=history.latest.investigation_id,
                outcome=AuditOutcome.SUCCESS,
                reason=None,
                occurred_at=occurred_at,
            )
            unit_of_work.commit()
            return EvidenceOperationResult(
                history=EvidenceHistory(
                    artifact=history.artifact,
                    versions=(*history.versions, corrected),
                    events=(*history.events, event),
                ),
                replayed=False,
            )

    def revoke(self, actor: ActorContext, command: RevokeEvidence) -> EvidenceOperationResult:
        """Append one terminal revocation; no evidence or artifact row is deleted."""

        if not isinstance(command, RevokeEvidence):
            raise TypeError("command must be a RevokeEvidence")
        command_digest = digest_revoke_evidence(actor, command)
        action = AuditActionCode.EVIDENCE_REVOKED
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, Permission.EVIDENCE_REVOKE, action)
            unit_of_work.evidence.acquire_command_lock(actor.workspace_id, command.command_id)
            existing = unit_of_work.evidence.get_history_by_command(
                actor.workspace_id, command.command_id
            )
            if existing is not None:
                return self._replay(unit_of_work, existing, command.command_id, command_digest)
            unit_of_work.evidence.acquire_history_lock(actor.workspace_id, command.evidence_id)
            history = unit_of_work.evidence.get_history(actor.workspace_id, command.evidence_id)
            if history is None:
                raise ResourceNotFoundError()
            self._validate_current_version(
                history, command.evidence_id, command.expected_evidence_digest
            )
            if history.is_revoked:
                raise EvidenceAlreadyRevokedError()
            occurred_at = self._clock.now()
            event = build_lifecycle_event(
                event_id=EvidenceLifecycleEventId.new(),
                workspace_id=history.latest.workspace_id,
                investigation_id=history.latest.investigation_id,
                evidence_id=history.latest.id,
                command_id=command.command_id,
                command_digest=command_digest,
                event_type=EvidenceLifecycleEventType.REVOKED,
                reason=command.reason,
                actor_user_id=actor.user_id,
                related_evidence_id=None,
                occurred_at=occurred_at,
            )
            unit_of_work.evidence.add_lifecycle_event(event)
            append_audit_event(
                unit_of_work,
                actor=actor,
                action=action,
                resource_type=AuditResourceType.INVESTIGATION,
                resource_id=history.latest.investigation_id,
                outcome=AuditOutcome.SUCCESS,
                reason=None,
                occurred_at=occurred_at,
            )
            unit_of_work.commit()
            return EvidenceOperationResult(
                history=EvidenceHistory(
                    artifact=history.artifact,
                    versions=history.versions,
                    events=(*history.events, event),
                ),
                replayed=False,
            )

    def get_history(self, actor: ActorContext, evidence_id: EvidenceId) -> EvidenceHistory:
        """Read a complete history only within the actor's authorized workspace."""

        if not isinstance(evidence_id, EvidenceId):
            raise TypeError("evidence_id must be an EvidenceId")
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(
                unit_of_work,
                actor,
                Permission.EVIDENCE_READ,
                AuditActionCode.EVIDENCE_READ_DENIED,
            )
            history = unit_of_work.evidence.get_history(actor.workspace_id, evidence_id)
            if history is None:
                raise ResourceNotFoundError()
            unit_of_work.commit()
            return history

    def _validated_context(
        self,
        unit_of_work: UnitOfWork,
        *,
        actor: ActorContext,
        investigation_id: InvestigationId,
        decision_id: EntityResolutionDecisionId,
    ) -> EntityResolutionDecisionRecord:
        investigation = unit_of_work.investigations.get(actor.workspace_id, investigation_id)
        decision = unit_of_work.entity_resolution_decisions.get_by_id(
            actor.workspace_id, decision_id
        )
        if (
            investigation is None
            or decision is None
            or investigation.state is not InvestigationState.COLLECTING
            or investigation.id != decision.investigation_id
            or investigation.confirmed_company_id != decision.company_id
        ):
            raise InvalidEvidenceContextError()
        return decision

    @staticmethod
    def _validate_current_version(
        history: EvidenceHistory, evidence_id: EvidenceId, expected_digest: str
    ) -> None:
        if history.latest.id != evidence_id or history.latest.evidence_digest != expected_digest:
            raise EvidenceVersionConflictError()

    @staticmethod
    def _replay(
        unit_of_work: UnitOfWork,
        history: EvidenceHistory,
        command_id: EvidenceCommandId,
        command_digest: str,
    ) -> EvidenceOperationResult:
        matches = [
            item.command_digest for item in history.versions if item.command_id == command_id
        ] + [item.command_digest for item in history.events if item.command_id == command_id]
        if not matches or any(value != command_digest for value in matches):
            raise EvidenceCommandCollisionError()
        unit_of_work.commit()
        return EvidenceOperationResult(history=history, replayed=True)

    def _authorize(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        permission: Permission,
        action: AuditActionCode,
    ) -> None:
        decision = self._authorizer.authorize(unit_of_work, actor, permission)
        if decision.is_allowed:
            return
        reason = decision.denial_reason
        if reason is None:
            raise RuntimeError("A denied authorization decision requires a reason.")
        commit_standalone_outcome(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=AuditResourceType.INVESTIGATION,
            resource_id=None,
            outcome=AuditOutcome.DENIED,
            reason=reason,
            occurred_at=self._clock.now(),
        )
        raise AuthorizationDeniedError()


__all__ = ["EvidenceService"]
