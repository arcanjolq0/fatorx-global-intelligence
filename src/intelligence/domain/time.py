"""Timezone validation and UTC normalization for domain timestamps."""

from datetime import UTC, datetime

from .errors import InvalidDateTimeError


def normalize_utc(value: datetime) -> datetime:
    """Return an aware timestamp normalized to UTC."""

    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InvalidDateTimeError("Domain timestamps must include timezone information.")
    return value.astimezone(UTC)


__all__ = ("normalize_utc",)
