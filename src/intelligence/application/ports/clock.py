"""Framework-neutral time source for deterministic application services."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Return the current timezone-aware UTC instant."""

    def now(self) -> datetime:
        """Return one timezone-aware UTC timestamp."""


__all__ = ["Clock"]
