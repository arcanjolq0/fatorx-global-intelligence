"""Explicit deterministic scenarios exposed by synthetic connector fixtures."""

from enum import StrEnum


class BusinessRegistryScenario(StrEnum):
    """Closed scenario vocabulary for the synthetic business registry connector."""

    SUCCESS = "SUCCESS"
    NO_RESULTS = "NO_RESULTS"
    MULTIPLE_CANDIDATES = "MULTIPLE_CANDIDATES"
    PARTIAL = "PARTIAL"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    CANCELLED = "CANCELLED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


__all__ = ["BusinessRegistryScenario"]
