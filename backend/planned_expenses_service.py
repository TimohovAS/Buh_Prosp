"""Сервис планируемых расходов — расчёт дат и сумм."""
from datetime import date, timedelta
import calendar

from backend.models import PlannedExpense


def next_payment_dates(pe: "PlannedExpense", from_date: date, limit: int = 12) -> list[date]:
    """Генерирует список дат следующих платежей для планируемого расхода."""
    result = []
    if not pe.is_active or pe.start_date > from_date:
        return result

    effective_end = pe.end_date if pe.end_date else date(from_date.year + 2, 12, 31)

    if pe.period == "weekly":
        d = pe.start_date
        while d <= from_date:
            d += timedelta(days=7)
        while len(result) < limit and d <= effective_end:
            if d >= from_date:
                result.append(d)
            d += timedelta(days=7)

    elif pe.period == "monthly":
        day = pe.payment_day if pe.payment_day is not None else 1
        day = max(1, min(day, 28))
        y, m = pe.start_date.year, pe.start_date.month
        if date(y, m, min(day, calendar.monthrange(y, m)[1])) < pe.start_date:
            m += 1
            if m > 12:
                m, y = 1, y + 1
        count = 0
        while count < limit:
            last = calendar.monthrange(y, m)[1]
            d = date(y, m, min(day, last))
            if d >= from_date and d <= effective_end and d >= pe.start_date:
                result.append(d)
                count += 1
            m += 1
            if m > 12:
                m, y = 1, y + 1
            if y > from_date.year + 2:
                break

    elif pe.period == "quarterly":
        day = pe.payment_day if pe.payment_day is not None else 1
        day = max(1, min(day, 28))
        y, m = pe.start_date.year, pe.start_date.month
        q = (m - 1) // 3 * 3 + 1
        m = q
        d = date(y, m, min(day, calendar.monthrange(y, m)[1]))
        if d < from_date:
            m += 3
            if m > 12:
                m -= 12
                y += 1
            d = date(y, m, min(day, calendar.monthrange(y, m)[1]))
        count = 0
        while count < limit:
            if d >= from_date and d <= effective_end and d >= pe.start_date:
                result.append(d)
                count += 1
            m += 3
            if m > 12:
                m -= 12
                y += 1
            last = calendar.monthrange(y, m)[1]
            d = date(y, m, min(day, last))
            if y > from_date.year + 2:
                break

    elif pe.period == "yearly":
        day = pe.payment_day if pe.payment_day is not None else pe.start_date.day
        day = max(1, day)
        m = pe.start_date.month
        y = pe.start_date.year
        last = calendar.monthrange(y, m)[1]
        d = date(y, m, min(day, last))
        while d < from_date:
            y += 1
            last = calendar.monthrange(y, m)[1]
            d = date(y, m, min(day, last))
        count = 0
        while count < limit and d <= effective_end:
            if d >= from_date:
                result.append(d)
                count += 1
            y += 1
            last = calendar.monthrange(y, m)[1]
            d = date(y, m, min(day, last))
            if y > from_date.year + 2:
                break

    return result[:limit]


def payment_dates_in_range(
    pe: "PlannedExpense", range_start: date, range_end: date, limit: int = 48
) -> list[date]:
    """Даты платежей в диапазоне [range_start, range_end], включая просроченные."""
    result = []
    if not pe.is_active or pe.start_date > range_end:
        return result

    effective_end = pe.end_date if pe.end_date else range_end
    if effective_end < range_start:
        return result

    if pe.period == "weekly":
        d = pe.start_date
        while d < range_start:
            d += timedelta(days=7)
        while len(result) < limit and d <= min(range_end, effective_end):
            if d >= range_start and d >= pe.start_date:
                result.append(d)
            d += timedelta(days=7)

    elif pe.period == "monthly":
        day = pe.payment_day if pe.payment_day is not None else 1
        day = max(1, min(day, 28))
        y, m = range_start.year, range_start.month
        count = 0
        while count < limit and date(y, m, 1) <= range_end:
            if date(y, m, 1) >= date(pe.start_date.year, pe.start_date.month, 1):
                last = calendar.monthrange(y, m)[1]
                d = date(y, m, min(day, last))
                if range_start <= d <= range_end and d >= pe.start_date and d <= effective_end:
                    result.append(d)
                    count += 1
            m += 1
            if m > 12:
                m, y = 1, y + 1
            if y > range_end.year + 1:
                break

    elif pe.period == "quarterly":
        day = pe.payment_day if pe.payment_day is not None else 1
        day = max(1, min(day, 28))
        y, m = range_start.year, range_start.month
        q = (m - 1) // 3 * 3 + 1
        m = q
        count = 0
        while count < limit:
            last = calendar.monthrange(y, m)[1]
            d = date(y, m, min(day, last))
            if range_start <= d <= range_end and d >= pe.start_date and d <= effective_end:
                result.append(d)
                count += 1
            m += 3
            if m > 12:
                m -= 12
                y += 1
            if date(y, m, 1) > range_end:
                break

    elif pe.period == "yearly":
        day = pe.payment_day if pe.payment_day is not None else pe.start_date.day
        day = max(1, day)
        m = pe.start_date.month
        y = range_start.year
        if date(y, m, 1) < date(range_start.year, range_start.month, 1):
            y += 1
        count = 0
        while count < limit and y <= range_end.year + 1:
            last = calendar.monthrange(y, m)[1]
            d = date(y, m, min(day, last))
            if range_start <= d <= range_end and d >= pe.start_date and d <= effective_end:
                result.append(d)
                count += 1
            y += 1

    return result[:limit]


def planned_expenses_sum_until(
    items: list["PlannedExpense"],
    from_date: date,
    to_date: date,
    paid_pairs: set[tuple[int, date]] | None = None,
) -> float:
    """Сумма планируемых расходов с датами в [from_date, to_date], исключая оплаченные (planned_expense_id, due_date)."""
    paid_pairs = paid_pairs or set()
    total = 0.0
    for pe in items:
        if not pe.is_active:
            continue
        dates = next_payment_dates(pe, from_date, limit=12)
        for d in dates:
            if from_date <= d <= to_date and (pe.id, d) not in paid_pairs:
                total += pe.amount
    return total


def planned_expenses_sum_until_including_overdue(
    items: list["PlannedExpense"],
    range_start: date,
    to_date: date,
    paid_pairs: set[tuple[int, date]] | None = None,
) -> float:
    """Сумма периодических расходов в [range_start, to_date], включая просроченные (неоплаченные)."""
    paid_pairs = paid_pairs or set()
    total = 0.0
    for pe in items:
        if not pe.is_active:
            continue
        dates = payment_dates_in_range(pe, range_start, to_date, limit=24)
        for d in dates:
            if (pe.id, d) not in paid_pairs:
                total += pe.amount
    return total
