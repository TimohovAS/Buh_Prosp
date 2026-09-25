"""Начисления работникам в дневнике работ и сверка их с выплатами.

Труд в записи дневника начисляется по режиму оплаты работника за дату:

- hourly — как раньше: часы на объекте × себестоимость часа, сверх 8 часов записи
  со сверхурочным коэффициентом;
- full_day — обычная дневная ставка работника (regular_day_rate);
- trip_day — ставка дня командировки (trip_work_day_rate).

Режим, дневная ставка и командировочные хранятся одной строкой на работника и дату
(WorkDiaryWorkerDay) и начисляются один раз за день: сумма делится между всеми
записями работника за эту дату пропорционально часам на объекте, в том числе между
разными проектами. Дневная ставка — фиксированная сумма за день: сверхурочные в
режимах за день не добавляются, как и в расчёте выплат работнику. Сумма заказчику от
режима не зависит — она по-прежнему считается от часов на объекте.

Выплата работнику записывается расходом проекта. Чтобы деньги не считались дважды —
начислением в дневнике и расходом выплаты, — выплату можно явно сопоставить с
начислениями дневника за её период (WorkerPayout.diary_reconciled). Сопоставленные
выплаты работника с одним и тем же периодом образуют группу: в затраты объекта
входит начисление, а из выплат группы — только часть сверх начислений.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.expense_service import CASH_TRANSFER_SOURCE, visible_expense_condition
from backend.models import (
    Expense,
    Project,
    WorkDiaryEntry,
    WorkDiaryEntryWorker,
    WorkDiaryWorkerDay,
    Worker,
    WorkerPayout,
)

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")
REGULAR_DAY_HOURS = Decimal("8")

PAY_MODE_HOURLY = "hourly"
PAY_MODE_FULL_DAY = "full_day"
PAY_MODE_TRIP_DAY = "trip_day"
DAY_PAY_MODES = (PAY_MODE_FULL_DAY, PAY_MODE_TRIP_DAY)

TRIP_PRICING_ALLOWANCES = "allowances"
TRIP_PRICING_FIXED = "fixed_plus_lodging"


def dec(value) -> Decimal:
    if value in (None, ""):
        return ZERO
    return Decimal(str(value))


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def worker_hourly_rate(worker: Worker | None) -> Decimal:
    """Себестоимость часа работника: внутренняя дневная ставка ÷ 8."""
    if not worker:
        return ZERO
    day_rate = dec(worker.regular_day_rate)
    return (day_rate / REGULAR_DAY_HOURS).quantize(CENT) if day_rate > 0 else ZERO


def card_day_rate(worker: Worker, pay_mode: str) -> Decimal:
    if pay_mode == PAY_MODE_FULL_DAY:
        return dec(worker.regular_day_rate)
    if pay_mode == PAY_MODE_TRIP_DAY:
        return dec(worker.trip_work_day_rate)
    return ZERO


def allocate(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Разложить сумму по весам в парах: доли — вниз до пары, остаток — последней доле.

    Части неотрицательны и в сумме дают ровно исходную сумму. Округление вниз, а не
    до ближайшего, нужно, чтобы остаток не стал отрицательным: 0,02 на четыре равные
    доли — это 0 + 0 + 0 + 0,02, а не 0,01 × 3 и −0,01. Тот же расчёт повторяет форма
    (allocateParas в workDiaryUtils.js).
    """
    if not weights:
        return []
    total_paras = int((money(total) * 100).to_integral_value())
    weights = [max(weight, ZERO) for weight in weights]
    weight_sum = sum(weights, ZERO)
    if weight_sum <= 0:
        weights = [ONE for _ in weights]
        weight_sum = Decimal(len(weights))
    parts = [
        int((Decimal(total_paras) * weight / weight_sum).to_integral_value(rounding=ROUND_FLOOR))
        for weight in weights[:-1]
    ]
    parts.append(total_paras - sum(parts))
    return [Decimal(part).scaleb(-2) for part in parts]


# --- Режим оплаты работника за дату -------------------------------------------------


