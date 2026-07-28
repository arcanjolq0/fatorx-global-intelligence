"""Tests for UTC timestamp normalization."""

from datetime import UTC, datetime, timedelta, timezone
from typing import cast

import pytest

from intelligence.domain.errors import InvalidDateTimeError
from intelligence.domain.time import normalize_utc


def test_aware_timestamp_is_normalized_to_utc() -> None:
    local_timestamp = datetime(
        2026,
        7,
        25,
        9,
        30,
        tzinfo=timezone(-timedelta(hours=3)),
    )

    normalized = normalize_utc(local_timestamp)

    assert normalized == datetime(2026, 7, 25, 12, 30, tzinfo=UTC)
    assert normalized.tzinfo is UTC


def test_utc_timestamp_remains_equal() -> None:
    timestamp = datetime(2026, 7, 25, 12, 30, tzinfo=UTC)

    assert normalize_utc(timestamp) == timestamp


def test_naive_timestamp_and_wrong_runtime_type_are_rejected() -> None:
    with pytest.raises(InvalidDateTimeError):
        normalize_utc(datetime(2026, 7, 25, 12, 30))

    with pytest.raises(InvalidDateTimeError):
        normalize_utc(cast(datetime, "2026-07-25T12:30:00Z"))
