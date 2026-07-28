"""Strongly typed UUID identifiers used by domain entities."""

from dataclasses import dataclass
from typing import Self
from uuid import UUID, uuid4

from .errors import InvalidIdentifierError


@dataclass(frozen=True, slots=True)
class _UUIDIdentifier:
    """Shared behavior for identifiers whose concrete classes stay distinct."""

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID) or self.value.int == 0:
            raise InvalidIdentifierError(f"{type(self).__name__} must contain a non-zero UUID.")

    @classmethod
    def new(cls) -> Self:
        """Create a new random identifier."""

        return cls(uuid4())

    @classmethod
    def from_value(cls, value: UUID | str) -> Self:
        """Reconstruct an identifier from a UUID or canonical UUID text."""

        if isinstance(value, UUID):
            return cls(value)

        try:
            parsed = UUID(value)
        except (ValueError, AttributeError) as error:
            raise InvalidIdentifierError(
                f"{cls.__name__} must be reconstructed from canonical UUID text."
            ) from error

        if value.lower() != str(parsed):
            raise InvalidIdentifierError(
                f"{cls.__name__} must be reconstructed from canonical UUID text."
            )
        return cls(parsed)

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"{type(self).__name__}('{self.value}')"


class WorkspaceId(_UUIDIdentifier):
    """Identifier for a workspace aggregate."""


class UserId(_UUIDIdentifier):
    """Identifier for an internal user reference."""


class CompanyId(_UUIDIdentifier):
    """Identifier for a canonical company."""


class InvestigationId(_UUIDIdentifier):
    """Identifier for an investigation aggregate."""


class MembershipId(_UUIDIdentifier):
    """Identifier for one user membership within a workspace."""


class AuditEventId(_UUIDIdentifier):
    """Identifier for an immutable audit event."""


class CorrelationId(_UUIDIdentifier):
    """Identifier used to correlate related operations and audit events."""


__all__ = (
    "AuditEventId",
    "CompanyId",
    "CorrelationId",
    "InvestigationId",
    "MembershipId",
    "UserId",
    "WorkspaceId",
)
