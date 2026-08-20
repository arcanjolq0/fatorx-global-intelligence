"""Typed failures for the canonical evidence core."""

from intelligence.domain.errors import DomainError


class EvidenceError(DomainError):
    """Base failure for evidence invariants and application rules."""


class EvidenceIntegrityError(EvidenceError):
    """Persisted or supplied evidence failed a custody-integrity check."""


class EvidenceHistoryError(EvidenceError):
    """A version series or its lifecycle events are inconsistent."""


__all__ = ["EvidenceError", "EvidenceHistoryError", "EvidenceIntegrityError"]
