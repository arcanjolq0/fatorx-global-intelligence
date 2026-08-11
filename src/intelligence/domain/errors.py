"""Framework-independent errors raised by domain invariants."""


class DomainError(Exception):
    """Base class for expected domain validation failures."""


class InvalidIdentifierError(DomainError):
    """An internal identifier is missing or malformed."""


class InvalidCountryCodeError(DomainError):
    """A country code does not satisfy the canonical format."""


class InvalidCurrencyCodeError(DomainError):
    """A currency code does not satisfy the canonical format."""


class InvalidMoneyError(DomainError):
    """A monetary value is invalid or used with an incompatible currency."""


class InvalidDateTimeError(DomainError):
    """A domain timestamp is missing timezone information or is invalid."""


class InvalidEmailAddressError(DomainError):
    """An email address does not satisfy the internal canonical format."""


class InvariantViolationError(DomainError):
    """An entity would be created in an inconsistent business state."""


class InvalidIdentificationInputError(DomainError):
    """An identification input violates its closed, versioned contract."""


class InvalidInvestigationTransitionError(InvariantViolationError):
    """An investigation command is invalid for the current snapshot."""


__all__ = (
    "DomainError",
    "InvalidCountryCodeError",
    "InvalidCurrencyCodeError",
    "InvalidDateTimeError",
    "InvalidEmailAddressError",
    "InvalidIdentificationInputError",
    "InvalidIdentifierError",
    "InvalidInvestigationTransitionError",
    "InvalidMoneyError",
    "InvariantViolationError",
)
