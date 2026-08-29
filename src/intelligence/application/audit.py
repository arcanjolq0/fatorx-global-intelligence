"""Closed audit vocabulary and explicit application-level event coordination."""

from datetime import datetime
from enum import StrEnum

from intelligence.application.actor_context import ActorContext
from intelligence.application.entity_confirmation import EntityConfirmationReason
from intelligence.application.errors import PersistenceError
from intelligence.application.ports.unit_of_work import UnitOfWork
from intelligence.domain.audit import (
    AuditEvent,
    AuditOutcome,
    AuditResourceId,
    AuditResourceType,
)
from intelligence.domain.identifiers import (
    AuditEventId,
    CollectionRunId,
    CompanyId,
    EntityCandidateBatchId,
    EntityCandidateId,
    EntityResolutionDecisionId,
    InvestigationCommandId,
    InvestigationPlanId,
)
from intelligence.domain.money import Money
from intelligence.entity_resolution.policy import MatchClassification


class AuditActionCode(StrEnum):
    """Closed actions recorded by the F2.4.2 application services."""

    MEMBERSHIP_ADDED = "MEMBERSHIP_ADDED"
    MEMBERSHIP_ROLE_CHANGED = "MEMBERSHIP_ROLE_CHANGED"
    MEMBERSHIP_DEACTIVATED = "MEMBERSHIP_DEACTIVATED"
    MEMBERSHIP_REACTIVATED = "MEMBERSHIP_REACTIVATED"
    COMPANY_CREATED = "COMPANY_CREATED"
    INVESTIGATION_CREATED = "INVESTIGATION_CREATED"
    INVESTIGATION_IDENTIFICATION_STARTED = "INVESTIGATION_IDENTIFICATION_STARTED"
    INVESTIGATION_CANCELLED = "INVESTIGATION_CANCELLED"
    INVESTIGATION_ENTITY_CONFIRMATION_REQUESTED = "INVESTIGATION_ENTITY_CONFIRMATION_REQUESTED"
    INVESTIGATION_ENTITY_CANDIDATE_CONFIRMED = "INVESTIGATION_ENTITY_CANDIDATE_CONFIRMED"
    INVESTIGATION_PLAN_CREATED = "INVESTIGATION_PLAN_CREATED"
    INVESTIGATION_COLLECTION_STARTED = "INVESTIGATION_COLLECTION_STARTED"
    COLLECTION_OPERATION_EXECUTED = "COLLECTION_OPERATION_EXECUTED"
    EVIDENCE_REGISTERED = "EVIDENCE_REGISTERED"
    EVIDENCE_CORRECTED = "EVIDENCE_CORRECTED"
    EVIDENCE_REVOKED = "EVIDENCE_REVOKED"
    EVIDENCE_READ_DENIED = "EVIDENCE_READ_DENIED"
    EVIDENCE_ADMISSIBILITY_DECIDED = "EVIDENCE_ADMISSIBILITY_DECIDED"
    EVIDENCE_ADMISSIBILITY_SUPERSEDED = "EVIDENCE_ADMISSIBILITY_SUPERSEDED"
    EVIDENCE_ADMISSIBILITY_READ_DENIED = "EVIDENCE_ADMISSIBILITY_READ_DENIED"
    CLAIM_REGISTERED = "CLAIM_REGISTERED"
    CLAIM_CORRECTED = "CLAIM_CORRECTED"
    CLAIM_READ_DENIED = "CLAIM_READ_DENIED"
    CLAIM_REVIEW_DECIDED = "CLAIM_REVIEW_DECIDED"
    CLAIM_REVIEW_SUPERSEDED = "CLAIM_REVIEW_SUPERSEDED"
    CLAIM_REVIEW_READ_DENIED = "CLAIM_REVIEW_READ_DENIED"
    COMPANY_READ_DENIED = "COMPANY_READ_DENIED"
    INVESTIGATION_READ_DENIED = "INVESTIGATION_READ_DENIED"


