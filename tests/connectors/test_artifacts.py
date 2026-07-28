"""Tests for safe bounded artifact payloads and opaque references."""

import hashlib
from datetime import UTC, datetime, timedelta, timezone
from typing import cast

import pytest

from intelligence.connectors.artifacts import (
    DEFAULT_MAX_INLINE_ARTIFACT_BYTES,
    ArtifactPayload,
    ArtifactReference,
)
from intelligence.connectors.enums import ArtifactRetentionMode
from intelligence.connectors.errors import InvalidConnectorArtifactError
from intelligence.connectors.identifiers import ArtifactRefId, CandidateRefId, OriginReferenceId


def payload(**overrides: object) -> ArtifactPayload:
    values: dict[str, object] = {
        "content": b'{"synthetic":true}',
        "media_type": "application/json",
        "retention": ArtifactRetentionMode.STORE_ORIGINAL,
        "origin_reference": OriginReferenceId("record-1"),
        "logical_name": "synthetic.json",
        "max_bytes": DEFAULT_MAX_INLINE_ARTIFACT_BYTES,
    }
    values.update(overrides)
    return ArtifactPayload(
        content=cast(bytes, values["content"]),
        media_type=cast(str, values["media_type"]),
        retention=cast(ArtifactRetentionMode, values["retention"]),
        origin_reference=cast(OriginReferenceId, values["origin_reference"]),
        logical_name=cast(str | None, values["logical_name"]),
        max_bytes=cast(int, values["max_bytes"]),
    )


def test_payload_calculates_size_digest_and_hides_bytes_from_repr() -> None:
    value = payload()

    assert value.size == len(value.content)
    assert value.sha256 == hashlib.sha256(value.content).hexdigest()
    assert value.media_type == "application/json"
    assert value.content.decode() not in repr(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content", bytearray(b"mutable")),
        ("content", b""),
        ("content", b"too-large"),
        ("max_bytes", 0),
        ("max_bytes", True),
        ("media_type", "text"),
        ("media_type", "text/plain; charset=utf-8"),
        ("logical_name", "../secret.txt"),
        ("logical_name", "folder/file.txt"),
    ],
)
def test_payload_rejects_invalid_content_and_metadata(field: str, value: object) -> None:
    overrides = {field: value}
    if field == "content" and value == b"too-large":
        overrides["max_bytes"] = 2
    with pytest.raises(InvalidConnectorArtifactError):
        payload(**overrides)


def test_artifact_reference_contains_no_url_or_fetch_method() -> None:
    reference = ArtifactReference(
        artifact_ref_id=ArtifactRefId.new(),
        media_type="APPLICATION/PDF",
        retention=ArtifactRetentionMode.REFERENCE_ONLY,
        origin_reference=OriginReferenceId("document-42"),
        size=2048,
        sha256="a" * 64,
        expires_at=datetime(2026, 7, 28, 9, tzinfo=timezone(-timedelta(hours=3))),
        logical_name="record.pdf",
    )

    assert reference.media_type == "application/pdf"
    assert reference.expires_at == datetime(2026, 7, 28, 12, tzinfo=UTC)
    assert not hasattr(reference, "url")
    assert not hasattr(reference, "fetch")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_ref_id", CandidateRefId.new()),
        ("retention", "REFERENCE_ONLY"),
        ("origin_reference", "record-1"),
        ("size", -1),
        ("size", True),
        ("sha256", "A" * 64),
        ("sha256", "a" * 63),
        ("expires_at", datetime(2026, 7, 28, 12)),
        ("logical_name", " "),
    ],
)
def test_artifact_reference_rejects_invalid_metadata(field: str, value: object) -> None:
    values: dict[str, object] = {
        "artifact_ref_id": ArtifactRefId.new(),
        "media_type": "application/pdf",
        "retention": ArtifactRetentionMode.REFERENCE_ONLY,
        "origin_reference": OriginReferenceId("record-1"),
        "size": None,
        "sha256": None,
        "expires_at": None,
        "logical_name": None,
    }
    values[field] = value
    with pytest.raises(InvalidConnectorArtifactError):
        ArtifactReference(
            artifact_ref_id=cast(ArtifactRefId, values["artifact_ref_id"]),
            media_type=cast(str, values["media_type"]),
            retention=cast(ArtifactRetentionMode, values["retention"]),
            origin_reference=cast(OriginReferenceId, values["origin_reference"]),
            size=cast(int | None, values["size"]),
            sha256=cast(str | None, values["sha256"]),
            expires_at=cast(datetime | None, values["expires_at"]),
            logical_name=cast(str | None, values["logical_name"]),
        )
