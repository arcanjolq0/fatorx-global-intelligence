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


class InvariantViolationError(DomainError):
    """An entity would be created in an inconsistent business state."""


__all__ = (
    "DomainError",
    "InvalidCountryCodeError",
    "InvalidCurrencyCodeError",
    "InvalidDateTimeError",
    "InvalidIdentifierError",
    "InvalidMoneyError",
    "InvariantViolationError",
)