class AuditReasonCode(StrEnum):
    """Closed, redacted explanations for denied and failed actions."""

    ACTOR_USER_NOT_FOUND = "ACTOR_USER_NOT_FOUND"
    ACTOR_USER_DISABLED = "ACTOR_USER_DISABLED"
    ACTOR_MEMBERSHIP_NOT_FOUND = "ACTOR_MEMBERSHIP_NOT_FOUND"
    ACTOR_MEMBERSHIP_INACTIVE = "ACTOR_MEMBERSHIP_INACTIVE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TARGET_USER_NOT_FOUND = "TARGET_USER_NOT_FOUND"
    TARGET_USER_DISABLED = "TARGET_USER_DISABLED"
    TARGET_MEMBERSHIP_NOT_FOUND = "TARGET_MEMBERSHIP_NOT_FOUND"
    TARGET_MEMBERSHIP_ALREADY_EXISTS = "TARGET_MEMBERSHIP_ALREADY_EXISTS"
    TARGET_ROLE_NOT_ALLOWED = "TARGET_ROLE_NOT_ALLOWED"
    SELF_MANAGEMENT_NOT_ALLOWED = "SELF_MANAGEMENT_NOT_ALLOWED"
    LAST_OWNER_PROTECTED = "LAST_OWNER_PROTECTED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    WORKSPACE_SCOPE_VIOLATION = "WORKSPACE_SCOPE_VIOLATION"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    PERSISTENCE_CONFLICT = "PERSISTENCE_CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"
    STATE_VERSION_CONFLICT = "STATE_VERSION_CONFLICT"
    COMMAND_ID_COLLISION = "COMMAND_ID_COLLISION"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    INPUT_DIGEST_MISMATCH = "INPUT_DIGEST_MISMATCH"
    CANDIDATE_REVIEW_INVALID = "CANDIDATE_REVIEW_INVALID"
    CANDIDATE_BATCH_INACTIVE = "CANDIDATE_BATCH_INACTIVE"
    CANDIDATE_NOT_IN_BATCH = "CANDIDATE_NOT_IN_BATCH"
    CANDIDATE_EXCLUDED = "CANDIDATE_EXCLUDED"
    CONFIRMATION_REASON_INCOMPATIBLE = "CONFIRMATION_REASON_INCOMPATIBLE"
    MATERIALIZATION_POLICY_INVALID = "MATERIALIZATION_POLICY_INVALID"
    PLANNING_POLICY_INVALID = "PLANNING_POLICY_INVALID"
    PLANNING_CONTEXT_INVALID = "PLANNING_CONTEXT_INVALID"
    REQUIRED_CAPABILITY_UNAVAILABLE = "REQUIRED_CAPABILITY_UNAVAILABLE"
    PLANNING_BUDGET_EXCEEDED = "PLANNING_BUDGET_EXCEEDED"
    PLANNING_DEADLINE_EXCEEDED = "PLANNING_DEADLINE_EXCEEDED"
    INVESTIGATION_PLAN_ALREADY_EXISTS = "INVESTIGATION_PLAN_ALREADY_EXISTS"
    COLLECTION_ACTIVATION_POLICY_INVALID = "COLLECTION_ACTIVATION_POLICY_INVALID"
    COLLECTION_CONTEXT_INVALID = "COLLECTION_CONTEXT_INVALID"
    COLLECTION_DEADLINE_EXCEEDED = "COLLECTION_DEADLINE_EXCEEDED"
    COLLECTION_RUN_ALREADY_EXISTS = "COLLECTION_RUN_ALREADY_EXISTS"
    COLLECTION_EXECUTION_INVALID = "COLLECTION_EXECUTION_INVALID"
    COLLECTION_EXECUTION_ALREADY_OWNED = "COLLECTION_EXECUTION_ALREADY_OWNED"
    COLLECTION_EXECUTION_IN_PROGRESS = "COLLECTION_EXECUTION_IN_PROGRESS"
    COLLECTION_EXECUTION_DEPENDENCY_PENDING = "COLLECTION_EXECUTION_DEPENDENCY_PENDING"
    EVIDENCE_CONTEXT_INVALID = "EVIDENCE_CONTEXT_INVALID"
    EVIDENCE_VERSION_CONFLICT = "EVIDENCE_VERSION_CONFLICT"
    EVIDENCE_ALREADY_REVOKED = "EVIDENCE_ALREADY_REVOKED"
    EVIDENCE_ADMISSIBILITY_SELF_APPROVAL = "EVIDENCE_ADMISSIBILITY_SELF_APPROVAL"
    EVIDENCE_ADMISSIBILITY_CONTEXT_INVALID = "EVIDENCE_ADMISSIBILITY_CONTEXT_INVALID"
    EVIDENCE_ADMISSIBILITY_POLICY_INVALID = "EVIDENCE_ADMISSIBILITY_POLICY_INVALID"
    EVIDENCE_ADMISSIBILITY_PREDECESSOR_INVALID = "EVIDENCE_ADMISSIBILITY_PREDECESSOR_INVALID"
    EVIDENCE_ADMISSIBILITY_HISTORY_INVALID = "EVIDENCE_ADMISSIBILITY_HISTORY_INVALID"
    CLAIM_CONTEXT_INVALID = "CLAIM_CONTEXT_INVALID"
    CLAIM_VERSION_CONFLICT = "CLAIM_VERSION_CONFLICT"
    CLAIM_EVIDENCE_INVALID = "CLAIM_EVIDENCE_INVALID"
    CLAIM_REVIEW_SELF_APPROVAL = "CLAIM_REVIEW_SELF_APPROVAL"
    CLAIM_REVIEW_CONTEXT_INVALID = "CLAIM_REVIEW_CONTEXT_INVALID"
    CLAIM_REVIEW_POLICY_INVALID = "CLAIM_REVIEW_POLICY_INVALID"
    CLAIM_REVIEW_PREDECESSOR_INVALID = "CLAIM_REVIEW_PREDECESSOR_INVALID"
    CLAIM_REVIEW_HISTORY_INVALID = "CLAIM_REVIEW_HISTORY_INVALID"
    CANCELLATION_USER_REQUESTED = "CANCELLATION_USER_REQUESTED"
    CANCELLATION_DUPLICATE_REQUEST = "CANCELLATION_DUPLICATE_REQUEST"
    CANCELLATION_NO_LONGER_REQUIRED = "CANCELLATION_NO_LONGER_REQUIRED"
    CANCELLATION_POLICY_REQUIRED = "CANCELLATION_POLICY_REQUIRED"


