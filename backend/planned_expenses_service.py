"""Сервис планируемых расходов — расчёт дат и сумм."""

from datetime import date, timedelta
import calendar
from decimal import Decimal

from backend.decimal_utils import ZERO_DECIMAL, to_decimal
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import PlannedExpense, PlannedExpensePayment, Worker, WorkerPayout


AUTO_WORKER_SALARY_NOTE = "auto:worker_salary_plan"
# Командировочные к зарплате за период отношения не имеют, остальное — да,
# включая покупку работнику в счёт зарплаты.
SALARY_SETTLING_PAYOUT_TYPES = frozenset({"regular", "weekly", "monthly", "purchase"})
DEFAULT_MONTHLY_SALARY_DAY = 5
DEFAULT_WEEKLY_SALARY_WEEKDAY = 0


def worker_salary_plan_settings(worker: "Worker") -> tuple[Decimal, str] | None:
    """Return the configured worker rate and matching planning period."""
    if worker.pay_scheme == "monthly":
        amount = to_decimal(worker.monthly_rate or ZERO_DECIMAL)
        return (amount, "monthly") if amount > ZERO_DECIMAL else None
    if worker.pay_scheme == "weekly":
        amount = to_decimal(worker.weekly_rate or ZERO_DECIMAL)
        return (amount, "weekly") if amount > ZERO_DECIMAL else None
    return None


async def sync_worker_salary_plan(
    db: AsyncSession,
    worker: "Worker",
    *,
    category_id: int | None = None,
    project_id: int | None = None,
    today: date | None = None,
) -> PlannedExpense | None:
    """Keep one hidden salary plan in sync with the worker's configured pay rate."""
    current_date = today or date.today()
    result = await db.execute(
        select(PlannedExpense).where(PlannedExpense.worker_id == worker.id).order_by(PlannedExpense.id.asc())
    )
    existing_plans = result.scalars().all()
    generated_plan = next((item for item in existing_plans if item.note == AUTO_WORKER_SALARY_NOTE), None)
    target = generated_plan or (existing_plans[0] if existing_plans else None)
    settings = worker_salary_plan_settings(worker)
    created_target = False

    if not worker.is_active:
        for plan in existing_plans:
            plan.is_active = False
        return None
    if settings is None:
        if generated_plan is not None:
            generated_plan.is_active = False
        return None

    amount, period = settings
    if target is None:
        created_target = True
        target = PlannedExpense(
            name=f"Зарплата — {worker.name}",
            amount=amount,
            currency="RSD",
            category_id=category_id,
            project_id=project_id,
            worker_id=worker.id,
            period=period,
            start_date=current_date,
            reminder_days=3,
            is_active=True,
            note=AUTO_WORKER_SALARY_NOTE,
        )
        db.add(target)

    target.amount = amount
    target.is_active = True
    if target.note == AUTO_WORKER_SALARY_NOTE:
        period_changed = target.period != period
        target.name = f"Зарплата — {worker.name}"
        target.currency = "RSD"
        target.category_id = category_id
        target.project_id = project_id
        target.period = period
        target.end_date = None
        if period == "monthly":
            if created_target or period_changed:
                target.start_date = date(current_date.year, current_date.month, 1)
            target.payment_day = DEFAULT_MONTHLY_SALARY_DAY
            target.payment_day_of_week = None
        else:
            if created_target or period_changed:
                target.start_date = current_date - timedelta(days=current_date.weekday())
            target.payment_day = None
            target.payment_day_of_week = DEFAULT_WEEKLY_SALARY_WEEKDAY

    await db.flush()
    return target


def next_payment_dates(pe: "PlannedExpense", from_date: date, limit: int = 12) -> list[date]:
    """Генерирует список дат следующих платежей для планируемого расхода."""
    result = []
    if not pe.is_active:
        return result

    effective_end = pe.end_date if pe.end_date else date(from_date.year + 2, 12, 31)

    if pe.period == "once":
        if pe.start_date >= from_date and pe.start_date <= effective_end:
            result.append(pe.start_date)

    elif pe.period == "weekly":
        d = pe.start_date
        while d < from_date:
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


