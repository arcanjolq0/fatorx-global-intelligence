"""Typed validation failures for the pure entity-resolution boundary."""

from intelligence.domain.errors import DomainError


class EntityResolutionError(DomainError):
    """Base class for deterministic entity-resolution contract failures."""


class InvalidCandidateError(EntityResolutionError):
    """A candidate identity or origin violates the closed schema."""


class InvalidCandidateBatchError(EntityResolutionError):
    """A candidate batch is empty, excessive, duplicated, or malformed."""


class InvalidMatchingPolicyError(EntityResolutionError):
    """A matching policy is incomplete, inconsistent, or unsafe."""


class InvalidMatchEvaluationError(EntityResolutionError):
    """A dimensional evaluation or ranking is inconsistent."""


__all__ = [
    "EntityResolutionError",
    "InvalidCandidateBatchError",
    "InvalidCandidateError",
    "InvalidMatchEvaluationError",
    "InvalidMatchingPolicyError",
]
