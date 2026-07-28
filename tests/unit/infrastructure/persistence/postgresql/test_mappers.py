"""Pure mapper tests without a database."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from intelligence.application.errors import PersistenceDataError
from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CompanyId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.investigations import Investigation, InvestigationState
from intelligence.domain.money import CurrencyCode, Money
from intelligence.domain.workspaces import Workspace, WorkspaceStatus
from intelligence.infrastructure.persistence.postgresql.mappers import (
    company_from_values,
    company_to_values,
    investigation_from_values,
    investigation_to_values,
    workspace_from_values,
    workspace_to_values,
)

CREATED_AT = datetime(2026, 7, 28, 12, tzinfo=UTC)


def _workspace(*, status: WorkspaceStatus = WorkspaceStatus.ACTIVE) -> Workspace:
    return Workspace(
        id=WorkspaceId.new(),
        name="Workspace",
        status=status,
        retention_policy_version="2026-01",
        created_at=CREATED_AT,
        updated_at=CREATED_AT + timedelta(minutes=1),
    )


def _company(workspace_id: WorkspaceId) -> Company:
    return Company(
        id=CompanyId.new(),
        workspace_id=workspace_id,
        legal_name="Empresa Ltda.",
        trade_name="Empresa",
        country_code=CountryCode("BR"),
        legal_form="Limitada",
        status=CompanyStatus.DISSOLVED,
        incorporated_on=date(2020, 1, 2),
        dissolved_on=date(2025, 3, 4),
        official_domain="empresa.example",
        created_at=CREATED_AT,
        updated_at=CREATED_AT + timedelta(minutes=1),
    )


def _investigation(workspace_id: WorkspaceId, company_id: CompanyId) -> Investigation:
    return Investigation.reconstitute(
        id=InvestigationId.new(),
        workspace_id=workspace_id,
        requested_by=UserId.new(),
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        state=InvestigationState.COMPLETED,
        state_version=11,
        confirmed_company_id=company_id,
        budget=Money(
            Decimal("12345678901234567890.12345678901234567890"),
            CurrencyCode("BRL"),
        ),
        deadline_at=CREATED_AT + timedelta(days=2),
        started_at=CREATED_AT + timedelta(minutes=1),
        completed_at=CREATED_AT + timedelta(minutes=2),
        created_at=CREATED_AT,
    )


@pytest.mark.parametrize("status", list(WorkspaceStatus))
def test_workspace_mapper_round_trip_preserves_strong_types_and_status(
    status: WorkspaceStatus,
) -> None:
    workspace = _workspace(status=status)

    restored = workspace_from_values(workspace_to_values(workspace))

    assert restored == workspace
    assert isinstance(restored.id, WorkspaceId)
    assert restored.status is status


def test_workspace_mapper_normalizes_aware_timestamps_to_utc() -> None:
    workspace = _workspace()
    values = workspace_to_values(workspace)
    values["created_at"] = datetime(
        2026,
        7,
        28,
        9,
        tzinfo=timezone(-timedelta(hours=3)),
    )

    restored = workspace_from_values(values)

    assert restored.created_at == CREATED_AT


def test_company_mapper_round_trip_preserves_all_optional_fields() -> None:
    company = _company(WorkspaceId.new())

    restored = company_from_values(company_to_values(company))

    assert restored == company
    assert isinstance(restored.id, CompanyId)
    assert isinstance(restored.workspace_id, WorkspaceId)
    assert restored.incorporated_on == date(2020, 1, 2)


def test_investigation_mapper_round_trip_preserves_decimal_and_persisted_state() -> None:
    investigation = _investigation(WorkspaceId.new(), CompanyId.new())

    restored = investigation_from_values(investigation_to_values(investigation))

    assert restored == investigation
    assert isinstance(restored.id, InvestigationId)
    assert isinstance(restored.requested_by, UserId)
    assert restored.state is InvestigationState.COMPLETED
    assert restored.state_version == 11
    assert restored.budget is not None
    assert restored.budget.amount == Decimal("12345678901234567890.12345678901234567890")


@pytest.mark.parametrize(
    ("mapper", "values"),
    [
        (workspace_from_values, {}),
        (
            workspace_from_values,
            {**workspace_to_values(_workspace()), "id": "not-a-native-uuid"},
        ),
        (
            company_from_values,
            {
                **company_to_values(_company(WorkspaceId.new())),
                "incorporated_on": CREATED_AT,
            },
        ),
        (
            investigation_from_values,
            {
                **investigation_to_values(_investigation(WorkspaceId.new(), CompanyId.new())),
                "budget_currency": None,
            },
        ),
        (
            investigation_from_values,
            {
                **investigation_to_values(_investigation(WorkspaceId.new(), CompanyId.new())),
                "state": "IDENTIFYING",
                "started_at": None,
                "completed_at": None,
            },
        ),
    ],
)
def test_mappers_reject_missing_mistyped_or_inconsistent_rows(
    mapper: object,
    values: dict[str, object],
) -> None:
    with pytest.raises(PersistenceDataError):
        if mapper is workspace_from_values:
            workspace_from_values(values)
        elif mapper is company_from_values:
            company_from_values(values)
        else:
            investigation_from_values(values)
