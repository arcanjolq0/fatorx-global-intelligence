"""Tests for geographic value objects."""

from typing import cast

import pytest

from intelligence.domain.errors import InvalidCountryCodeError
from intelligence.domain.geography import CountryCode


def test_country_code_normalizes_ascii_letters_to_uppercase() -> None:
    assert CountryCode("br").value == "BR"
    assert str(CountryCode("Us")) == "US"


def test_country_code_validates_format_not_official_membership() -> None:
    assert CountryCode("ZZ").value == "ZZ"


@pytest.mark.parametrize("value", ["B", "BRA", "B1", " B", "B ", "éU", ""])
def test_country_code_rejects_invalid_format(value: str) -> None:
    with pytest.raises(InvalidCountryCodeError):
        CountryCode(value)


def test_country_code_rejects_wrong_runtime_type() -> None:
    with pytest.raises(InvalidCountryCodeError):
        CountryCode(cast(str, 76))
