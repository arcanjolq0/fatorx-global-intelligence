"""Minimal authorized investigation creation and tenant-scoped retrieval."""

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
from intelligence.application.entity_candidate_review import (
    EntityCandidateBatchRecord,
    build_candidate_batch_record,
)
from intelligence.application.errors import (
    AuthorizationDeniedError,
    CandidateInputDigestMismatchError,
    CandidateReviewError,
    ConcurrentInvestigationUpdateError,
    InvalidOperationError,
    InvestigationCommandCollisionError,
    InvestigationTransitionError,
    ResourceNotFoundError,
)
from intelligence.application.investigation_lifecycle import (
    CancelInvestigation,
    InvestigationCancellationReason,
    InvestigationLifecycleCommand,
    InvestigationLifecycleResult,
    InvestigationTransitionRecord,
    RequestEntityConfirmation,
    StartIdentification,
    command_type_of,
    digest_investigation_command,
)
from intelligence.application.ports.clock import Clock
from intelligence.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from intelligence.domain.audit import AuditOutcome, AuditResourceType
from intelligence.domain.errors import DomainError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    EntityCandidateBatchId,
    InvestigationId,
    InvestigationTransitionId,
)
from intelligence.domain.investigations import Investigation
from intelligence.domain.money import Money
from intelligence.entity_resolution.errors import EntityResolutionError
from intelligence.entity_resolution.matching import evaluate_candidate_batch


