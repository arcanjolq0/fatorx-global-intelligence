"""Fundamental domain types without framework dependencies."""

from intelligence.domain.audit import (
    ACTION_CODE_MAX_LENGTH,
    REASON_CODE_MAX_LENGTH,
    AuditEvent,
    AuditOutcome,
    AuditResourceId,
    AuditResourceType,
)
from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.errors import (
    DomainError,
    InvalidCountryCodeError,
    InvalidCurrencyCodeError,
    InvalidDateTimeError,
    InvalidEmailAddressError,
    InvalidIdentifierError,
    InvalidMoneyError,
    InvariantViolationError,
)
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    AuditEventId,
    CompanyId,
    CorrelationId,
    InvestigationId,
    MembershipId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.identities import (
    EMAIL_ADDRESS_MAX_LENGTH,
    EmailAddress,
    MembershipRole,
    MembershipStatus,
    UserAccount,
    UserAccountStatus,
    WorkspaceMembership,
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
    "ACTION_CODE_MAX_LENGTH",
    "EMAIL_ADDRESS_MAX_LENGTH",
    "INITIAL_STATE_VERSION",
    "REASON_CODE_MAX_LENGTH",
    "TERMINAL_INVESTIGATION_STATES",
    "AuditEvent",
    "AuditEventId",
    "AuditOutcome",
    "AuditResourceId",
    "AuditResourceType",
    "Company",
    "CompanyId",
    "CompanyStatus",
    "CorrelationId",
    "CountryCode",
    "CurrencyCode",
    "DomainError",
    "EmailAddress",
    "InvalidCountryCodeError",
    "InvalidCurrencyCodeError",
    "InvalidDateTimeError",
    "InvalidEmailAddressError",
    "InvalidIdentifierError",
    "InvalidMoneyError",
    "InvariantViolationError",
    "Investigation",
    "InvestigationId",
    "InvestigationState",
    "MembershipId",
    "MembershipRole",
    "MembershipStatus",
    "Money",
    "UserAccount",
    "UserAccountStatus",
    "UserId",
    "Workspace",
    "WorkspaceId",
    "WorkspaceMembership",
    "WorkspaceStatus",
    "normalize_utc",
]
