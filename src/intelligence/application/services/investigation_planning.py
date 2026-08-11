"""Atomic F4.4 deterministic investigation-plan creation service."""

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
from intelligence.application.errors import (
    AuthorizationDeniedError,
    ConcurrentInvestigationUpdateError,
    InvalidInvestigationPlanningError,
    InvestigationCommandCollisionError,
    InvestigationPlanAlreadyExistsError,
    InvestigationPlanningBudgetError,
    InvestigationPlanningDeadlineError,
    PersistenceDataError,
    RequiredPlanningCapabilityUnavailableError,
    ResourceNotFoundError,
)
from intelligence.application.investigation_planning import (
    CreateInvestigationPlan,
    InvestigationPlanningResult,
    digest_create_investigation_plan_command,
)
from intelligence.application.ports.clock import Clock
from intelligence.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from intelligence.domain.audit import AuditOutcome, AuditResourceType
from intelligence.domain.errors import DomainError
from intelligence.domain.identifiers import (
    InvestigationPlanId,
    PlannedCapabilityId,
    PlannedConnectorOptionId,
)
from intelligence.domain.investigations import InvestigationState
from intelligence.orchestration.errors import (
    PlanningBudgetExceededError,
    PlanningDeadlineExceededError,
    RequiredCapabilityUnavailableError,
)
from intelligence.orchestration.planning import (
    INVESTIGATION_PLANNING_V1,
    PlanningConnectorCatalog,
    build_investigation_plan,
    count_eligible_options,
)


class InvestigationPlanningService:
    """Persist one deterministic READY plan without changing lifecycle state."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        authorizer: ContextualAuthorizer,
        clock: Clock,
        connector_registry: PlanningConnectorCatalog,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authorizer = authorizer
        self._clock = clock
        self._connector_registry = connector_registry

    def create_investigation_plan(
        self,
        actor: ActorContext,
        command: CreateInvestigationPlan,
    ) -> InvestigationPlanningResult:
        """Create or replay the sole immutable plan for one investigation."""

        if not isinstance(command, CreateInvestigationPlan):
            raise TypeError("command must be a CreateInvestigationPlan")
        action = AuditActionCode.INVESTIGATION_PLAN_CREATED
        command_digest = digest_create_investigation_plan_command(actor, command)
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, action)
            unit_of_work.investigation_transitions.acquire_command_lock(
                actor.workspace_id,
                command.command_id,
            )
            transition = unit_of_work.investigation_transitions.get_by_command(
                actor.workspace_id,
                command.command_id,
            )
            existing = unit_of_work.investigation_plans.get_by_command(
                actor.workspace_id,
                command.command_id,
            )
            if transition is not None and existing is not None:
                raise PersistenceDataError("Persisted planning command records are invalid.")
            if transition is not None:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.COMMAND_ID_COLLISION,
                    error=InvestigationCommandCollisionError(),
                )
            if existing is not None:
                if (
                    existing.investigation_id != command.investigation_id
                    or existing.command_digest != command_digest.value
                    or existing.investigation_state_version != command.expected_state_version
                ):
                    self._reject(
                        unit_of_work,
                        actor=actor,
                        action=action,
                        outcome=AuditOutcome.FAILURE,
                        reason=AuditReasonCode.COMMAND_ID_COLLISION,
                        error=InvestigationCommandCollisionError(),
                    )
                unit_of_work.commit()
                return InvestigationPlanningResult(plan=existing, replayed=True)

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
            competing = unit_of_work.investigation_plans.get_by_investigation(
                actor.workspace_id,
                command.investigation_id,
            )
            if competing is not None:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.INVESTIGATION_PLAN_ALREADY_EXISTS,
                    error=InvestigationPlanAlreadyExistsError(),
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
                    reason=AuditReasonCode.PLANNING_CONTEXT_INVALID,
                    error=InvalidInvestigationPlanningError(),
                )
            company = unit_of_work.companies.get(
                actor.workspace_id,
                investigation.confirmed_company_id,
            )
            if company is None:
                raise PersistenceDataError("Persisted investigation planning context is invalid.")
            if command.planning_policy != INVESTIGATION_PLANNING_V1:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.PLANNING_POLICY_INVALID,
                    error=InvalidInvestigationPlanningError(),
                )

            descriptors = self._connector_registry.list_descriptors()
            option_count = count_eligible_options(
                command.planning_policy,
                descriptors,
                company.country_code.value,
            )
            occurred_at = self._clock.now()
            try:
                plan = build_investigation_plan(
                    plan_id=InvestigationPlanId.new(),
                    capability_ids=tuple(
                        PlannedCapabilityId.new() for _ in command.planning_policy.capability_rules
                    ),
                    option_ids=tuple(PlannedConnectorOptionId.new() for _ in range(option_count)),
                    investigation=investigation,
                    company=company,
                    command_id=command.command_id,
                    command_digest=command_digest.value,
                    created_by=actor.user_id,
                    created_at=occurred_at,
                    policy=command.planning_policy,
                    descriptors=descriptors,
                )
            except RequiredCapabilityUnavailableError as cause:
                capability_error = RequiredPlanningCapabilityUnavailableError()
                capability_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.REQUIRED_CAPABILITY_UNAVAILABLE,
                    error=capability_error,
                    occurred_at=occurred_at,
                )
            except PlanningBudgetExceededError as cause:
                budget_error = InvestigationPlanningBudgetError()
                budget_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.PLANNING_BUDGET_EXCEEDED,
                    error=budget_error,
                    occurred_at=occurred_at,
                )
            except PlanningDeadlineExceededError as cause:
                deadline_error = InvestigationPlanningDeadlineError()
                deadline_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.PLANNING_DEADLINE_EXCEEDED,
                    error=deadline_error,
                    occurred_at=occurred_at,
                )
            except (DomainError, ValueError) as cause:
                planning_error = InvalidInvestigationPlanningError()
                planning_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.PLANNING_CONTEXT_INVALID,
                    error=planning_error,
                    occurred_at=occurred_at,
                )

            unit_of_work.investigation_plans.add(plan)
            append_audit_event(
                unit_of_work,
                actor=actor,
                action=action,
                resource_type=AuditResourceType.INVESTIGATION,
                resource_id=investigation.id,
                outcome=AuditOutcome.SUCCESS,
                reason=None,
                occurred_at=occurred_at,
                planning_command_id=command.command_id,
                investigation_plan_id=plan.id,
                planned_capability_count=len(plan.capabilities),
                planned_connector_option_count=sum(
                    len(capability.connector_options) for capability in plan.capabilities
                ),
                planning_policy_id=plan.planning_policy_id,
                planning_policy_version=plan.planning_policy_version,
                planning_maximum_estimated_cost_kind_code=(plan.maximum_estimated_cost_kind.value),
                planning_maximum_estimated_cost=plan.maximum_estimated_cost,
            )
            unit_of_work.commit()
            return InvestigationPlanningResult(plan=plan, replayed=False)

    def _authorize(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        action: AuditActionCode,
    ) -> None:
        decision = self._authorizer.authorize(
            unit_of_work,
            actor,
            Permission.INVESTIGATION_PLAN_CREATE,
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


__all__ = ["InvestigationPlanningService"]
