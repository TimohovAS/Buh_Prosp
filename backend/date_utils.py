from __future__ import annotations

from datetime import date, datetime


def coerce_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def days_between(left, right, *, absolute: bool = False) -> int:
    left_date = coerce_date(left)
    right_date = coerce_date(right)
    if left_date is None or right_date is None:
        raise ValueError("Cannot compare empty dates")
    delta = (left_date - right_date).days
    return abs(delta) if absolute else delta
