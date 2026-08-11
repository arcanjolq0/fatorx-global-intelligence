"""Atomic F4.5 activation of a READY plan into a durable collection manifest."""

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
from intelligence.application.collection_activation import (
    CollectionActivationResult,
    StartInvestigationCollection,
    digest_start_collection_command,
    validate_collection_activation_history,
)
from intelligence.application.errors import (
    AuthorizationDeniedError,
    CollectionActivationDeadlineError,
    CollectionRunAlreadyExistsError,
    ConcurrentInvestigationUpdateError,
    InvalidCollectionActivationError,
    InvestigationCommandCollisionError,
    PersistenceDataError,
    ResourceNotFoundError,
)
from intelligence.application.investigation_lifecycle import (
    InvestigationCommandType,
    InvestigationTransitionRecord,
)
from intelligence.application.ports.clock import Clock
from intelligence.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from intelligence.domain.audit import AuditOutcome, AuditResourceType
from intelligence.domain.errors import DomainError
from intelligence.domain.identifiers import (
    CollectionOperationId,
    CollectionRunId,
    InvestigationTransitionId,
)
from intelligence.domain.investigations import InvestigationState
from intelligence.orchestration.collection_activation import (
    COLLECTION_ACTIVATION_V1,
    CollectionRun,
    build_collection_run,
    validate_collection_activation_deadline,
)
from intelligence.orchestration.errors import CollectionActivationDeadlineExceededError
from intelligence.orchestration.planning import PlannedCapabilityStatus


