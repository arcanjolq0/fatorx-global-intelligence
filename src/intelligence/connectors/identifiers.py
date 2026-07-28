"""Strong identifiers scoped to the connector integration boundary."""

import re
from dataclasses import dataclass
from typing import Self
from uuid import UUID, uuid4

from intelligence.connectors.errors import InvalidConnectorIdentifierError

_READABLE_IDENTIFIER_PATTERN = re.compile(
    r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*",
    flags=re.ASCII,
)
_ORIGIN_REFERENCE_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]*",
    flags=re.ASCII,
)
_MAX_READABLE_IDENTIFIER_LENGTH = 128
_MAX_ORIGIN_REFERENCE_LENGTH = 256


@dataclass(frozen=True, slots=True)
class _ReadableIdentifier:
    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or not self.value
            or len(self.value) > _MAX_READABLE_IDENTIFIER_LENGTH
            or _READABLE_IDENTIFIER_PATTERN.fullmatch(self.value) is None
        ):
            raise InvalidConnectorIdentifierError(
                f"{type(self).__name__} must be a canonical readable identifier."
            )

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"{type(self).__name__}('{self.value}')"


class ConnectorId(_ReadableIdentifier):
    """Stable readable identifier for one connector implementation."""


class SourceId(_ReadableIdentifier):
    """Stable readable reference to a source catalog entry."""


@dataclass(frozen=True, slots=True)
class OriginReferenceId:
    """Logical source record reference that cannot carry a URL or query string."""

    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or not self.value
            or len(self.value) > _MAX_ORIGIN_REFERENCE_LENGTH
            or _ORIGIN_REFERENCE_PATTERN.fullmatch(self.value) is None
        ):
            raise InvalidConnectorIdentifierError(
                "OriginReferenceId must be an opaque canonical identifier without URL parts."
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class _UUIDIdentifier:
    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID) or self.value.int == 0:
            raise InvalidConnectorIdentifierError(
                f"{type(self).__name__} must contain a non-zero UUID."
            )

    @classmethod
    def new(cls) -> Self:
        """Create a random integration identifier."""

        return cls(uuid4())

    @classmethod
    def from_value(cls, value: UUID | str) -> Self:
        """Reconstruct an identifier from a UUID or canonical UUID text."""

        if isinstance(value, UUID):
            return cls(value)
        try:
            parsed = UUID(value)
        except (AttributeError, ValueError) as error:
            raise InvalidConnectorIdentifierError(
                f"{cls.__name__} must be reconstructed from canonical UUID text."
            ) from error
        if value.lower() != str(parsed):
            raise InvalidConnectorIdentifierError(
                f"{cls.__name__} must be reconstructed from canonical UUID text."
            )
        return cls(parsed)

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"{type(self).__name__}('{self.value}')"


class OperationId(_UUIDIdentifier):
    """Idempotency scope for one future logical connector operation."""


class RequestId(_UUIDIdentifier):
    """Identifier for one connector request envelope."""


class CandidateRefId(_UUIDIdentifier):
    """Opaque candidate identifier, meaningful only with its connector ID."""


class ArtifactRefId(_UUIDIdentifier):
    """Opaque identifier for temporary or externally managed artifact content."""


__all__ = [
    "ArtifactRefId",
    "CandidateRefId",
    "ConnectorId",
    "OperationId",
    "OriginReferenceId",
    "RequestId",
    "SourceId",
]