def _resolve_allowance(value, existing_value, card_value, *, pay_mode: str, same_mode: bool, fixed_trip: bool):
    # При фиксированной ставке командировки суточные и питание уже внутри неё —
    # так же их исключает расчёт выплаты работнику.
    if fixed_trip:
        return ZERO
    if value is not None:
        return dec(value)
    if same_mode:
        return dec(existing_value)
    if pay_mode == PAY_MODE_TRIP_DAY:
        return dec(card_value)
    return ZERO


async def apply_worker_day_inputs(
    db: AsyncSession,
    *,
    day: date,
    workers: list[Worker],
    inputs: list,
) -> None:
    """Сохранить режимы оплаты и командировочные работников записи на её дату.

    Строка общая для всех записей работника за эту дату. Пустые суммы означают «по
    карточке работника», но уже сохранённый снимок того же режима при этом не
    перечитывается: позднейшая правка карточки прошлую себестоимость не меняет.
    Нулевой снимок ставки — пробел, а не решение, поэтому его берём из карточки заново.
    """
    if not inputs:
        return
    workers_by_id = {worker.id: worker for worker in workers}
    unknown = [item.worker_id for item in inputs if item.worker_id not in workers_by_id]
    if unknown:
        raise HTTPException(400, f"Worker {unknown[0]} is not assigned to this work diary entry")

    result = await db.execute(
        select(WorkDiaryWorkerDay).where(
            WorkDiaryWorkerDay.date == day,
            WorkDiaryWorkerDay.worker_id.in_(list(workers_by_id)),
        )
    )
    existing_by_worker = {row.worker_id: row for row in result.scalars().all()}

    for item in inputs:
        worker = workers_by_id[item.worker_id]
        existing = existing_by_worker.get(worker.id)
        pay_mode = item.pay_mode
        same_mode = existing is not None and existing.pay_mode == pay_mode

        day_rate = ZERO
        day_rate_manual = False
        trip_pricing_mode = None
        if pay_mode in DAY_PAY_MODES:
            if item.day_rate is not None:
                day_rate = dec(item.day_rate)
                day_rate_manual = True
            elif same_mode and not existing.day_rate_manual and dec(existing.day_rate) > 0:
                day_rate = dec(existing.day_rate)
            else:
                day_rate = card_day_rate(worker, pay_mode)
        if pay_mode == PAY_MODE_TRIP_DAY:
            trip_pricing_mode = (
                existing.trip_pricing_mode
                if same_mode and existing.trip_pricing_mode
                else (worker.trip_pricing_mode or TRIP_PRICING_ALLOWANCES)
            )
        fixed_trip = pay_mode == PAY_MODE_TRIP_DAY and trip_pricing_mode == TRIP_PRICING_FIXED
        rules = {"pay_mode": pay_mode, "same_mode": same_mode, "fixed_trip": fixed_trip}
        per_diem = _resolve_allowance(
            item.per_diem_amount, getattr(existing, "per_diem_amount", None), worker.trip_per_diem_rate, **rules
        )
        food = _resolve_allowance(
            item.food_amount, getattr(existing, "food_amount", None), worker.trip_food_rate, **rules
        )
        if item.lodging_amount is not None:
            lodging = dec(item.lodging_amount)
        else:
            lodging = dec(existing.lodging_amount) if existing is not None else ZERO

        if pay_mode == PAY_MODE_HOURLY and per_diem == 0 and food == 0 and lodging == 0:
            if existing is not None:
                await db.delete(existing)
            continue

        row = existing or WorkDiaryWorkerDay(worker_id=worker.id, date=day)
        row.pay_mode = pay_mode
        row.day_rate = day_rate
        row.day_rate_manual = day_rate_manual
        row.trip_pricing_mode = trip_pricing_mode
        row.per_diem_amount = per_diem
        row.food_amount = food
        row.lodging_amount = lodging
        if existing is None:
            db.add(row)


