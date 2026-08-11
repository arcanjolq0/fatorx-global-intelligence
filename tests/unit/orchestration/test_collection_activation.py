"""F4.5 deterministic collection-manifest construction tests."""

from datetime import UTC, datetime

import pytest

from intelligence.connectors.enums import ConnectorCapability
from intelligence.domain.companies import Company
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    CollectionOperationId,
    CollectionRunId,
    InvestigationCommandId,
)
from intelligence.domain.investigations import Investigation
from intelligence.orchestration.collection_activation import (
    COLLECTION_ACTIVATION_V1,
    CollectionActivationPolicy,
    CollectionOperationStatus,
    CollectionRun,
    CollectionRunStatus,
    build_collection_run,
    ready_operation_critical_path_seconds,
    validate_collection_run_context,
)
from intelligence.orchestration.planning import InvestigationPlan, PlannedCapabilityStatus
from tests.unit.orchestration.test_planning import _context, _descriptor, _plan

NOW = datetime(2026, 8, 1, 19, tzinfo=UTC)


def _build() -> tuple[Investigation, Company, InvestigationPlan, CollectionRun]:
    investigation, company = _context()
    plan = _plan(
        investigation=investigation,
        company=company,
        descriptors=(
            _descriptor("a.country"),
            _descriptor("b.country"),
        ),
    )
    ready = tuple(
        item for item in plan.capabilities if item.status is PlannedCapabilityStatus.READY
    )
    run = build_collection_run(
        run_id=CollectionRunId.new(),
        operation_ids=tuple(CollectionOperationId.new() for _ in ready),
        investigation=investigation,
        company=company,
        plan=plan,
        command_id=InvestigationCommandId.new(),
        command_digest="b" * 64,
        created_by=investigation.requested_by,
        created_at=NOW,
        activation_policy=COLLECTION_ACTIVATION_V1,
    )
    return investigation, company, plan, run


def test_manifest_selects_only_rank_one_ready_options_and_initial_states() -> None:
    _, _, plan, run = _build()

    assert run.status is CollectionRunStatus.PENDING
    assert len(run.operations) == sum(
        item.status is PlannedCapabilityStatus.READY for item in plan.capabilities
    )
    assert all(item.status is CollectionOperationStatus.PENDING for item in run.operations)
    assert all(item.attempt == 0 for item in run.operations)
    for operation in run.operations:
        capability = next(
            item for item in plan.capabilities if item.id == operation.planned_capability_id
        )
        selected = next(
            item
            for item in capability.connector_options
            if item.id == operation.planned_connector_option_id
        )
        assert selected.eligibility_rank == 1
        assert selected.connector_id == operation.connector_id
    unavailable = {
        item.capability
        for item in plan.capabilities
        if item.status is PlannedCapabilityStatus.OPTIONAL_UNAVAILABLE
    }
    assert unavailable.isdisjoint(item.capability for item in run.operations)


def test_critical_path_uses_only_ready_rank_one_operations() -> None:
    investigation, company = _context()
    plan = _plan(
        investigation=investigation,
        company=company,
        descriptors=(
            _descriptor(
                "required.country",
                capabilities=(
                    ConnectorCapability.COMPANY_IDENTITY,
                    ConnectorCapability.COMPANY_REGISTRY,
                ),
            ),
        ),
    )
    ready = tuple(
        capability
        for capability in plan.capabilities
        if capability.status is PlannedCapabilityStatus.READY
    )
    expected = max(
        capability.connector_options[0].estimated_duration_seconds for capability in ready
    )
    unavailable = next(
        item
        for item in plan.capabilities
        if item.status is PlannedCapabilityStatus.OPTIONAL_UNAVAILABLE
    )
    object.__setattr__(unavailable, "estimated_duration_seconds", 2_592_000)

    assert ready_operation_critical_path_seconds(plan) == expected


def test_capability_dependencies_are_converted_to_same_run_operation_ids() -> None:
    _, _, _, run = _build()
    ownership = next(
        item for item in run.operations if item.capability is ConnectorCapability.OWNERSHIP
    )
    registration = next(
        item for item in run.operations if item.capability is ConnectorCapability.COMPANY_REGISTRY
    )
    assert ownership.dependency_operation_ids == (registration.id,)


def test_policy_is_closed_to_rank_one_v1() -> None:
    with pytest.raises(InvariantViolationError, match="rank one"):
        CollectionActivationPolicy(
            policy_id="COLLECTION_ACTIVATION_V1",
            version=1,
            selected_eligibility_rank=2,
        )


def test_tampered_plan_fails_closed_before_manifest_creation() -> None:
    investigation, company = _context()
    plan = _plan(investigation=investigation, company=company)
    object.__setattr__(plan, "plan_digest", "f" * 64)
    with pytest.raises(InvariantViolationError, match="digest"):
        build_collection_run(
            run_id=CollectionRunId.new(),
            operation_ids=tuple(CollectionOperationId.new() for _ in plan.capabilities),
            investigation=investigation,
            company=company,
            plan=plan,
            command_id=InvestigationCommandId.new(),
            command_digest="b" * 64,
            created_by=investigation.requested_by,
            created_at=NOW,
            activation_policy=COLLECTION_ACTIVATION_V1,
        )


def test_run_reconstitution_context_rejects_company_or_plan_divergence() -> None:
    investigation, company, plan, run = _build()
    collecting = investigation.start_collection(occurred_at=NOW).investigation
    validate_collection_run_context(run, investigation=collecting, company=company, plan=plan)
    object.__setattr__(run, "plan_digest", "e" * 64)
    with pytest.raises(InvariantViolationError, match="context"):
        validate_collection_run_context(run, investigation=collecting, company=company, plan=plan)
