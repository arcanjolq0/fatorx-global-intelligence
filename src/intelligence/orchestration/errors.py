"""Typed failures raised by deterministic investigation orchestration."""

from intelligence.domain.errors import DomainError


class InvestigationPlanningError(DomainError):
    """Base error for invalid or infeasible deterministic plans."""


class UnsupportedPlanningPolicyError(InvestigationPlanningError):
    """The supplied policy is not the single supported planning policy."""


class UnsupportedPlanningProfileError(InvestigationPlanningError):
    """The persisted investigation profile has no closed V1 mapping."""


class RequiredCapabilityUnavailableError(InvestigationPlanningError):
    """A required capability has no statically eligible connector."""


class InvalidPlanningDependencyError(InvestigationPlanningError):
    """Capability dependencies are absent or cyclic."""


class PlanningBudgetExceededError(InvestigationPlanningError):
    """A known maximum plan cost exceeds the persisted investigation budget."""


class PlanningDeadlineExceededError(InvestigationPlanningError):
    """The deterministic critical path does not fit before the deadline."""


class CollectionActivationDeadlineExceededError(DomainError):
    """The persisted READY-operation critical path no longer fits before the deadline."""


__all__ = [
    "CollectionActivationDeadlineExceededError",
    "InvalidPlanningDependencyError",
    "InvestigationPlanningError",
    "PlanningBudgetExceededError",
    "PlanningDeadlineExceededError",
    "RequiredCapabilityUnavailableError",
    "UnsupportedPlanningPolicyError",
    "UnsupportedPlanningProfileError",
]