async def delete_orphan_worker_days(db: AsyncSession, pairs: set[tuple[int, date]]) -> None:
    """Убрать начисления за дни, в которых у работника не осталось ни одной записи.

    Вызывать после flush: перенос или удаление записи уже должны быть в базе.
    """
    if not pairs:
        return
    worker_ids = {worker_id for worker_id, _ in pairs}
    dates = {day for _, day in pairs}
    occupied_result = await db.execute(
        select(WorkDiaryEntryWorker.worker_id, WorkDiaryEntry.date)
        .join(WorkDiaryEntry, WorkDiaryEntry.id == WorkDiaryEntryWorker.entry_id)
        .where(WorkDiaryEntryWorker.worker_id.in_(worker_ids), WorkDiaryEntry.date.in_(dates))
        .distinct()
    )
    occupied = set(occupied_result.all())
    orphan_ids = []
    rows = await db.execute(
        select(WorkDiaryWorkerDay).where(
            WorkDiaryWorkerDay.worker_id.in_(worker_ids),
            WorkDiaryWorkerDay.date.in_(dates),
        )
    )
    for row in rows.scalars().all():
        key = (row.worker_id, row.date)
        if key in pairs and key not in occupied:
            orphan_ids.append(row.id)
    if orphan_ids:
        await db.execute(delete(WorkDiaryWorkerDay).where(WorkDiaryWorkerDay.id.in_(orphan_ids)))


# --- Расчёт начислений записи ----------------------------------------------------------


@dataclass
class DayContext:
    """Всё, что нужно записи из соседних записей её работников за ту же дату.

    day_entries — записи работника за дату по возрастанию id с часами на объекте:
    по ним дневная сумма раскладывается в парах одинаково для каждой из записей.
    """

    worker_days: dict[tuple[int, date], WorkDiaryWorkerDay] = field(default_factory=dict)
    day_entries: dict[tuple[int, date], list[tuple[int, Decimal]]] = field(default_factory=dict)
    hourly_rates: dict[tuple[int, int], Decimal | None] = field(default_factory=dict)

    def entries_of_day(self, key: tuple[int, date], entry_id: int, hours: Decimal) -> list[tuple[int, Decimal]]:
        rows = list(self.day_entries.get(key, []))
        if all(row_id != entry_id for row_id, _ in rows):
            rows.append((entry_id, hours))
            rows.sort(key=lambda row: row[0])
        return rows


def day_part(amount: Decimal, rows: list[tuple[int, Decimal]], entry_id: int) -> Decimal:
    """Часть дневной суммы, приходящаяся на запись: по часам, в парах.

    Остаток от округления получает запись с наибольшим id — так сумма частей по всем
    записям дня (и по всем проектам) ровно равна дневной сумме.
    """
    if amount == 0:
        return ZERO
    parts = allocate(amount, [hours for _, hours in rows])
    return next(part for (row_id, _), part in zip(rows, parts, strict=True) if row_id == entry_id)


async def load_day_context(db: AsyncSession, entries: list[WorkDiaryEntry]) -> DayContext:
    context = DayContext()
    pairs = {(worker.id, entry.date) for entry in entries for worker in entry.workers}
    if not pairs:
        return context
    worker_ids = {worker_id for worker_id, _ in pairs}
    dates = {day for _, day in pairs}

    worker_days = await db.execute(
        select(WorkDiaryWorkerDay).where(
            WorkDiaryWorkerDay.worker_id.in_(worker_ids),
            WorkDiaryWorkerDay.date.in_(dates),
        )
    )
    for row in worker_days.scalars().all():
        key = (row.worker_id, row.date)
        if key in pairs:
            context.worker_days[key] = row

    day_rows = await db.execute(
        select(
            WorkDiaryEntryWorker.worker_id,
            WorkDiaryEntry.date,
            WorkDiaryEntry.id,
            WorkDiaryEntry.duration_hours,
        )
        .join(WorkDiaryEntry, WorkDiaryEntry.id == WorkDiaryEntryWorker.entry_id)
        .where(WorkDiaryEntryWorker.worker_id.in_(worker_ids), WorkDiaryEntry.date.in_(dates))
        .order_by(WorkDiaryEntry.id)
    )
    for worker_id, day, entry_id, duration_hours in day_rows.all():
        key = (worker_id, day)
        if key in pairs:
            context.day_entries.setdefault(key, []).append((entry_id, dec(duration_hours).quantize(CENT)))

    entry_ids = [entry.id for entry in entries if entry.id is not None]
    if entry_ids:
        rates = await db.execute(
            select(
                WorkDiaryEntryWorker.entry_id,
                WorkDiaryEntryWorker.worker_id,
                WorkDiaryEntryWorker.hourly_rate_snapshot,
            ).where(WorkDiaryEntryWorker.entry_id.in_(entry_ids))
        )
        for entry_id, worker_id, rate in rates.all():
            context.hourly_rates[(entry_id, worker_id)] = dec(rate) if rate is not None else None
    return context


