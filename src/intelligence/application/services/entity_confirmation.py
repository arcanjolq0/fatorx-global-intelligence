"""Atomic F4.3 human entity confirmation and Company materialization service."""

from datetime import datetime
from typing import Never

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import (
    AuditActionCode,
    AuditReasonCode,
    append_audit_event,
    commit_standalone_outcome,
)
from intelligence.application.authorization import ContextualAuthorizer, Permission
from intelligence.application.entity_confirmation import (
    ConfirmEntityCandidate,
    EntityConfirmationResult,
    EntityResolutionDecisionRecord,
    build_entity_resolution_decision_record,
    digest_entity_confirmation_command,
    validate_confirmation_reason,
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
    ResourceNotFoundError,
)
from intelligence.application.investigation_lifecycle import (
    InvestigationCommandDigest,
    InvestigationCommandType,
    InvestigationTransitionRecord,
)
from intelligence.application.ports.clock import Clock
from intelligence.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from intelligence.domain.audit import AuditOutcome, AuditResourceType
from intelligence.domain.errors import DomainError, InvariantViolationError
from intelligence.domain.identifiers import (
    CompanyId,
    EntityResolutionDecisionId,
    InvestigationTransitionId,
)
from intelligence.domain.investigations import InvestigationState
from intelligence.entity_resolution.errors import EntityResolutionError
from intelligence.entity_resolution.materialization import (
    COMPANY_MATERIALIZATION_V1,
    materialize_company,
)
from intelligence.entity_resolution.policy import MatchClassification


