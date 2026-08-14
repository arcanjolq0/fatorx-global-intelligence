"""Pure mappings between domain snapshots and relational values."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import cast
from uuid import UUID

from intelligence.application.collection_execution import (
    CollectionExecutionOwnership,
    CollectionExecutionResultRecord,
)
from intelligence.application.entity_candidate_review import (
    CandidateReviewDecision,
    EntityCandidateBatchRecord,
    EntityCandidateDimensionRecord,
    EntityCandidateRecord,
)
from intelligence.application.entity_confirmation import (
    EntityConfirmationReason,
    EntityResolutionDecisionRecord,
    EntityResolutionDecisionType,
)
from intelligence.application.errors import PersistenceDataError
from intelligence.application.investigation_lifecycle import (
    InvestigationCancellationReason,
    InvestigationCommandDigest,
    InvestigationCommandType,
    InvestigationTransitionRecord,
)
from intelligence.connectors.context import LocaleTag
from intelligence.connectors.enums import (
    ConnectorAccessType,
    ConnectorCapability,
    ConnectorCoverageKind,
    ConnectorErrorCode,
    ConnectorOperation,
    ConnectorOutcomeStatus,
    ConnectorWarningCode,
    UsageCostKind,
)
from intelligence.connectors.errors import ConnectorContractError
from intelligence.connectors.execution.contracts import (
    ConnectorExecutionControlCode,
    ConnectorExecutionIdempotencyStatus,
)
from intelligence.connectors.identifiers import ConnectorId, SourceId
from intelligence.connectors.versions import SemanticVersion, SourcePolicyVersion
from intelligence.domain.audit import AuditEvent, AuditOutcome, AuditResourceId, AuditResourceType
from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.errors import DomainError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    AuditEventId,
    CollectionOperationId,
    CollectionRunId,
    CompanyId,
    CorrelationId,
    EntityCandidateBatchId,
    EntityCandidateId,
    EntityResolutionDecisionId,
    InvestigationCommandId,
    InvestigationId,
    InvestigationPlanId,
    InvestigationTransitionId,
    MembershipId,
    PlannedCapabilityId,
    PlannedConnectorOptionId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.identities import (
    EmailAddress,
    MembershipRole,
    MembershipStatus,
    UserAccount,
    UserAccountStatus,
    WorkspaceMembership,
)
from intelligence.domain.investigation_inputs import IdentificationInput
from intelligence.domain.investigations import Investigation, InvestigationState
from intelligence.domain.money import CurrencyCode, Money
from intelligence.domain.workspaces import Workspace, WorkspaceStatus
from intelligence.entity_resolution.contracts import (
    CandidateIdentitySnapshot,
    CandidateOriginSnapshot,
)
from intelligence.entity_resolution.matching import DimensionScore
from intelligence.entity_resolution.policy import (
    MatchClassification,
    MatchDimension,
    MatchExplanationCode,
    MatchPolicy,
)
from intelligence.orchestration.collection_activation import (
    CollectionOperation,
    CollectionOperationStatus,
    CollectionRun,
    CollectionRunStatus,
)
from intelligence.orchestration.planning import (
    EstimatedCostKind,
    InvestigationPlan,
    InvestigationPlanStatus,
    PlannedCapability,
    PlannedCapabilityStatus,
    PlannedConnectorOption,
    PlanningReason,
)

RelationalValues = Mapping[str, object]


def workspace_to_values(workspace: Workspace) -> dict[str, object]:
    """Map a workspace snapshot to values accepted by the Core table."""

    return {
        "id": workspace.id.value,
        "name": workspace.name,
        "status": workspace.status.value,
        "retention_policy_version": workspace.retention_policy_version,
        "created_at": workspace.created_at,
        "updated_at": workspace.updated_at,
    }


def workspace_from_values(values: RelationalValues) -> Workspace:
    """Reconstitute a workspace while validating every persisted value."""

    try:
        return Workspace(
            id=WorkspaceId(_required(values, "id", UUID)),
            name=_required(values, "name", str),
            status=_enum(values, "status", WorkspaceStatus),
            retention_policy_version=_required(values, "retention_policy_version", str),
            created_at=_required_datetime(values, "created_at"),
            updated_at=_required_datetime(values, "updated_at"),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted Workspace data is invalid.") from error


def company_to_values(company: Company) -> dict[str, object]:
    """Map a company snapshot to values accepted by the Core table."""

    return {
        "id": company.id.value,
        "workspace_id": company.workspace_id.value,
        "legal_name": company.legal_name,
        "trade_name": company.trade_name,
        "country_code": company.country_code.value,
        "legal_form": company.legal_form,
        "status": company.status.value,
        "incorporated_on": company.incorporated_on,
        "dissolved_on": company.dissolved_on,
        "official_domain": company.official_domain,
        "created_at": company.created_at,
        "updated_at": company.updated_at,
    }


def company_from_values(values: RelationalValues) -> Company:
    """Reconstitute a company while validating every persisted value."""

    try:
        return Company(
            id=CompanyId(_required(values, "id", UUID)),
            workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
            legal_name=_required(values, "legal_name", str),
            trade_name=_optional(values, "trade_name", str),
            country_code=CountryCode(_required(values, "country_code", str)),
            legal_form=_optional(values, "legal_form", str),
            status=_enum(values, "status", CompanyStatus),
            incorporated_on=_optional_date(values, "incorporated_on"),
            dissolved_on=_optional_date(values, "dissolved_on"),
            official_domain=_optional(values, "official_domain", str),
            created_at=_required_datetime(values, "created_at"),
            updated_at=_required_datetime(values, "updated_at"),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted Company data is invalid.") from error


def investigation_to_values(investigation: Investigation) -> dict[str, object]:
    """Map an investigation snapshot to values accepted by the Core table."""

    budget_amount: Decimal | None = None
    budget_currency: str | None = None
    if investigation.budget is not None:
        budget_amount = investigation.budget.amount
        budget_currency = investigation.budget.currency.value

    input_values = investigation_input_to_values(investigation.identification_input)
    return {
        "id": investigation.id.value,
        "workspace_id": investigation.workspace_id.value,
        "requested_by": investigation.requested_by.value,
        "profile_code": investigation.profile_code,
        "country_code": investigation.country_code.value,
        "state": investigation.state.value,
        "state_version": investigation.state_version,
        **input_values,
        "active_candidate_batch_id": (
            investigation.active_candidate_batch_id.value
            if investigation.active_candidate_batch_id is not None
            else None
        ),
        "confirmed_company_id": (
            investigation.confirmed_company_id.value
            if investigation.confirmed_company_id is not None
            else None
        ),
        "budget_amount": budget_amount,
        "budget_currency": budget_currency,
        "deadline_at": investigation.deadline_at,
        "started_at": investigation.started_at,
        "completed_at": investigation.completed_at,
        "created_at": investigation.created_at,
    }


def investigation_input_to_values(
    identification_input: IdentificationInput | None,
) -> dict[str, object]:
    """Map the versioned input to a JSONB object plus integrity metadata."""

    if identification_input is None:
        return {
            "input_snapshot": None,
            "input_schema_version": None,
            "input_digest": None,
        }
    canonical = identification_input.to_canonical_json()
    return {
        "input_snapshot": json.loads(canonical),
        "input_schema_version": identification_input.schema_version,
        "input_digest": identification_input.digest,
    }


def investigation_lifecycle_to_values(investigation: Investigation) -> dict[str, object]:
    """Map only lifecycle-owned fields for compare-and-swap updates."""

    return {
        "state": investigation.state.value,
        "state_version": investigation.state_version,
        "started_at": investigation.started_at,
        "completed_at": investigation.completed_at,
        **investigation_input_to_values(investigation.identification_input),
        "active_candidate_batch_id": (
            investigation.active_candidate_batch_id.value
            if investigation.active_candidate_batch_id is not None
            else None
        ),
        "confirmed_company_id": (
            investigation.confirmed_company_id.value
            if investigation.confirmed_company_id is not None
            else None
        ),
    }


def investigation_from_values(values: RelationalValues) -> Investigation:
    """Reconstitute any valid persisted state through the domain contract."""

    try:
        confirmed_company_uuid = _optional(values, "confirmed_company_id", UUID)
        budget_amount = _optional(values, "budget_amount", Decimal)
        budget_currency = _optional(values, "budget_currency", str)
        if (budget_amount is None) != (budget_currency is None):
            raise PersistenceDataError("Persisted Investigation budget data is incomplete.")
        budget = (
            Money(budget_amount, CurrencyCode(budget_currency))
            if budget_amount is not None and budget_currency is not None
            else None
        )
        input_snapshot = _optional_json_object(values, "input_snapshot")
        input_schema_version = _optional_integer(values, "input_schema_version")
        input_digest = _optional(values, "input_digest", str)
        active_candidate_batch_uuid = _optional(values, "active_candidate_batch_id", UUID)
        if (
            len(
                {
                    input_snapshot is None,
                    input_schema_version is None,
                    input_digest is None,
                }
            )
            != 1
        ):
            raise PersistenceDataError(
                "Persisted Investigation input snapshot metadata is incomplete."
            )
        identification_input: IdentificationInput | None = None
        if input_snapshot is not None:
            serialized_input = json.dumps(
                input_snapshot,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            identification_input = IdentificationInput.from_canonical_json(serialized_input)
            if (
                input_schema_version != identification_input.schema_version
                or input_digest != identification_input.digest
            ):
                raise PersistenceDataError(
                    "Persisted Investigation input snapshot integrity metadata is invalid."
                )

        return Investigation.reconstitute(
            id=InvestigationId(_required(values, "id", UUID)),
            workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
            requested_by=UserId(_required(values, "requested_by", UUID)),
            profile_code=_required(values, "profile_code", str),
            country_code=CountryCode(_required(values, "country_code", str)),
            state=_enum(values, "state", InvestigationState),
            state_version=_required_integer(values, "state_version"),
            confirmed_company_id=(
                CompanyId(confirmed_company_uuid) if confirmed_company_uuid is not None else None
            ),
            budget=budget,
            deadline_at=_optional_datetime(values, "deadline_at"),
            started_at=_optional_datetime(values, "started_at"),
            completed_at=_optional_datetime(values, "completed_at"),
            created_at=_required_datetime(values, "created_at"),
            identification_input=identification_input,
            active_candidate_batch_id=(
                EntityCandidateBatchId(active_candidate_batch_uuid)
                if active_candidate_batch_uuid is not None
                else None
            ),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted Investigation data is invalid.") from error


def user_account_to_values(user: UserAccount) -> dict[str, object]:
    """Map an internal identity snapshot to relational values."""

    return {
        "id": user.id.value,
        "email": user.email.value,
        "display_name": user.display_name,
        "status": user.status.value,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def user_account_from_values(values: RelationalValues) -> UserAccount:
    """Reconstitute an internal identity from validated relational values."""

    try:
        return UserAccount(
            id=UserId(_required(values, "id", UUID)),
            email=EmailAddress(_required(values, "email", str)),
            display_name=_required(values, "display_name", str),
            status=_enum(values, "status", UserAccountStatus),
            created_at=_required_datetime(values, "created_at"),
            updated_at=_required_datetime(values, "updated_at"),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted UserAccount data is invalid.") from error


def workspace_membership_to_values(
    membership: WorkspaceMembership,
) -> dict[str, object]:
    """Map a membership snapshot to relational values."""

    return {
        "id": membership.id.value,
        "workspace_id": membership.workspace_id.value,
        "user_id": membership.user_id.value,
        "role": membership.role.value,
        "status": membership.status.value,
        "created_at": membership.created_at,
        "updated_at": membership.updated_at,
        "deactivated_at": membership.deactivated_at,
    }


def workspace_membership_from_values(values: RelationalValues) -> WorkspaceMembership:
    """Reconstitute a membership snapshot from relational values."""

    try:
        return WorkspaceMembership(
            id=MembershipId(_required(values, "id", UUID)),
            workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
            user_id=UserId(_required(values, "user_id", UUID)),
            role=_enum(values, "role", MembershipRole),
            status=_enum(values, "status", MembershipStatus),
            created_at=_required_datetime(values, "created_at"),
            updated_at=_required_datetime(values, "updated_at"),
            deactivated_at=_optional_datetime(values, "deactivated_at"),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted WorkspaceMembership data is invalid.") from error


def audit_event_to_values(event: AuditEvent) -> dict[str, object]:
    """Map an append-only audit event to its minimal relational representation."""

    return {
        "id": event.id.value,
        "workspace_id": event.workspace_id.value,
        "actor_user_id": event.actor_user_id.value,
        "action_code": event.action_code,
        "resource_type": event.resource_type.value,
        "resource_id": event.resource_id.value if event.resource_id is not None else None,
        "outcome": event.outcome.value,
        "reason_code": event.reason_code,
        "correlation_id": event.correlation_id.value,
        "occurred_at": event.occurred_at,
        "command_id": event.command_id.value if event.command_id is not None else None,
        "policy_id": event.policy_id,
        "policy_version": event.policy_version,
        "candidate_count": event.candidate_count,
        "top_classification": event.top_classification_code,
        "confirmation_command_id": (
            event.confirmation_command_id.value
            if event.confirmation_command_id is not None
            else None
        ),
        "entity_resolution_decision_id": (
            event.entity_resolution_decision_id.value
            if event.entity_resolution_decision_id is not None
            else None
        ),
        "confirmed_company_id": (
            event.confirmed_company_id.value if event.confirmed_company_id is not None else None
        ),
        "confirmed_candidate_batch_id": (
            event.confirmed_candidate_batch_id.value
            if event.confirmed_candidate_batch_id is not None
            else None
        ),
        "confirmed_candidate_id": (
            event.confirmed_candidate_id.value if event.confirmed_candidate_id is not None else None
        ),
        "confirmation_reason_code": event.confirmation_reason_code,
        "confirmed_candidate_classification": event.confirmed_candidate_classification_code,
        "confirmed_candidate_rank": event.confirmed_candidate_rank,
        "matching_policy_id": event.matching_policy_id,
        "matching_policy_version": event.matching_policy_version,
        "materialization_policy_id": event.materialization_policy_id,
        "materialization_policy_version": event.materialization_policy_version,
        "planning_command_id": (
            event.planning_command_id.value if event.planning_command_id is not None else None
        ),
        "investigation_plan_id": (
            event.investigation_plan_id.value if event.investigation_plan_id is not None else None
        ),
        "planned_capability_count": event.planned_capability_count,
        "planned_connector_option_count": event.planned_connector_option_count,
        "planning_policy_id": event.planning_policy_id,
        "planning_policy_version": event.planning_policy_version,
        "planning_maximum_estimated_cost_kind": (event.planning_maximum_estimated_cost_kind_code),
        "planning_maximum_estimated_cost_amount": (
            event.planning_maximum_estimated_cost.amount
            if event.planning_maximum_estimated_cost is not None
            else None
        ),
        "planning_maximum_estimated_cost_currency": (
            event.planning_maximum_estimated_cost.currency.value
            if event.planning_maximum_estimated_cost is not None
            else None
        ),
        "collection_command_id": (
            event.collection_command_id.value if event.collection_command_id is not None else None
        ),
        "collection_run_id": (
            event.collection_run_id.value if event.collection_run_id is not None else None
        ),
        "collection_operation_count": event.collection_operation_count,
        "collection_activation_policy_id": event.collection_activation_policy_id,
        "collection_activation_policy_version": event.collection_activation_policy_version,
        "collection_maximum_estimated_cost_kind": (
            event.collection_maximum_estimated_cost_kind_code
        ),
        "collection_maximum_estimated_cost_amount": (
            event.collection_maximum_estimated_cost.amount
            if event.collection_maximum_estimated_cost is not None
            else None
        ),
        "collection_maximum_estimated_cost_currency": (
            event.collection_maximum_estimated_cost.currency.value
            if event.collection_maximum_estimated_cost is not None
            else None
        ),
    }


def audit_event_from_values(values: RelationalValues) -> AuditEvent:
    """Reconstitute an audit event and its strongly typed resource ID."""

    try:
        resource_type = _enum(values, "resource_type", AuditResourceType)
        resource_uuid = _optional(values, "resource_id", UUID)
        return AuditEvent(
            id=AuditEventId(_required(values, "id", UUID)),
            workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
            actor_user_id=UserId(_required(values, "actor_user_id", UUID)),
            action_code=_required(values, "action_code", str),
            resource_type=resource_type,
            resource_id=(
                _audit_resource_id(resource_type, resource_uuid)
                if resource_uuid is not None
                else None
            ),
            outcome=_enum(values, "outcome", AuditOutcome),
            reason_code=_optional(values, "reason_code", str),
            correlation_id=CorrelationId(_required(values, "correlation_id", UUID)),
            occurred_at=_required_datetime(values, "occurred_at"),
            command_id=(
                InvestigationCommandId(command_uuid)
                if (command_uuid := _optional(values, "command_id", UUID)) is not None
                else None
            ),
            policy_id=_optional(values, "policy_id", str),
            policy_version=_optional_integer(values, "policy_version"),
            candidate_count=_optional_integer(values, "candidate_count"),
            top_classification_code=_optional(values, "top_classification", str),
            confirmation_command_id=(
                InvestigationCommandId(confirmation_command_uuid)
                if (confirmation_command_uuid := _optional(values, "confirmation_command_id", UUID))
                is not None
                else None
            ),
            entity_resolution_decision_id=(
                EntityResolutionDecisionId(decision_uuid)
                if (decision_uuid := _optional(values, "entity_resolution_decision_id", UUID))
                is not None
                else None
            ),
            confirmed_company_id=(
                CompanyId(company_uuid)
                if (company_uuid := _optional(values, "confirmed_company_id", UUID)) is not None
                else None
            ),
            confirmed_candidate_batch_id=(
                EntityCandidateBatchId(confirmed_batch_uuid)
                if (confirmed_batch_uuid := _optional(values, "confirmed_candidate_batch_id", UUID))
                is not None
                else None
            ),
            confirmed_candidate_id=(
                EntityCandidateId(confirmed_candidate_uuid)
                if (confirmed_candidate_uuid := _optional(values, "confirmed_candidate_id", UUID))
                is not None
                else None
            ),
            confirmation_reason_code=_optional(values, "confirmation_reason_code", str),
            confirmed_candidate_classification_code=_optional(
                values, "confirmed_candidate_classification", str
            ),
            confirmed_candidate_rank=_optional_integer(values, "confirmed_candidate_rank"),
            matching_policy_id=_optional(values, "matching_policy_id", str),
            matching_policy_version=_optional_integer(values, "matching_policy_version"),
            materialization_policy_id=_optional(values, "materialization_policy_id", str),
            materialization_policy_version=_optional_integer(
                values, "materialization_policy_version"
            ),
            planning_command_id=(
                InvestigationCommandId(planning_command_uuid)
                if (planning_command_uuid := _optional(values, "planning_command_id", UUID))
                is not None
                else None
            ),
            investigation_plan_id=(
                InvestigationPlanId(plan_uuid)
                if (plan_uuid := _optional(values, "investigation_plan_id", UUID)) is not None
                else None
            ),
            planned_capability_count=_optional_integer(values, "planned_capability_count"),
            planned_connector_option_count=_optional_integer(
                values, "planned_connector_option_count"
            ),
            planning_policy_id=_optional(values, "planning_policy_id", str),
            planning_policy_version=_optional_integer(values, "planning_policy_version"),
            planning_maximum_estimated_cost_kind_code=_optional(
                values, "planning_maximum_estimated_cost_kind", str
            ),
            planning_maximum_estimated_cost=_money_from_columns(
                values,
                amount_field="planning_maximum_estimated_cost_amount",
                currency_field="planning_maximum_estimated_cost_currency",
            ),
            collection_command_id=(
                InvestigationCommandId(collection_command_uuid)
                if (collection_command_uuid := _optional(values, "collection_command_id", UUID))
                is not None
                else None
            ),
            collection_run_id=(
                CollectionRunId(collection_run_uuid)
                if (collection_run_uuid := _optional(values, "collection_run_id", UUID)) is not None
                else None
            ),
            collection_operation_count=_optional_integer(values, "collection_operation_count"),
            collection_activation_policy_id=_optional(
                values, "collection_activation_policy_id", str
            ),
            collection_activation_policy_version=_optional_integer(
                values, "collection_activation_policy_version"
            ),
            collection_maximum_estimated_cost_kind_code=_optional(
                values, "collection_maximum_estimated_cost_kind", str
            ),
            collection_maximum_estimated_cost=_money_from_columns(
                values,
                amount_field="collection_maximum_estimated_cost_amount",
                currency_field="collection_maximum_estimated_cost_currency",
            ),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted AuditEvent data is invalid.") from error


def investigation_transition_to_values(
    record: InvestigationTransitionRecord,
) -> dict[str, object]:
    """Map an append-only lifecycle transition record to relational values."""

    return {
        "id": record.id.value,
        "workspace_id": record.workspace_id.value,
        "investigation_id": record.investigation_id.value,
        "command_id": record.command_id.value,
        "command_type": record.command_type.value,
        "state_before": record.state_before.value,
        "version_before": record.version_before,
        "state_after": record.state_after.value,
        "version_after": record.version_after,
        "actor_user_id": record.actor_user_id.value,
        "reason_code": record.reason.value if record.reason is not None else None,
        "occurred_at": record.occurred_at,
        "command_digest": record.command_digest.value,
        "correlation_id": record.correlation_id.value,
        "candidate_batch_id": (
            record.candidate_batch_id.value if record.candidate_batch_id is not None else None
        ),
        "candidate_count": record.candidate_count,
        "top_classification": (
            record.top_classification.value if record.top_classification is not None else None
        ),
        "policy_id": record.policy_id,
        "policy_version": record.policy_version,
        "confirmation_decision_id": (
            record.confirmation_decision_id.value
            if record.confirmation_decision_id is not None
            else None
        ),
        "confirmed_company_id": (
            record.confirmed_company_id.value if record.confirmed_company_id is not None else None
        ),
        "confirmed_candidate_batch_id": (
            record.confirmed_candidate_batch_id.value
            if record.confirmed_candidate_batch_id is not None
            else None
        ),
        "confirmed_candidate_id": (
            record.confirmed_candidate_id.value
            if record.confirmed_candidate_id is not None
            else None
        ),
        "confirmation_reason_code": record.confirmation_reason_code,
        "confirmed_candidate_classification": (
            record.confirmed_candidate_classification.value
            if record.confirmed_candidate_classification is not None
            else None
        ),
        "confirmed_candidate_rank": record.confirmed_candidate_rank,
        "matching_policy_id": record.matching_policy_id,
        "matching_policy_version": record.matching_policy_version,
        "materialization_policy_id": record.materialization_policy_id,
        "materialization_policy_version": record.materialization_policy_version,
        "collection_run_id": (
            record.collection_run_id.value if record.collection_run_id is not None else None
        ),
        "collection_company_id": (
            record.collection_company_id.value if record.collection_company_id is not None else None
        ),
        "collection_plan_id": (
            record.collection_plan_id.value if record.collection_plan_id is not None else None
        ),
        "collection_operation_count": record.collection_operation_count,
        "collection_activation_policy_id": record.collection_activation_policy_id,
        "collection_activation_policy_version": record.collection_activation_policy_version,
    }


def investigation_transition_from_values(
    values: RelationalValues,
) -> InvestigationTransitionRecord:
    """Reconstitute and validate a durable lifecycle transition record."""

    try:
        reason_code = _optional(values, "reason_code", str)
        return InvestigationTransitionRecord(
            id=InvestigationTransitionId(_required(values, "id", UUID)),
            workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
            investigation_id=InvestigationId(_required(values, "investigation_id", UUID)),
            command_id=InvestigationCommandId(_required(values, "command_id", UUID)),
            command_type=_enum(values, "command_type", InvestigationCommandType),
            state_before=_enum(values, "state_before", InvestigationState),
            version_before=_required_integer(values, "version_before"),
            state_after=_enum(values, "state_after", InvestigationState),
            version_after=_required_integer(values, "version_after"),
            actor_user_id=UserId(_required(values, "actor_user_id", UUID)),
            reason=(
                InvestigationCancellationReason(reason_code) if reason_code is not None else None
            ),
            occurred_at=_required_datetime(values, "occurred_at"),
            command_digest=InvestigationCommandDigest(_required(values, "command_digest", str)),
            correlation_id=CorrelationId(_required(values, "correlation_id", UUID)),
            candidate_batch_id=(
                EntityCandidateBatchId(batch_uuid)
                if (batch_uuid := _optional(values, "candidate_batch_id", UUID)) is not None
                else None
            ),
            candidate_count=_optional_integer(values, "candidate_count"),
            top_classification=(
                MatchClassification(classification)
                if (classification := _optional(values, "top_classification", str)) is not None
                else None
            ),
            policy_id=_optional(values, "policy_id", str),
            policy_version=_optional_integer(values, "policy_version"),
            confirmation_decision_id=(
                EntityResolutionDecisionId(confirmation_decision_uuid)
                if (
                    confirmation_decision_uuid := _optional(
                        values, "confirmation_decision_id", UUID
                    )
                )
                is not None
                else None
            ),
            confirmed_company_id=(
                CompanyId(confirmed_company_uuid)
                if (confirmed_company_uuid := _optional(values, "confirmed_company_id", UUID))
                is not None
                else None
            ),
            confirmed_candidate_batch_id=(
                EntityCandidateBatchId(confirmed_batch_uuid)
                if (confirmed_batch_uuid := _optional(values, "confirmed_candidate_batch_id", UUID))
                is not None
                else None
            ),
            confirmed_candidate_id=(
                EntityCandidateId(confirmed_candidate_uuid)
                if (confirmed_candidate_uuid := _optional(values, "confirmed_candidate_id", UUID))
                is not None
                else None
            ),
            confirmation_reason_code=_optional(values, "confirmation_reason_code", str),
            confirmed_candidate_classification=(
                MatchClassification(confirmed_classification)
                if (
                    confirmed_classification := _optional(
                        values, "confirmed_candidate_classification", str
                    )
                )
                is not None
                else None
            ),
            confirmed_candidate_rank=_optional_integer(values, "confirmed_candidate_rank"),
            matching_policy_id=_optional(values, "matching_policy_id", str),
            matching_policy_version=_optional_integer(values, "matching_policy_version"),
            materialization_policy_id=_optional(values, "materialization_policy_id", str),
            materialization_policy_version=_optional_integer(
                values, "materialization_policy_version"
            ),
            collection_run_id=(
                CollectionRunId(collection_run_uuid)
                if (collection_run_uuid := _optional(values, "collection_run_id", UUID)) is not None
                else None
            ),
            collection_company_id=(
                CompanyId(collection_company_uuid)
                if (collection_company_uuid := _optional(values, "collection_company_id", UUID))
                is not None
                else None
            ),
            collection_plan_id=(
                InvestigationPlanId(collection_plan_uuid)
                if (collection_plan_uuid := _optional(values, "collection_plan_id", UUID))
                is not None
                else None
            ),
            collection_operation_count=_optional_integer(values, "collection_operation_count"),
            collection_activation_policy_id=_optional(
                values, "collection_activation_policy_id", str
            ),
            collection_activation_policy_version=_optional_integer(
                values, "collection_activation_policy_version"
            ),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted InvestigationTransition data is invalid.") from error


def collection_run_to_values(run: CollectionRun) -> dict[str, object]:
    """Map one immutable collection manifest header."""

    return {
        "id": run.id.value,
        "workspace_id": run.workspace_id.value,
        "investigation_id": run.investigation_id.value,
        "company_id": run.company_id.value,
        "plan_id": run.plan_id.value,
        "run_version": run.run_version,
        "status": run.status.value,
        "activation_policy_id": run.activation_policy_id,
        "activation_policy_version": run.activation_policy_version,
        "activation_policy_snapshot": run.activation_policy_snapshot,
        "activation_policy_digest": run.activation_policy_digest,
        "plan_digest": run.plan_digest,
        "company_snapshot_digest": run.company_snapshot_digest,
        "budget_amount": run.budget.amount if run.budget is not None else None,
        "budget_currency": run.budget.currency.value if run.budget is not None else None,
        "deadline_at": run.deadline_at,
        "maximum_estimated_cost_kind": run.maximum_estimated_cost_kind.value,
        "maximum_estimated_cost_amount": (
            run.maximum_estimated_cost.amount if run.maximum_estimated_cost is not None else None
        ),
        "maximum_estimated_cost_currency": (
            run.maximum_estimated_cost.currency.value
            if run.maximum_estimated_cost is not None
            else None
        ),
        "command_id": run.command_id.value,
        "command_digest": run.command_digest,
        "created_by": run.created_by.value,
        "created_at": run.created_at,
        "investigation_state_version": run.investigation_state_version,
        "run_digest": run.run_digest,
        "schema_version": run.schema_version,
    }


def collection_operation_to_values(operation: CollectionOperation) -> dict[str, object]:
    """Map one immutable prepared operation without operational execution state."""

    return {
        "id": operation.id.value,
        "collection_run_id": operation.collection_run_id.value,
        "workspace_id": operation.workspace_id.value,
        "investigation_id": operation.investigation_id.value,
        "plan_id": operation.plan_id.value,
        "capability": operation.capability.value,
        "priority": operation.priority,
        "planned_capability_id": operation.planned_capability_id.value,
        "planned_connector_option_id": operation.planned_connector_option_id.value,
        "connector_id": operation.connector_id.value,
        "connector_version": str(operation.connector_version),
        "contract_version": str(operation.contract_version),
        "source_id": operation.source_id.value,
        "connector_operations": [item.value for item in operation.connector_operations],
        "coverage_kind": operation.coverage_kind.value,
        "access_type": operation.access_type.value,
        "estimated_cost_kind": operation.estimated_cost_kind.value,
        "estimated_cost_amount": (
            operation.estimated_cost.amount if operation.estimated_cost is not None else None
        ),
        "estimated_cost_currency": (
            operation.estimated_cost.currency.value
            if operation.estimated_cost is not None
            else None
        ),
        "estimated_duration_seconds": operation.estimated_duration_seconds,
        "status": operation.status.value,
        "attempt": operation.attempt,
        "operation_digest": operation.operation_digest,
        "operation_version": operation.operation_version,
        "schema_version": operation.schema_version,
    }


def collection_dependency_to_values(
    operation: CollectionOperation,
    dependency_id: CollectionOperationId,
    dependency_order: int,
) -> dict[str, object]:
    """Map one dependency edge scoped to its immutable run."""

    return {
        "collection_run_id": operation.collection_run_id.value,
        "operation_id": operation.id.value,
        "depends_on_operation_id": dependency_id.value,
        "dependency_order": dependency_order,
        "workspace_id": operation.workspace_id.value,
        "investigation_id": operation.investigation_id.value,
        "plan_id": operation.plan_id.value,
    }


def collection_run_from_values(
    run_values: RelationalValues,
    operation_values: tuple[RelationalValues, ...],
    dependency_values: tuple[RelationalValues, ...],
) -> CollectionRun:
    """Reconstitute a collection manifest and fail closed on every child edge."""

    try:
        run_id = CollectionRunId(_required(run_values, "id", UUID))
        workspace_id = WorkspaceId(_required(run_values, "workspace_id", UUID))
        investigation_id = InvestigationId(_required(run_values, "investigation_id", UUID))
        plan_id = InvestigationPlanId(_required(run_values, "plan_id", UUID))
        operation_ids = {_required(item, "id", UUID) for item in operation_values}
        dependencies_by_operation: dict[UUID, list[RelationalValues]] = {}
        for edge in dependency_values:
            edge_run_id = _required(edge, "collection_run_id", UUID)
            operation_id = _required(edge, "operation_id", UUID)
            depends_on_id = _required(edge, "depends_on_operation_id", UUID)
            if (
                edge_run_id != run_id.value
                or operation_id not in operation_ids
                or depends_on_id not in operation_ids
            ):
                raise PersistenceDataError("Persisted collection dependency scope is invalid.")
            dependencies_by_operation.setdefault(operation_id, []).append(edge)
        operations = tuple(
            _collection_operation_from_values(
                values,
                tuple(dependencies_by_operation.get(_required(values, "id", UUID), [])),
                run_id=run_id,
                workspace_id=workspace_id,
                investigation_id=investigation_id,
                plan_id=plan_id,
            )
            for values in operation_values
        )
        return CollectionRun(
            id=run_id,
            workspace_id=workspace_id,
            investigation_id=investigation_id,
            company_id=CompanyId(_required(run_values, "company_id", UUID)),
            plan_id=plan_id,
            run_version=_required_integer(run_values, "run_version"),
            status=_enum(run_values, "status", CollectionRunStatus),
            operations=tuple(
                sorted(operations, key=lambda item: (item.priority, item.capability.value))
            ),
            activation_policy_id=_required(run_values, "activation_policy_id", str),
            activation_policy_version=_required_integer(run_values, "activation_policy_version"),
            activation_policy_snapshot=_required(run_values, "activation_policy_snapshot", str),
            activation_policy_digest=_required(run_values, "activation_policy_digest", str),
            plan_digest=_required(run_values, "plan_digest", str),
            company_snapshot_digest=_required(run_values, "company_snapshot_digest", str),
            budget=_money_from_columns(
                run_values, amount_field="budget_amount", currency_field="budget_currency"
            ),
            deadline_at=_optional_datetime(run_values, "deadline_at"),
            maximum_estimated_cost_kind=_enum(
                run_values, "maximum_estimated_cost_kind", EstimatedCostKind
            ),
            maximum_estimated_cost=_money_from_columns(
                run_values,
                amount_field="maximum_estimated_cost_amount",
                currency_field="maximum_estimated_cost_currency",
            ),
            command_id=InvestigationCommandId(_required(run_values, "command_id", UUID)),
            command_digest=_required(run_values, "command_digest", str),
            created_by=UserId(_required(run_values, "created_by", UUID)),
            created_at=_required_datetime(run_values, "created_at"),
            investigation_state_version=_required_integer(
                run_values, "investigation_state_version"
            ),
            run_digest=_required(run_values, "run_digest", str),
            schema_version=_required_integer(run_values, "schema_version"),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted collection run is invalid.") from error


def _collection_operation_from_values(
    values: RelationalValues,
    dependencies: tuple[RelationalValues, ...],
    *,
    run_id: CollectionRunId,
    workspace_id: WorkspaceId,
    investigation_id: InvestigationId,
    plan_id: InvestigationPlanId,
) -> CollectionOperation:
    if (
        CollectionRunId(_required(values, "collection_run_id", UUID)) != run_id
        or WorkspaceId(_required(values, "workspace_id", UUID)) != workspace_id
        or InvestigationId(_required(values, "investigation_id", UUID)) != investigation_id
        or InvestigationPlanId(_required(values, "plan_id", UUID)) != plan_id
    ):
        raise PersistenceDataError("Persisted collection operation scope is invalid.")
    raw_operations = _required(values, "connector_operations", list)
    if any(not isinstance(item, str) for item in raw_operations):
        raise PersistenceDataError("Persisted collection connector operations are invalid.")
    ordered_dependencies = sorted(
        dependencies, key=lambda item: _required_integer(item, "dependency_order")
    )
    if [_required_integer(item, "dependency_order") for item in ordered_dependencies] != list(
        range(1, len(ordered_dependencies) + 1)
    ):
        raise PersistenceDataError("Persisted collection dependency order is invalid.")
    return CollectionOperation(
        id=CollectionOperationId(_required(values, "id", UUID)),
        collection_run_id=run_id,
        workspace_id=workspace_id,
        investigation_id=investigation_id,
        plan_id=plan_id,
        capability=_enum(values, "capability", ConnectorCapability),
        priority=_required_integer(values, "priority"),
        dependency_operation_ids=tuple(
            CollectionOperationId(_required(item, "depends_on_operation_id", UUID))
            for item in ordered_dependencies
        ),
        planned_capability_id=PlannedCapabilityId(_required(values, "planned_capability_id", UUID)),
        planned_connector_option_id=PlannedConnectorOptionId(
            _required(values, "planned_connector_option_id", UUID)
        ),
        connector_id=ConnectorId(_required(values, "connector_id", str)),
        connector_version=SemanticVersion.parse(_required(values, "connector_version", str)),
        contract_version=SemanticVersion.parse(_required(values, "contract_version", str)),
        source_id=SourceId(_required(values, "source_id", str)),
        connector_operations=tuple(ConnectorOperation(cast(str, item)) for item in raw_operations),
        coverage_kind=_enum(values, "coverage_kind", ConnectorCoverageKind),
        access_type=_enum(values, "access_type", ConnectorAccessType),
        estimated_cost_kind=_enum(values, "estimated_cost_kind", EstimatedCostKind),
        estimated_cost=_money_from_columns(
            values,
            amount_field="estimated_cost_amount",
            currency_field="estimated_cost_currency",
        ),
        estimated_duration_seconds=_required_integer(values, "estimated_duration_seconds"),
        status=_enum(values, "status", CollectionOperationStatus),
        attempt=_required_integer(values, "attempt"),
        operation_digest=_required(values, "operation_digest", str),
        operation_version=_required_integer(values, "operation_version"),
        schema_version=_required_integer(values, "schema_version"),
    )


def entity_candidate_batch_to_values(record: EntityCandidateBatchRecord) -> dict[str, object]:
    """Map one immutable batch header to relational values."""

    return {
        "id": record.id.value,
        "workspace_id": record.workspace_id.value,
        "investigation_id": record.investigation_id.value,
        "batch_version": record.batch_version,
        "input_digest": record.input_digest,
        "policy_id": record.policy_id,
        "policy_version": record.policy_version,
        "policy_digest": record.policy_digest,
        "policy_snapshot": json.loads(record.policy_snapshot),
        "command_id": record.command_id.value,
        "created_by": record.created_by.value,
        "created_at": record.created_at,
        "submission_digest": record.submission_digest,
        "evaluation_digest": record.evaluation_digest,
    }


def entity_candidate_to_values(record: EntityCandidateRecord) -> dict[str, object]:
    """Map one neutral candidate snapshot and ranked result."""

    return {
        "id": record.id.value,
        "workspace_id": record.workspace_id.value,
        "investigation_id": record.investigation_id.value,
        "batch_id": record.batch_id.value,
        "candidate_key": record.candidate_key,
        "rank": record.rank,
        "total_score": record.total_score,
        "coverage": record.coverage,
        "classification": record.classification.value,
        "hard_conflict": record.hard_conflict,
        "identity_snapshot": json.loads(record.identity.to_canonical_json()),
        "identity_schema_version": record.identity.schema_version,
        "identity_digest": record.identity.digest,
        "origin_snapshot": json.loads(record.origin.to_canonical_json()),
        "origin_schema_version": record.origin.schema_version,
        "origin_digest": record.origin.digest,
        "evaluation_digest": record.evaluation_digest,
        "decision": record.decision.value,
        "decision_by": record.decision_by.value if record.decision_by is not None else None,
        "decided_at": record.decided_at,
    }


def entity_candidate_dimension_to_values(
    record: EntityCandidateDimensionRecord,
) -> dict[str, object]:
    """Map one independently explainable dimensional score."""

    return {
        "workspace_id": record.workspace_id.value,
        "investigation_id": record.investigation_id.value,
        "batch_id": record.batch_id.value,
        "candidate_id": record.candidate_id.value,
        "dimension": record.score.dimension.value,
        "score": record.score.score,
        "weight": record.score.weight,
        "contribution": record.score.contribution,
        "available": record.score.available,
        "hard_conflict": record.score.hard_conflict,
        "explanation_code": record.score.explanation.value,
    }


def entity_resolution_decision_to_values(
    record: EntityResolutionDecisionRecord,
) -> dict[str, object]:
    """Map one append-only human entity-resolution decision."""

    return {
        "id": record.id.value,
        "workspace_id": record.workspace_id.value,
        "investigation_id": record.investigation_id.value,
        "command_id": record.command_id.value,
        "command_digest": record.command_digest.value,
        "candidate_batch_id": record.candidate_batch_id.value,
        "candidate_id": record.candidate_id.value,
        "company_id": record.company_id.value,
        "reviewed_by": record.reviewed_by.value,
        "review_reason": record.review_reason.value,
        "decided_at": record.decided_at,
        "decision_type": record.decision_type.value,
        "decision_schema_version": record.decision_schema_version,
        "candidate_rank": record.candidate_rank,
        "candidate_classification": record.candidate_classification.value,
        "candidate_total_score": record.candidate_total_score,
        "candidate_coverage": record.candidate_coverage,
        "candidate_identity_digest": record.candidate_identity_digest,
        "candidate_evaluation_digest": record.candidate_evaluation_digest,
        "batch_submission_digest": record.batch_submission_digest,
        "batch_evaluation_digest": record.batch_evaluation_digest,
        "matching_policy_id": record.matching_policy_id,
        "matching_policy_version": record.matching_policy_version,
        "matching_policy_digest": record.matching_policy_digest,
        "input_digest": record.input_digest,
        "materialization_policy_id": record.materialization_policy_id,
        "materialization_policy_version": record.materialization_policy_version,
        "materialization_policy_digest": record.materialization_policy_digest,
        "materialization_policy_snapshot": json.loads(record.materialization_policy_snapshot),
        "company_snapshot_digest": record.company_snapshot_digest,
        "decision_digest": record.decision_digest,
    }


def entity_resolution_decision_from_values(
    values: RelationalValues,
) -> EntityResolutionDecisionRecord:
    """Reconstitute and validate the decision's closed persisted representation."""

    try:
        return EntityResolutionDecisionRecord(
            id=EntityResolutionDecisionId(_required(values, "id", UUID)),
            workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
            investigation_id=InvestigationId(_required(values, "investigation_id", UUID)),
            command_id=InvestigationCommandId(_required(values, "command_id", UUID)),
            command_digest=InvestigationCommandDigest(_required(values, "command_digest", str)),
            candidate_batch_id=EntityCandidateBatchId(
                _required(values, "candidate_batch_id", UUID)
            ),
            candidate_id=EntityCandidateId(_required(values, "candidate_id", UUID)),
            company_id=CompanyId(_required(values, "company_id", UUID)),
            reviewed_by=UserId(_required(values, "reviewed_by", UUID)),
            review_reason=_enum(values, "review_reason", EntityConfirmationReason),
            decided_at=_required_datetime(values, "decided_at"),
            decision_type=_enum(values, "decision_type", EntityResolutionDecisionType),
            decision_schema_version=_required_integer(values, "decision_schema_version"),
            candidate_rank=_required_integer(values, "candidate_rank"),
            candidate_classification=_enum(values, "candidate_classification", MatchClassification),
            candidate_total_score=_required_integer(values, "candidate_total_score"),
            candidate_coverage=_required_integer(values, "candidate_coverage"),
            candidate_identity_digest=_required(values, "candidate_identity_digest", str),
            candidate_evaluation_digest=_required(values, "candidate_evaluation_digest", str),
            batch_submission_digest=_required(values, "batch_submission_digest", str),
            batch_evaluation_digest=_required(values, "batch_evaluation_digest", str),
            matching_policy_id=_required(values, "matching_policy_id", str),
            matching_policy_version=_required_integer(values, "matching_policy_version"),
            matching_policy_digest=_required(values, "matching_policy_digest", str),
            input_digest=_required(values, "input_digest", str),
            materialization_policy_id=_required(values, "materialization_policy_id", str),
            materialization_policy_version=_required_integer(
                values, "materialization_policy_version"
            ),
            materialization_policy_digest=_required(values, "materialization_policy_digest", str),
            materialization_policy_snapshot=_canonical_json_object(
                values, "materialization_policy_snapshot"
            ),
            company_snapshot_digest=_required(values, "company_snapshot_digest", str),
            decision_digest=_required(values, "decision_digest", str),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted entity resolution decision is invalid.") from error


def collection_execution_ownership_to_values(
    ownership: CollectionExecutionOwnership,
) -> dict[str, object]:
    return {
        "command_id": ownership.command_id.value,
        "workspace_id": ownership.workspace_id.value,
        "investigation_id": ownership.investigation_id.value,
        "collection_run_id": ownership.collection_run_id.value,
        "collection_operation_id": ownership.collection_operation_id.value,
        "command_digest": ownership.command_digest,
        "actor_user_id": ownership.actor_user_id.value,
        "connector_id": ownership.connector_id.value,
        "connector_version": str(ownership.connector_version),
        "contract_version": str(ownership.contract_version),
        "source_id": ownership.source_id.value,
        "source_policy_version": ownership.source_policy_version.value,
        "accepted_locales": [item.value for item in ownership.accepted_locales],
        "execution_policy_snapshot": ownership.execution_policy_snapshot,
        "execution_policy_digest": ownership.execution_policy_digest,
        "started_at": ownership.started_at,
        "ownership_digest": ownership.ownership_digest,
        "schema_version": ownership.schema_version,
    }


def collection_execution_ownership_from_values(
    values: RelationalValues,
) -> CollectionExecutionOwnership:
    raw_locales = _read(values, "accepted_locales")
    if not isinstance(raw_locales, (list, tuple)) or any(
        not isinstance(item, str) for item in raw_locales
    ):
        raise PersistenceDataError("Persisted collection execution locales are invalid.")
    try:
        return CollectionExecutionOwnership(
            command_id=InvestigationCommandId(_required(values, "command_id", UUID)),
            workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
            investigation_id=InvestigationId(_required(values, "investigation_id", UUID)),
            collection_run_id=CollectionRunId(_required(values, "collection_run_id", UUID)),
            collection_operation_id=CollectionOperationId(
                _required(values, "collection_operation_id", UUID)
            ),
            command_digest=_required(values, "command_digest", str),
            actor_user_id=UserId(_required(values, "actor_user_id", UUID)),
            connector_id=ConnectorId(_required(values, "connector_id", str)),
            connector_version=SemanticVersion.parse(_required(values, "connector_version", str)),
            contract_version=SemanticVersion.parse(_required(values, "contract_version", str)),
            source_id=SourceId(_required(values, "source_id", str)),
            source_policy_version=SourcePolicyVersion(
                _required(values, "source_policy_version", str)
            ),
            accepted_locales=tuple(LocaleTag(cast(str, item)) for item in raw_locales),
            execution_policy_snapshot=_required(values, "execution_policy_snapshot", str),
            execution_policy_digest=_required(values, "execution_policy_digest", str),
            started_at=_required_datetime(values, "started_at"),
            ownership_digest=_required(values, "ownership_digest", str),
            schema_version=_required_integer(values, "schema_version"),
        )
    except (DomainError, ConnectorContractError, ValueError) as error:
        raise PersistenceDataError(
            "Persisted collection execution ownership is invalid."
        ) from error


def collection_execution_result_to_values(
    result: CollectionExecutionResultRecord,
) -> dict[str, object]:
    return {
        "command_id": result.command_id.value,
        "workspace_id": result.workspace_id.value,
        "investigation_id": result.investigation_id.value,
        "collection_run_id": result.collection_run_id.value,
        "collection_operation_id": result.collection_operation_id.value,
        "command_digest": result.command_digest,
        "outcome_status": result.outcome_status.value,
        "error_code": result.error_code.value if result.error_code is not None else None,
        "warning_codes": [item.value for item in result.warning_codes],
        "attempts_started": result.attempts_started,
        "usage_calls": result.usage_calls,
        "usage_bytes_received": result.usage_bytes_received,
        "usage_duration_microseconds": result.usage_duration_microseconds,
        "usage_cost_amount": (result.usage_cost.amount if result.usage_cost is not None else None),
        "usage_cost_currency": (
            result.usage_cost.currency.value if result.usage_cost is not None else None
        ),
        "usage_cost_kind": (
            result.usage_cost_kind.value if result.usage_cost_kind is not None else None
        ),
        "request_fingerprint": result.request_fingerprint,
        "execution_digest": result.execution_digest,
        "idempotency_status": result.idempotency_status.value,
        "control_code": result.control_code.value if result.control_code is not None else None,
        "completed_at": result.completed_at,
        "result_digest": result.result_digest,
        "schema_version": result.schema_version,
    }


def collection_execution_result_from_values(
    values: RelationalValues,
) -> CollectionExecutionResultRecord:
    raw_warnings = _read(values, "warning_codes")
    if not isinstance(raw_warnings, (list, tuple)) or any(
        not isinstance(item, str) for item in raw_warnings
    ):
        raise PersistenceDataError("Persisted collection execution warnings are invalid.")
    try:
        return CollectionExecutionResultRecord(
            command_id=InvestigationCommandId(_required(values, "command_id", UUID)),
            workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
            investigation_id=InvestigationId(_required(values, "investigation_id", UUID)),
            collection_run_id=CollectionRunId(_required(values, "collection_run_id", UUID)),
            collection_operation_id=CollectionOperationId(
                _required(values, "collection_operation_id", UUID)
            ),
            command_digest=_required(values, "command_digest", str),
            outcome_status=_enum(values, "outcome_status", ConnectorOutcomeStatus),
            error_code=(
                ConnectorErrorCode(value)
                if (value := _optional(values, "error_code", str)) is not None
                else None
            ),
            warning_codes=tuple(ConnectorWarningCode(cast(str, item)) for item in raw_warnings),
            attempts_started=_required_integer(values, "attempts_started"),
            usage_calls=_required_integer(values, "usage_calls"),
            usage_bytes_received=_required_integer(values, "usage_bytes_received"),
            usage_duration_microseconds=_required_integer(values, "usage_duration_microseconds"),
            usage_cost=_money_from_columns(
                values,
                amount_field="usage_cost_amount",
                currency_field="usage_cost_currency",
            ),
            usage_cost_kind=(
                UsageCostKind(value)
                if (value := _optional(values, "usage_cost_kind", str)) is not None
                else None
            ),
            request_fingerprint=_required(values, "request_fingerprint", str),
            execution_digest=_required(values, "execution_digest", str),
            idempotency_status=_enum(
                values, "idempotency_status", ConnectorExecutionIdempotencyStatus
            ),
            control_code=(
                ConnectorExecutionControlCode(value)
                if (value := _optional(values, "control_code", str)) is not None
                else None
            ),
            completed_at=_required_datetime(values, "completed_at"),
            result_digest=_required(values, "result_digest", str),
            schema_version=_required_integer(values, "schema_version"),
        )
    except (DomainError, ValueError) as error:
        raise PersistenceDataError("Persisted collection execution result is invalid.") from error


def investigation_plan_to_values(plan: InvestigationPlan) -> dict[str, object]:
    """Map the immutable plan record that also carries its command ledger fields."""

    return {
        "id": plan.id.value,
        "workspace_id": plan.workspace_id.value,
        "investigation_id": plan.investigation_id.value,
        "company_id": plan.company_id.value,
        "profile_code": plan.profile_code,
        "country_code": plan.country_code,
        "plan_version": plan.plan_version,
        "status": plan.status.value,
        "budget_amount": plan.budget.amount if plan.budget is not None else None,
        "budget_currency": plan.budget.currency.value if plan.budget is not None else None,
        "deadline_at": plan.deadline_at,
        "maximum_estimated_cost_kind": plan.maximum_estimated_cost_kind.value,
        "maximum_estimated_cost_amount": (
            plan.maximum_estimated_cost.amount if plan.maximum_estimated_cost is not None else None
        ),
        "maximum_estimated_cost_currency": (
            plan.maximum_estimated_cost.currency.value
            if plan.maximum_estimated_cost is not None
            else None
        ),
        "planning_policy_id": plan.planning_policy_id,
        "planning_policy_version": plan.planning_policy_version,
        "planning_policy_snapshot": plan.planning_policy_snapshot,
        "planning_policy_digest": plan.planning_policy_digest,
        "input_digest": plan.input_digest,
        "company_snapshot_digest": plan.company_snapshot_digest,
        "plan_digest": plan.plan_digest,
        "command_id": plan.command_id.value,
        "command_digest": plan.command_digest,
        "created_by": plan.created_by.value,
        "created_at": plan.created_at,
        "investigation_state_version": plan.investigation_state_version,
        "schema_version": plan.schema_version,
    }


def planned_capability_to_values(
    capability: PlannedCapability,
    *,
    plan: InvestigationPlan,
) -> dict[str, object]:
    """Map one capability with its closed dependency snapshot."""

    return {
        "id": capability.id.value,
        "plan_id": plan.id.value,
        "workspace_id": plan.workspace_id.value,
        "investigation_id": plan.investigation_id.value,
        "capability": capability.capability.value,
        "required": capability.required,
        "priority": capability.priority,
        "reason": capability.reason.value,
        "dependencies": [item.value for item in capability.dependencies],
        "estimated_cost_kind": capability.estimated_cost_kind.value,
        "estimated_cost_amount": (
            capability.estimated_cost.amount if capability.estimated_cost is not None else None
        ),
        "estimated_cost_currency": (
            capability.estimated_cost.currency.value
            if capability.estimated_cost is not None
            else None
        ),
        "estimated_duration_seconds": capability.estimated_duration_seconds,
        "status": capability.status.value,
    }


def planned_connector_option_to_values(
    option: PlannedConnectorOption,
    *,
    plan: InvestigationPlan,
) -> dict[str, object]:
    """Map one statically eligible connector option without credentials or payloads."""

    return {
        "id": option.id.value,
        "planned_capability_id": option.planned_capability_id.value,
        "plan_id": plan.id.value,
        "workspace_id": plan.workspace_id.value,
        "investigation_id": plan.investigation_id.value,
        "connector_id": option.connector_id.value,
        "connector_version": str(option.connector_version),
        "contract_version": str(option.contract_version),
        "source_id": option.source_id.value,
        "coverage_kind": option.coverage_kind.value,
        "access_type": option.access_type.value,
        "operations": [item.value for item in option.operations],
        "eligibility_rank": option.eligibility_rank,
        "estimated_cost_kind": option.estimated_cost_kind.value,
        "estimated_cost_amount": (
            option.estimated_cost.amount if option.estimated_cost is not None else None
        ),
        "estimated_cost_currency": (
            option.estimated_cost.currency.value if option.estimated_cost is not None else None
        ),
        "estimated_duration_seconds": option.estimated_duration_seconds,
    }


def investigation_plan_from_values(
    plan_values: RelationalValues,
    capability_values: tuple[RelationalValues, ...],
    option_values: tuple[RelationalValues, ...],
) -> InvestigationPlan:
    """Reconstitute a complete plan and fail closed on any child divergence."""

    try:
        plan_id = InvestigationPlanId(_required(plan_values, "id", UUID))
        workspace_id = WorkspaceId(_required(plan_values, "workspace_id", UUID))
        investigation_id = InvestigationId(_required(plan_values, "investigation_id", UUID))
        options_by_capability: dict[UUID, list[RelationalValues]] = {}
        for values in option_values:
            options_by_capability.setdefault(
                _required(values, "planned_capability_id", UUID), []
            ).append(values)
        capability_ids = {_required(values, "id", UUID) for values in capability_values}
        if not set(options_by_capability).issubset(capability_ids):
            raise PersistenceDataError("Persisted plan option ownership is invalid.")
        capabilities = tuple(
            _planned_capability_from_values(
                values,
                tuple(options_by_capability.get(_required(values, "id", UUID), [])),
                plan_id=plan_id,
                workspace_id=workspace_id,
                investigation_id=investigation_id,
            )
            for values in capability_values
        )
        return InvestigationPlan(
            id=plan_id,
            workspace_id=workspace_id,
            investigation_id=investigation_id,
            company_id=CompanyId(_required(plan_values, "company_id", UUID)),
            profile_code=_required(plan_values, "profile_code", str),
            country_code=_required(plan_values, "country_code", str),
            plan_version=_required_integer(plan_values, "plan_version"),
            status=_enum(plan_values, "status", InvestigationPlanStatus),
            capabilities=tuple(
                sorted(capabilities, key=lambda item: (item.priority, item.capability.value))
            ),
            budget=_money_from_columns(
                plan_values,
                amount_field="budget_amount",
                currency_field="budget_currency",
            ),
            deadline_at=_optional_datetime(plan_values, "deadline_at"),
            maximum_estimated_cost_kind=_enum(
                plan_values, "maximum_estimated_cost_kind", EstimatedCostKind
            ),
            maximum_estimated_cost=_money_from_columns(
                plan_values,
                amount_field="maximum_estimated_cost_amount",
                currency_field="maximum_estimated_cost_currency",
            ),
            planning_policy_id=_required(plan_values, "planning_policy_id", str),
            planning_policy_version=_required_integer(plan_values, "planning_policy_version"),
            planning_policy_snapshot=_required(plan_values, "planning_policy_snapshot", str),
            planning_policy_digest=_required(plan_values, "planning_policy_digest", str),
            input_digest=_required(plan_values, "input_digest", str),
            company_snapshot_digest=_required(plan_values, "company_snapshot_digest", str),
            plan_digest=_required(plan_values, "plan_digest", str),
            command_id=InvestigationCommandId(_required(plan_values, "command_id", UUID)),
            command_digest=_required(plan_values, "command_digest", str),
            created_by=UserId(_required(plan_values, "created_by", UUID)),
            created_at=_required_datetime(plan_values, "created_at"),
            investigation_state_version=_required_integer(
                plan_values, "investigation_state_version"
            ),
            schema_version=_required_integer(plan_values, "schema_version"),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted investigation plan is invalid.") from error


def _planned_capability_from_values(
    values: RelationalValues,
    options: tuple[RelationalValues, ...],
    *,
    plan_id: InvestigationPlanId,
    workspace_id: WorkspaceId,
    investigation_id: InvestigationId,
) -> PlannedCapability:
    if (
        InvestigationPlanId(_required(values, "plan_id", UUID)) != plan_id
        or WorkspaceId(_required(values, "workspace_id", UUID)) != workspace_id
        or InvestigationId(_required(values, "investigation_id", UUID)) != investigation_id
    ):
        raise PersistenceDataError("Persisted planned capability scope is invalid.")
    capability_id = PlannedCapabilityId(_required(values, "id", UUID))
    connector_options = tuple(
        _planned_connector_option_from_values(
            item,
            capability_id=capability_id,
            plan_id=plan_id,
            workspace_id=workspace_id,
            investigation_id=investigation_id,
        )
        for item in options
    )
    dependency_values = _required(values, "dependencies", list)
    if any(not isinstance(item, str) for item in dependency_values):
        raise PersistenceDataError("Persisted planned capability dependencies are invalid.")
    return PlannedCapability(
        id=capability_id,
        capability=_enum(values, "capability", ConnectorCapability),
        required=_required(values, "required", bool),
        priority=_required_integer(values, "priority"),
        reason=_enum(values, "reason", PlanningReason),
        dependencies=tuple(ConnectorCapability(cast(str, item)) for item in dependency_values),
        connector_options=tuple(sorted(connector_options, key=lambda item: item.eligibility_rank)),
        estimated_cost_kind=_enum(values, "estimated_cost_kind", EstimatedCostKind),
        estimated_cost=_money_from_columns(
            values,
            amount_field="estimated_cost_amount",
            currency_field="estimated_cost_currency",
        ),
        estimated_duration_seconds=_required_integer(values, "estimated_duration_seconds"),
        status=_enum(values, "status", PlannedCapabilityStatus),
    )


def _planned_connector_option_from_values(
    values: RelationalValues,
    *,
    capability_id: PlannedCapabilityId,
    plan_id: InvestigationPlanId,
    workspace_id: WorkspaceId,
    investigation_id: InvestigationId,
) -> PlannedConnectorOption:
    if (
        PlannedCapabilityId(_required(values, "planned_capability_id", UUID)) != capability_id
        or InvestigationPlanId(_required(values, "plan_id", UUID)) != plan_id
        or WorkspaceId(_required(values, "workspace_id", UUID)) != workspace_id
        or InvestigationId(_required(values, "investigation_id", UUID)) != investigation_id
    ):
        raise PersistenceDataError("Persisted planned connector option scope is invalid.")
    operations = _required(values, "operations", list)
    if any(not isinstance(item, str) for item in operations):
        raise PersistenceDataError("Persisted planned connector operations are invalid.")
    return PlannedConnectorOption(
        id=PlannedConnectorOptionId(_required(values, "id", UUID)),
        planned_capability_id=capability_id,
        connector_id=ConnectorId(_required(values, "connector_id", str)),
        connector_version=SemanticVersion.parse(_required(values, "connector_version", str)),
        contract_version=SemanticVersion.parse(_required(values, "contract_version", str)),
        source_id=SourceId(_required(values, "source_id", str)),
        coverage_kind=_enum(values, "coverage_kind", ConnectorCoverageKind),
        access_type=_enum(values, "access_type", ConnectorAccessType),
        operations=tuple(ConnectorOperation(cast(str, item)) for item in operations),
        eligibility_rank=_required_integer(values, "eligibility_rank"),
        estimated_cost_kind=_enum(values, "estimated_cost_kind", EstimatedCostKind),
        estimated_cost=_money_from_columns(
            values,
            amount_field="estimated_cost_amount",
            currency_field="estimated_cost_currency",
        ),
        estimated_duration_seconds=_required_integer(values, "estimated_duration_seconds"),
    )


def entity_candidate_batch_from_values(
    batch_values: RelationalValues,
    candidate_values: tuple[RelationalValues, ...],
    dimension_values: tuple[RelationalValues, ...],
) -> EntityCandidateBatchRecord:
    """Reconstitute a complete closed batch and validate all snapshot digests."""

    try:
        batch_id = EntityCandidateBatchId(_required(batch_values, "id", UUID))
        workspace_id = WorkspaceId(_required(batch_values, "workspace_id", UUID))
        investigation_id = InvestigationId(_required(batch_values, "investigation_id", UUID))
        input_digest = _required(batch_values, "input_digest", str)
        policy_snapshot = _canonical_json_object(batch_values, "policy_snapshot")
        policy = MatchPolicy.from_canonical_json(policy_snapshot)
        dimensions_by_candidate: dict[UUID, list[RelationalValues]] = {}
        for values in dimension_values:
            dimensions_by_candidate.setdefault(_required(values, "candidate_id", UUID), []).append(
                values
            )
        candidate_ids = {_required(values, "id", UUID) for values in candidate_values}
        if set(dimensions_by_candidate) != candidate_ids:
            raise PersistenceDataError("Persisted candidate dimension ownership is invalid.")
        candidates = tuple(
            _entity_candidate_from_values(
                values,
                tuple(dimensions_by_candidate.get(_required(values, "id", UUID), [])),
                policy=policy,
                input_digest=input_digest,
            )
            for values in candidate_values
        )
        return EntityCandidateBatchRecord(
            id=batch_id,
            workspace_id=workspace_id,
            investigation_id=investigation_id,
            batch_version=_required_integer(batch_values, "batch_version"),
            input_digest=input_digest,
            policy_id=_required(batch_values, "policy_id", str),
            policy_version=_required_integer(batch_values, "policy_version"),
            policy_digest=_required(batch_values, "policy_digest", str),
            policy_snapshot=policy_snapshot,
            command_id=InvestigationCommandId(_required(batch_values, "command_id", UUID)),
            created_by=UserId(_required(batch_values, "created_by", UUID)),
            created_at=_required_datetime(batch_values, "created_at"),
            submission_digest=_required(batch_values, "submission_digest", str),
            evaluation_digest=_required(batch_values, "evaluation_digest", str),
            candidates=tuple(sorted(candidates, key=lambda value: value.rank)),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted entity candidate batch is invalid.") from error


def _entity_candidate_from_values(
    values: RelationalValues,
    dimensions: tuple[RelationalValues, ...],
    *,
    policy: MatchPolicy,
    input_digest: str,
) -> EntityCandidateRecord:
    candidate_id = EntityCandidateId(_required(values, "id", UUID))
    workspace_id = WorkspaceId(_required(values, "workspace_id", UUID))
    investigation_id = InvestigationId(_required(values, "investigation_id", UUID))
    batch_id = EntityCandidateBatchId(_required(values, "batch_id", UUID))
    identity = CandidateIdentitySnapshot.from_canonical_json(
        _canonical_json_object(values, "identity_snapshot")
    )
    origin = CandidateOriginSnapshot.from_canonical_json(
        _canonical_json_object(values, "origin_snapshot")
    )
    if identity.schema_version != _required_integer(values, "identity_schema_version") or (
        identity.digest != _required(values, "identity_digest", str)
    ):
        raise PersistenceDataError("Persisted candidate identity integrity is invalid.")
    if origin.schema_version != _required_integer(values, "origin_schema_version") or (
        origin.digest != _required(values, "origin_digest", str)
    ):
        raise PersistenceDataError("Persisted candidate origin integrity is invalid.")
    dimension_records = tuple(
        _entity_candidate_dimension_from_values(
            item,
            workspace_id=workspace_id,
            investigation_id=investigation_id,
            batch_id=batch_id,
            candidate_id=candidate_id,
        )
        for item in dimensions
    )
    return EntityCandidateRecord(
        id=candidate_id,
        workspace_id=workspace_id,
        investigation_id=investigation_id,
        batch_id=batch_id,
        candidate_key=_required(values, "candidate_key", str),
        rank=_required_integer(values, "rank"),
        total_score=_required_integer(values, "total_score"),
        coverage=_required_integer(values, "coverage"),
        classification=_enum(values, "classification", MatchClassification),
        hard_conflict=_required(values, "hard_conflict", bool),
        identity=identity,
        origin=origin,
        evaluation_digest=_required(values, "evaluation_digest", str),
        matching_policy=policy,
        input_digest=input_digest,
        decision=_enum(values, "decision", CandidateReviewDecision),
        decision_by=(
            UserId(decision_user)
            if (decision_user := _optional(values, "decision_by", UUID)) is not None
            else None
        ),
        decided_at=_optional_datetime(values, "decided_at"),
        dimensions=tuple(sorted(dimension_records, key=lambda item: item.score.dimension.value)),
    )


def _entity_candidate_dimension_from_values(
    values: RelationalValues,
    *,
    workspace_id: WorkspaceId,
    investigation_id: InvestigationId,
    batch_id: EntityCandidateBatchId,
    candidate_id: EntityCandidateId,
) -> EntityCandidateDimensionRecord:
    persisted_scope = (
        WorkspaceId(_required(values, "workspace_id", UUID)),
        InvestigationId(_required(values, "investigation_id", UUID)),
        EntityCandidateBatchId(_required(values, "batch_id", UUID)),
        EntityCandidateId(_required(values, "candidate_id", UUID)),
    )
    if persisted_scope != (workspace_id, investigation_id, batch_id, candidate_id):
        raise PersistenceDataError("Persisted candidate dimension scope is invalid.")
    return EntityCandidateDimensionRecord(
        workspace_id=workspace_id,
        investigation_id=investigation_id,
        batch_id=batch_id,
        candidate_id=candidate_id,
        score=DimensionScore(
            dimension=_enum(values, "dimension", MatchDimension),
            score=_required_integer(values, "score"),
            weight=_required_integer(values, "weight"),
            contribution=_required_integer(values, "contribution"),
            available=_required(values, "available", bool),
            hard_conflict=_required(values, "hard_conflict", bool),
            explanation=_enum(values, "explanation_code", MatchExplanationCode),
        ),
    )


def _canonical_json_object(values: RelationalValues, field_name: str) -> str:
    value = _required(values, field_name, dict)
    if any(not isinstance(key, str) for key in value):
        raise PersistenceDataError(f"Persisted field {field_name} has an invalid type.")
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _audit_resource_id(
    resource_type: AuditResourceType,
    resource_uuid: UUID,
) -> AuditResourceId:
    identifier_types: dict[AuditResourceType, type[AuditResourceId]] = {
        AuditResourceType.WORKSPACE: WorkspaceId,
        AuditResourceType.USER: UserId,
        AuditResourceType.MEMBERSHIP: MembershipId,
        AuditResourceType.COMPANY: CompanyId,
        AuditResourceType.INVESTIGATION: InvestigationId,
    }
    return identifier_types[resource_type](resource_uuid)


def _read(values: RelationalValues, field_name: str) -> object:
    try:
        return values[field_name]
    except KeyError as error:
        raise PersistenceDataError(
            f"Persisted data is missing required field {field_name}."
        ) from error


def _required[Value](
    values: RelationalValues,
    field_name: str,
    expected_type: type[Value],
) -> Value:
    value = _read(values, field_name)
    if not isinstance(value, expected_type):
        raise PersistenceDataError(f"Persisted field {field_name} has an invalid type.")
    return value


def _optional[Value](
    values: RelationalValues,
    field_name: str,
    expected_type: type[Value],
) -> Value | None:
    value = _read(values, field_name)
    if value is None:
        return None
    if not isinstance(value, expected_type):
        raise PersistenceDataError(f"Persisted field {field_name} has an invalid type.")
    return value


def _required_integer(values: RelationalValues, field_name: str) -> int:
    value = _read(values, field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PersistenceDataError(f"Persisted field {field_name} has an invalid type.")
    return value


def _optional_integer(values: RelationalValues, field_name: str) -> int | None:
    value = _read(values, field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise PersistenceDataError(f"Persisted field {field_name} has an invalid type.")
    return value


def _optional_json_object(
    values: RelationalValues,
    field_name: str,
) -> dict[str, object] | None:
    value = _read(values, field_name)
    if value is None:
        return None
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise PersistenceDataError(f"Persisted field {field_name} has an invalid type.")
    return cast(dict[str, object], value)


def _required_datetime(values: RelationalValues, field_name: str) -> datetime:
    return _required(values, field_name, datetime)


def _optional_datetime(values: RelationalValues, field_name: str) -> datetime | None:
    return _optional(values, field_name, datetime)


def _optional_date(values: RelationalValues, field_name: str) -> date | None:
    value = _read(values, field_name)
    if value is None:
        return None
    if not isinstance(value, date) or isinstance(value, datetime):
        raise PersistenceDataError(f"Persisted field {field_name} has an invalid type.")
    return value


def _money_from_columns(
    values: RelationalValues,
    *,
    amount_field: str,
    currency_field: str,
) -> Money | None:
    amount = _optional(values, amount_field, Decimal)
    currency = _optional(values, currency_field, str)
    if (amount is None) != (currency is None):
        raise PersistenceDataError("Persisted money columns are incomplete.")
    return Money(amount, CurrencyCode(currency)) if amount is not None and currency else None


def _enum[EnumValue: StrEnum](
    values: RelationalValues,
    field_name: str,
    enum_type: type[EnumValue],
) -> EnumValue:
    return enum_type(_required(values, field_name, str))


__all__ = [
    "RelationalValues",
    "audit_event_from_values",
    "audit_event_to_values",
    "collection_dependency_to_values",
    "collection_execution_ownership_from_values",
    "collection_execution_ownership_to_values",
    "collection_execution_result_from_values",
    "collection_execution_result_to_values",
    "collection_operation_to_values",
    "collection_run_from_values",
    "collection_run_to_values",
    "company_from_values",
    "company_to_values",
    "entity_candidate_batch_from_values",
    "entity_candidate_batch_to_values",
    "entity_candidate_dimension_to_values",
    "entity_candidate_to_values",
    "entity_resolution_decision_from_values",
    "entity_resolution_decision_to_values",
    "investigation_from_values",
    "investigation_input_to_values",
    "investigation_lifecycle_to_values",
    "investigation_plan_from_values",
    "investigation_plan_to_values",
    "investigation_to_values",
    "investigation_transition_from_values",
    "investigation_transition_to_values",
    "planned_capability_to_values",
    "planned_connector_option_to_values",
    "user_account_from_values",
    "user_account_to_values",
    "workspace_from_values",
    "workspace_membership_from_values",
    "workspace_membership_to_values",
    "workspace_to_values",
]