@dataclass
class WorkerShare:
    worker_id: int
    worker_name: str
    pay_mode: str
    hourly_rate: Decimal
    day_rate: Decimal
    day_rate_manual: bool
    rate_missing: bool
    trip_pricing_mode: str | None
    per_diem: Decimal
    food: Decimal
    lodging: Decimal
    day_hours: Decimal
    day_entries: int
    share: Decimal
    labor: Decimal
    allowances: Decimal

    @property
    def accrued(self) -> Decimal:
        return self.labor + self.allowances


@dataclass
class EntryCost:
    hourly_labor: Decimal
    day_labor: Decimal
    worker_day_allowances: Decimal
    legacy_allowances: Decimal
    workers: list[WorkerShare]

    @property
    def labor(self) -> Decimal:
        return self.hourly_labor + self.day_labor

    @property
    def allowances(self) -> Decimal:
        return self.legacy_allowances + self.worker_day_allowances


def entry_cost(entry: WorkDiaryEntry, context: DayContext) -> EntryCost:
    """Начисления по записи: почасовой труд, доли дневных ставок и командировочных.

    Почасовая часть считается от ставки бригады, как раньше, и делится между
    работниками по их ставкам часа; работники, оплачиваемые за день, из неё
    выпадают и получают долю своей дневной суммы — в парах, по часам записей дня.
    Пока вся бригада оплачивается по часам, итог совпадает с прежним расчётом.
    """
    workers = sorted(entry.workers, key=lambda worker: (worker.name or "").casefold())
    worker_count = len(workers)
    hours = dec(entry.duration_hours)
    team_rate = dec(entry.team_hourly_rate_snapshot)
    hour_units = dec(entry.regular_duration_hours) + dec(entry.overtime_duration_hours) * dec(entry.overtime_multiplier)
    team_hourly_labor = hour_units * team_rate

    # Старые надбавки записи: дневница и питание — на человека, проживание — на бригаду.
    legacy_per_worker = ZERO
    if entry.per_diem:
        legacy_per_worker += dec(entry.per_diem_amount)
    if entry.food_allowance:
        legacy_per_worker += dec(entry.food_amount)
    legacy_lodging = dec(entry.lodging_amount)
    legacy_total = legacy_lodging + legacy_per_worker * worker_count

    rates = []
    for worker in workers:
        snapshot = context.hourly_rates.get((entry.id, worker.id))
        rates.append(snapshot if snapshot is not None else worker_hourly_rate(worker))
    total_rate = sum(rates, ZERO)

    shares: list[WorkerShare] = []
    hourly_rate_sum = ZERO
    hourly_count = 0
    day_labor = ZERO
    worker_day_allowances = ZERO
    for worker, rate in zip(workers, rates, strict=True):
        key = (worker.id, entry.date)
        worker_day = context.worker_days.get(key)
        pay_mode = worker_day.pay_mode if worker_day is not None else PAY_MODE_HOURLY
        day_rows = context.entries_of_day(key, entry.id, hours)
        day_hours = sum((row_hours for _, row_hours in day_rows), ZERO)
        share = hours / day_hours if day_hours > 0 else ONE / Decimal(len(day_rows))
        weight = rate / total_rate if total_rate > 0 else ONE / Decimal(worker_count)

        day_rate = dec(worker_day.day_rate) if worker_day is not None else ZERO
        if pay_mode in DAY_PAY_MODES:
            labor = day_part(day_rate, day_rows, entry.id)
            day_labor += labor
        else:
            labor = team_hourly_labor * weight
            hourly_rate_sum += rate
            hourly_count += 1

        per_diem = dec(worker_day.per_diem_amount) if worker_day is not None else ZERO
        food = dec(worker_day.food_amount) if worker_day is not None else ZERO
        lodging = dec(worker_day.lodging_amount) if worker_day is not None else ZERO
        own_allowances = day_part(per_diem + food + lodging, day_rows, entry.id)
        worker_day_allowances += own_allowances
        legacy_share = legacy_per_worker + (legacy_lodging / Decimal(worker_count) if worker_count else ZERO)

        shares.append(
            WorkerShare(
                worker_id=worker.id,
                worker_name=worker.name,
                pay_mode=pay_mode,
                hourly_rate=rate,
                day_rate=day_rate,
                day_rate_manual=bool(worker_day.day_rate_manual) if worker_day is not None else False,
                rate_missing=(pay_mode in DAY_PAY_MODES and day_rate <= 0 and not bool(worker_day.day_rate_manual)),
                trip_pricing_mode=worker_day.trip_pricing_mode if worker_day is not None else None,
                per_diem=per_diem,
                food=food,
                lodging=lodging,
                day_hours=day_hours,
                day_entries=len(day_rows),
                share=share,
                labor=labor,
                allowances=own_allowances + legacy_share,
            )
        )

    if total_rate > 0:
        hourly_fraction = hourly_rate_sum / total_rate
    else:
        hourly_fraction = Decimal(hourly_count) / Decimal(worker_count) if worker_count else ONE
    return EntryCost(
        hourly_labor=team_hourly_labor * hourly_fraction,
        day_labor=day_labor,
        worker_day_allowances=worker_day_allowances,
        legacy_allowances=legacy_total,
        workers=shares,
    )


