"""Typed failures for the canonical evidence core."""

from intelligence.domain.errors import DomainError


class EvidenceError(DomainError):
    """Base failure for evidence invariants and application rules."""


class EvidenceIntegrityError(EvidenceError):
    """Persisted or supplied evidence failed a custody-integrity check."""


class EvidenceHistoryError(EvidenceError):
    """A version series or its lifecycle events are inconsistent."""


class EvidenceAdmissibilityError(EvidenceError):
    """A global Evidence admissibility invariant was violated."""


class EvidenceAdmissibilityHistoryError(EvidenceAdmissibilityError):
    """An admissibility decision chain is incomplete or inconsistent."""


class EvidenceAdmissibilityIntegrityError(EvidenceAdmissibilityError):
    """An admissibility decision digest is invalid."""


class EvidenceNotExistingAtCutoffError(EvidenceAdmissibilityError):
    """Evidence did not yet exist at the requested historical cutoff."""


__all__ = [
    "EvidenceAdmissibilityError",
    "EvidenceAdmissibilityHistoryError",
    "EvidenceAdmissibilityIntegrityError",
    "EvidenceError",
    "EvidenceHistoryError",
    "EvidenceIntegrityError",
    "EvidenceNotExistingAtCutoffError",
]