class EntityConfirmationService:
    """Confirm one explicitly selected persisted candidate in a single transaction."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        authorizer: ContextualAuthorizer,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authorizer = authorizer
        self._clock = clock

    def confirm_entity_candidate(
        self,
        actor: ActorContext,
        command: ConfirmEntityCandidate,
    ) -> EntityConfirmationResult:
        """Apply one positive human decision or return its durable replay."""

        if not isinstance(command, ConfirmEntityCandidate):
            raise TypeError("command must be a ConfirmEntityCandidate")
        action = AuditActionCode.INVESTIGATION_ENTITY_CANDIDATE_CONFIRMED
        command_digest = digest_entity_confirmation_command(actor, command)
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, action)
            unit_of_work.investigation_transitions.acquire_command_lock(
                actor.workspace_id,
                command.command_id,
            )
            existing_transition = unit_of_work.investigation_transitions.get_by_command(
                actor.workspace_id,
                command.command_id,
            )
            existing_decision = unit_of_work.entity_resolution_decisions.get_by_command(
                actor.workspace_id,
                command.command_id,
            )
            if existing_transition is not None or existing_decision is not None:
                return self._replay_existing_confirmation(
                    unit_of_work,
                    actor=actor,
                    command=command,
                    command_digest=command_digest,
                    transition=existing_transition,
                    decision=existing_decision,
                    action=action,
                )

            investigation = unit_of_work.investigations.get_for_update(
                actor.workspace_id,
                command.investigation_id,
            )
            if investigation is None:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.DENIED,
                    reason=AuditReasonCode.RESOURCE_NOT_FOUND,
                    error=ResourceNotFoundError(),
                )
            if investigation.state_version != command.expected_state_version:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.STATE_VERSION_CONFLICT,
                    error=ConcurrentInvestigationUpdateError(),
                )
            if investigation.state is not InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.INVALID_TRANSITION,
                    error=InvestigationTransitionError(),
                )
            if investigation.active_candidate_batch_id != command.candidate_batch_id:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.CANDIDATE_BATCH_INACTIVE,
                    error=InactiveCandidateBatchError(),
                )

            batch = unit_of_work.entity_candidate_batches.get(
                actor.workspace_id,
                command.candidate_batch_id,
            )
            if batch is None or batch.investigation_id != command.investigation_id:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.CANDIDATE_BATCH_INACTIVE,
                    error=InactiveCandidateBatchError(),
                )
            candidate = next(
                (item for item in batch.candidates if item.id == command.candidate_id),
                None,
            )
            if candidate is None:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.CANDIDATE_NOT_IN_BATCH,
                    error=CandidateNotInBatchError(),
                )
            if candidate.classification is MatchClassification.EXCLUDED:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.CANDIDATE_EXCLUDED,
                    error=CandidateExcludedError(),
                )
            try:
                validate_confirmation_reason(candidate, command.review_reason)
            except InvariantViolationError as cause:
                reason_error = EntityConfirmationReasonError()
                reason_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.CONFIRMATION_REASON_INCOMPATIBLE,
                    error=reason_error,
                )
            if command.materialization_policy != COMPANY_MATERIALIZATION_V1:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.MATERIALIZATION_POLICY_INVALID,
                    error=InvalidMaterializationPolicyError(),
                )

            occurred_at = self._clock.now()
            company_id = CompanyId.new()
            decision_id = EntityResolutionDecisionId.new()
            try:
                company = materialize_company(
                    policy=command.materialization_policy,
                    company_id=company_id,
                    workspace_id=actor.workspace_id,
                    candidate_identity=candidate.identity,
                    occurred_at=occurred_at,
                )
                decision = build_entity_resolution_decision_record(
                    decision_id=decision_id,
                    actor=actor,
                    command=command,
                    command_digest=command_digest,
                    batch=batch,
                    candidate=candidate,
                    company=company,
                    decided_at=occurred_at,
                )
                domain_result = investigation.confirm_entity(
                    company_id=company.id,
                    candidate_batch_id=command.candidate_batch_id,
                    occurred_at=occurred_at,
                )
            except EntityResolutionError as cause:
                policy_error = InvalidMaterializationPolicyError()
                policy_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.MATERIALIZATION_POLICY_INVALID,
                    error=policy_error,
                    occurred_at=occurred_at,
                )
            except DomainError as cause:
                transition_error = InvestigationTransitionError()
                transition_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.INVALID_TRANSITION,
                    error=transition_error,
                    occurred_at=occurred_at,
                )

            transition = InvestigationTransitionRecord(
                id=InvestigationTransitionId.new(),
                workspace_id=actor.workspace_id,
                investigation_id=command.investigation_id,
                command_id=command.command_id,
                command_type=InvestigationCommandType.CONFIRM_ENTITY_CANDIDATE,
                state_before=domain_result.transition.state_before,
                version_before=domain_result.transition.version_before,
                state_after=domain_result.transition.state_after,
                version_after=domain_result.transition.version_after,
                actor_user_id=actor.user_id,
                reason=None,
                occurred_at=occurred_at,
                command_digest=command_digest,
                correlation_id=actor.correlation_id,
                confirmation_decision_id=decision.id,
                confirmed_company_id=company.id,
                confirmed_candidate_batch_id=batch.id,
                confirmed_candidate_id=candidate.id,
                confirmation_reason_code=command.review_reason.value,
                confirmed_candidate_classification=candidate.classification,
                confirmed_candidate_rank=candidate.rank,
                matching_policy_id=batch.policy_id,
                matching_policy_version=batch.policy_version,
                materialization_policy_id=command.materialization_policy.policy_id,
                materialization_policy_version=command.materialization_policy.version,
            )
            unit_of_work.companies.add(company)
            unit_of_work.entity_resolution_decisions.add(decision)
            updated = unit_of_work.investigations.update_if_version(
                domain_result.investigation,
                expected_state_version=command.expected_state_version,
            )
            if not updated:
                unit_of_work.rollback()
                raise ConcurrentInvestigationUpdateError()
            unit_of_work.investigation_transitions.add(transition)
            append_audit_event(
                unit_of_work,
                actor=actor,
                action=action,
                resource_type=AuditResourceType.INVESTIGATION,
                resource_id=command.investigation_id,
                outcome=AuditOutcome.SUCCESS,
                reason=None,
                occurred_at=occurred_at,
                confirmation_command_id=command.command_id,
                entity_resolution_decision_id=decision.id,
                confirmed_company_id=company.id,
                confirmed_candidate_batch_id=batch.id,
                confirmed_candidate_id=candidate.id,
                confirmation_reason=command.review_reason,
                confirmed_candidate_classification=candidate.classification,
                confirmed_candidate_rank=candidate.rank,
                matching_policy_id=batch.policy_id,
                matching_policy_version=batch.policy_version,
                materialization_policy_id=command.materialization_policy.policy_id,
                materialization_policy_version=command.materialization_policy.version,
            )
            unit_of_work.commit()
            return EntityConfirmationResult(
                decision=decision,
                company=company,
                replayed=False,
            )

    def _replay_existing_confirmation(
        self,
        unit_of_work: UnitOfWork,
        *,
        actor: ActorContext,
        command: ConfirmEntityCandidate,
        command_digest: InvestigationCommandDigest,
        transition: InvestigationTransitionRecord | None,
        decision: EntityResolutionDecisionRecord | None,
        action: AuditActionCode,
    ) -> EntityConfirmationResult:
        if transition is None or decision is None:
            if transition is not None and (
                transition.command_type is not InvestigationCommandType.CONFIRM_ENTITY_CANDIDATE
                or transition.investigation_id != command.investigation_id
                or transition.command_digest != command_digest
            ):
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.COMMAND_ID_COLLISION,
                    error=InvestigationCommandCollisionError(),
                )
            raise PersistenceDataError("Persisted entity confirmation records are invalid.")
        company = unit_of_work.companies.get(actor.workspace_id, decision.company_id)
        investigation = unit_of_work.investigations.get(
            actor.workspace_id,
            decision.investigation_id,
        )
        batch = unit_of_work.entity_candidate_batches.get(
            actor.workspace_id,
            decision.candidate_batch_id,
        )
        if company is None or investigation is None or batch is None:
            raise PersistenceDataError("Persisted entity confirmation records are invalid.")
        try:
            validate_entity_resolution_decision_context(
                decision,
                transition=transition,
                investigation=investigation,
                batch=batch,
                company=company,
            )
        except DomainError as cause:
            raise PersistenceDataError(
                "Persisted entity confirmation records are invalid."
            ) from cause
        if (
            transition.command_type is not InvestigationCommandType.CONFIRM_ENTITY_CANDIDATE
            or transition.investigation_id != command.investigation_id
            or transition.command_digest != command_digest
        ):
            self._reject(
                unit_of_work,
                actor=actor,
                action=action,
                outcome=AuditOutcome.FAILURE,
                reason=AuditReasonCode.COMMAND_ID_COLLISION,
                error=InvestigationCommandCollisionError(),
            )
        if (
            transition.version_before != command.expected_state_version
            or transition.version_after != command.expected_state_version + 1
            or decision.command_digest != command_digest
        ):
            raise PersistenceDataError("Persisted entity confirmation records are invalid.")
        unit_of_work.commit()
        return EntityConfirmationResult(decision=decision, company=company, replayed=True)

    def _authorize(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        action: AuditActionCode,
    ) -> None:
        decision = self._authorizer.authorize(
            unit_of_work,
            actor,
            Permission.INVESTIGATION_ENTITY_CONFIRM,
        )
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

    def _reject(
        self,
        unit_of_work: UnitOfWork,
        *,
        actor: ActorContext,
        action: AuditActionCode,
        outcome: AuditOutcome,
        reason: AuditReasonCode,
        error: Exception,
        occurred_at: datetime | None = None,
    ) -> Never:
        commit_standalone_outcome(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=AuditResourceType.INVESTIGATION,
            resource_id=None,
            outcome=outcome,
            reason=reason,
            occurred_at=occurred_at or self._clock.now(),
        )
        raise error


__all__ = ["EntityConfirmationService"]
