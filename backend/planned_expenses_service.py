"""Сервис планируемых расходов — расчёт дат и сумм."""
from datetime import date, timedelta
import calendar
from decimal import Decimal

from backend.decimal_utils import ZERO_DECIMAL, to_decimal
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import PlannedExpense, PlannedExpensePayment, WorkerPayout


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
) -> Decimal:
    """Сумма планируемых расходов с датами в [from_date, to_date], исключая оплаченные (planned_expense_id, due_date)."""
    paid_pairs = paid_pairs or set()
    total = ZERO_DECIMAL
    for pe in items:
        if not pe.is_active:
            continue
        dates = next_payment_dates(pe, from_date, limit=12)
        for d in dates:
            if from_date <= d <= to_date and (pe.id, d) not in paid_pairs:
                total += to_decimal(pe.amount or ZERO_DECIMAL)
    return total


def planned_expenses_sum_until_including_overdue(
    items: list["PlannedExpense"],
    range_start: date,
    to_date: date,
    paid_pairs: set[tuple[int, date]] | None = None,
) -> Decimal:
    """Сумма периодических расходов в [range_start, to_date], включая просроченные (неоплаченные)."""
    paid_pairs = paid_pairs or set()
    total = ZERO_DECIMAL
    for pe in items:
        if not pe.is_active:
            continue
        dates = payment_dates_in_range(pe, range_start, to_date, limit=24)
        for d in dates:
            if (pe.id, d) not in paid_pairs:
                total += to_decimal(pe.amount or ZERO_DECIMAL)
    return total


async def sync_worker_payout_planned_payment(
    db: AsyncSession,
    payout: WorkerPayout,
) -> PlannedExpensePayment | None:
    """Mark one linked planned expense occurrence as paid by this worker payout.

    This keeps planned expenses as reminders only: no expenses or cash entries are
    created here. Existing automatic marks for the same payout are rebuilt so
    editing a payout moves the reminder mark instead of leaving stale rows.
    """
    await db.execute(
        delete(PlannedExpensePayment).where(PlannedExpensePayment.worker_payout_id == payout.id)
    )

    if payout.payout_type not in {"regular", "weekly", "monthly"}:
        return None
    if not payout.worker_id or not payout.date:
        return None

    range_start = payout.period_start or (payout.date - timedelta(days=45))
    range_end = payout.period_end or (payout.date + timedelta(days=14))
    if range_end < range_start:
        range_start = range_end = payout.date

    result = await db.execute(
        select(PlannedExpense)
        .where(PlannedExpense.is_active == True)
        .where(PlannedExpense.worker_id == payout.worker_id)
    )
    planned_items = result.scalars().all()
    if not planned_items:
        return None

    candidate_pairs: list[tuple[PlannedExpense, date]] = []
    for planned in planned_items:
        for due_date in payment_dates_in_range(planned, range_start, range_end, limit=24):
            candidate_pairs.append((planned, due_date))
    if not candidate_pairs:
        return None

    paid_result = await db.execute(
        select(PlannedExpensePayment.planned_expense_id, PlannedExpensePayment.due_date).where(
            PlannedExpensePayment.planned_expense_id.in_({item.id for item, _ in candidate_pairs})
        )
    )
    paid_pairs = {(row[0], row[1]) for row in paid_result.fetchall()}

    unpaid_pairs = [
        (planned, due_date)
        for planned, due_date in candidate_pairs
        if (planned.id, due_date) not in paid_pairs
    ]
    if not unpaid_pairs:
        return None

    planned, due_date = min(
        unpaid_pairs,
        key=lambda pair: (
            abs((pair[1] - payout.date).days),
            pair[1] > payout.date,
            pair[1],
            pair[0].id,
        ),
    )
    payment = PlannedExpensePayment(
        planned_expense_id=planned.id,
        due_date=due_date,
        paid_date=payout.date,
        worker_payout_id=payout.id,
        note=f"auto_worker_payout:{payout.id}",
    )
    db.add(payment)
    await db.flush()
    return payment


