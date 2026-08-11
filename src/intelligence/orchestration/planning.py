"""Immutable deterministic F4.4 investigation plans and policy V1."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Protocol, Self

from intelligence.connectors.descriptor import ConnectorDescriptor, validate_connector_descriptor
from intelligence.connectors.enums import (
    ConnectorAccessType,
    ConnectorCapability,
    ConnectorCoverageKind,
    ConnectorOperation,
)
from intelligence.connectors.identifiers import ConnectorId, SourceId
from intelligence.connectors.versions import CONNECTOR_CONTRACT_VERSION, SemanticVersion
from intelligence.domain.companies import Company
from intelligence.domain.errors import DomainError, InvariantViolationError
from intelligence.domain.identifiers import (
    CompanyId,
    InvestigationCommandId,
    InvestigationId,
    InvestigationPlanId,
    PlannedCapabilityId,
    PlannedConnectorOptionId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.investigations import Investigation, InvestigationState
from intelligence.domain.money import Money
from intelligence.domain.time import normalize_utc
from intelligence.orchestration.errors import (
    InvalidPlanningDependencyError,
    PlanningBudgetExceededError,
    PlanningDeadlineExceededError,
    RequiredCapabilityUnavailableError,
    UnsupportedPlanningPolicyError,
    UnsupportedPlanningProfileError,
)

PLANNING_POLICY_SCHEMA_VERSION = 1
INVESTIGATION_PLAN_SCHEMA_VERSION = 1
INVESTIGATION_PLAN_VERSION = 1
_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_.:-]{0,63}", flags=re.ASCII)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)
_SUPPORTED_PROFILE = "SUPPLIER_STANDARD"
_PLAN_CONTINUITY_STATES = frozenset(
    {
        InvestigationState.PLANNING,
        InvestigationState.COLLECTING,
        InvestigationState.NORMALIZING,
        InvestigationState.VERIFYING,
        InvestigationState.ANALYZING,
        InvestigationState.WAITING_FOR_REVIEW,
        InvestigationState.COMPLETED,
        InvestigationState.PARTIALLY_COMPLETED,
        InvestigationState.FAILED,
        InvestigationState.CANCELLED,
    }
)


class PlanningConnectorCatalog(Protocol):
    """Read-only admission-time descriptor catalog consumed by planning."""

    def list_descriptors(self) -> tuple[ConnectorDescriptor, ...]: ...


class InvestigationPlanStatus(StrEnum):
    """Closed F4.4 plan state."""

    READY = "READY"


class PlannedCapabilityStatus(StrEnum):
    """Initial outcome of planning one capability."""

    READY = "READY"
    OPTIONAL_UNAVAILABLE = "OPTIONAL_UNAVAILABLE"


class PlanningReason(StrEnum):
    """Closed reasons for including capabilities in policy V1."""

    COMPANY_IDENTITY = "COMPANY_IDENTITY"
    BUSINESS_REGISTRATION = "BUSINESS_REGISTRATION"
    OWNERSHIP_STRUCTURE = "OWNERSHIP_STRUCTURE"
    BUSINESS_CONTACTS = "BUSINESS_CONTACTS"
    FINANCIAL_REVIEW = "FINANCIAL_REVIEW"
    INSOLVENCY_REVIEW = "INSOLVENCY_REVIEW"
    LEGAL_CASE_REVIEW = "LEGAL_CASE_REVIEW"
    CONFIRMED_COMPANY_SANCTIONS = "CONFIRMED_COMPANY_SANCTIONS"
    ADVERSE_MEDIA_REVIEW = "ADVERSE_MEDIA_REVIEW"
    SUPPORTING_DOCUMENTS = "SUPPORTING_DOCUMENTS"


class EstimatedCostKind(StrEnum):
    """Whether a static connector estimate is available."""

    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanningCapabilityRule:
    capability: ConnectorCapability
    required: bool
    priority: int
    reason: PlanningReason
    dependencies: tuple[ConnectorCapability, ...]
    estimated_duration_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.capability, ConnectorCapability):
            raise InvariantViolationError("Planning capability rule must use a closed capability.")
        if not isinstance(self.required, bool):
            raise InvariantViolationError("Planning capability requirement must be boolean.")
        if (
            isinstance(self.priority, bool)
            or not isinstance(self.priority, int)
            or not 1 <= self.priority <= 1000
        ):
            raise InvariantViolationError("Planning capability priority is invalid.")
        if not isinstance(self.reason, PlanningReason):
            raise InvariantViolationError("Planning capability reason is invalid.")
        if (
            not isinstance(self.dependencies, tuple)
            or any(not isinstance(item, ConnectorCapability) for item in self.dependencies)
            or tuple(sorted(set(self.dependencies), key=lambda item: item.value))
            != self.dependencies
            or self.capability in self.dependencies
        ):
            raise InvariantViolationError("Planning capability dependencies are invalid.")
        if (
            isinstance(self.estimated_duration_seconds, bool)
            or not isinstance(self.estimated_duration_seconds, int)
            or not 1 <= self.estimated_duration_seconds <= 2_592_000
        ):
            raise InvariantViolationError("Planning capability duration is invalid.")


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class PlanningPolicy:
    """Closed profile-to-capability policy with a canonical snapshot."""

    policy_id: str
    version: int
    supported_profiles: tuple[str, ...]
    capability_rules: tuple[PlanningCapabilityRule, ...]
    supported_contract_major: int
    schema_version: int = PLANNING_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _code(self.policy_id, "Planning policy ID")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise InvariantViolationError("Planning policy version must be positive.")
        if self.schema_version != PLANNING_POLICY_SCHEMA_VERSION:
            raise InvariantViolationError("Planning policy schema is unsupported.")
        if (
            not isinstance(self.supported_profiles, tuple)
            or not self.supported_profiles
            or tuple(sorted(set(self.supported_profiles))) != self.supported_profiles
            or any(not isinstance(value, str) or not value for value in self.supported_profiles)
        ):
            raise InvariantViolationError("Planning policy profiles are invalid.")
        if (
            not isinstance(self.capability_rules, tuple)
            or not self.capability_rules
            or any(not isinstance(rule, PlanningCapabilityRule) for rule in self.capability_rules)
        ):
            raise InvariantViolationError("Planning policy capability rules are invalid.")
        capabilities = tuple(rule.capability for rule in self.capability_rules)
        priorities = tuple(rule.priority for rule in self.capability_rules)
        if len(set(capabilities)) != len(capabilities) or len(set(priorities)) != len(priorities):
            raise InvariantViolationError("Planning policy capabilities and priorities are unique.")
        if tuple(sorted(self.capability_rules, key=_rule_sort_key)) != self.capability_rules:
            raise InvariantViolationError("Planning policy rules must use canonical ordering.")
        _validate_dependency_graph(self.capability_rules)
        if (
            isinstance(self.supported_contract_major, bool)
            or self.supported_contract_major != CONNECTOR_CONTRACT_VERSION.major
        ):
            raise InvariantViolationError("Planning policy connector contract is unsupported.")

    @property
    def digest(self) -> str:
        return sha256(self.to_canonical_json().encode("utf-8")).hexdigest()

    def to_canonical_json(self) -> str:
        return _canonical_json(
            {
                "capability_rules": [
                    {
                        "capability": rule.capability.value,
                        "dependencies": [value.value for value in rule.dependencies],
                        "estimated_duration_seconds": rule.estimated_duration_seconds,
                        "priority": rule.priority,
                        "reason": rule.reason.value,
                        "required": rule.required,
                    }
                    for rule in self.capability_rules
                ],
                "policy_id": self.policy_id,
                "schema_version": self.schema_version,
                "supported_contract_major": self.supported_contract_major,
                "supported_profiles": list(self.supported_profiles),
                "version": self.version,
            }
        )

    @classmethod
    def from_canonical_json(cls, serialized: str) -> Self:
        if not isinstance(serialized, str):
            raise InvariantViolationError("Persisted planning policy must be canonical JSON text.")
        try:
            raw = json.loads(serialized)
            if not isinstance(raw, dict):
                raise TypeError
            raw_rules = raw["capability_rules"]
            if not isinstance(raw_rules, list):
                raise TypeError
            rules = tuple(
                PlanningCapabilityRule(
                    capability=ConnectorCapability(item["capability"]),
                    required=item["required"],
                    priority=item["priority"],
                    reason=PlanningReason(item["reason"]),
                    dependencies=tuple(
                        ConnectorCapability(value) for value in item["dependencies"]
                    ),
                    estimated_duration_seconds=item["estimated_duration_seconds"],
                )
                for item in raw_rules
                if isinstance(item, dict)
            )
            policy = cls(
                policy_id=raw["policy_id"],
                version=raw["version"],
                supported_profiles=tuple(raw["supported_profiles"]),
                capability_rules=rules,
                supported_contract_major=raw["supported_contract_major"],
                schema_version=raw["schema_version"],
            )
        except (KeyError, TypeError, ValueError, InvariantViolationError) as error:
            raise InvariantViolationError(
                "Persisted planning policy snapshot is invalid."
            ) from error
        if policy.to_canonical_json() != serialized:
            raise InvariantViolationError("Persisted planning policy is not canonical.")
        return policy


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannedConnectorOption:
    id: PlannedConnectorOptionId
    planned_capability_id: PlannedCapabilityId
    connector_id: ConnectorId
    connector_version: SemanticVersion
    contract_version: SemanticVersion
    source_id: SourceId
    coverage_kind: ConnectorCoverageKind
    access_type: ConnectorAccessType
    operations: tuple[ConnectorOperation, ...]
    eligibility_rank: int
    estimated_cost_kind: EstimatedCostKind
    estimated_cost: Money | None
    estimated_duration_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.id, PlannedConnectorOptionId) or not isinstance(
            self.planned_capability_id, PlannedCapabilityId
        ):
            raise InvariantViolationError("Planned connector option identifiers must be typed.")
        expected = (
            (self.connector_id, ConnectorId),
            (self.connector_version, SemanticVersion),
            (self.contract_version, SemanticVersion),
            (self.source_id, SourceId),
            (self.coverage_kind, ConnectorCoverageKind),
            (self.access_type, ConnectorAccessType),
            (self.estimated_cost_kind, EstimatedCostKind),
        )
        if any(not isinstance(value, expected_type) for value, expected_type in expected):
            raise InvariantViolationError("Planned connector option metadata is invalid.")
        if (
            not self.contract_version.is_compatible_with(CONNECTOR_CONTRACT_VERSION)
            or not isinstance(self.operations, tuple)
            or not self.operations
            or tuple(sorted(set(self.operations), key=lambda item: item.value)) != self.operations
        ):
            raise InvariantViolationError("Planned connector option contract is invalid.")
        if (
            isinstance(self.eligibility_rank, bool)
            or not isinstance(self.eligibility_rank, int)
            or self.eligibility_rank < 1
        ):
            raise InvariantViolationError("Planned connector option rank is invalid.")
        _validate_cost(self.estimated_cost_kind, self.estimated_cost, "connector option")
        _duration(self.estimated_duration_seconds, "connector option")


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannedCapability:
    id: PlannedCapabilityId
    capability: ConnectorCapability
    required: bool
    priority: int
    reason: PlanningReason
    dependencies: tuple[ConnectorCapability, ...]
    connector_options: tuple[PlannedConnectorOption, ...]
    estimated_cost_kind: EstimatedCostKind
    estimated_cost: Money | None
    estimated_duration_seconds: int
    status: PlannedCapabilityStatus

    def __post_init__(self) -> None:
        PlanningCapabilityRule(
            capability=self.capability,
            required=self.required,
            priority=self.priority,
            reason=self.reason,
            dependencies=self.dependencies,
            estimated_duration_seconds=self.estimated_duration_seconds,
        )
        if not isinstance(self.id, PlannedCapabilityId):
            raise InvariantViolationError("Planned capability ID must be typed.")
        if not isinstance(self.connector_options, tuple) or any(
            not isinstance(option, PlannedConnectorOption) for option in self.connector_options
        ):
            raise InvariantViolationError("Planned capability options must be typed.")
        if any(option.planned_capability_id != self.id for option in self.connector_options):
            raise InvariantViolationError("Planned connector option references another capability.")
        if tuple(option.eligibility_rank for option in self.connector_options) != tuple(
            range(1, len(self.connector_options) + 1)
        ) or len({option.connector_id for option in self.connector_options}) != len(
            self.connector_options
        ):
            raise InvariantViolationError("Planned connector options have invalid ordering.")
        _validate_cost(self.estimated_cost_kind, self.estimated_cost, "capability")
        if self.required and not self.connector_options:
            raise RequiredCapabilityUnavailableError(
                "A required capability has no eligible connector."
            )
        expected_status = (
            PlannedCapabilityStatus.READY
            if self.connector_options
            else PlannedCapabilityStatus.OPTIONAL_UNAVAILABLE
        )
        if self.status is not expected_status:
            raise InvariantViolationError("Planned capability status is inconsistent.")


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class InvestigationPlan:
    id: InvestigationPlanId
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    company_id: CompanyId
    profile_code: str
    country_code: str
    plan_version: int
    status: InvestigationPlanStatus
    capabilities: tuple[PlannedCapability, ...]
    budget: Money | None
    deadline_at: datetime | None
    maximum_estimated_cost_kind: EstimatedCostKind
    maximum_estimated_cost: Money | None
    planning_policy_id: str
    planning_policy_version: int
    planning_policy_snapshot: str = field(repr=False)
    planning_policy_digest: str
    input_digest: str
    company_snapshot_digest: str
    plan_digest: str
    command_id: InvestigationCommandId
    command_digest: str
    created_by: UserId
    created_at: datetime
    investigation_state_version: int
    schema_version: int = INVESTIGATION_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        typed_ids = (
            (self.id, InvestigationPlanId),
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.company_id, CompanyId),
            (self.command_id, InvestigationCommandId),
            (self.created_by, UserId),
        )
        if any(not isinstance(value, expected) for value, expected in typed_ids):
            raise InvariantViolationError("Investigation plan identifiers must be typed.")
        if not isinstance(self.profile_code, str) or not self.profile_code:
            raise InvariantViolationError("Investigation plan profile is invalid.")
        if not isinstance(self.country_code, str) or len(self.country_code) != 2:
            raise InvariantViolationError("Investigation plan country is invalid.")
        if self.plan_version != INVESTIGATION_PLAN_VERSION or self.schema_version != 1:
            raise InvariantViolationError("Investigation plan version is unsupported.")
        if self.status is not InvestigationPlanStatus.READY:
            raise InvariantViolationError("Investigation plan status is unsupported.")
        if (
            isinstance(self.investigation_state_version, bool)
            or not isinstance(self.investigation_state_version, int)
            or self.investigation_state_version < 1
        ):
            raise InvariantViolationError("Investigation plan state version is invalid.")
        for digest, name in (
            (self.planning_policy_digest, "planning policy"),
            (self.input_digest, "input"),
            (self.company_snapshot_digest, "Company snapshot"),
            (self.plan_digest, "plan"),
            (self.command_digest, "command"),
        ):
            _digest(digest, name)
        try:
            policy = PlanningPolicy.from_canonical_json(self.planning_policy_snapshot)
        except DomainError as error:
            raise InvariantViolationError(
                "Investigation plan policy snapshot is invalid."
            ) from error
        if (
            policy != INVESTIGATION_PLANNING_V1
            or policy.policy_id != self.planning_policy_id
            or policy.version != self.planning_policy_version
            or policy.digest != self.planning_policy_digest
            or self.profile_code not in policy.supported_profiles
        ):
            raise InvariantViolationError("Investigation plan policy reference is inconsistent.")
        if (
            not isinstance(self.capabilities, tuple)
            or tuple(
                sorted(self.capabilities, key=lambda item: (item.priority, item.capability.value))
            )
            != self.capabilities
        ):
            raise InvariantViolationError("Investigation plan capabilities are not canonical.")
        if len(self.capabilities) != len(policy.capability_rules):
            raise InvariantViolationError("Investigation plan capability set is incomplete.")
        for planned, rule in zip(self.capabilities, policy.capability_rules, strict=True):
            if (
                planned.capability != rule.capability
                or planned.required != rule.required
                or planned.priority != rule.priority
                or planned.reason != rule.reason
                or planned.dependencies != rule.dependencies
                or planned.estimated_duration_seconds != rule.estimated_duration_seconds
            ):
                raise InvariantViolationError("Investigation plan capability diverges from policy.")
        _validate_dependency_graph(
            tuple(
                PlanningCapabilityRule(
                    capability=item.capability,
                    required=item.required,
                    priority=item.priority,
                    reason=item.reason,
                    dependencies=item.dependencies,
                    estimated_duration_seconds=item.estimated_duration_seconds,
                )
                for item in self.capabilities
            )
        )
        _validate_cost(
            self.maximum_estimated_cost_kind,
            self.maximum_estimated_cost,
            "plan maximum",
        )
        if self.budget is not None and self.budget.amount < 0:
            raise InvariantViolationError("Investigation plan budget cannot be negative.")
        created_at = normalize_utc(self.created_at)
        deadline_at = normalize_utc(self.deadline_at) if self.deadline_at is not None else None
        if deadline_at is not None and deadline_at < created_at:
            raise PlanningDeadlineExceededError("Investigation plan deadline is incompatible.")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "deadline_at", deadline_at)
        expected_cost = _aggregate_maximum_cost(self.capabilities)
        if expected_cost != (self.maximum_estimated_cost_kind, self.maximum_estimated_cost):
            raise InvariantViolationError("Investigation plan maximum cost is inconsistent.")
        if self.budget is not None and self.maximum_estimated_cost is not None:
            if self.budget.currency != self.maximum_estimated_cost.currency:
                raise PlanningBudgetExceededError(
                    "Investigation plan budget currency is incompatible."
                )
            if self.maximum_estimated_cost.amount > self.budget.amount:
                raise PlanningBudgetExceededError("Investigation plan exceeds its budget.")
        if deadline_at is not None:
            critical_seconds = _critical_path_seconds(self.capabilities)
            if created_at + timedelta(seconds=critical_seconds) > deadline_at:
                raise PlanningDeadlineExceededError("Investigation plan exceeds its deadline.")
        if self.plan_digest != investigation_plan_digest(self):
            raise InvariantViolationError("Investigation plan digest is inconsistent.")

    def __repr__(self) -> str:
        return (
            "InvestigationPlan("
            f"id={self.id!r}, investigation_id={self.investigation_id!r}, "
            f"company_id={self.company_id!r}, capability_count={len(self.capabilities)}, "
            "payload=<redacted>)"
        )


def build_investigation_plan(
    *,
    plan_id: InvestigationPlanId,
    capability_ids: tuple[PlannedCapabilityId, ...],
    option_ids: tuple[PlannedConnectorOptionId, ...],
    investigation: Investigation,
    company: Company,
    command_id: InvestigationCommandId,
    command_digest: str,
    created_by: UserId,
    created_at: datetime,
    policy: PlanningPolicy,
    descriptors: tuple[ConnectorDescriptor, ...],
) -> InvestigationPlan:
    """Create one plan from persisted inputs and admission-time connector metadata."""

    if policy != INVESTIGATION_PLANNING_V1:
        raise UnsupportedPlanningPolicyError("Planning policy is not supported.")
    if investigation.profile_code not in policy.supported_profiles:
        raise UnsupportedPlanningProfileError("Investigation profile is not supported.")
    if investigation.state is not InvestigationState.PLANNING:
        raise InvariantViolationError("Investigation must be in PLANNING to create a plan.")
    if (
        investigation.confirmed_company_id != company.id
        or company.workspace_id != investigation.workspace_id
    ):
        raise InvariantViolationError("Investigation confirmed Company context is invalid.")
    if (
        investigation.active_candidate_batch_id is not None
        or investigation.identification_input is None
    ):
        raise InvariantViolationError("Investigation planning context is incomplete.")
    if len(capability_ids) != len(policy.capability_rules):
        raise InvariantViolationError("Planner capability identifiers are incomplete.")
    for descriptor in descriptors:
        validate_connector_descriptor(descriptor)
    normalized_at = normalize_utc(created_at)
    option_cursor = 0
    planned: list[PlannedCapability] = []
    country = company.country_code
    for rule, capability_id in zip(policy.capability_rules, capability_ids, strict=True):
        eligible = sorted(
            (
                descriptor
                for descriptor in descriptors
                if rule.capability in descriptor.capabilities
                and descriptor.contract_version.major == policy.supported_contract_major
                and (
                    descriptor.coverage_kind is ConnectorCoverageKind.GLOBAL
                    or country in descriptor.countries
                )
            ),
            key=lambda descriptor: (
                0 if descriptor.coverage_kind is ConnectorCoverageKind.COUNTRY_SET else 1,
                0 if descriptor.contract_version == CONNECTOR_CONTRACT_VERSION else 1,
                descriptor.connector_id.value,
            ),
        )
        options: list[PlannedConnectorOption] = []
        for rank, descriptor in enumerate(eligible, start=1):
            if option_cursor >= len(option_ids):
                raise InvariantViolationError(
                    "Planner connector option identifiers are incomplete."
                )
            options.append(
                PlannedConnectorOption(
                    id=option_ids[option_cursor],
                    planned_capability_id=capability_id,
                    connector_id=descriptor.connector_id,
                    connector_version=descriptor.version,
                    contract_version=descriptor.contract_version,
                    source_id=descriptor.source_id,
                    coverage_kind=descriptor.coverage_kind,
                    access_type=descriptor.access_type,
                    operations=tuple(sorted(descriptor.operations, key=lambda item: item.value)),
                    eligibility_rank=rank,
                    estimated_cost_kind=EstimatedCostKind.UNKNOWN,
                    estimated_cost=None,
                    estimated_duration_seconds=rule.estimated_duration_seconds,
                )
            )
            option_cursor += 1
        if rule.required and not options:
            raise RequiredCapabilityUnavailableError(
                "A required capability has no eligible connector."
            )
        planned.append(
            PlannedCapability(
                id=capability_id,
                capability=rule.capability,
                required=rule.required,
                priority=rule.priority,
                reason=rule.reason,
                dependencies=rule.dependencies,
                connector_options=tuple(options),
                estimated_cost_kind=EstimatedCostKind.UNKNOWN,
                estimated_cost=None,
                estimated_duration_seconds=rule.estimated_duration_seconds,
                status=(
                    PlannedCapabilityStatus.READY
                    if options
                    else PlannedCapabilityStatus.OPTIONAL_UNAVAILABLE
                ),
            )
        )
    if option_cursor != len(option_ids):
        raise InvariantViolationError("Planner connector option identifiers are excessive.")
    maximum_kind, maximum_cost = _aggregate_maximum_cost(tuple(planned))
    base: dict[str, object] = {
        "id": plan_id,
        "workspace_id": investigation.workspace_id,
        "investigation_id": investigation.id,
        "company_id": company.id,
        "profile_code": investigation.profile_code,
        "country_code": company.country_code.value,
        "plan_version": INVESTIGATION_PLAN_VERSION,
        "status": InvestigationPlanStatus.READY,
        "capabilities": tuple(planned),
        "budget": investigation.budget,
        "deadline_at": investigation.deadline_at,
        "maximum_estimated_cost_kind": maximum_kind,
        "maximum_estimated_cost": maximum_cost,
        "planning_policy_id": policy.policy_id,
        "planning_policy_version": policy.version,
        "planning_policy_snapshot": policy.to_canonical_json(),
        "planning_policy_digest": policy.digest,
        "input_digest": investigation.identification_input.digest,
        "company_snapshot_digest": company_planning_snapshot_digest(company),
        "command_id": command_id,
        "command_digest": command_digest,
        "created_by": created_by,
        "created_at": normalized_at,
        "investigation_state_version": investigation.state_version,
        "schema_version": INVESTIGATION_PLAN_SCHEMA_VERSION,
    }
    return InvestigationPlan(
        id=plan_id,
        workspace_id=investigation.workspace_id,
        investigation_id=investigation.id,
        company_id=company.id,
        profile_code=investigation.profile_code,
        country_code=company.country_code.value,
        plan_version=INVESTIGATION_PLAN_VERSION,
        status=InvestigationPlanStatus.READY,
        capabilities=tuple(planned),
        budget=investigation.budget,
        deadline_at=investigation.deadline_at,
        maximum_estimated_cost_kind=maximum_kind,
        maximum_estimated_cost=maximum_cost,
        planning_policy_id=policy.policy_id,
        planning_policy_version=policy.version,
        planning_policy_snapshot=policy.to_canonical_json(),
        planning_policy_digest=policy.digest,
        input_digest=investigation.identification_input.digest,
        company_snapshot_digest=company_planning_snapshot_digest(company),
        plan_digest=_plan_digest_from_values(base),
        command_id=command_id,
        command_digest=command_digest,
        created_by=created_by,
        created_at=normalized_at,
        investigation_state_version=investigation.state_version,
        schema_version=INVESTIGATION_PLAN_SCHEMA_VERSION,
    )


def validate_investigation_plan_context(
    plan: InvestigationPlan,
    *,
    investigation: Investigation,
    company: Company,
) -> None:
    """Validate immutable plan inputs against the current persisted context."""

    if (
        investigation.workspace_id != plan.workspace_id
        or investigation.id != plan.investigation_id
        or investigation.confirmed_company_id != plan.company_id
        or investigation.active_candidate_batch_id is not None
        or investigation.profile_code != plan.profile_code
        or investigation.country_code.value != plan.country_code
        or investigation.budget != plan.budget
        or investigation.deadline_at != plan.deadline_at
        or investigation.identification_input is None
        or investigation.identification_input.digest != plan.input_digest
        or investigation.state_version < plan.investigation_state_version
        or investigation.state not in _PLAN_CONTINUITY_STATES
        or (
            investigation.state_version == plan.investigation_state_version
            and investigation.state is not InvestigationState.PLANNING
        )
    ):
        raise InvariantViolationError("Persisted investigation plan context is invalid.")
    if (
        company.workspace_id != plan.workspace_id
        or company.id != plan.company_id
        or company.country_code.value != plan.country_code
        or company_planning_snapshot_digest(company) != plan.company_snapshot_digest
    ):
        raise InvariantViolationError("Persisted investigation plan Company is invalid.")


def investigation_plan_digest(plan: InvestigationPlan) -> str:
    values = {
        field_name: getattr(plan, field_name)
        for field_name in (
            "id",
            "workspace_id",
            "investigation_id",
            "company_id",
            "profile_code",
            "country_code",
            "plan_version",
            "status",
            "capabilities",
            "budget",
            "deadline_at",
            "maximum_estimated_cost_kind",
            "maximum_estimated_cost",
            "planning_policy_id",
            "planning_policy_version",
            "planning_policy_snapshot",
            "planning_policy_digest",
            "input_digest",
            "company_snapshot_digest",
            "command_id",
            "command_digest",
            "created_by",
            "created_at",
            "investigation_state_version",
            "schema_version",
        )
    }
    return _plan_digest_from_values(values)


def company_planning_snapshot_digest(company: Company) -> str:
    payload = {
        "company_id": str(company.id),
        "country_code": company.country_code.value,
        "created_at": company.created_at.isoformat(),
        "dissolved_on": company.dissolved_on.isoformat() if company.dissolved_on else None,
        "incorporated_on": company.incorporated_on.isoformat() if company.incorporated_on else None,
        "legal_form": company.legal_form,
        "legal_name": company.legal_name,
        "official_domain": company.official_domain,
        "status": company.status.value,
        "trade_name": company.trade_name,
        "updated_at": company.updated_at.isoformat(),
        "workspace_id": str(company.workspace_id),
    }
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def count_eligible_options(
    policy: PlanningPolicy,
    descriptors: tuple[ConnectorDescriptor, ...],
    country_code: str,
) -> int:
    """Count IDs required before pure plan materialization."""

    return sum(
        1
        for rule in policy.capability_rules
        for descriptor in descriptors
        if rule.capability in descriptor.capabilities
        and descriptor.contract_version.major == policy.supported_contract_major
        and (
            descriptor.coverage_kind is ConnectorCoverageKind.GLOBAL
            or any(country.value == country_code for country in descriptor.countries)
        )
    )


def _plan_digest_from_values(values: dict[str, object]) -> str:
    capabilities = values["capabilities"]
    if not isinstance(capabilities, tuple):
        raise InvariantViolationError("Investigation plan capabilities are invalid.")
    payload = {
        "budget": _money_payload(values["budget"]),
        "capabilities": [_capability_payload(item) for item in capabilities],
        "command_digest": values["command_digest"],
        "command_id": str(values["command_id"]),
        "company_id": str(values["company_id"]),
        "company_snapshot_digest": values["company_snapshot_digest"],
        "country_code": values["country_code"],
        "created_at": _datetime_text(values["created_at"]),
        "created_by": str(values["created_by"]),
        "deadline_at": _datetime_text(values["deadline_at"]),
        "input_digest": values["input_digest"],
        "investigation_id": str(values["investigation_id"]),
        "investigation_state_version": values["investigation_state_version"],
        "maximum_estimated_cost": _money_payload(values["maximum_estimated_cost"]),
        "maximum_estimated_cost_kind": _enum_text(values["maximum_estimated_cost_kind"]),
        "plan_id": str(values["id"]),
        "plan_version": values["plan_version"],
        "planning_policy_digest": values["planning_policy_digest"],
        "planning_policy_id": values["planning_policy_id"],
        "planning_policy_snapshot": values["planning_policy_snapshot"],
        "planning_policy_version": values["planning_policy_version"],
        "profile_code": values["profile_code"],
        "schema_version": values["schema_version"],
        "status": _enum_text(values["status"]),
        "workspace_id": str(values["workspace_id"]),
    }
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _capability_payload(value: object) -> dict[str, object]:
    if not isinstance(value, PlannedCapability):
        raise InvariantViolationError("Investigation plan capability is invalid.")
    return {
        "capability": value.capability.value,
        "dependencies": [item.value for item in value.dependencies],
        "estimated_cost": _money_payload(value.estimated_cost),
        "estimated_cost_kind": value.estimated_cost_kind.value,
        "estimated_duration_seconds": value.estimated_duration_seconds,
        "id": str(value.id),
        "options": [_option_payload(item) for item in value.connector_options],
        "priority": value.priority,
        "reason": value.reason.value,
        "required": value.required,
        "status": value.status.value,
    }


def _option_payload(value: PlannedConnectorOption) -> dict[str, object]:
    return {
        "access_type": value.access_type.value,
        "connector_id": value.connector_id.value,
        "connector_version": str(value.connector_version),
        "contract_version": str(value.contract_version),
        "coverage_kind": value.coverage_kind.value,
        "eligibility_rank": value.eligibility_rank,
        "estimated_cost": _money_payload(value.estimated_cost),
        "estimated_cost_kind": value.estimated_cost_kind.value,
        "estimated_duration_seconds": value.estimated_duration_seconds,
        "id": str(value.id),
        "operations": [item.value for item in value.operations],
        "source_id": value.source_id.value,
    }


def _aggregate_maximum_cost(
    capabilities: tuple[PlannedCapability, ...],
) -> tuple[EstimatedCostKind, Money | None]:
    ready = tuple(item for item in capabilities if item.connector_options)
    if any(item.estimated_cost_kind is EstimatedCostKind.UNKNOWN for item in ready):
        return EstimatedCostKind.UNKNOWN, None
    costs = tuple(item.estimated_cost for item in ready)
    if any(item is None for item in costs):
        raise InvariantViolationError("Known capability cost is missing.")
    typed_costs = tuple(item for item in costs if item is not None)
    if not typed_costs:
        return EstimatedCostKind.KNOWN, None
    currency = typed_costs[0].currency
    if any(item.currency != currency for item in typed_costs):
        raise InvariantViolationError("Plan costs use incompatible currencies.")
    total = Money(Decimal("0"), currency)
    for item in typed_costs:
        total = total + item
    return EstimatedCostKind.KNOWN, total


def _critical_path_seconds(capabilities: tuple[PlannedCapability, ...]) -> int:
    by_capability = {
        item.capability: item
        for item in capabilities
        if item.status is PlannedCapabilityStatus.READY
    }
    cache: dict[ConnectorCapability, int] = {}

    def total(capability: ConnectorCapability) -> int:
        if capability in cache:
            return cache[capability]
        item = by_capability[capability]
        dependency_seconds = max(
            (total(dep) for dep in item.dependencies if dep in by_capability),
            default=0,
        )
        cache[capability] = dependency_seconds + item.estimated_duration_seconds
        return cache[capability]

    return max((total(capability) for capability in by_capability), default=0)


def _validate_dependency_graph(rules: tuple[PlanningCapabilityRule, ...]) -> None:
    present = {rule.capability for rule in rules}
    if any(dependency not in present for rule in rules for dependency in rule.dependencies):
        raise InvalidPlanningDependencyError("Planning dependency references an absent capability.")
    graph = {rule.capability: rule.dependencies for rule in rules}
    visiting: set[ConnectorCapability] = set()
    visited: set[ConnectorCapability] = set()

    def visit(capability: ConnectorCapability) -> None:
        if capability in visiting:
            raise InvalidPlanningDependencyError("Planning capability dependency cycle detected.")
        if capability in visited:
            return
        visiting.add(capability)
        for dependency in graph[capability]:
            visit(dependency)
        visiting.remove(capability)
        visited.add(capability)

    for capability in graph:
        visit(capability)


def _validate_cost(kind: EstimatedCostKind, value: Money | None, scope: str) -> None:
    if not isinstance(kind, EstimatedCostKind):
        raise InvariantViolationError(f"Planning {scope} cost kind is invalid.")
    if (kind is EstimatedCostKind.KNOWN) != (value is not None):
        raise InvariantViolationError(f"Planning {scope} cost metadata is inconsistent.")
    if value is not None and (not isinstance(value, Money) or value.amount < 0):
        raise InvariantViolationError(f"Planning {scope} cost is invalid.")


def _duration(value: int, scope: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 2_592_000:
        raise InvariantViolationError(f"Planning {scope} duration is invalid.")


def _rule_sort_key(rule: PlanningCapabilityRule) -> tuple[int, str]:
    return rule.priority, rule.capability.value


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _code(value: str, name: str) -> str:
    if not isinstance(value, str) or _CODE_PATTERN.fullmatch(value) is None:
        raise InvariantViolationError(f"{name} is invalid.")
    return value


def _digest(value: str, name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise InvariantViolationError(f"Investigation plan {name} digest is invalid.")


def _money_payload(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Money):
        raise InvariantViolationError("Investigation plan money value is invalid.")
    return {"amount": str(value.amount), "currency": value.currency.value}


def _datetime_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise InvariantViolationError("Investigation plan timestamp is invalid.")
    return normalize_utc(value).isoformat()


def _enum_text(value: object) -> str:
    if not isinstance(value, StrEnum):
        raise InvariantViolationError("Investigation plan enum value is invalid.")
    return value.value


def _rule(
    capability: ConnectorCapability,
    *,
    required: bool,
    priority: int,
    reason: PlanningReason,
    dependencies: tuple[ConnectorCapability, ...] = (),
    duration: int = 3600,
) -> PlanningCapabilityRule:
    return PlanningCapabilityRule(
        capability=capability,
        required=required,
        priority=priority,
        reason=reason,
        dependencies=dependencies,
        estimated_duration_seconds=duration,
    )


INVESTIGATION_PLANNING_V1 = PlanningPolicy(
    policy_id="INVESTIGATION_PLANNING_V1",
    version=1,
    supported_profiles=(_SUPPORTED_PROFILE,),
    supported_contract_major=CONNECTOR_CONTRACT_VERSION.major,
    capability_rules=(
        _rule(
            ConnectorCapability.COMPANY_IDENTITY,
            required=True,
            priority=10,
            reason=PlanningReason.COMPANY_IDENTITY,
        ),
        _rule(
            ConnectorCapability.COMPANY_REGISTRY,
            required=True,
            priority=20,
            reason=PlanningReason.BUSINESS_REGISTRATION,
        ),
        _rule(
            ConnectorCapability.OWNERSHIP,
            required=False,
            priority=30,
            reason=PlanningReason.OWNERSHIP_STRUCTURE,
            dependencies=(ConnectorCapability.COMPANY_REGISTRY,),
        ),
        _rule(
            ConnectorCapability.CONTACTS,
            required=False,
            priority=40,
            reason=PlanningReason.BUSINESS_CONTACTS,
        ),
        _rule(
            ConnectorCapability.FINANCIALS,
            required=False,
            priority=50,
            reason=PlanningReason.FINANCIAL_REVIEW,
        ),
        _rule(
            ConnectorCapability.INSOLVENCY,
            required=False,
            priority=60,
            reason=PlanningReason.INSOLVENCY_REVIEW,
        ),
        _rule(
            ConnectorCapability.LEGAL_CASES,
            required=False,
            priority=70,
            reason=PlanningReason.LEGAL_CASE_REVIEW,
        ),
        _rule(
            ConnectorCapability.SANCTIONS,
            required=False,
            priority=80,
            reason=PlanningReason.CONFIRMED_COMPANY_SANCTIONS,
        ),
        _rule(
            ConnectorCapability.ADVERSE_MEDIA,
            required=False,
            priority=90,
            reason=PlanningReason.ADVERSE_MEDIA_REVIEW,
        ),
        _rule(
            ConnectorCapability.DOCUMENTS,
            required=False,
            priority=100,
            reason=PlanningReason.SUPPORTING_DOCUMENTS,
        ),
    ),
)


__all__ = [
    "INVESTIGATION_PLANNING_V1",
    "INVESTIGATION_PLAN_SCHEMA_VERSION",
    "INVESTIGATION_PLAN_VERSION",
    "EstimatedCostKind",
    "InvestigationPlan",
    "InvestigationPlanStatus",
    "PlannedCapability",
    "PlannedCapabilityStatus",
    "PlannedConnectorOption",
    "PlanningCapabilityRule",
    "PlanningConnectorCatalog",
    "PlanningPolicy",
    "PlanningReason",
    "build_investigation_plan",
    "company_planning_snapshot_digest",
    "count_eligible_options",
    "investigation_plan_digest",
    "validate_investigation_plan_context",
]
