"""Version values kept distinct across connector contracts and source policy."""

import re
from dataclasses import dataclass
from functools import total_ordering
from typing import Self

from intelligence.connectors.errors import (
    InvalidConnectorIdentifierError,
    InvalidSemanticVersionError,
)

_SEMANTIC_VERSION_PATTERN = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
    flags=re.ASCII,
)
_POLICY_VERSION_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]*",
    flags=re.ASCII,
)


@total_ordering
@dataclass(frozen=True, slots=True)
class SemanticVersion:
    """Minimal SemVer without prerelease or build metadata."""

    major: int
    minor: int
    patch: int

    def __post_init__(self) -> None:
        for component in (self.major, self.minor, self.patch):
            if isinstance(component, bool) or not isinstance(component, int) or component < 0:
                raise InvalidSemanticVersionError(
                    "SemanticVersion components must be non-negative integers."
                )

    @classmethod
    def parse(cls, value: str) -> Self:
        """Parse the sole accepted canonical ``MAJOR.MINOR.PATCH`` form."""

        if not isinstance(value, str):
            raise InvalidSemanticVersionError("SemanticVersion text must be canonical SemVer.")
        match = _SEMANTIC_VERSION_PATTERN.fullmatch(value)
        if match is None:
            raise InvalidSemanticVersionError("SemanticVersion text must be canonical SemVer.")
        return cls(*(int(component) for component in match.groups()))

    def is_compatible_with(self, other: object) -> bool:
        """Return whether two contract versions share the same major."""

        if not isinstance(other, SemanticVersion):
            return False
        return self.major == other.major

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, slots=True)
class SourcePolicyVersion:
    """Opaque stable version of the approved source policy snapshot."""

    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or not self.value
            or len(self.value) > 64
            or _POLICY_VERSION_PATTERN.fullmatch(self.value) is None
        ):
            raise InvalidConnectorIdentifierError(
                "SourcePolicyVersion must be a non-empty canonical reference."
            )

    def __str__(self) -> str:
        return self.value


CONNECTOR_CONTRACT_VERSION = SemanticVersion(1, 0, 0)
SUPPORTED_CONTRACT_MAJORS = frozenset({CONNECTOR_CONTRACT_VERSION.major})

__all__ = [
    "CONNECTOR_CONTRACT_VERSION",
    "SUPPORTED_CONTRACT_MAJORS",
    "SemanticVersion",
    "SourcePolicyVersion",
]
