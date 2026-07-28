"""Tests for exact monetary value objects."""

from decimal import Decimal
from typing import cast

import pytest

from intelligence.domain.errors import InvalidCurrencyCodeError, InvalidMoneyError
from intelligence.domain.money import CurrencyCode, Money


def test_currency_code_normalizes_and_validates_format_only() -> None:
    assert CurrencyCode("brl").value == "BRL"
    assert str(CurrencyCode("Xyz")) == "XYZ"


@pytest.mark.parametrize("value", ["BR", "BRLL", "B1L", " BR", "BR ", "EU€", ""])
def test_currency_code_rejects_invalid_format(value: str) -> None:
    with pytest.raises(InvalidCurrencyCodeError):
        CurrencyCode(value)


def test_currency_code_rejects_wrong_runtime_type() -> None:
    with pytest.raises(InvalidCurrencyCodeError):
        CurrencyCode(cast(str, 986))


def test_money_preserves_decimal_amount_without_rounding() -> None:
    amount = Decimal("12345678901234567890.12345678901234567890")

    money = Money(amount, CurrencyCode("BRL"))

    assert money.amount == amount
    assert money.amount.as_tuple() == amount.as_tuple()


@pytest.mark.parametrize(
    "amount",
    [Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_money_rejects_non_finite_decimal(amount: Decimal) -> None:
    with pytest.raises(InvalidMoneyError):
        Money(amount, CurrencyCode("BRL"))


def test_money_rejects_float_and_untyped_currency() -> None:
    with pytest.raises(InvalidMoneyError):
        Money(cast(Decimal, 0.1), CurrencyCode("BRL"))

    with pytest.raises(InvalidMoneyError):
        Money(Decimal("1"), cast(CurrencyCode, "BRL"))


def test_money_addition_and_subtraction_are_exact_for_same_currency() -> None:
    first = Money(Decimal("99999999999999999999.999"), CurrencyCode("BRL"))
    second = Money(Decimal("0.001"), CurrencyCode("BRL"))

    total = first + second
    restored = total - second

    assert total.amount == Decimal("100000000000000000000.000")
    assert restored.amount == first.amount
    assert total.currency == CurrencyCode("BRL")


def test_money_rejects_cross_currency_and_non_money_operations() -> None:
    brl = Money(Decimal("1"), CurrencyCode("BRL"))
    usd = Money(Decimal("1"), CurrencyCode("USD"))

    with pytest.raises(InvalidMoneyError):
        _ = brl + usd
    with pytest.raises(TypeError):
        _ = brl + cast(Money, Decimal("1"))