class CollectionActivationService:
    """Create or replay one immutable collection manifest without calling connectors."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        authorizer: ContextualAuthorizer,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authorizer = authorizer
        self._clock = clock

    def start_investigation_collection(
        self,
        actor: ActorContext,
        command: StartInvestigationCollection,
    ) -> CollectionActivationResult:
        """Persist a rank-one manifest and advance PLANNING to COLLECTING once."""

        if not isinstance(command, StartInvestigationCollection):
            raise TypeError("command must be a StartInvestigationCollection")
        action = AuditActionCode.INVESTIGATION_COLLECTION_STARTED
        command_digest = digest_start_collection_command(actor, command)
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, action)
            unit_of_work.investigation_transitions.acquire_command_lock(
                actor.workspace_id, command.command_id
            )
            transition = unit_of_work.investigation_transitions.get_by_command(
                actor.workspace_id, command.command_id
            )
            if transition is not None and (
                transition.command_type is not InvestigationCommandType.START_COLLECTION
                or transition.command_digest.value != command_digest.value
            ):
                self._collision(unit_of_work, actor=actor, action=action)
            existing = unit_of_work.collection_runs.get_by_command(
                actor.workspace_id, command.command_id
            )
            if transition is not None or existing is not None:
                return self._replay(
                    unit_of_work,
                    actor=actor,
                    command=command,
                    command_digest=command_digest.value,
                    transition=transition,
                    run=existing,
                    action=action,
                )

            investigation = unit_of_work.investigations.get_for_update(
                actor.workspace_id, command.investigation_id
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
            if (
                investigation.state is not InvestigationState.PLANNING
                or investigation.confirmed_company_id is None
                or investigation.active_candidate_batch_id is not None
            ):
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.COLLECTION_CONTEXT_INVALID,
                    error=InvalidCollectionActivationError(),
                )
            company = unit_of_work.companies.get(
                actor.workspace_id, investigation.confirmed_company_id
            )
            plan = unit_of_work.investigation_plans.get_by_id(actor.workspace_id, command.plan_id)
            if company is None or plan is None:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.COLLECTION_CONTEXT_INVALID,
                    error=InvalidCollectionActivationError(),
                )
            competing_investigation = unit_of_work.collection_runs.get_by_investigation(
                actor.workspace_id, command.investigation_id
            )
            competing_plan = unit_of_work.collection_runs.get_by_plan(
                actor.workspace_id, command.plan_id
            )
            if competing_investigation is not None or competing_plan is not None:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.COLLECTION_RUN_ALREADY_EXISTS,
                    error=CollectionRunAlreadyExistsError(),
                )
            if command.activation_policy != COLLECTION_ACTIVATION_V1:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.COLLECTION_ACTIVATION_POLICY_INVALID,
                    error=InvalidCollectionActivationError(),
                )

            occurred_at = self._clock.now()
            ready_count = sum(
                capability.status is PlannedCapabilityStatus.READY
                for capability in plan.capabilities
            )
            try:
                validate_collection_activation_deadline(
                    investigation=investigation,
                    plan=plan,
                    activated_at=occurred_at,
                )
            except CollectionActivationDeadlineExceededError as cause:
                deadline_error = CollectionActivationDeadlineError()
                deadline_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.COLLECTION_DEADLINE_EXCEEDED,
                    error=deadline_error,
                    occurred_at=occurred_at,
                )
            try:
                run = build_collection_run(
                    run_id=CollectionRunId.new(),
                    operation_ids=tuple(CollectionOperationId.new() for _ in range(ready_count)),
                    investigation=investigation,
                    company=company,
                    plan=plan,
                    command_id=command.command_id,
                    command_digest=command_digest.value,
                    created_by=actor.user_id,
                    created_at=occurred_at,
                    activation_policy=command.activation_policy,
                )
                domain_result = investigation.start_collection(occurred_at=occurred_at)
            except (DomainError, ValueError) as cause:
                activation_error = InvalidCollectionActivationError()
                activation_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.COLLECTION_CONTEXT_INVALID,
                    error=activation_error,
                    occurred_at=occurred_at,
                )

            transition_record = InvestigationTransitionRecord(
                id=InvestigationTransitionId.new(),
                workspace_id=actor.workspace_id,
                investigation_id=command.investigation_id,
                command_id=command.command_id,
                command_type=InvestigationCommandType.START_COLLECTION,
                state_before=domain_result.transition.state_before,
                version_before=domain_result.transition.version_before,
                state_after=domain_result.transition.state_after,
                version_after=domain_result.transition.version_after,
                actor_user_id=actor.user_id,
                reason=None,
                occurred_at=occurred_at,
                command_digest=command_digest,
                correlation_id=actor.correlation_id,
                collection_run_id=run.id,
                collection_company_id=run.company_id,
                collection_plan_id=run.plan_id,
                collection_operation_count=len(run.operations),
                collection_activation_policy_id=run.activation_policy_id,
                collection_activation_policy_version=run.activation_policy_version,
            )
            unit_of_work.collection_runs.add(run)
            updated = unit_of_work.investigations.update_if_version(
                domain_result.investigation,
                expected_state_version=command.expected_state_version,
            )
            if not updated:
                unit_of_work.rollback()
                raise ConcurrentInvestigationUpdateError()
            unit_of_work.investigation_transitions.add(transition_record)
            append_audit_event(
                unit_of_work,
                actor=actor,
                action=action,
                resource_type=AuditResourceType.INVESTIGATION,
                resource_id=command.investigation_id,
                outcome=AuditOutcome.SUCCESS,
                reason=None,
                occurred_at=occurred_at,
                collection_command_id=command.command_id,
                collection_run_id=run.id,
                collection_operation_count=len(run.operations),
                collection_activation_policy_id=run.activation_policy_id,
                collection_activation_policy_version=run.activation_policy_version,
                collection_maximum_estimated_cost_kind_code=(run.maximum_estimated_cost_kind.value),
                collection_maximum_estimated_cost=run.maximum_estimated_cost,
            )
            unit_of_work.commit()
            return CollectionActivationResult(collection_run=run, replayed=False)

    def _replay(
        self,
        unit_of_work: UnitOfWork,
        *,
        actor: ActorContext,
        command: StartInvestigationCollection,
        command_digest: str,
        transition: InvestigationTransitionRecord | None,
        run: CollectionRun | None,
        action: AuditActionCode,
    ) -> CollectionActivationResult:
        if transition is None or run is None:
            if transition is not None and (
                transition.command_type is not InvestigationCommandType.START_COLLECTION
                or transition.command_digest.value != command_digest
            ):
                self._collision(unit_of_work, actor=actor, action=action)
            raise PersistenceDataError("Persisted collection activation records are invalid.")
        if (
            transition.command_type is not InvestigationCommandType.START_COLLECTION
            or transition.command_digest.value != command_digest
        ):
            self._collision(unit_of_work, actor=actor, action=action)
        try:
            validate_collection_activation_history(run, transition)
        except DomainError as error:
            raise PersistenceDataError(
                "Persisted collection activation records are invalid."
            ) from error
        if (
            transition.workspace_id != actor.workspace_id
            or transition.investigation_id != command.investigation_id
            or transition.version_before != command.expected_state_version
            or run.plan_id != command.plan_id
            or run.command_digest != command_digest
        ):
            raise PersistenceDataError("Persisted collection activation records are invalid.")
        unit_of_work.commit()
        return CollectionActivationResult(collection_run=run, replayed=True)

    def _collision(
        self,
        unit_of_work: UnitOfWork,
        *,
        actor: ActorContext,
        action: AuditActionCode,
    ) -> Never:
        self._reject(
            unit_of_work,
            actor=actor,
            action=action,
            outcome=AuditOutcome.FAILURE,
            reason=AuditReasonCode.COMMAND_ID_COLLISION,
            error=InvestigationCommandCollisionError(),
        )

    def _authorize(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        action: AuditActionCode,
    ) -> None:
        decision = self._authorizer.authorize(
            unit_of_work, actor, Permission.INVESTIGATION_COLLECTION_START
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


__all__ = ["CollectionActivationService"]