# --- Сверка начислений с выплатами -----------------------------------------------------


@dataclass
class WorkerAccrual:
    worker_id: int
    day: date
    entry_id: int
    project_id: int
    amount: Decimal


async def load_worker_accruals(
    db: AsyncSession,
    worker_ids: set[int],
    date_from: date,
    date_to: date,
) -> list[WorkerAccrual]:
    """Начисления работников по дневнику за период — по всем проектам."""
    if not worker_ids or date_from > date_to:
        return []
    result = await db.execute(
        select(WorkDiaryEntry)
        .options(selectinload(WorkDiaryEntry.workers))
        .where(
            WorkDiaryEntry.date >= date_from,
            WorkDiaryEntry.date <= date_to,
            WorkDiaryEntry.workers.any(Worker.id.in_(worker_ids)),
        )
    )
    entries = list(result.scalars().unique().all())
    context = await load_day_context(db, entries)
    accruals = []
    for entry in entries:
        for share in entry_cost(entry, context).workers:
            if share.worker_id in worker_ids:
                accruals.append(
                    WorkerAccrual(
                        worker_id=share.worker_id,
                        day=entry.date,
                        entry_id=entry.id,
                        project_id=entry.project_id,
                        amount=share.accrued,
                    )
                )
    return accruals


@dataclass
class PayoutCost:
    payout: WorkerPayout
    amount: Decimal
    worker_name: str | None
    project_name: str | None
    in_project: bool
    reconciled: bool
    period_accrued: Decimal | None = None
    excess: Decimal = ZERO


@dataclass
class ReconciliationGroup:
    worker_id: int
    worker_name: str | None
    period_start: date
    period_end: date
    accrued: Decimal = ZERO
    accrued_in_project: Decimal = ZERO
    payouts: list[PayoutCost] = field(default_factory=list)

    @property
    def paid(self) -> Decimal:
        return sum((item.amount for item in self.payouts), ZERO)


@dataclass
class ProjectPayouts:
    payouts: list[PayoutCost]
    groups: list[ReconciliationGroup]

    @property
    def total(self) -> Decimal:
        return sum((item.amount for item in self.payouts), ZERO)

    @property
    def unmatched(self) -> Decimal:
        return sum((item.amount for item in self.payouts if not item.reconciled), ZERO)

    @property
    def excess(self) -> Decimal:
        return sum((item.excess for item in self.payouts if item.reconciled), ZERO)

    @property
    def matched(self) -> Decimal:
        return sum((item.amount - item.excess for item in self.payouts if item.reconciled), ZERO)