def payment_dates_in_range(pe: "PlannedExpense", range_start: date, range_end: date, limit: int = 48) -> list[date]:
    """Даты платежей в диапазоне [range_start, range_end], включая просроченные."""
    result = []
    if not pe.is_active or pe.start_date > range_end:
        return result

    effective_end = pe.end_date if pe.end_date else range_end
    if effective_end < range_start:
        return result

    if pe.period == "once":
        if range_start <= pe.start_date <= min(range_end, effective_end):
            result.append(pe.start_date)

    elif pe.period == "weekly":
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
    settled: dict[tuple[int, date], Decimal] | None = None,
) -> Decimal:
    """Сколько ещё предстоит заплатить в [range_start, to_date], с просроченными.

    Зарплату закрывают частями, поэтому считаем непогашенный остаток каждого
    платежа, а не весь его размер: частичное погашение не должно прятать
    оставшийся долг целиком.
    """
    settled = settled or {}
    total = ZERO_DECIMAL
    for pe in items:
        if not pe.is_active:
            continue
        dates = payment_dates_in_range(pe, range_start, to_date, limit=24)
        for d in dates:
            total += occurrence_remaining(pe, settled.get((pe.id, d), ZERO_DECIMAL))
    return total


async def settled_amounts_by_occurrence(
    db: AsyncSession,
    planned_expense_ids: set[int],
    *,
    exclude_payout_id: int | None = None,
) -> dict[tuple[int, date], Decimal]:
    """Сколько уже погашено по каждому плановому платежу.

    exclude_payout_id нужен, когда выплату правят: её собственное погашение
    считать «уже закрытым» нельзя, иначе она ограничит сама себя.
    """
    if not planned_expense_ids:
        return {}
    query = (
        select(
            PlannedExpensePayment.planned_expense_id,
            PlannedExpensePayment.due_date,
            func.sum(PlannedExpensePayment.amount),
        )
        .where(PlannedExpensePayment.planned_expense_id.in_(planned_expense_ids))
        .group_by(PlannedExpensePayment.planned_expense_id, PlannedExpensePayment.due_date)
    )
    if exclude_payout_id is not None:
        query = query.where(
            (PlannedExpensePayment.worker_payout_id.is_(None))
            | (PlannedExpensePayment.worker_payout_id != exclude_payout_id)
        )
    result = await db.execute(query)
    return {(row[0], row[1]): to_decimal(row[2] or ZERO_DECIMAL) for row in result.fetchall()}


def occurrence_remaining(planned: PlannedExpense, settled: Decimal) -> Decimal:
    """Остаток планового платежа: переплату в минус не уводим."""
    remaining = to_decimal(planned.amount or ZERO_DECIMAL) - to_decimal(settled or ZERO_DECIMAL)
    return remaining if remaining > ZERO_DECIMAL else ZERO_DECIMAL


def payout_settlement_window(payout: WorkerPayout) -> tuple[date, date]:
    """Период, за который засчитывается выплата."""
    range_start = payout.period_start or (payout.date - timedelta(days=45))
    range_end = payout.period_end or (payout.date + timedelta(days=14))
    if range_end < range_start:
        range_start = range_end = payout.date
    return range_start, range_end


def _settling_occurrences(
    planned_items: list[PlannedExpense],
    payout: WorkerPayout,
    settled: dict[tuple[int, date], Decimal],
) -> list[tuple[PlannedExpense, date]]:
    """Открытые плановые платежи в окне выплаты, ближайший к её дате первым.

    Одна выплата может закрыть несколько периодов: при недельной ставке покупка
    на три недели вперёд гасит три платежа, а не один.
    """
    range_start, range_end = payout_settlement_window(payout)
    open_pairs = [
        (planned, due_date)
        for planned in planned_items
        for due_date in payment_dates_in_range(planned, range_start, range_end, limit=24)
        if occurrence_remaining(planned, settled.get((planned.id, due_date), ZERO_DECIMAL)) > ZERO_DECIMAL
    ]
    return sorted(
        open_pairs,
        key=lambda pair: (
            abs((pair[1] - payout.date).days),
            pair[1] > payout.date,
            pair[1],
            pair[0].id,
        ),
    )


