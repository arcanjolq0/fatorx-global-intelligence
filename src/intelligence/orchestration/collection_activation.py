"""Immutable F4.5 collection activation manifest built only from a persisted plan."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Self

from intelligence.connectors.enums import (
    ConnectorAccessType,
    ConnectorCapability,
    ConnectorCoverageKind,
    ConnectorOperation,
)
from intelligence.connectors.identifiers import ConnectorId, SourceId
from intelligence.connectors.versions import SemanticVersion
from intelligence.domain.companies import Company
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    CollectionOperationId,
    CollectionRunId,
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
from intelligence.orchestration.errors import CollectionActivationDeadlineExceededError
from intelligence.orchestration.planning import (
    EstimatedCostKind,
    InvestigationPlan,
    InvestigationPlanStatus,
    PlannedCapability,
    PlannedCapabilityStatus,
    PlannedConnectorOption,
    company_planning_snapshot_digest,
    investigation_plan_digest,
    validate_investigation_plan_context,
)

COLLECTION_ACTIVATION_POLICY_SCHEMA_VERSION = 1
COLLECTION_RUN_SCHEMA_VERSION = 1
COLLECTION_RUN_VERSION = 1
COLLECTION_OPERATION_SCHEMA_VERSION = 1
COLLECTION_OPERATION_VERSION = 1
_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_.:-]{0,63}", flags=re.ASCII)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)
_COLLECTION_CONTINUITY_STATES = frozenset(
    {
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


class CollectionRunStatus(StrEnum):
    """Closed initial state of a collection manifest."""

    PENDING = "PENDING"


class CollectionOperationStatus(StrEnum):
    """Closed initial state of a prepared collection operation."""

    PENDING = "PENDING"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CollectionActivationPolicy:
    """Versioned policy that activates exactly rank-one persisted plan options."""

    policy_id: str
    version: int
    selected_eligibility_rank: int
    schema_version: int = COLLECTION_ACTIVATION_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or _CODE_PATTERN.fullmatch(self.policy_id) is None:
            raise InvariantViolationError("Collection activation policy ID is invalid.")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise InvariantViolationError("Collection activation policy version is invalid.")
        if self.selected_eligibility_rank != 1:
            raise InvariantViolationError("Collection activation policy must select rank one.")
        if self.schema_version != COLLECTION_ACTIVATION_POLICY_SCHEMA_VERSION:
            raise InvariantViolationError("Collection activation policy schema is unsupported.")

    @property
    def digest(self) -> str:
        return sha256(self.to_canonical_json().encode("utf-8")).hexdigest()

    def to_canonical_json(self) -> str:
        return _canonical_json(
            {
                "policy_id": self.policy_id,
                "schema_version": self.schema_version,
                "selected_eligibility_rank": self.selected_eligibility_rank,
                "version": self.version,
            }
        )

    @classmethod
    def from_canonical_json(cls, serialized: str) -> Self:
        if not isinstance(serialized, str):
            raise InvariantViolationError("Persisted activation policy must be JSON text.")
        try:
            raw = json.loads(serialized)
            if not isinstance(raw, dict):
                raise TypeError
            policy = cls(
                policy_id=raw["policy_id"],
                version=raw["version"],
                selected_eligibility_rank=raw["selected_eligibility_rank"],
                schema_version=raw["schema_version"],
            )
        except (KeyError, TypeError, ValueError, InvariantViolationError) as error:
            raise InvariantViolationError("Persisted activation policy is invalid.") from error
        if policy.to_canonical_json() != serialized:
            raise InvariantViolationError("Persisted activation policy is not canonical.")
        return policy


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CollectionOperation:
    """One immutable operation selected from a READY planned capability."""

    id: CollectionOperationId
    collection_run_id: CollectionRunId
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    plan_id: InvestigationPlanId
    capability: ConnectorCapability
    priority: int
    dependency_operation_ids: tuple[CollectionOperationId, ...]
    planned_capability_id: PlannedCapabilityId
    planned_connector_option_id: PlannedConnectorOptionId
    connector_id: ConnectorId
    connector_version: SemanticVersion
    contract_version: SemanticVersion
    source_id: SourceId
    connector_operations: tuple[ConnectorOperation, ...]
    coverage_kind: ConnectorCoverageKind
    access_type: ConnectorAccessType
    estimated_cost_kind: EstimatedCostKind
    estimated_cost: Money | None
    estimated_duration_seconds: int
    status: CollectionOperationStatus
    attempt: int
    operation_digest: str
    operation_version: int = COLLECTION_OPERATION_VERSION
    schema_version: int = COLLECTION_OPERATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        typed = (
            (self.id, CollectionOperationId),
            (self.collection_run_id, CollectionRunId),
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.plan_id, InvestigationPlanId),
            (self.planned_capability_id, PlannedCapabilityId),
            (self.planned_connector_option_id, PlannedConnectorOptionId),
            (self.connector_id, ConnectorId),
            (self.connector_version, SemanticVersion),
            (self.contract_version, SemanticVersion),
            (self.source_id, SourceId),
            (self.capability, ConnectorCapability),
            (self.coverage_kind, ConnectorCoverageKind),
            (self.access_type, ConnectorAccessType),
            (self.estimated_cost_kind, EstimatedCostKind),
            (self.status, CollectionOperationStatus),
        )
        if any(not isinstance(value, expected) for value, expected in typed):
            raise InvariantViolationError("Collection operation metadata is invalid.")
        if self.operation_version != 1 or self.schema_version != 1:
            raise InvariantViolationError("Collection operation version is unsupported.")
        if self.status is not CollectionOperationStatus.PENDING or self.attempt != 0:
            raise InvariantViolationError("Collection operation initial state is invalid.")
        if (
            isinstance(self.priority, bool)
            or not isinstance(self.priority, int)
            or not 1 <= self.priority <= 1000
        ):
            raise InvariantViolationError("Collection operation priority is invalid.")
        if (
            not isinstance(self.dependency_operation_ids, tuple)
            or any(
                not isinstance(item, CollectionOperationId)
                for item in self.dependency_operation_ids
            )
            or len(set(self.dependency_operation_ids)) != len(self.dependency_operation_ids)
            or self.id in self.dependency_operation_ids
        ):
            raise InvariantViolationError("Collection operation dependencies are invalid.")
        if (
            not isinstance(self.connector_operations, tuple)
            or not self.connector_operations
            or tuple(sorted(set(self.connector_operations), key=lambda item: item.value))
            != self.connector_operations
        ):
            raise InvariantViolationError("Collection connector operations are invalid.")
        _validate_cost(self.estimated_cost_kind, self.estimated_cost)
        if (
            isinstance(self.estimated_duration_seconds, bool)
            or not isinstance(self.estimated_duration_seconds, int)
            or not 1 <= self.estimated_duration_seconds <= 2_592_000
        ):
            raise InvariantViolationError("Collection operation duration is invalid.")
        _digest(self.operation_digest, "operation")
        if self.operation_digest != collection_operation_digest(self):
            raise InvariantViolationError("Collection operation digest is inconsistent.")

    def __repr__(self) -> str:
        return (
            "CollectionOperation("
            f"id={self.id!r}, capability={self.capability.value!r}, "
            f"connector_id={self.connector_id!r}, payload=<redacted>)"
        )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CollectionRun:
    """Durable immutable activation manifest for one investigation plan."""

    id: CollectionRunId
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    company_id: CompanyId
    plan_id: InvestigationPlanId
    run_version: int
    status: CollectionRunStatus
    operations: tuple[CollectionOperation, ...]
    activation_policy_id: str
    activation_policy_version: int
    activation_policy_snapshot: str = field(repr=False)
    activation_policy_digest: str
    plan_digest: str
    company_snapshot_digest: str
    budget: Money | None
    deadline_at: datetime | None
    maximum_estimated_cost_kind: EstimatedCostKind
    maximum_estimated_cost: Money | None
    command_id: InvestigationCommandId
    command_digest: str
    created_by: UserId
    created_at: datetime
    investigation_state_version: int
    run_digest: str
    schema_version: int = COLLECTION_RUN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        typed = (
            (self.id, CollectionRunId),
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.company_id, CompanyId),
            (self.plan_id, InvestigationPlanId),
            (self.command_id, InvestigationCommandId),
            (self.created_by, UserId),
            (self.status, CollectionRunStatus),
            (self.maximum_estimated_cost_kind, EstimatedCostKind),
        )
        if any(not isinstance(value, expected) for value, expected in typed):
            raise InvariantViolationError("Collection run metadata is invalid.")
        if self.run_version != 1 or self.schema_version != 1:
            raise InvariantViolationError("Collection run version is unsupported.")
        if self.status is not CollectionRunStatus.PENDING:
            raise InvariantViolationError("Collection run initial status is invalid.")
        if (
            isinstance(self.investigation_state_version, bool)
            or not isinstance(self.investigation_state_version, int)
            or self.investigation_state_version < 2
        ):
            raise InvariantViolationError("Collection run state version is invalid.")
        for value, name in (
            (self.activation_policy_digest, "activation policy"),
            (self.plan_digest, "plan"),
            (self.company_snapshot_digest, "Company snapshot"),
            (self.command_digest, "command"),
            (self.run_digest, "run"),
        ):
            _digest(value, name)
        policy = CollectionActivationPolicy.from_canonical_json(self.activation_policy_snapshot)
        if (
            policy != COLLECTION_ACTIVATION_V1
            or policy.policy_id != self.activation_policy_id
            or policy.version != self.activation_policy_version
            or policy.digest != self.activation_policy_digest
        ):
            raise InvariantViolationError("Collection activation policy is inconsistent.")
        if (
            not isinstance(self.operations, tuple)
            or not self.operations
            or tuple(
                sorted(self.operations, key=lambda item: (item.priority, item.capability.value))
            )
            != self.operations
            or len({item.capability for item in self.operations}) != len(self.operations)
            or len({item.priority for item in self.operations}) != len(self.operations)
        ):
            raise InvariantViolationError("Collection operations are not canonical.")
        if any(
            operation.collection_run_id != self.id
            or operation.workspace_id != self.workspace_id
            or operation.investigation_id != self.investigation_id
            or operation.plan_id != self.plan_id
            for operation in self.operations
        ):
            raise InvariantViolationError("Collection operation scope is inconsistent.")
        _validate_operation_graph(self.operations)
        _validate_cost(self.maximum_estimated_cost_kind, self.maximum_estimated_cost)
        if _aggregate_operation_cost(self.operations) != (
            self.maximum_estimated_cost_kind,
            self.maximum_estimated_cost,
        ):
            raise InvariantViolationError("Collection run aggregate cost is inconsistent.")
        if self.budget is not None and (
            not isinstance(self.budget, Money) or self.budget.amount < 0
        ):
            raise InvariantViolationError("Collection run budget is invalid.")
        created_at = normalize_utc(self.created_at)
        deadline_at = normalize_utc(self.deadline_at) if self.deadline_at is not None else None
        if deadline_at is not None and (
            deadline_at < created_at
            or created_at + timedelta(seconds=_operation_critical_path_seconds(self.operations))
            > deadline_at
        ):
            raise InvariantViolationError("Collection run cannot fit before its deadline.")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "deadline_at", deadline_at)
        if self.run_digest != collection_run_digest(self):
            raise InvariantViolationError("Collection run digest is inconsistent.")

    def __repr__(self) -> str:
        return (
            "CollectionRun("
            f"id={self.id!r}, investigation_id={self.investigation_id!r}, "
            f"plan_id={self.plan_id!r}, operation_count={len(self.operations)}, "
            "payload=<redacted>)"
        )


def build_collection_run(
    *,
    run_id: CollectionRunId,
    operation_ids: tuple[CollectionOperationId, ...],
    investigation: Investigation,
    company: Company,
    plan: InvestigationPlan,
    command_id: InvestigationCommandId,
    command_digest: str,
    created_by: UserId,
    created_at: datetime,
    activation_policy: CollectionActivationPolicy,
) -> CollectionRun:
    """Activate rank-one options from an already persisted and validated plan."""

    if activation_policy != COLLECTION_ACTIVATION_V1:
        raise InvariantViolationError("Collection activation policy is unsupported.")
    if investigation.state is not InvestigationState.PLANNING:
        raise InvariantViolationError("Collection activation requires PLANNING.")
    validate_investigation_plan_context(plan, investigation=investigation, company=company)
    if plan.plan_digest != investigation_plan_digest(plan):
        raise InvariantViolationError("Investigation plan digest is inconsistent.")
    if plan.status is not InvestigationPlanStatus.READY:
        raise InvariantViolationError("Collection activation requires a READY plan.")
    validate_collection_activation_deadline(
        investigation=investigation,
        plan=plan,
        activated_at=created_at,
    )
    ready = tuple(
        capability
        for capability in plan.capabilities
        if capability.status is PlannedCapabilityStatus.READY
    )
    if len(operation_ids) != len(ready):
        raise InvariantViolationError("Collection operation identifiers are incomplete.")
    operation_id_by_capability = {
        capability.capability: operation_id
        for capability, operation_id in zip(ready, operation_ids, strict=True)
    }
    if len(operation_id_by_capability) != len(ready):
        raise InvariantViolationError("Collection capability set is inconsistent.")
    operations: list[CollectionOperation] = []
    for capability, operation_id in zip(ready, operation_ids, strict=True):
        rank_one = tuple(
            option
            for option in capability.connector_options
            if option.eligibility_rank == activation_policy.selected_eligibility_rank
        )
        if len(rank_one) != 1:
            raise InvariantViolationError("READY capability must have exactly one rank-one option.")
        dependency_ids: list[CollectionOperationId] = []
        for dependency in capability.dependencies:
            dependency_id = operation_id_by_capability.get(dependency)
            if dependency_id is None:
                raise InvariantViolationError(
                    "Collection dependency cannot be converted to an operation."
                )
            dependency_ids.append(dependency_id)
        operations.append(
            _build_operation(
                operation_id=operation_id,
                run_id=run_id,
                plan=plan,
                capability=capability,
                option=rank_one[0],
                dependency_ids=tuple(dependency_ids),
            )
        )
    normalized_at = normalize_utc(created_at)
    maximum_kind, maximum_cost = _aggregate_operation_cost(tuple(operations))
    base: dict[str, object] = {
        "id": run_id,
        "workspace_id": plan.workspace_id,
        "investigation_id": plan.investigation_id,
        "company_id": plan.company_id,
        "plan_id": plan.id,
        "run_version": COLLECTION_RUN_VERSION,
        "status": CollectionRunStatus.PENDING,
        "operations": tuple(operations),
        "activation_policy_id": activation_policy.policy_id,
        "activation_policy_version": activation_policy.version,
        "activation_policy_snapshot": activation_policy.to_canonical_json(),
        "activation_policy_digest": activation_policy.digest,
        "plan_digest": plan.plan_digest,
        "company_snapshot_digest": plan.company_snapshot_digest,
        "budget": plan.budget,
        "deadline_at": plan.deadline_at,
        "maximum_estimated_cost_kind": maximum_kind,
        "maximum_estimated_cost": maximum_cost,
        "command_id": command_id,
        "command_digest": command_digest,
        "created_by": created_by,
        "created_at": normalized_at,
        "investigation_state_version": investigation.state_version + 1,
        "schema_version": COLLECTION_RUN_SCHEMA_VERSION,
    }
    return CollectionRun(run_digest=_run_digest_from_values(base), **base)  # type: ignore[arg-type]


def validate_collection_activation_deadline(
    *,
    investigation: Investigation,
    plan: InvestigationPlan,
    activated_at: datetime,
) -> None:
    """Revalidate remaining time from only the operations a READY plan would materialize."""

    normalized_at = normalize_utc(activated_at)
    deadline_at = investigation.deadline_at
    if deadline_at is None:
        return
    critical_seconds = ready_operation_critical_path_seconds(plan)
    if normalized_at + timedelta(seconds=critical_seconds) > deadline_at:
        raise CollectionActivationDeadlineExceededError(
            "Collection activation critical path exceeds the investigation deadline."
        )


def ready_operation_critical_path_seconds(plan: InvestigationPlan) -> int:
    """Return the dependency-aware duration of rank-one operations for READY capabilities."""

    ready = {
        capability.capability: capability
        for capability in plan.capabilities
        if capability.status is PlannedCapabilityStatus.READY
    }
    cache: dict[ConnectorCapability, int] = {}

    def total(capability_code: ConnectorCapability) -> int:
        cached = cache.get(capability_code)
        if cached is not None:
            return cached
        capability = ready[capability_code]
        rank_one = tuple(
            option
            for option in capability.connector_options
            if option.eligibility_rank == COLLECTION_ACTIVATION_V1.selected_eligibility_rank
        )
        if len(rank_one) != 1:
            raise InvariantViolationError("READY capability must have exactly one rank-one option.")
        dependency_seconds = max(
            (total(dependency) for dependency in capability.dependencies if dependency in ready),
            default=0,
        )
        cache[capability_code] = dependency_seconds + rank_one[0].estimated_duration_seconds
        return cache[capability_code]

    return max((total(capability_code) for capability_code in ready), default=0)


def validate_collection_run_context(
    run: CollectionRun,
    *,
    investigation: Investigation,
    company: Company,
    plan: InvestigationPlan,
) -> None:
    """Fail closed if a persisted manifest diverges from its plan or current context."""

    validate_investigation_plan_context(plan, investigation=investigation, company=company)
    if plan.plan_digest != investigation_plan_digest(plan):
        raise InvariantViolationError("Persisted investigation plan digest is inconsistent.")
    if (
        run.workspace_id != plan.workspace_id
        or run.investigation_id != plan.investigation_id
        or run.company_id != plan.company_id
        or run.plan_id != plan.id
        or run.plan_digest != plan.plan_digest
        or run.company_snapshot_digest != plan.company_snapshot_digest
        or run.company_snapshot_digest != company_planning_snapshot_digest(company)
        or run.budget != plan.budget
        or run.deadline_at != plan.deadline_at
        or investigation.state_version < run.investigation_state_version
        or investigation.state not in _COLLECTION_CONTINUITY_STATES
        or (
            investigation.state_version == run.investigation_state_version
            and investigation.state is not InvestigationState.COLLECTING
        )
    ):
        raise InvariantViolationError("Persisted collection run context is invalid.")
    ready = tuple(
        capability
        for capability in plan.capabilities
        if capability.status is PlannedCapabilityStatus.READY
    )
    if len(run.operations) != len(ready):
        raise InvariantViolationError("Persisted collection operation set is incomplete.")
    by_capability = {operation.capability: operation for operation in run.operations}
    for capability in ready:
        operation = by_capability.get(capability.capability)
        rank_one = tuple(
            option for option in capability.connector_options if option.eligibility_rank == 1
        )
        if operation is None or len(rank_one) != 1:
            raise InvariantViolationError("Persisted collection selection is invalid.")
        option = rank_one[0]
        expected_dependencies = tuple(
            by_capability[dependency].id
            for dependency in capability.dependencies
            if dependency in by_capability
        )
        if len(expected_dependencies) != len(capability.dependencies) or not _matches_plan(
            operation,
            capability,
            option,
            expected_dependencies,
        ):
            raise InvariantViolationError("Persisted collection operation diverges from plan.")


def collection_operation_digest(operation: CollectionOperation) -> str:
    values = {
        field_name: getattr(operation, field_name)
        for field_name in (
            "id",
            "collection_run_id",
            "workspace_id",
            "investigation_id",
            "plan_id",
            "capability",
            "priority",
            "dependency_operation_ids",
            "planned_capability_id",
            "planned_connector_option_id",
            "connector_id",
            "connector_version",
            "contract_version",
            "source_id",
            "connector_operations",
            "coverage_kind",
            "access_type",
            "estimated_cost_kind",
            "estimated_cost",
            "estimated_duration_seconds",
            "status",
            "attempt",
            "operation_version",
            "schema_version",
        )
    }
    return _operation_digest_from_values(values)


def collection_run_digest(run: CollectionRun) -> str:
    values = {
        field_name: getattr(run, field_name)
        for field_name in (
            "id",
            "workspace_id",
            "investigation_id",
            "company_id",
            "plan_id",
            "run_version",
            "status",
            "operations",
            "activation_policy_id",
            "activation_policy_version",
            "activation_policy_snapshot",
            "activation_policy_digest",
            "plan_digest",
            "company_snapshot_digest",
            "budget",
            "deadline_at",
            "maximum_estimated_cost_kind",
            "maximum_estimated_cost",
            "command_id",
            "command_digest",
            "created_by",
            "created_at",
            "investigation_state_version",
            "schema_version",
        )
    }
    return _run_digest_from_values(values)


def _build_operation(
    *,
    operation_id: CollectionOperationId,
    run_id: CollectionRunId,
    plan: InvestigationPlan,
    capability: PlannedCapability,
    option: PlannedConnectorOption,
    dependency_ids: tuple[CollectionOperationId, ...],
) -> CollectionOperation:
    base: dict[str, object] = {
        "id": operation_id,
        "collection_run_id": run_id,
        "workspace_id": plan.workspace_id,
        "investigation_id": plan.investigation_id,
        "plan_id": plan.id,
        "capability": capability.capability,
        "priority": capability.priority,
        "dependency_operation_ids": dependency_ids,
        "planned_capability_id": capability.id,
        "planned_connector_option_id": option.id,
        "connector_id": option.connector_id,
        "connector_version": option.connector_version,
        "contract_version": option.contract_version,
        "source_id": option.source_id,
        "connector_operations": option.operations,
        "coverage_kind": option.coverage_kind,
        "access_type": option.access_type,
        "estimated_cost_kind": option.estimated_cost_kind,
        "estimated_cost": option.estimated_cost,
        "estimated_duration_seconds": option.estimated_duration_seconds,
        "status": CollectionOperationStatus.PENDING,
        "attempt": 0,
        "operation_version": COLLECTION_OPERATION_VERSION,
        "schema_version": COLLECTION_OPERATION_SCHEMA_VERSION,
    }
    return CollectionOperation(
        operation_digest=_operation_digest_from_values(base),
        **base,  # type: ignore[arg-type]
    )


def _matches_plan(
    operation: CollectionOperation,
    capability: PlannedCapability,
    option: PlannedConnectorOption,
    dependencies: tuple[CollectionOperationId, ...],
) -> bool:
    return (
        operation.priority == capability.priority
        and operation.dependency_operation_ids == dependencies
        and operation.planned_capability_id == capability.id
        and operation.planned_connector_option_id == option.id
        and operation.connector_id == option.connector_id
        and operation.connector_version == option.connector_version
        and operation.contract_version == option.contract_version
        and operation.source_id == option.source_id
        and operation.connector_operations == option.operations
        and operation.coverage_kind == option.coverage_kind
        and operation.access_type == option.access_type
        and operation.estimated_cost_kind == option.estimated_cost_kind
        and operation.estimated_cost == option.estimated_cost
        and operation.estimated_duration_seconds == option.estimated_duration_seconds
    )


def _validate_operation_graph(operations: tuple[CollectionOperation, ...]) -> None:
    by_id = {operation.id: operation for operation in operations}
    if any(
        dependency not in by_id
        for operation in operations
        for dependency in operation.dependency_operation_ids
    ):
        raise InvariantViolationError("Collection dependency references an absent operation.")
    visiting: set[CollectionOperationId] = set()
    visited: set[CollectionOperationId] = set()

    def visit(operation_id: CollectionOperationId) -> None:
        if operation_id in visiting:
            raise InvariantViolationError("Collection operation dependency cycle detected.")
        if operation_id in visited:
            return
        visiting.add(operation_id)
        for dependency in by_id[operation_id].dependency_operation_ids:
            visit(dependency)
        visiting.remove(operation_id)
        visited.add(operation_id)

    for operation_id in by_id:
        visit(operation_id)


def _operation_critical_path_seconds(operations: tuple[CollectionOperation, ...]) -> int:
    by_id = {operation.id: operation for operation in operations}
    cache: dict[CollectionOperationId, int] = {}

    def total(operation_id: CollectionOperationId) -> int:
        cached = cache.get(operation_id)
        if cached is not None:
            return cached
        operation = by_id[operation_id]
        dependency_seconds = max(
            (total(dependency_id) for dependency_id in operation.dependency_operation_ids),
            default=0,
        )
        cache[operation_id] = dependency_seconds + operation.estimated_duration_seconds
        return cache[operation_id]

    return max((total(operation_id) for operation_id in by_id), default=0)


def _aggregate_operation_cost(
    operations: tuple[CollectionOperation, ...],
) -> tuple[EstimatedCostKind, Money | None]:
    if any(item.estimated_cost_kind is EstimatedCostKind.UNKNOWN for item in operations):
        return EstimatedCostKind.UNKNOWN, None
    costs = tuple(item.estimated_cost for item in operations)
    if any(value is None for value in costs):
        raise InvariantViolationError("Known collection operation cost is missing.")
    typed = tuple(value for value in costs if value is not None)
    currency = typed[0].currency
    if any(value.currency != currency for value in typed):
        raise InvariantViolationError("Collection operation costs use different currencies.")
    total = Money(Decimal("0"), currency)
    for value in typed:
        total += value
    return EstimatedCostKind.KNOWN, total


def _operation_digest_from_values(values: dict[str, object]) -> str:
    connector_operations = values["connector_operations"]
    dependency_operation_ids = values["dependency_operation_ids"]
    if not isinstance(connector_operations, tuple) or not isinstance(
        dependency_operation_ids, tuple
    ):
        raise InvariantViolationError("CollectionOperation digest values are invalid.")
    payload = {
        "access_type": _enum(values["access_type"]),
        "attempt": values["attempt"],
        "capability": _enum(values["capability"]),
        "collection_run_id": str(values["collection_run_id"]),
        "connector_id": str(values["connector_id"]),
        "connector_operations": [_enum(item) for item in connector_operations],
        "connector_version": str(values["connector_version"]),
        "contract_version": str(values["contract_version"]),
        "coverage_kind": _enum(values["coverage_kind"]),
        "dependencies": [str(item) for item in dependency_operation_ids],
        "estimated_cost": _money(values["estimated_cost"]),
        "estimated_cost_kind": _enum(values["estimated_cost_kind"]),
        "estimated_duration_seconds": values["estimated_duration_seconds"],
        "id": str(values["id"]),
        "investigation_id": str(values["investigation_id"]),
        "operation_version": values["operation_version"],
        "plan_id": str(values["plan_id"]),
        "planned_capability_id": str(values["planned_capability_id"]),
        "planned_connector_option_id": str(values["planned_connector_option_id"]),
        "priority": values["priority"],
        "schema_version": values["schema_version"],
        "source_id": str(values["source_id"]),
        "status": _enum(values["status"]),
        "workspace_id": str(values["workspace_id"]),
    }
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _run_digest_from_values(values: dict[str, object]) -> str:
    operations = values["operations"]
    if not isinstance(operations, tuple):
        raise InvariantViolationError("Collection run operations are invalid.")
    payload = {
        "activation_policy_digest": values["activation_policy_digest"],
        "activation_policy_id": values["activation_policy_id"],
        "activation_policy_snapshot": values["activation_policy_snapshot"],
        "activation_policy_version": values["activation_policy_version"],
        "budget": _money(values["budget"]),
        "command_digest": values["command_digest"],
        "command_id": str(values["command_id"]),
        "company_id": str(values["company_id"]),
        "company_snapshot_digest": values["company_snapshot_digest"],
        "created_at": _datetime(values["created_at"]),
        "created_by": str(values["created_by"]),
        "deadline_at": _datetime(values["deadline_at"]),
        "id": str(values["id"]),
        "investigation_id": str(values["investigation_id"]),
        "investigation_state_version": values["investigation_state_version"],
        "maximum_estimated_cost": _money(values["maximum_estimated_cost"]),
        "maximum_estimated_cost_kind": _enum(values["maximum_estimated_cost_kind"]),
        "operation_digests": [item.operation_digest for item in operations],
        "plan_digest": values["plan_digest"],
        "plan_id": str(values["plan_id"]),
        "run_version": values["run_version"],
        "schema_version": values["schema_version"],
        "status": _enum(values["status"]),
        "workspace_id": str(values["workspace_id"]),
    }
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _validate_cost(kind: EstimatedCostKind, cost: Money | None) -> None:
    if not isinstance(kind, EstimatedCostKind):
        raise InvariantViolationError("Collection cost kind is invalid.")
    if (kind is EstimatedCostKind.KNOWN) != (cost is not None):
        raise InvariantViolationError("Collection cost metadata is inconsistent.")
    if cost is not None and (not isinstance(cost, Money) or cost.amount < 0):
        raise InvariantViolationError("Collection cost is invalid.")


def _digest(value: str, name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise InvariantViolationError(f"Collection {name} digest is invalid.")


def _money(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Money):
        raise InvariantViolationError("Collection money value is invalid.")
    return {"amount": str(value.amount), "currency": value.currency.value}


def _enum(value: object) -> str:
    if not isinstance(value, StrEnum):
        raise InvariantViolationError("Collection enum value is invalid.")
    return value.value


def _datetime(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise InvariantViolationError("Collection datetime value is invalid.")
    return normalize_utc(value).isoformat()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


COLLECTION_ACTIVATION_V1 = CollectionActivationPolicy(
    policy_id="COLLECTION_ACTIVATION_V1",
    version=1,
    selected_eligibility_rank=1,
)


__all__ = [
    "COLLECTION_ACTIVATION_V1",
    "COLLECTION_OPERATION_SCHEMA_VERSION",
    "COLLECTION_OPERATION_VERSION",
    "COLLECTION_RUN_SCHEMA_VERSION",
    "COLLECTION_RUN_VERSION",
    "CollectionActivationPolicy",
    "CollectionOperation",
    "CollectionOperationStatus",
    "CollectionRun",
    "CollectionRunStatus",
    "build_collection_run",
    "collection_operation_digest",
    "collection_run_digest",
    "ready_operation_critical_path_seconds",
    "validate_collection_activation_deadline",
    "validate_collection_run_context",
]