def is_reconciled(payout: WorkerPayout) -> bool:
    return bool(payout.diary_reconciled and payout.period_start and payout.period_end)


def _payout_query():
    return (
        select(WorkerPayout, Expense.amount, Expense.project_id, Worker.name, Project.name)
        .join(Expense, Expense.id == WorkerPayout.expense_id)
        .outerjoin(Worker, Worker.id == WorkerPayout.worker_id)
        .outerjoin(Project, Project.id == Expense.project_id)
        .where(
            WorkerPayout.cancelled_at.is_(None),
            Expense.source != CASH_TRANSFER_SOURCE,
            visible_expense_condition(),
        )
    )


async def project_payouts(
    db: AsyncSession,
    *,
    project_id: int,
    date_from: date | None,
    date_to: date | None,
    project_accruals: list[WorkerAccrual],
) -> ProjectPayouts:
    """Выплаты работникам, записанные расходами проекта, и их сверка с дневником.

    project_accruals — начисления этого проекта по дневнику (все даты): по ним
    находятся группы сверки, покрывающие работу на объекте, даже если сами выплаты
    записаны на другой проект, например зарплатный.
    """
    query = _payout_query().where(Expense.project_id == project_id)
    if date_from is not None:
        query = query.where(Expense.date >= date_from)
    if date_to is not None:
        query = query.where(Expense.date <= date_to)
    result = await db.execute(query.order_by(Expense.date, WorkerPayout.id))
    payouts = [
        PayoutCost(
            payout=payout,
            amount=dec(amount),
            worker_name=worker_name,
            project_name=project_name,
            in_project=True,
            reconciled=is_reconciled(payout),
        )
        for payout, amount, _, worker_name, project_name in result.all()
    ]

    # Группы сверки: сопоставленные выплаты этого проекта и сопоставленные выплаты
    # работников, чья работа на объекте попадает в их период.
    group_keys: set[tuple[int, date, date]] = {
        (item.payout.worker_id, item.payout.period_start, item.payout.period_end) for item in payouts if item.reconciled
    }
    accrual_workers = {accrual.worker_id for accrual in project_accruals}
    if accrual_workers:
        first_day = min(accrual.day for accrual in project_accruals)
        last_day = max(accrual.day for accrual in project_accruals)
        covering = await db.execute(
            select(WorkerPayout.worker_id, WorkerPayout.period_start, WorkerPayout.period_end).where(
                WorkerPayout.cancelled_at.is_(None),
                WorkerPayout.diary_reconciled.is_(True),
                WorkerPayout.worker_id.in_(accrual_workers),
                WorkerPayout.period_start.is_not(None),
                WorkerPayout.period_end.is_not(None),
                WorkerPayout.period_start <= last_day,
                WorkerPayout.period_end >= first_day,
            )
        )
        accrual_days = {(accrual.worker_id, accrual.day) for accrual in project_accruals}
        for worker_id, start, end in covering.all():
            if any(worker == worker_id and start <= day <= end for worker, day in accrual_days):
                group_keys.add((worker_id, start, end))

    groups: dict[tuple[int, date, date], ReconciliationGroup] = {}
    if group_keys:
        group_workers = {worker_id for worker_id, _, _ in group_keys}
        members = await db.execute(
            _payout_query()
            .where(
                WorkerPayout.diary_reconciled.is_(True),
                WorkerPayout.worker_id.in_(group_workers),
                WorkerPayout.period_start.is_not(None),
                WorkerPayout.period_end.is_not(None),
            )
            .order_by(Expense.date, WorkerPayout.id)
        )
        listed = {item.payout.id: item for item in payouts}
        for payout, amount, expense_project_id, worker_name, project_name in members.all():
            key = (payout.worker_id, payout.period_start, payout.period_end)
            if key not in group_keys:
                continue
            group = groups.setdefault(
                key,
                ReconciliationGroup(
                    worker_id=payout.worker_id,
                    worker_name=worker_name,
                    period_start=payout.period_start,
                    period_end=payout.period_end,
                ),
            )
            # Выплата проекта вне фильтра по датам тоже участвует в группе, но в итог
            # затрат проекта за выбранный период не попадает.
            group.payouts.append(
                listed.get(payout.id)
                or PayoutCost(
                    payout=payout,
                    amount=dec(amount),
                    worker_name=worker_name,
                    project_name=project_name,
                    in_project=expense_project_id == project_id,
                    reconciled=True,
                )
            )

    # Начисления по дневнику за периоды групп и выплат с периодом — по всем проектам.
    windows: dict[int, tuple[date, date]] = {}

    def widen(worker_id: int, start: date, end: date) -> None:
        current = windows.get(worker_id)
        windows[worker_id] = (min(current[0], start), max(current[1], end)) if current else (start, end)

    for worker_id, start, end in groups:
        widen(worker_id, start, end)
    for item in payouts:
        if item.payout.period_start and item.payout.period_end:
            widen(item.payout.worker_id, item.payout.period_start, item.payout.period_end)
    accruals_by_worker: dict[int, list[WorkerAccrual]] = defaultdict(list)
    if windows:
        first_day = min(start for start, _ in windows.values())
        last_day = max(end for _, end in windows.values())
        for accrual in await load_worker_accruals(db, set(windows), first_day, last_day):
            accruals_by_worker[accrual.worker_id].append(accrual)

    def accrued_between(worker_id: int, start: date, end: date, project: int | None = None) -> Decimal:
        return sum(
            (
                accrual.amount
                for accrual in accruals_by_worker.get(worker_id, [])
                if start <= accrual.day <= end and (project is None or accrual.project_id == project)
            ),
            ZERO,
        )

    for item in payouts:
        if item.payout.period_start and item.payout.period_end:
            item.period_accrued = accrued_between(
                item.payout.worker_id, item.payout.period_start, item.payout.period_end
            )

    for (worker_id, start, end), group in groups.items():
        group.accrued = accrued_between(worker_id, start, end)
        group.accrued_in_project = accrued_between(worker_id, start, end, project_id)
        # Выплачено сверх начислений — настоящие деньги, которых в дневнике нет: эта
        # часть остаётся затратой проекта, куда записана выплата.
        excess_total = max(group.paid - money(group.accrued), ZERO)
        for member, part in zip(
            group.payouts, allocate(excess_total, [member.amount for member in group.payouts]), strict=True
        ):
            member.excess = part

    return ProjectPayouts(
        payouts=payouts,
        groups=sorted(groups.values(), key=lambda group: (group.period_start, group.worker_name or "")),
    )


