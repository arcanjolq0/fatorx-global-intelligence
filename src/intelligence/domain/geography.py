"""Geographic value objects with deterministic canonical forms."""

import re
from dataclasses import dataclass

from .errors import InvalidCountryCodeError

_COUNTRY_CODE_PATTERN = re.compile(r"[A-Za-z]{2}", flags=re.ASCII)


@dataclass(frozen=True, slots=True)
class CountryCode:
    """ISO 3166-1 alpha-2-shaped country code.

    F2.1 validates the two-letter format, not membership in the official list.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _COUNTRY_CODE_PATTERN.fullmatch(self.value) is None:
            raise InvalidCountryCodeError(
                "CountryCode must contain exactly two ASCII letters without spaces."
            )
        object.__setattr__(self, "value", self.value.upper())

    def __str__(self) -> str:
        return self.value


__all__ = ("CountryCode",)