async def salary_remaining_for_payout(
    db: AsyncSession,
    *,
    worker_id: int | None,
    payout_date: date,
    period_start: date | None,
    period_end: date | None,
    exclude_payout_id: int | None = None,
) -> Decimal | None:
    """Сколько ещё причитается работнику по плану за этот период.

    None — плана нет или в окне нет открытых платежей, тогда ограничивать
    выплату нечем.
    """
    if not worker_id:
        return None
    result = await db.execute(
        select(PlannedExpense).where(PlannedExpense.is_active == True).where(PlannedExpense.worker_id == worker_id)
    )
    planned_items = list(result.scalars().all())
    if not planned_items:
        return None

    settled = await settled_amounts_by_occurrence(
        db, {item.id for item in planned_items}, exclude_payout_id=exclude_payout_id
    )
    probe = WorkerPayout(
        worker_id=worker_id,
        date=payout_date,
        period_start=period_start,
        period_end=period_end,
    )
    open_pairs = _settling_occurrences(planned_items, probe, settled)
    if not (period_start and period_end):
        open_pairs = open_pairs[:1]
    if not open_pairs:
        return None
    return sum(
        (
            occurrence_remaining(planned, settled.get((planned.id, due_date), ZERO_DECIMAL))
            for planned, due_date in open_pairs
        ),
        ZERO_DECIMAL,
    )


async def resync_worker_salary_settlements(db: AsyncSession, worker_id: int | None) -> None:
    """Пересобрать погашения плановой зарплаты работника целиком.

    Раскладка не должна зависеть от порядка действий: выплаты переигрываются по
    дате, поэтому после сторно, отвязки или правки любой из них остальные
    распределяются заново, а не остаются с урезанными когда-то суммами.

    Ручные отметки не трогаем — их ставил человек, и они считаются уже
    погашенной частью.
    """
    if not worker_id:
        return

    payout_ids = select(WorkerPayout.id).where(WorkerPayout.worker_id == worker_id)
    await db.execute(delete(PlannedExpensePayment).where(PlannedExpensePayment.worker_payout_id.in_(payout_ids)))
    await db.flush()

    result = await db.execute(
        select(PlannedExpense).where(PlannedExpense.is_active == True).where(PlannedExpense.worker_id == worker_id)
    )
    planned_items = list(result.scalars().all())
    if not planned_items:
        return

    settled = await settled_amounts_by_occurrence(db, {item.id for item in planned_items})
    result = await db.execute(
        select(WorkerPayout)
        .where(WorkerPayout.worker_id == worker_id)
        .where(WorkerPayout.cancelled_at.is_(None))
        .where(WorkerPayout.payout_type.in_(SALARY_SETTLING_PAYOUT_TYPES))
        .order_by(WorkerPayout.date.asc(), WorkerPayout.id.asc())
    )
    for payout in result.scalars().all():
        paid_amount = to_decimal(payout.cash_paid_amount or ZERO_DECIMAL)
        if paid_amount <= ZERO_DECIMAL or not payout.date:
            continue
        left = paid_amount
        # Разносить по нескольким периодам вправе только выплата, назвавшая свой
        # период. Без него неизвестно, что она покрывает, и трогать соседние
        # месяцы нельзя: деньги молча закрыли бы старые долги.
        occurrences = _settling_occurrences(planned_items, payout, settled)
        if not (payout.period_start and payout.period_end):
            occurrences = occurrences[:1]
        for planned, due_date in occurrences:
            if left <= ZERO_DECIMAL:
                break
            key = (planned.id, due_date)
            # Больше остатка периода не засчитываем, лишнее переходит на следующий.
            amount = min(left, occurrence_remaining(planned, settled.get(key, ZERO_DECIMAL)))
            if amount <= ZERO_DECIMAL:
                continue
            db.add(
                PlannedExpensePayment(
                    planned_expense_id=planned.id,
                    due_date=due_date,
                    paid_date=payout.date,
                    amount=amount,
                    worker_payout_id=payout.id,
                    note=f"auto_worker_payout:{payout.id}",
                )
            )
            settled[key] = settled.get(key, ZERO_DECIMAL) + amount
            left -= amount
    await db.flush()


async def sync_worker_payout_planned_payment(
    db: AsyncSession,
    payout: WorkerPayout,
) -> None:
    """Пересчитать погашения зарплаты работника после изменения его выплаты.

    Планируемые расходы остаются напоминанием: ни расходов, ни записей в кассе
    здесь не создаётся. Покупка в счёт зарплаты участвует наравне с деньгами —
    работник получил её вместо части зарплаты.
    """
    await resync_worker_salary_settlements(db, payout.worker_id)