async def set_payout_reconciliation(db: AsyncSession, payout_id: int, reconciled: bool) -> WorkerPayout:
    result = await db.execute(select(WorkerPayout).where(WorkerPayout.id == payout_id))
    payout = result.scalar_one_or_none()
    if payout is None:
        raise HTTPException(404, "Worker payout not found")
    if reconciled:
        if payout.cancelled_at is not None:
            raise HTTPException(400, "A cancelled payout cannot be reconciled with the work diary")
        if not (payout.period_start and payout.period_end):
            raise HTTPException(400, "Set the payout period before reconciling it with the work diary")
        overlapping = await db.execute(
            select(WorkerPayout.id).where(
                WorkerPayout.id != payout.id,
                WorkerPayout.worker_id == payout.worker_id,
                WorkerPayout.diary_reconciled.is_(True),
                WorkerPayout.cancelled_at.is_(None),
                WorkerPayout.period_start <= payout.period_end,
                WorkerPayout.period_end >= payout.period_start,
                ~((WorkerPayout.period_start == payout.period_start) & (WorkerPayout.period_end == payout.period_end)),
            )
        )
        if overlapping.scalars().first() is not None:
            raise HTTPException(
                409,
                "Another reconciled payout of this worker covers an overlapping but different period.",
            )
    payout.diary_reconciled = reconciled
    return payout
