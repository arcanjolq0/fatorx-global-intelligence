"""Bounded inline artifacts and opaque references with no storage behavior."""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

from intelligence.connectors.enums import ArtifactRetentionMode
from intelligence.connectors.errors import InvalidConnectorArtifactError
from intelligence.connectors.identifiers import ArtifactRefId, OriginReferenceId
from intelligence.domain.errors import InvalidDateTimeError
from intelligence.domain.time import normalize_utc

DEFAULT_MAX_INLINE_ARTIFACT_BYTES = 65_536
_MEDIA_TYPE_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*",
    flags=re.ASCII,
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class ArtifactPayload:
    """Small immutable byte payload intended for synthetic fixtures and handoff."""

    content: bytes = field(repr=False)
    media_type: str
    size: int
    sha256: str
    logical_name: str | None
    retention: ArtifactRetentionMode
    origin_reference: OriginReferenceId

    def __init__(
        self,
        *,
        content: bytes,
        media_type: str,
        retention: ArtifactRetentionMode,
        origin_reference: OriginReferenceId,
        logical_name: str | None = None,
        max_bytes: int = DEFAULT_MAX_INLINE_ARTIFACT_BYTES,
    ) -> None:
        if not isinstance(content, bytes):
            raise InvalidConnectorArtifactError("ArtifactPayload content must be immutable bytes.")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise InvalidConnectorArtifactError(
                "ArtifactPayload max_bytes must be a positive integer."
            )
        if not content:
            raise InvalidConnectorArtifactError("ArtifactPayload content cannot be empty.")
        if len(content) > max_bytes:
            raise InvalidConnectorArtifactError(
                "ArtifactPayload content exceeds the configured inline limit."
            )
        canonical_media_type = _media_type(media_type)
        if not isinstance(retention, ArtifactRetentionMode):
            raise InvalidConnectorArtifactError(
                "ArtifactPayload retention must be an ArtifactRetentionMode."
            )
        if not isinstance(origin_reference, OriginReferenceId):
            raise InvalidConnectorArtifactError(
                "ArtifactPayload origin_reference must be an OriginReferenceId."
            )
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "media_type", canonical_media_type)
        object.__setattr__(self, "size", len(content))
        object.__setattr__(self, "sha256", hashlib.sha256(content).hexdigest())
        object.__setattr__(self, "logical_name", _logical_name(logical_name))
        object.__setattr__(self, "retention", retention)
        object.__setattr__(self, "origin_reference", origin_reference)


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactReference:
    """Opaque artifact handle with metadata and no retrieval method or URL."""

    artifact_ref_id: ArtifactRefId
    media_type: str
    retention: ArtifactRetentionMode
    origin_reference: OriginReferenceId
    size: int | None = None
    sha256: str | None = None
    expires_at: datetime | None = None
    logical_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_ref_id, ArtifactRefId):
            raise InvalidConnectorArtifactError(
                "ArtifactReference artifact_ref_id must be an ArtifactRefId."
            )
        if not isinstance(self.retention, ArtifactRetentionMode):
            raise InvalidConnectorArtifactError(
                "ArtifactReference retention must be an ArtifactRetentionMode."
            )
        if not isinstance(self.origin_reference, OriginReferenceId):
            raise InvalidConnectorArtifactError(
                "ArtifactReference origin_reference must be an OriginReferenceId."
            )
        if self.size is not None and (
            isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0
        ):
            raise InvalidConnectorArtifactError(
                "ArtifactReference size must be a non-negative integer."
            )
        if self.sha256 is not None and (
            not isinstance(self.sha256, str) or _SHA256_PATTERN.fullmatch(self.sha256) is None
        ):
            raise InvalidConnectorArtifactError(
                "ArtifactReference sha256 must be a canonical SHA-256 digest."
            )
        expires_at = None
        if self.expires_at is not None:
            try:
                expires_at = normalize_utc(self.expires_at)
            except InvalidDateTimeError as error:
                raise InvalidConnectorArtifactError(
                    "ArtifactReference expires_at must include timezone information."
                ) from error
        object.__setattr__(self, "media_type", _media_type(self.media_type))
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "logical_name", _logical_name(self.logical_name))


def _media_type(value: str) -> str:
    if not isinstance(value, str):
        raise InvalidConnectorArtifactError("Artifact media type must be text.")
    canonical = value.strip().lower()
    if _MEDIA_TYPE_PATTERN.fullmatch(canonical) is None:
        raise InvalidConnectorArtifactError("Artifact media type has an invalid format.")
    return canonical


def _logical_name(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidConnectorArtifactError("Artifact logical name must be text.")
    canonical = value.strip()
    if (
        not canonical
        or len(canonical) > 128
        or canonical in {".", ".."}
        or "/" in canonical
        or "\\" in canonical
        or any(character in "\r\n\x00" for character in canonical)
    ):
        raise InvalidConnectorArtifactError("Artifact logical name has an invalid format.")
    return canonical


__all__ = [
    "DEFAULT_MAX_INLINE_ARTIFACT_BYTES",
    "ArtifactPayload",
    "ArtifactReference",
]
