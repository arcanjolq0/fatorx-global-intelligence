"""Tests for investigation initial snapshots and lifecycle vocabulary."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, cast

import pytest

from intelligence.domain.errors import InvalidDateTimeError, InvariantViolationError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CompanyId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.investigations import (
    INITIAL_STATE_VERSION,
    TERMINAL_INVESTIGATION_STATES,
    Investigation,
    InvestigationState,
)
from intelligence.domain.money import CurrencyCode, Money


def _investigation(**overrides: object) -> Investigation:
    values: dict[str, object] = {
        "id": InvestigationId.new(),
        "workspace_id": WorkspaceId.new(),
        "requested_by": UserId.new(),
        "profile_code": "  SUPPLIER_STANDARD  ",
        "country_code": CountryCode("BR"),
        "created_at": datetime(
            2026,
            7,
            25,
            9,
            tzinfo=timezone(-timedelta(hours=3)),
        ),
        "confirmed_company_id": CompanyId.new(),
        "budget": Money(Decimal("250.00"), CurrencyCode("BRL")),
        "deadline_at": datetime(2026, 7, 30, 12, tzinfo=UTC),
    }
    values.update(overrides)
    return Investigation(**cast(Any, values))


def test_investigation_starts_created_at_version_one_and_normalizes_time() -> None:
    investigation = _investigation()

    assert investigation.state is InvestigationState.CREATED
    assert investigation.state_version == INITIAL_STATE_VERSION == 1
    assert investigation.profile_code == "SUPPLIER_STANDARD"
    assert investigation.created_at == datetime(2026, 7, 25, 12, tzinfo=UTC)
    assert investigation.completed_at is None


def test_created_investigation_can_reference_existing_company() -> None:
    company_id = CompanyId.new()

    investigation = _investigation(confirmed_company_id=company_id)

    assert investigation.confirmed_company_id == company_id


def test_investigation_state_vocabulary_matches_documented_lifecycle() -> None:
    assert {state.value for state in InvestigationState} == {
        "CREATED",
        "IDENTIFYING",
        "WAITING_FOR_ENTITY_CONFIRMATION",
        "PLANNING",
        "COLLECTING",
        "NORMALIZING",
        "VERIFYING",
        "ANALYZING",
        "WAITING_FOR_REVIEW",
        "COMPLETED",
        "PARTIALLY_COMPLETED",
        "FAILED",
        "CANCELLED",
    }
    assert {
        InvestigationState.COMPLETED,
        InvestigationState.PARTIALLY_COMPLETED,
        InvestigationState.FAILED,
        InvestigationState.CANCELLED,
    } == TERMINAL_INVESTIGATION_STATES


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("id", "investigation"),
        ("workspace_id", "workspace"),
        ("requested_by", "user"),
        ("country_code", "BR"),
        ("state", "CREATED"),
        ("confirmed_company_id", "company"),
        ("budget", Decimal("1")),
    ],
)
def test_investigation_rejects_untyped_domain_fields(
    field_name: str,
    invalid_value: object,
) -> None:
    with pytest.raises(InvariantViolationError):
        _investigation(**{field_name: invalid_value})


def test_investigation_requires_profile_and_initial_state_version() -> None:
    with pytest.raises(InvariantViolationError):
        _investigation(profile_code="  ")
    with pytest.raises(InvariantViolationError):
        _investigation(state=InvestigationState.IDENTIFYING)
    with pytest.raises(InvariantViolationError):
        _investigation(state_version=2)
    with pytest.raises(InvariantViolationError):
        _investigation(state_version=cast(int, True))


def test_investigation_rejects_inconsistent_timestamps() -> None:
    with pytest.raises(InvariantViolationError):
        _investigation(started_at=datetime(2026, 7, 25, 11, tzinfo=UTC))
    with pytest.raises(InvariantViolationError):
        _investigation(
            started_at=None,
            completed_at=datetime(2026, 7, 25, 13, tzinfo=UTC),
        )
    with pytest.raises(InvariantViolationError):
        _investigation(
            started_at=datetime(2026, 7, 25, 14, tzinfo=UTC),
            completed_at=datetime(2026, 7, 25, 13, tzinfo=UTC),
        )
    with pytest.raises(InvariantViolationError):
        _investigation(
            completed_at=datetime(2026, 7, 25, 13, tzinfo=UTC),
        )
    with pytest.raises(InvalidDateTimeError):
        _investigation(deadline_at=datetime(2026, 7, 30, 12))


def test_created_investigation_rejects_started_at_and_expired_deadline() -> None:
    with pytest.raises(InvariantViolationError):
        _investigation(started_at=datetime(2026, 7, 25, 12, 1, tzinfo=UTC))
    with pytest.raises(InvariantViolationError):
        _investigation(deadline_at=datetime(2026, 7, 25, 11, 59, tzinfo=UTC))
