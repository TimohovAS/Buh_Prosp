from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

MONEY_PLACES = Decimal("0.01")
ZERO_DECIMAL = Decimal("0.00")


def to_decimal(value: Any, default: Decimal = ZERO_DECIMAL) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
    if isinstance(value, bool):
        return default
    return Decimal(str(value)).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def quantize_money(value: Any) -> Decimal:
    return to_decimal(value)


def decimal_sum(values: list[Any] | tuple[Any, ...]) -> Decimal:
    total = ZERO_DECIMAL
    for value in values:
        total += to_decimal(value)
    return total.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def money_eq(left: Any, right: Any) -> bool:
    return to_decimal(left) == to_decimal(right)


def money_gt(left: Any, right: Any = ZERO_DECIMAL) -> bool:
    return to_decimal(left) > to_decimal(right)


def money_gte(left: Any, right: Any = ZERO_DECIMAL) -> bool:
    return to_decimal(left) >= to_decimal(right)


def money_abs(value: Any) -> Decimal:
    return abs(to_decimal(value)).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)

