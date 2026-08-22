"""Typed failures for the immutable claims domain."""

from intelligence.domain.errors import DomainError


class ClaimError(DomainError):
    """Base class for claim validation failures."""


class ClaimIntegrityError(ClaimError):
    """A claim or link digest does not match its canonical payload."""


class ClaimHistoryError(ClaimError):
    """A persisted claim series cannot be reconstituted safely."""


__all__ = ["ClaimError", "ClaimHistoryError", "ClaimIntegrityError"]
