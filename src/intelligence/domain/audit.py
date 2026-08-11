"""Immutable minimal audit events without arbitrary payloads."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    AuditEventId,
    CollectionRunId,
    CompanyId,
    CorrelationId,
    EntityCandidateBatchId,
    EntityCandidateId,
    EntityResolutionDecisionId,
    InvestigationCommandId,
    InvestigationId,
    InvestigationPlanId,
    MembershipId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.money import Money
from intelligence.domain.time import normalize_utc

ACTION_CODE_MAX_LENGTH = 64
REASON_CODE_MAX_LENGTH = 64
_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_.:-]*", flags=re.ASCII)

type AuditResourceId = WorkspaceId | UserId | MembershipId | CompanyId | InvestigationId


class AuditOutcome(StrEnum):
    """Result recorded for one attempted action."""

    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    FAILURE = "FAILURE"


class AuditResourceType(StrEnum):
    """Initial closed resource vocabulary for audit events."""

    WORKSPACE = "WORKSPACE"
    USER = "USER"
    MEMBERSHIP = "MEMBERSHIP"
    COMPANY = "COMPANY"
    INVESTIGATION = "INVESTIGATION"


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditEvent:
    """Append-only audit snapshot with a minimal redacted shape."""

    id: AuditEventId
    workspace_id: WorkspaceId
    actor_user_id: UserId
    action_code: str
    resource_type: AuditResourceType
    resource_id: AuditResourceId | None
    outcome: AuditOutcome
    reason_code: str | None
    correlation_id: CorrelationId
    occurred_at: datetime
    command_id: InvestigationCommandId | None = None
    policy_id: str | None = None
    policy_version: int | None = None
    candidate_count: int | None = None
    top_classification_code: str | None = None
    confirmation_command_id: InvestigationCommandId | None = None
    entity_resolution_decision_id: EntityResolutionDecisionId | None = None
    confirmed_company_id: CompanyId | None = None
    confirmed_candidate_batch_id: EntityCandidateBatchId | None = None
    confirmed_candidate_id: EntityCandidateId | None = None
    confirmation_reason_code: str | None = None
    confirmed_candidate_classification_code: str | None = None
    confirmed_candidate_rank: int | None = None
    matching_policy_id: str | None = None
    matching_policy_version: int | None = None
    materialization_policy_id: str | None = None
    materialization_policy_version: int | None = None
    planning_command_id: InvestigationCommandId | None = None
    investigation_plan_id: InvestigationPlanId | None = None
    planned_capability_count: int | None = None
    planned_connector_option_count: int | None = None
    planning_policy_id: str | None = None
    planning_policy_version: int | None = None
    planning_maximum_estimated_cost_kind_code: str | None = None
    planning_maximum_estimated_cost: Money | None = None
    collection_command_id: InvestigationCommandId | None = None
    collection_run_id: CollectionRunId | None = None
    collection_operation_count: int | None = None
    collection_activation_policy_id: str | None = None
    collection_activation_policy_version: int | None = None
    collection_maximum_estimated_cost_kind_code: str | None = None
    collection_maximum_estimated_cost: Money | None = None

    def __post_init__(self) -> None:
        _validate_types(self)
        action_code = _code(
            self.action_code,
            field_name="AuditEvent action_code",
            maximum_length=ACTION_CODE_MAX_LENGTH,
        )
        reason_code = (
            _code(
                self.reason_code,
                field_name="AuditEvent reason_code",
                maximum_length=REASON_CODE_MAX_LENGTH,
            )
            if self.reason_code is not None
            else None
        )
        occurred_at = normalize_utc(self.occurred_at)

        candidate_metadata = (
            self.command_id,
            self.policy_id,
            self.policy_version,
            self.candidate_count,
            self.top_classification_code,
        )
        if any(value is not None for value in candidate_metadata) and any(
            value is None for value in candidate_metadata
        ):
            raise InvariantViolationError(
                "AuditEvent candidate-review metadata must be complete or absent."
            )
        if self.command_id is not None:
            if self.outcome is not AuditOutcome.SUCCESS or self.resource_type is not (
                AuditResourceType.INVESTIGATION
            ):
                raise InvariantViolationError(
                    "AuditEvent candidate-review metadata is limited to successful investigations."
                )
            if not isinstance(self.policy_id, str):
                raise InvariantViolationError("AuditEvent policy_id must be text.")
            policy_id = _code(
                self.policy_id,
                field_name="AuditEvent policy_id",
                maximum_length=64,
            )
            if (
                isinstance(self.policy_version, bool)
                or not isinstance(self.policy_version, int)
                or self.policy_version < 1
            ):
                raise InvariantViolationError("AuditEvent policy_version must be positive.")
            if (
                isinstance(self.candidate_count, bool)
                or not isinstance(self.candidate_count, int)
                or not 1 <= self.candidate_count <= 100
            ):
                raise InvariantViolationError(
                    "AuditEvent candidate_count must be between 1 and 100."
                )
            if self.top_classification_code not in {"HIGH", "MEDIUM", "LOW", "EXCLUDED"}:
                raise InvariantViolationError("AuditEvent top_classification_code is invalid.")
            object.__setattr__(self, "policy_id", policy_id)

        confirmation_metadata = (
            self.confirmation_command_id,
            self.entity_resolution_decision_id,
            self.confirmed_company_id,
            self.confirmed_candidate_batch_id,
            self.confirmed_candidate_id,
            self.confirmation_reason_code,
            self.confirmed_candidate_classification_code,
            self.confirmed_candidate_rank,
            self.matching_policy_id,
            self.matching_policy_version,
            self.materialization_policy_id,
            self.materialization_policy_version,
        )
        if any(value is not None for value in confirmation_metadata) and any(
            value is None for value in confirmation_metadata
        ):
            raise InvariantViolationError(
                "AuditEvent entity-confirmation metadata must be complete or absent."
            )
        if self.confirmation_command_id is not None:
            if self.outcome is not AuditOutcome.SUCCESS or self.resource_type is not (
                AuditResourceType.INVESTIGATION
            ):
                raise InvariantViolationError(
                    "AuditEvent entity-confirmation metadata is limited to successful "
                    "investigations."
                )
            if self.confirmation_reason_code not in {
                "IDENTIFIERS_REVIEWED",
                "CORPORATE_DATA_REVIEWED",
                "SOURCE_REFERENCE_REVIEWED",
                "MANUAL_OVERRIDE",
            }:
                raise InvariantViolationError("AuditEvent confirmation_reason_code is invalid.")
            if self.confirmed_candidate_classification_code not in {"HIGH", "MEDIUM", "LOW"}:
                raise InvariantViolationError(
                    "AuditEvent confirmed_candidate_classification_code is invalid."
                )
            if (
                isinstance(self.confirmed_candidate_rank, bool)
                or not isinstance(self.confirmed_candidate_rank, int)
                or not 1 <= self.confirmed_candidate_rank <= 100
            ):
                raise InvariantViolationError("AuditEvent confirmed_candidate_rank is invalid.")
            for confirmation_policy_id, confirmation_policy_version in (
                (self.matching_policy_id, self.matching_policy_version),
                (self.materialization_policy_id, self.materialization_policy_version),
            ):
                if not isinstance(confirmation_policy_id, str):
                    raise InvariantViolationError("AuditEvent confirmation policy ID is invalid.")
                _code(
                    confirmation_policy_id,
                    field_name="AuditEvent policy ID",
                    maximum_length=64,
                )
                if (
                    isinstance(confirmation_policy_version, bool)
                    or not isinstance(confirmation_policy_version, int)
                    or confirmation_policy_version < 1
                ):
                    raise InvariantViolationError(
                        "AuditEvent confirmation policy version is invalid."
                    )

        planning_metadata = (
            self.planning_command_id,
            self.investigation_plan_id,
            self.planned_capability_count,
            self.planned_connector_option_count,
            self.planning_policy_id,
            self.planning_policy_version,
            self.planning_maximum_estimated_cost_kind_code,
        )
        if any(value is not None for value in planning_metadata) and any(
            value is None for value in planning_metadata
        ):
            raise InvariantViolationError(
                "AuditEvent investigation-planning metadata must be complete or absent."
            )
        if self.planning_command_id is not None:
            if self.outcome is not AuditOutcome.SUCCESS or self.resource_type is not (
                AuditResourceType.INVESTIGATION
            ):
                raise InvariantViolationError(
                    "AuditEvent planning metadata is limited to successful investigations."
                )
            if (
                isinstance(self.planned_capability_count, bool)
                or not isinstance(self.planned_capability_count, int)
                or not 1 <= self.planned_capability_count <= 10
            ):
                raise InvariantViolationError("AuditEvent planning capability count is invalid.")
            if (
                isinstance(self.planned_connector_option_count, bool)
                or not isinstance(self.planned_connector_option_count, int)
                or not 0 <= self.planned_connector_option_count <= 1000
            ):
                raise InvariantViolationError("AuditEvent planning option count is invalid.")
            if not isinstance(self.planning_policy_id, str):
                raise InvariantViolationError("AuditEvent planning policy ID is invalid.")
            _code(
                self.planning_policy_id,
                field_name="AuditEvent planning policy ID",
                maximum_length=64,
            )
            if (
                isinstance(self.planning_policy_version, bool)
                or not isinstance(self.planning_policy_version, int)
                or self.planning_policy_version < 1
            ):
                raise InvariantViolationError("AuditEvent planning policy version is invalid.")
            if self.planning_maximum_estimated_cost_kind_code not in {"KNOWN", "UNKNOWN"}:
                raise InvariantViolationError("AuditEvent planning cost kind is invalid.")
            if (self.planning_maximum_estimated_cost_kind_code == "KNOWN") != (
                self.planning_maximum_estimated_cost is not None
            ):
                raise InvariantViolationError("AuditEvent planning cost metadata is inconsistent.")
            if self.planning_maximum_estimated_cost is not None and (
                not isinstance(self.planning_maximum_estimated_cost, Money)
                or self.planning_maximum_estimated_cost.amount < 0
            ):
                raise InvariantViolationError("AuditEvent planning cost is invalid.")
        elif self.planning_maximum_estimated_cost is not None:
            raise InvariantViolationError("AuditEvent planning cost requires planning metadata.")

        collection_metadata = (
            self.collection_command_id,
            self.collection_run_id,
            self.collection_operation_count,
            self.collection_activation_policy_id,
            self.collection_activation_policy_version,
            self.collection_maximum_estimated_cost_kind_code,
        )
        if any(value is not None for value in collection_metadata) and any(
            value is None for value in collection_metadata
        ):
            raise InvariantViolationError(
                "AuditEvent collection-activation metadata must be complete or absent."
            )
        if self.collection_command_id is not None:
            if self.outcome is not AuditOutcome.SUCCESS or self.resource_type is not (
                AuditResourceType.INVESTIGATION
            ):
                raise InvariantViolationError(
                    "AuditEvent collection metadata is limited to successful investigations."
                )
            if (
                isinstance(self.collection_operation_count, bool)
                or not isinstance(self.collection_operation_count, int)
                or not 1 <= self.collection_operation_count <= 10
            ):
                raise InvariantViolationError("AuditEvent collection operation count is invalid.")
            if not isinstance(self.collection_activation_policy_id, str):
                raise InvariantViolationError("AuditEvent collection policy ID is invalid.")
            _code(
                self.collection_activation_policy_id,
                field_name="AuditEvent collection policy ID",
                maximum_length=64,
            )
            if (
                isinstance(self.collection_activation_policy_version, bool)
                or not isinstance(self.collection_activation_policy_version, int)
                or self.collection_activation_policy_version < 1
            ):
                raise InvariantViolationError("AuditEvent collection policy version is invalid.")
            if self.collection_maximum_estimated_cost_kind_code not in {"KNOWN", "UNKNOWN"}:
                raise InvariantViolationError("AuditEvent collection cost kind is invalid.")
            if (self.collection_maximum_estimated_cost_kind_code == "KNOWN") != (
                self.collection_maximum_estimated_cost is not None
            ):
                raise InvariantViolationError(
                    "AuditEvent collection cost metadata is inconsistent."
                )
            if self.collection_maximum_estimated_cost is not None and (
                not isinstance(self.collection_maximum_estimated_cost, Money)
                or self.collection_maximum_estimated_cost.amount < 0
            ):
                raise InvariantViolationError("AuditEvent collection cost is invalid.")
        elif self.collection_maximum_estimated_cost is not None:
            raise InvariantViolationError(
                "AuditEvent collection cost requires collection metadata."
            )

        object.__setattr__(self, "action_code", action_code)
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "occurred_at", occurred_at)


def _validate_types(event: AuditEvent) -> None:
    if not isinstance(event.id, AuditEventId):
        raise InvariantViolationError("AuditEvent id must be an AuditEventId.")
    if not isinstance(event.workspace_id, WorkspaceId):
        raise InvariantViolationError("AuditEvent workspace_id must be a WorkspaceId.")
    if not isinstance(event.actor_user_id, UserId):
        raise InvariantViolationError("AuditEvent actor_user_id must be a UserId.")
    if not isinstance(event.resource_type, AuditResourceType):
        raise InvariantViolationError("AuditEvent resource_type must be an AuditResourceType.")
    if event.resource_id is not None and not isinstance(
        event.resource_id,
        (WorkspaceId, UserId, MembershipId, CompanyId, InvestigationId),
    ):
        raise InvariantViolationError("AuditEvent resource_id must be a typed resource ID.")
    expected_identifier_types: dict[AuditResourceType, type[AuditResourceId]] = {
        AuditResourceType.WORKSPACE: WorkspaceId,
        AuditResourceType.USER: UserId,
        AuditResourceType.MEMBERSHIP: MembershipId,
        AuditResourceType.COMPANY: CompanyId,
        AuditResourceType.INVESTIGATION: InvestigationId,
    }
    if event.resource_id is not None and not isinstance(
        event.resource_id, expected_identifier_types[event.resource_type]
    ):
        raise InvariantViolationError("AuditEvent resource_id must match its resource_type.")
    if not isinstance(event.outcome, AuditOutcome):
        raise InvariantViolationError("AuditEvent outcome must be an AuditOutcome.")
    if not isinstance(event.correlation_id, CorrelationId):
        raise InvariantViolationError("AuditEvent correlation_id must be a CorrelationId.")
    if event.command_id is not None and not isinstance(event.command_id, InvestigationCommandId):
        raise InvariantViolationError("AuditEvent command_id must be an InvestigationCommandId.")
    confirmation_ids = (
        (event.confirmation_command_id, InvestigationCommandId),
        (event.entity_resolution_decision_id, EntityResolutionDecisionId),
        (event.confirmed_company_id, CompanyId),
        (event.confirmed_candidate_batch_id, EntityCandidateBatchId),
        (event.confirmed_candidate_id, EntityCandidateId),
    )
    for value, expected_type in confirmation_ids:
        if value is not None and not isinstance(value, expected_type):
            raise InvariantViolationError("AuditEvent confirmation identifier is invalid.")
    planning_ids = (
        (event.planning_command_id, InvestigationCommandId),
        (event.investigation_plan_id, InvestigationPlanId),
    )
    for planning_value, planning_type in planning_ids:
        if planning_value is not None and not isinstance(planning_value, planning_type):
            raise InvariantViolationError("AuditEvent planning identifier is invalid.")
    collection_ids = (
        (event.collection_command_id, InvestigationCommandId),
        (event.collection_run_id, CollectionRunId),
    )
    for collection_value, collection_type in collection_ids:
        if collection_value is not None and not isinstance(collection_value, collection_type):
            raise InvariantViolationError("AuditEvent collection identifier is invalid.")


def _code(value: str, *, field_name: str, maximum_length: int) -> str:
    if not isinstance(value, str):
        raise InvariantViolationError(f"{field_name} must be text.")
    canonical = value.strip().upper()
    if not canonical:
        raise InvariantViolationError(f"{field_name} cannot be empty.")
    if len(canonical) > maximum_length:
        raise InvariantViolationError(f"{field_name} cannot exceed {maximum_length} characters.")
    if _CODE_PATTERN.fullmatch(canonical) is None:
        raise InvariantViolationError(f"{field_name} has an invalid format.")
    return canonical


__all__ = [
    "ACTION_CODE_MAX_LENGTH",
    "REASON_CODE_MAX_LENGTH",
    "AuditEvent",
    "AuditOutcome",
    "AuditResourceId",
    "AuditResourceType",
]
