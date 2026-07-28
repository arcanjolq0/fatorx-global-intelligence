"""Company entity and invariants."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import CompanyId, WorkspaceId
from intelligence.domain.time import normalize_utc

_DOMAIN_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


class CompanyStatus(StrEnum):
    """Operational status of a company."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DISSOLVED = "DISSOLVED"


@dataclass(frozen=True, slots=True, kw_only=True)
class Company:
    """Immutable representation of a company within one workspace."""

    id: CompanyId
    workspace_id: WorkspaceId
    legal_name: str
    country_code: CountryCode
    status: CompanyStatus
    created_at: datetime
    updated_at: datetime
    trade_name: str | None = None
    legal_form: str | None = None
    incorporated_on: date | None = None
    dissolved_on: date | None = None
    official_domain: str | None = None

    def __post_init__(self) -> None:
        _validate_types(self)

        legal_name = _required_text(self.legal_name, field_name="Company legal name")
        trade_name = _optional_text(self.trade_name, field_name="Company trade name")
        legal_form = _optional_text(self.legal_form, field_name="Company legal form")
        official_domain = _normalize_domain(self.official_domain)
        created_at = normalize_utc(self.created_at)
        updated_at = normalize_utc(self.updated_at)

        if updated_at < created_at:
            raise InvariantViolationError("Company updated_at cannot precede created_at.")
        if (
            self.incorporated_on is not None
            and self.dissolved_on is not None
            and self.dissolved_on < self.incorporated_on
        ):
            raise InvariantViolationError("Company dissolved_on cannot precede incorporated_on.")
        if self.status is CompanyStatus.DISSOLVED and self.dissolved_on is None:
            raise InvariantViolationError("A dissolved company must define dissolved_on.")
        if self.status is not CompanyStatus.DISSOLVED and self.dissolved_on is not None:
            raise InvariantViolationError("Only a dissolved company may define dissolved_on.")

        object.__setattr__(self, "legal_name", legal_name)
        object.__setattr__(self, "trade_name", trade_name)
        object.__setattr__(self, "legal_form", legal_form)
        object.__setattr__(self, "official_domain", official_domain)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)


def _validate_types(company: Company) -> None:
    if not isinstance(company.id, CompanyId):
        raise InvariantViolationError("Company id must be a CompanyId.")
    if not isinstance(company.workspace_id, WorkspaceId):
        raise InvariantViolationError("Company workspace_id must be a WorkspaceId.")
    if not isinstance(company.country_code, CountryCode):
        raise InvariantViolationError("Company country_code must be a CountryCode.")
    if not isinstance(company.status, CompanyStatus):
        raise InvariantViolationError("Company status must be a CompanyStatus.")
    _validate_optional_date(company.incorporated_on, field_name="incorporated_on")
    _validate_optional_date(company.dissolved_on, field_name="dissolved_on")


def _validate_optional_date(value: date | None, *, field_name: str) -> None:
    if value is not None and (not isinstance(value, date) or isinstance(value, datetime)):
        raise InvariantViolationError(f"Company {field_name} must be a date.")


def _required_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvariantViolationError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name=field_name)


def _normalize_domain(value: str | None) -> str | None:
    if value is None:
        return None
    domain = value.strip().lower()
    if not domain or len(domain) > 253 or domain.endswith("."):
        raise InvariantViolationError("Company official_domain has an invalid format.")
    if any(character.isspace() for character in domain):
        raise InvariantViolationError("Company official_domain cannot contain whitespace.")
    if any(character in domain for character in "/:@?#"):
        raise InvariantViolationError(
            "Company official_domain must contain only a host name, without URL parts."
        )
    labels = domain.split(".")
    if any(not _DOMAIN_LABEL_PATTERN.fullmatch(label) for label in labels):
        raise InvariantViolationError("Company official_domain has an invalid format.")
    return domain


__all__ = ["Company", "CompanyStatus"]
