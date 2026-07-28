"""Currency and monetary value objects without conversion or implicit rounding."""

import re
from dataclasses import dataclass
from decimal import Decimal, DecimalException, Inexact, localcontext

from .errors import InvalidCurrencyCodeError, InvalidMoneyError

_CURRENCY_CODE_PATTERN = re.compile(r"[A-Za-z]{3}", flags=re.ASCII)


@dataclass(frozen=True, slots=True)
class CurrencyCode:
    """ISO 4217-shaped currency code normalized to uppercase.

    F2.1 validates the three-letter format, not membership in the official list.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _CURRENCY_CODE_PATTERN.fullmatch(self.value) is None:
            raise InvalidCurrencyCodeError(
                "CurrencyCode must contain exactly three ASCII letters without spaces."
            )
        object.__setattr__(self, "value", self.value.upper())

    def __str__(self) -> str:
        return self.value


def _finite_exponent(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise InvalidMoneyError("Money amount must be a finite Decimal value.")
    return exponent


def _exact_operation(first: Decimal, second: Decimal, *, subtract: bool) -> Decimal:
    minimum_exponent = min(_finite_exponent(first), _finite_exponent(second))
    maximum_adjusted = max(first.adjusted(), second.adjusted())
    required_precision = max(1, maximum_adjusted - minimum_exponent + 2)

    try:
        with localcontext() as context:
            context.prec = max(context.prec, required_precision)
            context.traps[Inexact] = True
            return first - second if subtract else first + second
    except DecimalException as error:
        raise InvalidMoneyError("Money operation would lose decimal precision.") from error


@dataclass(frozen=True, slots=True)
class Money:
    """An exact Decimal amount paired with an explicit currency."""

    amount: Decimal
    currency: CurrencyCode

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise InvalidMoneyError("Money amount must be provided as Decimal, never float.")
        if not self.amount.is_finite():
            raise InvalidMoneyError("Money amount must be finite; NaN and infinity are invalid.")
        if not isinstance(self.currency, CurrencyCode):
            raise InvalidMoneyError("Money currency must be an explicit CurrencyCode.")

    def _compatible(self, other: object) -> Money:
        if not isinstance(other, Money):
            raise TypeError("Money operations require another Money value.")
        if self.currency != other.currency:
            raise InvalidMoneyError("Money values with different currencies are incompatible.")
        return other

    def __add__(self, other: object) -> Money:
        compatible = self._compatible(other)
        return Money(
            amount=_exact_operation(self.amount, compatible.amount, subtract=False),
            currency=self.currency,
        )

    def __sub__(self, other: object) -> Money:
        compatible = self._compatible(other)
        return Money(
            amount=_exact_operation(self.amount, compatible.amount, subtract=True),
            currency=self.currency,
        )


__all__ = ("CurrencyCode", "Money")
