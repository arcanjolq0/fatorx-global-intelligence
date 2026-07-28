"""Tests for company entity invariants."""

from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any, cast

import pytest

from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.errors import InvalidDateTimeError, InvariantViolationError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import CompanyId, WorkspaceId


def _company(**overrides: object) -> Company:
    values: dict[str, object] = {
        "id": CompanyId.new(),
        "workspace_id": WorkspaceId.new(),
        "legal_name": "  Fator X Ltda.  ",
        "trade_name": "  Fator X  ",
        "country_code": CountryCode("BR"),
        "legal_form": "  Limitada  ",
        "status": CompanyStatus.ACTIVE,
        "incorporated_on": date(2020, 1, 10),
        "official_domain": "  FATORX.EXAMPLE  ",
        "created_at": datetime(
            2026,
            7,
            25,
            9,
            tzinfo=timezone(-timedelta(hours=3)),
        ),
        "updated_at": datetime(2026, 7, 25, 13, tzinfo=UTC),
    }
    values.update(overrides)
    return Company(**cast(Any, values))


def test_company_normalizes_text_domain_and_timestamps() -> None:
    company = _company()

    assert company.legal_name == "Fator X Ltda."
    assert company.trade_name == "Fator X"
    assert company.legal_form == "Limitada"
    assert company.official_domain == "fatorx.example"
    assert company.created_at == datetime(2026, 7, 25, 12, tzinfo=UTC)


def test_company_keeps_workspace_as_explicit_tenant_boundary() -> None:
    first_workspace = WorkspaceId.new()
    second_workspace = WorkspaceId.new()

    assert _company(workspace_id=first_workspace).workspace_id == first_workspace
    assert _company(workspace_id=second_workspace).workspace_id == second_workspace


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [("legal_name", " "), ("trade_name", ""), ("legal_form", "  ")],
)
def test_company_rejects_empty_present_text(field_name: str, invalid_value: str) -> None:
    with pytest.raises(InvariantViolationError):
        _company(**{field_name: invalid_value})


@pytest.mark.parametrize(
    "domain",
    [
        "https://fatorx.example",
        "fatorx.example/path",
        "user@fatorx.example",
        "fatorx.example:443",
        "fator x.example",
        "-fatorx.example",
        "fatorx..example",
        "fatorx.example.",
        "",
    ],
)
def test_company_rejects_url_parts_or_invalid_official_domain(domain: str) -> None:
    with pytest.raises(InvariantViolationError):
        _company(official_domain=domain)


def test_company_dissolution_invariants() -> None:
    with pytest.raises(InvariantViolationError):
        _company(status=CompanyStatus.DISSOLVED, dissolved_on=None)
    with pytest.raises(InvariantViolationError):
        _company(status=CompanyStatus.ACTIVE, dissolved_on=date(2025, 1, 1))
    with pytest.raises(InvariantViolationError):
        _company(
            status=CompanyStatus.DISSOLVED,
            incorporated_on=date(2025, 1, 1),
            dissolved_on=date(2024, 1, 1),
        )

    company = _company(
        status=CompanyStatus.DISSOLVED,
        dissolved_on=date(2025, 1, 1),
    )
    assert company.dissolved_on == date(2025, 1, 1)


def test_company_rejects_invalid_types_and_timestamp_order() -> None:
    with pytest.raises(InvariantViolationError):
        _company(id=cast(CompanyId, "company"))
    with pytest.raises(InvariantViolationError):
        _company(workspace_id=cast(WorkspaceId, "workspace"))
    with pytest.raises(InvariantViolationError):
        _company(country_code=cast(CountryCode, "BR"))
    with pytest.raises(InvariantViolationError):
        _company(status=cast(CompanyStatus, "ACTIVE"))
    with pytest.raises(InvariantViolationError):
        _company(incorporated_on=cast(date, datetime(2020, 1, 1, tzinfo=UTC)))
    with pytest.raises(InvariantViolationError):
        _company(updated_at=datetime(2026, 7, 25, 11, tzinfo=UTC))
    with pytest.raises(InvalidDateTimeError):
        _company(created_at=datetime(2026, 7, 25, 12))