class InvestigationService:
    """Create and retrieve investigations under the actor's effective workspace."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        authorizer: ContextualAuthorizer,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authorizer = authorizer
        self._clock = clock

    def create_investigation(
        self,
        actor: ActorContext,
        *,
        profile_code: str,
        country_code: CountryCode,
        budget: Money | None = None,
        deadline_at: datetime | None = None,
    ) -> Investigation:
        action = AuditActionCode.INVESTIGATION_CREATED
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, Permission.INVESTIGATION_CREATE, action)
            occurred_at = self._clock.now()
            try:
                investigation = Investigation(
                    id=InvestigationId.new(),
                    workspace_id=actor.workspace_id,
                    requested_by=actor.user_id,
                    profile_code=profile_code,
                    country_code=country_code,
                    budget=budget,
                    deadline_at=deadline_at,
                    created_at=occurred_at,
                )
            except DomainError as cause:
                error = InvalidOperationError()
                error.__cause__ = cause
                self._fail(unit_of_work, actor, action, error)

            unit_of_work.investigations.add(investigation)
            append_audit_event(
                unit_of_work,
                actor=actor,
                action=action,
                resource_type=AuditResourceType.INVESTIGATION,
                resource_id=investigation.id,
                outcome=AuditOutcome.SUCCESS,
                reason=None,
                occurred_at=occurred_at,
            )
            unit_of_work.commit()
            return investigation

    def get_investigation(
        self,
        actor: ActorContext,
        *,
        investigation_id: InvestigationId,
    ) -> Investigation:
        action = AuditActionCode.INVESTIGATION_READ_DENIED
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, Permission.INVESTIGATION_READ, action)
            investigation = unit_of_work.investigations.get(
                actor.workspace_id,
                investigation_id,
            )
            if investigation is None:
                commit_standalone_outcome(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    resource_type=AuditResourceType.INVESTIGATION,
                    resource_id=None,
                    outcome=AuditOutcome.DENIED,
                    reason=AuditReasonCode.RESOURCE_NOT_FOUND,
                    occurred_at=self._clock.now(),
                )
                raise ResourceNotFoundError()
            unit_of_work.commit()
            return investigation

    def start_identification(
        self,
        actor: ActorContext,
        command: StartIdentification,
    ) -> InvestigationLifecycleResult:
        """Atomically apply or replay the only F4.1 identification start command."""

        if not isinstance(command, StartIdentification):
            raise TypeError("command must be a StartIdentification")
        return self._execute_lifecycle_command(actor, command)

    def cancel_investigation(
        self,
        actor: ActorContext,
        command: CancelInvestigation,
    ) -> InvestigationLifecycleResult:
        """Atomically cancel or replay cancellation for one non-terminal investigation."""

        if not isinstance(command, CancelInvestigation):
            raise TypeError("command must be a CancelInvestigation")
        return self._execute_lifecycle_command(actor, command)

    def request_entity_confirmation(
        self,
        actor: ActorContext,
        command: RequestEntityConfirmation,
    ) -> InvestigationLifecycleResult:
        """Atomically persist ranked candidates and pause for future human review."""

        if not isinstance(command, RequestEntityConfirmation):
            raise TypeError("command must be a RequestEntityConfirmation")
        return self._execute_lifecycle_command(actor, command)

    def _execute_lifecycle_command(
        self,
        actor: ActorContext,
        command: InvestigationLifecycleCommand,
    ) -> InvestigationLifecycleResult:
        action, permission = _lifecycle_policy(command)
        command_digest = digest_investigation_command(actor, command)
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, permission, action)
            unit_of_work.investigation_transitions.acquire_command_lock(
                actor.workspace_id,
                command.command_id,
            )
            existing = unit_of_work.investigation_transitions.get_by_command(
                actor.workspace_id,
                command.command_id,
            )
            if existing is not None:
                if (
                    existing.investigation_id == command.investigation_id
                    and existing.command_type is command_type_of(command)
                    and existing.command_digest == command_digest
                ):
                    unit_of_work.commit()
                    return InvestigationLifecycleResult.from_record(
                        existing,
                        replayed=True,
                    )
                self._reject_lifecycle(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.COMMAND_ID_COLLISION,
                    error=InvestigationCommandCollisionError(),
                )

            investigation = unit_of_work.investigations.get(
                actor.workspace_id,
                command.investigation_id,
            )
            if investigation is None:
                self._reject_lifecycle(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.DENIED,
                    reason=AuditReasonCode.RESOURCE_NOT_FOUND,
                    error=ResourceNotFoundError(),
                )
            if investigation.state_version != command.expected_state_version:
                self._reject_lifecycle(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.STATE_VERSION_CONFLICT,
                    error=ConcurrentInvestigationUpdateError(),
                )

            candidate_batch_record: EntityCandidateBatchRecord | None = None
            candidate_batch_id: EntityCandidateBatchId | None = None
            candidate_count: int | None = None
            top_classification = None
            if isinstance(command, RequestEntityConfirmation):
                identification_input = investigation.identification_input
                if (
                    identification_input is None
                    or command.candidate_batch.input_digest != identification_input.digest
                ):
                    self._reject_lifecycle(
                        unit_of_work,
                        actor=actor,
                        action=action,
                        outcome=AuditOutcome.FAILURE,
                        reason=AuditReasonCode.INPUT_DIGEST_MISMATCH,
                        error=CandidateInputDigestMismatchError(),
                    )
                try:
                    evaluation = evaluate_candidate_batch(
                        investigation_country_code=investigation.country_code,
                        identification_input=identification_input,
                        batch=command.candidate_batch,
                        policy=command.matching_policy,
                    )
                except EntityResolutionError as cause:
                    candidate_error = CandidateReviewError()
                    candidate_error.__cause__ = cause
                    self._reject_lifecycle(
                        unit_of_work,
                        actor=actor,
                        action=action,
                        outcome=AuditOutcome.FAILURE,
                        reason=AuditReasonCode.CANDIDATE_REVIEW_INVALID,
                        error=candidate_error,
                    )
                candidate_batch_id = EntityCandidateBatchId.new()
                candidate_count = len(evaluation.candidates)
                top_classification = evaluation.top_classification

            occurred_at = self._clock.now()
            try:
                if isinstance(command, StartIdentification):
                    domain_result = investigation.start_identification(
                        identification_input=command.identification_input,
                        occurred_at=occurred_at,
                    )
                elif isinstance(command, CancelInvestigation):
                    domain_result = investigation.cancel(occurred_at=occurred_at)
                else:
                    if candidate_batch_id is None:
                        raise RuntimeError("Candidate batch ID was not initialized.")
                    domain_result = investigation.request_entity_confirmation(
                        candidate_batch_id=candidate_batch_id,
                        occurred_at=occurred_at,
                    )
            except DomainError as cause:
                transition_error = InvestigationTransitionError()
                transition_error.__cause__ = cause
                self._reject_lifecycle(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.INVALID_TRANSITION,
                    error=transition_error,
                    occurred_at=occurred_at,
                )

            if isinstance(command, RequestEntityConfirmation):
                if candidate_batch_id is None:
                    raise RuntimeError("Candidate batch ID was not initialized.")
                candidate_batch_record = build_candidate_batch_record(
                    batch_id=candidate_batch_id,
                    workspace_id=actor.workspace_id,
                    investigation_id=command.investigation_id,
                    command_id=command.command_id,
                    created_by=actor.user_id,
                    created_at=occurred_at,
                    submission=command.candidate_batch,
                    policy=command.matching_policy,
                    evaluation=evaluation,
                )

            record = InvestigationTransitionRecord.from_transition(
                record_id=InvestigationTransitionId.new(),
                actor=actor,
                command=command,
                transition=domain_result.transition,
                command_digest=command_digest,
                candidate_batch_id=candidate_batch_id,
                candidate_count=candidate_count,
                top_classification=top_classification,
            )
            updated = unit_of_work.investigations.update_if_version(
                domain_result.investigation,
                expected_state_version=command.expected_state_version,
            )
            if not updated:
                self._reject_lifecycle(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.STATE_VERSION_CONFLICT,
                    error=ConcurrentInvestigationUpdateError(),
                    occurred_at=occurred_at,
                )
            if candidate_batch_record is not None:
                unit_of_work.entity_candidate_batches.add(candidate_batch_record)
            unit_of_work.investigation_transitions.add(record)
            append_audit_event(
                unit_of_work,
                actor=actor,
                action=action,
                resource_type=AuditResourceType.INVESTIGATION,
                resource_id=command.investigation_id,
                outcome=AuditOutcome.SUCCESS,
                reason=_success_reason(command),
                occurred_at=occurred_at,
                command_id=(
                    command.command_id if isinstance(command, RequestEntityConfirmation) else None
                ),
                policy_id=(
                    command.matching_policy.policy_id
                    if isinstance(command, RequestEntityConfirmation)
                    else None
                ),
                policy_version=(
                    command.matching_policy.version
                    if isinstance(command, RequestEntityConfirmation)
                    else None
                ),
                candidate_count=candidate_count,
                top_classification=top_classification,
            )
            unit_of_work.commit()
            return InvestigationLifecycleResult.from_record(record, replayed=False)

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

    def _fail(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        action: AuditActionCode,
        error: Exception,
    ) -> Never:
        commit_standalone_outcome(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=AuditResourceType.INVESTIGATION,
            resource_id=None,
            outcome=AuditOutcome.FAILURE,
            reason=AuditReasonCode.VALIDATION_FAILURE,
            occurred_at=self._clock.now(),
        )
        raise error

    def _reject_lifecycle(
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


def _lifecycle_policy(
    command: InvestigationLifecycleCommand,
) -> tuple[AuditActionCode, Permission]:
    if isinstance(command, StartIdentification):
        return (
            AuditActionCode.INVESTIGATION_IDENTIFICATION_STARTED,
            Permission.INVESTIGATION_START_IDENTIFICATION,
        )
    if isinstance(command, CancelInvestigation):
        return (
            AuditActionCode.INVESTIGATION_CANCELLED,
            Permission.INVESTIGATION_CANCEL,
        )
    if isinstance(command, RequestEntityConfirmation):
        return (
            AuditActionCode.INVESTIGATION_ENTITY_CONFIRMATION_REQUESTED,
            Permission.INVESTIGATION_REQUEST_ENTITY_CONFIRMATION,
        )
    raise TypeError("Unsupported investigation lifecycle command.")


_CANCELLATION_AUDIT_REASONS = {
    InvestigationCancellationReason.USER_REQUESTED: AuditReasonCode.CANCELLATION_USER_REQUESTED,
    InvestigationCancellationReason.DUPLICATE_REQUEST: (
        AuditReasonCode.CANCELLATION_DUPLICATE_REQUEST
    ),
    InvestigationCancellationReason.NO_LONGER_REQUIRED: (
        AuditReasonCode.CANCELLATION_NO_LONGER_REQUIRED
    ),
    InvestigationCancellationReason.POLICY_REQUIRED: AuditReasonCode.CANCELLATION_POLICY_REQUIRED,
}


def _success_reason(
    command: InvestigationLifecycleCommand,
) -> AuditReasonCode | None:
    return (
        _CANCELLATION_AUDIT_REASONS[command.reason]
        if isinstance(command, CancelInvestigation)
        else None
    )


__all__ = ["InvestigationService"]
