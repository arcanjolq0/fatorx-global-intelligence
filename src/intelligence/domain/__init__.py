"""Fundamental domain types without framework dependencies."""

from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.errors import (
    DomainError,
    InvalidCountryCodeError,
    InvalidCurrencyCodeError,
    InvalidDateTimeError,
    InvalidIdentifierError,
    InvalidMoneyError,
    InvariantViolationError,
)
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
from intelligence.domain.time import normalize_utc
from intelligence.domain.workspaces import Workspace, WorkspaceStatus

__all__ = [
    "INITIAL_STATE_VERSION",
    "TERMINAL_INVESTIGATION_STATES",
    "Company",
    "CompanyId",
    "CompanyStatus",
    "CountryCode",
    "CurrencyCode",
    "DomainError",
    "InvalidCountryCodeError",
    "InvalidCurrencyCodeError",
    "InvalidDateTimeError",
    "InvalidIdentifierError",
    "InvalidMoneyError",
    "InvariantViolationError",
    "Investigation",
    "InvestigationId",
    "InvestigationState",
    "Money",
    "UserId",
    "Workspace",
    "WorkspaceId",
    "WorkspaceStatus",
    "normalize_utc",
]