def build_audit_event(
    *,
    actor: ActorContext,
    action: AuditActionCode,
    resource_type: AuditResourceType,
    resource_id: AuditResourceId | None,
    outcome: AuditOutcome,
    reason: AuditReasonCode | None,
    occurred_at: datetime,
    command_id: InvestigationCommandId | None = None,
    policy_id: str | None = None,
    policy_version: int | None = None,
    candidate_count: int | None = None,
    top_classification: MatchClassification | None = None,
    confirmation_command_id: InvestigationCommandId | None = None,
    entity_resolution_decision_id: EntityResolutionDecisionId | None = None,
    confirmed_company_id: CompanyId | None = None,
    confirmed_candidate_batch_id: EntityCandidateBatchId | None = None,
    confirmed_candidate_id: EntityCandidateId | None = None,
    confirmation_reason: EntityConfirmationReason | None = None,
    confirmed_candidate_classification: MatchClassification | None = None,
    confirmed_candidate_rank: int | None = None,
    matching_policy_id: str | None = None,
    matching_policy_version: int | None = None,
    materialization_policy_id: str | None = None,
    materialization_policy_version: int | None = None,
    planning_command_id: InvestigationCommandId | None = None,
    investigation_plan_id: InvestigationPlanId | None = None,
    planned_capability_count: int | None = None,
    planned_connector_option_count: int | None = None,
    planning_policy_id: str | None = None,
    planning_policy_version: int | None = None,
    planning_maximum_estimated_cost_kind_code: str | None = None,
    planning_maximum_estimated_cost: Money | None = None,
    collection_command_id: InvestigationCommandId | None = None,
    collection_run_id: CollectionRunId | None = None,
    collection_operation_count: int | None = None,
    collection_activation_policy_id: str | None = None,
    collection_activation_policy_version: int | None = None,
    collection_maximum_estimated_cost_kind_code: str | None = None,
    collection_maximum_estimated_cost: Money | None = None,
) -> AuditEvent:
    """Build one minimal event using only trusted context and closed codes."""

    if not isinstance(action, AuditActionCode):
        raise TypeError("action must be an AuditActionCode")
    if reason is not None and not isinstance(reason, AuditReasonCode):
        raise TypeError("reason must be an AuditReasonCode or None")
    if outcome is not AuditOutcome.SUCCESS and reason is None:
        raise ValueError("Denied and failed audit events require a reason code.")
    return AuditEvent(
        id=AuditEventId.new(),
        workspace_id=actor.workspace_id,
        actor_user_id=actor.user_id,
        action_code=action.value,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        reason_code=reason.value if reason is not None else None,
        correlation_id=actor.correlation_id,
        occurred_at=occurred_at,
        command_id=command_id,
        policy_id=policy_id,
        policy_version=policy_version,
        candidate_count=candidate_count,
        top_classification_code=(
            top_classification.value if top_classification is not None else None
        ),
        confirmation_command_id=confirmation_command_id,
        entity_resolution_decision_id=entity_resolution_decision_id,
        confirmed_company_id=confirmed_company_id,
        confirmed_candidate_batch_id=confirmed_candidate_batch_id,
        confirmed_candidate_id=confirmed_candidate_id,
        confirmation_reason_code=(
            confirmation_reason.value if confirmation_reason is not None else None
        ),
        confirmed_candidate_classification_code=(
            confirmed_candidate_classification.value
            if confirmed_candidate_classification is not None
            else None
        ),
        confirmed_candidate_rank=confirmed_candidate_rank,
        matching_policy_id=matching_policy_id,
        matching_policy_version=matching_policy_version,
        materialization_policy_id=materialization_policy_id,
        materialization_policy_version=materialization_policy_version,
        planning_command_id=planning_command_id,
        investigation_plan_id=investigation_plan_id,
        planned_capability_count=planned_capability_count,
        planned_connector_option_count=planned_connector_option_count,
        planning_policy_id=planning_policy_id,
        planning_policy_version=planning_policy_version,
        planning_maximum_estimated_cost_kind_code=(planning_maximum_estimated_cost_kind_code),
        planning_maximum_estimated_cost=planning_maximum_estimated_cost,
        collection_command_id=collection_command_id,
        collection_run_id=collection_run_id,
        collection_operation_count=collection_operation_count,
        collection_activation_policy_id=collection_activation_policy_id,
        collection_activation_policy_version=collection_activation_policy_version,
        collection_maximum_estimated_cost_kind_code=(collection_maximum_estimated_cost_kind_code),
        collection_maximum_estimated_cost=collection_maximum_estimated_cost,
    )


