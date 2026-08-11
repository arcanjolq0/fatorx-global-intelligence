"""F4.4 deterministic planning policy, graph, ordering, and digest tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from intelligence.connectors.descriptor import ConnectorDescriptor
from intelligence.connectors.enums import (
    ConnectorAccessType,
    ConnectorCapability,
    ConnectorCoverageKind,
    ConnectorOperation,
)
from intelligence.connectors.identifiers import ConnectorId, SourceId
from intelligence.connectors.versions import CONNECTOR_CONTRACT_VERSION, SemanticVersion
from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CompanyId,
    EntityCandidateBatchId,
    InvestigationCommandId,
    InvestigationId,
    InvestigationPlanId,
    PlannedCapabilityId,
    PlannedConnectorOptionId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.investigation_inputs import IdentificationInput, OriginalAndNormalizedText
from intelligence.domain.investigations import (
    TERMINAL_INVESTIGATION_STATES,
    Investigation,
    InvestigationState,
)
from intelligence.domain.money import CurrencyCode, Money
from intelligence.orchestration.errors import (
    InvalidPlanningDependencyError,
    PlanningBudgetExceededError,
    PlanningDeadlineExceededError,
    RequiredCapabilityUnavailableError,
    UnsupportedPlanningProfileError,
)
from intelligence.orchestration.planning import (
    INVESTIGATION_PLANNING_V1,
    EstimatedCostKind,
    InvestigationPlan,
    PlannedCapabilityStatus,
    PlanningCapabilityRule,
    PlanningPolicy,
    PlanningReason,
    build_investigation_plan,
    count_eligible_options,
    investigation_plan_digest,
    validate_investigation_plan_context,
)

NOW = datetime(2026, 8, 1, 18, tzinfo=UTC)
ALL_CAPABILITIES = tuple(ConnectorCapability)
PLAN_CONTINUITY_STATES = (
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
)


def _descriptor(
    connector_id: str,
    *,
    coverage: ConnectorCoverageKind = ConnectorCoverageKind.COUNTRY_SET,
    capabilities: tuple[ConnectorCapability, ...] = ALL_CAPABILITIES,
) -> ConnectorDescriptor:
    return ConnectorDescriptor(
        connector_id=ConnectorId(connector_id),
        version=SemanticVersion(1, 2, 0),
        contract_version=CONNECTOR_CONTRACT_VERSION,
        source_id=SourceId(f"source.{connector_id}"),
        coverage_kind=coverage,
        countries=(CountryCode("BR"),) if coverage is ConnectorCoverageKind.COUNTRY_SET else (),
        capabilities=capabilities,
        operations=(ConnectorOperation.SEARCH, ConnectorOperation.FETCH_DETAILS),
        access_type=ConnectorAccessType.API,
    )


def _context(
    *,
    profile_code: str = "SUPPLIER_STANDARD",
    deadline_at: datetime | None = NOW + timedelta(hours=3),
    budget: Money | None = None,
) -> tuple[Investigation, Company]:
    workspace_id = WorkspaceId.new()
    user_id = UserId.new()
    company = Company(
        id=CompanyId.new(),
        workspace_id=workspace_id,
        legal_name="Empresa Exemplo S.A.",
        country_code=CountryCode("BR"),
        status=CompanyStatus.ACTIVE,
        created_at=NOW - timedelta(minutes=5),
        updated_at=NOW - timedelta(minutes=5),
    )
    input_value = IdentificationInput(
        legal_name=OriginalAndNormalizedText(
            original_value="Empresa Exemplo S.A.",
            normalized_value="empresa exemplo s.a.",
        )
    )
    investigation = Investigation.reconstitute(
        id=InvestigationId.new(),
        workspace_id=workspace_id,
        requested_by=user_id,
        profile_code=profile_code,
        country_code=CountryCode("BR"),
        created_at=NOW - timedelta(hours=1),
        state=InvestigationState.PLANNING,
        state_version=4,
        confirmed_company_id=company.id,
        budget=budget,
        deadline_at=deadline_at,
        started_at=NOW - timedelta(minutes=30),
        identification_input=input_value,
    )
    return investigation, company


def _plan(
    *,
    descriptors: tuple[ConnectorDescriptor, ...] | None = None,
    investigation: Investigation | None = None,
    company: Company | None = None,
) -> InvestigationPlan:
    if investigation is None or company is None:
        investigation, company = _context()
    selected = descriptors or (_descriptor("country.connector"),)
    option_count = count_eligible_options(
        INVESTIGATION_PLANNING_V1,
        selected,
        company.country_code.value,
    )
    return build_investigation_plan(
        plan_id=InvestigationPlanId.new(),
        capability_ids=tuple(
            PlannedCapabilityId.new() for _ in INVESTIGATION_PLANNING_V1.capability_rules
        ),
        option_ids=tuple(PlannedConnectorOptionId.new() for _ in range(option_count)),
        investigation=investigation,
        company=company,
        command_id=InvestigationCommandId.new(),
        command_digest="a" * 64,
        created_by=investigation.requested_by,
        created_at=NOW,
        policy=INVESTIGATION_PLANNING_V1,
        descriptors=selected,
    )


def _current_snapshot(
    investigation: Investigation,
    *,
    state: InvestigationState,
    state_version: int,
) -> Investigation:
    before_confirmation = {
        InvestigationState.CREATED,
        InvestigationState.IDENTIFYING,
        InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION,
    }
    return Investigation.reconstitute(
        id=investigation.id,
        workspace_id=investigation.workspace_id,
        requested_by=investigation.requested_by,
        profile_code=investigation.profile_code,
        country_code=investigation.country_code,
        created_at=investigation.created_at,
        state=state,
        state_version=state_version,
        confirmed_company_id=(
            None if state in before_confirmation else investigation.confirmed_company_id
        ),
        budget=investigation.budget,
        deadline_at=investigation.deadline_at,
        started_at=None if state is InvestigationState.CREATED else investigation.started_at,
        completed_at=NOW if state in TERMINAL_INVESTIGATION_STATES else None,
        identification_input=(
            None if state is InvestigationState.CREATED else investigation.identification_input
        ),
        active_candidate_batch_id=(
            EntityCandidateBatchId.new()
            if state is InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION
            else None
        ),
    )


def test_policy_snapshot_digest_and_plan_digest_are_deterministic() -> None:
    snapshot = INVESTIGATION_PLANNING_V1.to_canonical_json()
    assert PlanningPolicy.from_canonical_json(snapshot) == INVESTIGATION_PLANNING_V1
    assert INVESTIGATION_PLANNING_V1.digest == INVESTIGATION_PLANNING_V1.digest
    plan = _plan()
    assert plan.plan_digest == investigation_plan_digest(plan)
    assert len(plan.plan_digest) == 64


def test_policy_contains_closed_v1_capabilities_and_ownership_dependency() -> None:
    capabilities = tuple(rule.capability for rule in INVESTIGATION_PLANNING_V1.capability_rules)
    assert capabilities == ALL_CAPABILITIES
    ownership = next(
        rule
        for rule in INVESTIGATION_PLANNING_V1.capability_rules
        if rule.capability is ConnectorCapability.OWNERSHIP
    )
    assert ownership.dependencies == (ConnectorCapability.COMPANY_REGISTRY,)
    sanctions = next(
        rule
        for rule in INVESTIGATION_PLANNING_V1.capability_rules
        if rule.capability is ConnectorCapability.SANCTIONS
    )
    assert sanctions.dependencies == ()


def test_exact_country_precedes_global_then_connector_id() -> None:
    plan = _plan(
        descriptors=(
            _descriptor("z.global", coverage=ConnectorCoverageKind.GLOBAL),
            _descriptor("z.country"),
            _descriptor("a.country"),
        )
    )
    registration = next(
        item
        for item in plan.capabilities
        if item.capability is ConnectorCapability.COMPANY_REGISTRY
    )
    assert [item.connector_id.value for item in registration.connector_options] == [
        "a.country",
        "z.country",
        "z.global",
    ]
    assert [item.eligibility_rank for item in registration.connector_options] == [1, 2, 3]


def test_optional_capabilities_without_connector_remain_explicitly_unavailable() -> None:
    plan = _plan(
        descriptors=(
            _descriptor(
                "required.only",
                capabilities=(
                    ConnectorCapability.COMPANY_IDENTITY,
                    ConnectorCapability.COMPANY_REGISTRY,
                ),
            ),
        )
    )
    assert len(plan.capabilities) == 10
    assert (
        sum(
            item.status is PlannedCapabilityStatus.OPTIONAL_UNAVAILABLE
            for item in plan.capabilities
        )
        == 8
    )


def test_required_capability_without_connector_fails_closed() -> None:
    with pytest.raises(RequiredCapabilityUnavailableError):
        _plan(
            descriptors=(
                _descriptor(
                    "identity.only",
                    capabilities=(ConnectorCapability.COMPANY_IDENTITY,),
                ),
            )
        )


def test_missing_dependency_and_cycle_are_rejected() -> None:
    registration = PlanningCapabilityRule(
        capability=ConnectorCapability.COMPANY_REGISTRY,
        required=True,
        priority=10,
        reason=PlanningReason.BUSINESS_REGISTRATION,
        dependencies=(ConnectorCapability.OWNERSHIP,),
        estimated_duration_seconds=1,
    )
    with pytest.raises(InvalidPlanningDependencyError):
        PlanningPolicy(
            policy_id="TEST_POLICY",
            version=1,
            supported_profiles=("SUPPLIER_STANDARD",),
            capability_rules=(registration,),
            supported_contract_major=1,
        )
    ownership = PlanningCapabilityRule(
        capability=ConnectorCapability.OWNERSHIP,
        required=False,
        priority=20,
        reason=PlanningReason.OWNERSHIP_STRUCTURE,
        dependencies=(ConnectorCapability.COMPANY_REGISTRY,),
        estimated_duration_seconds=1,
    )
    with pytest.raises(InvalidPlanningDependencyError):
        PlanningPolicy(
            policy_id="TEST_POLICY",
            version=1,
            supported_profiles=("SUPPLIER_STANDARD",),
            capability_rules=(registration, ownership),
            supported_contract_major=1,
        )


def test_unknown_profile_and_incompatible_deadline_are_typed() -> None:
    investigation, company = _context(profile_code="UNKNOWN_PROFILE")
    with pytest.raises(UnsupportedPlanningProfileError):
        _plan(investigation=investigation, company=company)


def test_optional_unavailable_capabilities_do_not_consume_deadline() -> None:
    investigation, company = _context(deadline_at=NOW + timedelta(hours=1))
    plan = _plan(
        investigation=investigation,
        company=company,
        descriptors=(
            _descriptor(
                "required.only",
                capabilities=(
                    ConnectorCapability.COMPANY_IDENTITY,
                    ConnectorCapability.COMPANY_REGISTRY,
                ),
            ),
        ),
    )

    assert sum(item.status is PlannedCapabilityStatus.READY for item in plan.capabilities) == 2
    assert (
        sum(
            item.status is PlannedCapabilityStatus.OPTIONAL_UNAVAILABLE
            for item in plan.capabilities
        )
        == 8
    )

    investigation, company = _context(deadline_at=NOW + timedelta(minutes=30))
    with pytest.raises(PlanningDeadlineExceededError):
        _plan(investigation=investigation, company=company)


def test_known_cost_above_budget_is_rejected_even_though_v1_descriptors_have_unknown_cost() -> None:
    currency = CurrencyCode("USD")
    investigation, company = _context(budget=Money(Decimal("0"), currency))
    plan = _plan(investigation=investigation, company=company)
    known_capabilities = tuple(
        replace(
            item,
            estimated_cost_kind=EstimatedCostKind.KNOWN,
            estimated_cost=Money(Decimal("1"), currency),
        )
        if item.connector_options
        else item
        for item in plan.capabilities
    )
    known_total = sum(1 for item in known_capabilities if item.connector_options)
    with pytest.raises(PlanningBudgetExceededError):
        replace(
            plan,
            capabilities=known_capabilities,
            maximum_estimated_cost_kind=EstimatedCostKind.KNOWN,
            maximum_estimated_cost=Money(Decimal(known_total), currency),
        )


def test_context_rejects_company_swap_and_state_or_version_regression() -> None:
    investigation, company = _context()
    plan = _plan(investigation=investigation, company=company)
    validate_investigation_plan_context(plan, investigation=investigation, company=company)
    swapped = replace(company, id=CompanyId.new())
    with pytest.raises(InvariantViolationError):
        validate_investigation_plan_context(plan, investigation=investigation, company=swapped)
    regressed = Investigation.reconstitute(
        id=investigation.id,
        workspace_id=investigation.workspace_id,
        requested_by=investigation.requested_by,
        profile_code=investigation.profile_code,
        country_code=investigation.country_code,
        created_at=investigation.created_at,
        state=InvestigationState.PLANNING,
        state_version=3,
        confirmed_company_id=company.id,
        deadline_at=investigation.deadline_at,
        started_at=investigation.started_at,
        identification_input=investigation.identification_input,
    )
    with pytest.raises(InvariantViolationError):
        validate_investigation_plan_context(plan, investigation=regressed, company=company)


@pytest.mark.parametrize("state", PLAN_CONTINUITY_STATES)
def test_context_accepts_plan_after_every_allowed_lifecycle_state(
    state: InvestigationState,
) -> None:
    investigation, company = _context()
    plan = _plan(investigation=investigation, company=company)
    current = _current_snapshot(investigation, state=state, state_version=5)

    validate_investigation_plan_context(plan, investigation=current, company=company)


@pytest.mark.parametrize(
    "state",
    (
        InvestigationState.CREATED,
        InvestigationState.IDENTIFYING,
        InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION,
    ),
)
def test_context_rejects_states_before_confirmation(state: InvestigationState) -> None:
    investigation, company = _context()
    plan = _plan(investigation=investigation, company=company)
    previous = _current_snapshot(investigation, state=state, state_version=5)

    with pytest.raises(InvariantViolationError):
        validate_investigation_plan_context(plan, investigation=previous, company=company)


def test_context_requires_planning_when_version_equals_plan_creation() -> None:
    investigation, company = _context()
    plan = _plan(investigation=investigation, company=company)
    same_version_wrong_state = _current_snapshot(
        investigation,
        state=InvestigationState.COLLECTING,
        state_version=plan.investigation_state_version,
    )

    with pytest.raises(InvariantViolationError):
        validate_investigation_plan_context(
            plan,
            investigation=same_version_wrong_state,
            company=company,
        )


def test_context_rejects_reintroduced_active_batch() -> None:
    investigation, company = _context()
    plan = _plan(investigation=investigation, company=company)
    current = _current_snapshot(
        investigation,
        state=InvestigationState.COLLECTING,
        state_version=5,
    )
    object.__setattr__(current, "active_candidate_batch_id", EntityCandidateBatchId.new())

    with pytest.raises(InvariantViolationError):
        validate_investigation_plan_context(plan, investigation=current, company=company)
