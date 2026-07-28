"""Standard-library implementation of the application Clock port."""

from datetime import UTC, datetime


class SystemClock:
    """Read the current instant from the standard-library UTC clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)


__all__ = ["SystemClock"]