def append_audit_event(
    unit_of_work: UnitOfWork,
    *,
    actor: ActorContext,
    action: AuditActionCode,
    resource_type: AuditResourceType,
    resource_id: AuditResourceId | None,
    outcome: AuditOutcome,
    reason: AuditReasonCode | None,
    occurred_at: datetime,
    command_id: InvestigationCommandId | None = None,
    policy_id: str | None = None,
    policy_version: int | None = None,
    candidate_count: int | None = None,
    top_classification: MatchClassification | None = None,
    confirmation_command_id: InvestigationCommandId | None = None,
    entity_resolution_decision_id: EntityResolutionDecisionId | None = None,
    confirmed_company_id: CompanyId | None = None,
    confirmed_candidate_batch_id: EntityCandidateBatchId | None = None,
    confirmed_candidate_id: EntityCandidateId | None = None,
    confirmation_reason: EntityConfirmationReason | None = None,
    confirmed_candidate_classification: MatchClassification | None = None,
    confirmed_candidate_rank: int | None = None,
    matching_policy_id: str | None = None,
    matching_policy_version: int | None = None,
    materialization_policy_id: str | None = None,
    materialization_policy_version: int | None = None,
    planning_command_id: InvestigationCommandId | None = None,
    investigation_plan_id: InvestigationPlanId | None = None,
    planned_capability_count: int | None = None,
    planned_connector_option_count: int | None = None,
    planning_policy_id: str | None = None,
    planning_policy_version: int | None = None,
    planning_maximum_estimated_cost_kind_code: str | None = None,
    planning_maximum_estimated_cost: Money | None = None,
    collection_command_id: InvestigationCommandId | None = None,
    collection_run_id: CollectionRunId | None = None,
    collection_operation_count: int | None = None,
    collection_activation_policy_id: str | None = None,
    collection_activation_policy_version: int | None = None,
    collection_maximum_estimated_cost_kind_code: str | None = None,
    collection_maximum_estimated_cost: Money | None = None,
) -> AuditEvent:
    """Append an event to the caller's active transaction without committing it."""

    event = build_audit_event(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        reason=reason,
        occurred_at=occurred_at,
        command_id=command_id,
        policy_id=policy_id,
        policy_version=policy_version,
        candidate_count=candidate_count,
        top_classification=top_classification,
        confirmation_command_id=confirmation_command_id,
        entity_resolution_decision_id=entity_resolution_decision_id,
        confirmed_company_id=confirmed_company_id,
        confirmed_candidate_batch_id=confirmed_candidate_batch_id,
        confirmed_candidate_id=confirmed_candidate_id,
        confirmation_reason=confirmation_reason,
        confirmed_candidate_classification=confirmed_candidate_classification,
        confirmed_candidate_rank=confirmed_candidate_rank,
        matching_policy_id=matching_policy_id,
        matching_policy_version=matching_policy_version,
        materialization_policy_id=materialization_policy_id,
        materialization_policy_version=materialization_policy_version,
        planning_command_id=planning_command_id,
        investigation_plan_id=investigation_plan_id,
        planned_capability_count=planned_capability_count,
        planned_connector_option_count=planned_connector_option_count,
        planning_policy_id=planning_policy_id,
        planning_policy_version=planning_policy_version,
        planning_maximum_estimated_cost_kind_code=(planning_maximum_estimated_cost_kind_code),
        planning_maximum_estimated_cost=planning_maximum_estimated_cost,
        collection_command_id=collection_command_id,
        collection_run_id=collection_run_id,
        collection_operation_count=collection_operation_count,
        collection_activation_policy_id=collection_activation_policy_id,
        collection_activation_policy_version=collection_activation_policy_version,
        collection_maximum_estimated_cost_kind_code=(collection_maximum_estimated_cost_kind_code),
        collection_maximum_estimated_cost=collection_maximum_estimated_cost,
    )
    unit_of_work.audit_events.add(event)
    return event


def commit_standalone_outcome(
    unit_of_work: UnitOfWork,
    *,
    actor: ActorContext,
    action: AuditActionCode,
    resource_type: AuditResourceType,
    resource_id: AuditResourceId | None,
    outcome: AuditOutcome,
    reason: AuditReasonCode,
    occurred_at: datetime,
) -> bool:
    """Persist a denial/failure without replacing the original application error."""

    try:
        append_audit_event(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            reason=reason,
            occurred_at=occurred_at,
        )
        unit_of_work.commit()
    except PersistenceError:
        return False
    return True


__all__ = [
    "AuditActionCode",
    "AuditReasonCode",
    "append_audit_event",
    "build_audit_event",
    "commit_standalone_outcome",
]
