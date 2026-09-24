"""Rebuild salary settlements so old purchases count against the right month.

Revision ID: 20260922_0023
Revises: 20260922_0022
Create Date: 2026-09-22 00:00:00.000000

"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from backend.planned_expenses_service import payment_dates_in_range


revision: str = "20260922_0023"
down_revision: Union[str, Sequence[str], None] = "20260922_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Раскладка зарплаты по периодам раньше зависела от порядка действий, а покупки
# в её счёт не участвовали вовсе. Пересобираем её так же, как это теперь делает
# приложение: автоматические отметки сносим, ручные оставляем как уже погашенное,
# выплаты переигрываем по дате.
SETTLING_TYPES = ("regular", "weekly", "monthly", "purchase")
ZERO = Decimal("0")


def _as_date(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _plan_stub(row) -> SimpleNamespace:
    """Минимум полей, которые нужны генератору дат платежей."""
    return SimpleNamespace(
        id=int(row.id),
        worker_id=int(row.worker_id),
        amount=Decimal(str(row.amount or 0)),
        period=row.period,
        payment_day=row.payment_day,
        payment_day_of_week=row.payment_day_of_week,
        start_date=_as_date(row.start_date),
        end_date=_as_date(row.end_date),
        is_active=bool(row.is_active),
    )


def _active_view(plan: SimpleNamespace) -> SimpleNamespace:
    """Выключенный план глазами раскладки: действующим в его датах."""
    return SimpleNamespace(**{**vars(plan), "is_active": True})


def _month_bounds(day: date) -> tuple[date, date]:
    first = day.replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return first, next_month - timedelta(days=1)


def upgrade() -> None:
    connection = op.get_bind()

    # Покупка без периода попала бы в соседний месяц: проставляем ей месяц самой
    # траты. Делаем это до всего остального — даже если зарплатных планов нет,
    # период должен быть записан, чтобы будущий пересчёт был устойчивым.
    for row in connection.execute(
        sa.text(
            "SELECT id, date FROM worker_payouts"
            " WHERE payout_type = 'purchase' AND (period_start IS NULL OR period_end IS NULL)"
        )
    ).fetchall():
        payout_date = _as_date(row.date)
        if payout_date is None:
            continue
        period_start, period_end = _month_bounds(payout_date)
        connection.execute(
            sa.text("UPDATE worker_payouts SET period_start = :start, period_end = :end WHERE id = :id"),
            {"start": period_start.isoformat(), "end": period_end.isoformat(), "id": int(row.id)},
        )

    # Все планы работников: выключенные тоже — выплата, которая уже закрывала
    # такой план, продолжает к нему относиться. Новые выплаты на них не ложатся.
    plans_by_id: dict[int, SimpleNamespace] = {}
    active_by_worker: dict[int, list[SimpleNamespace]] = {}
    for row in connection.execute(
        sa.text(
            "SELECT id, worker_id, amount, period, payment_day, payment_day_of_week,"
            " start_date, end_date, is_active"
            " FROM planned_expenses WHERE worker_id IS NOT NULL ORDER BY id"
        )
    ):
        plan = _plan_stub(row)
        plans_by_id[plan.id] = plan
        if plan.is_active:
            active_by_worker.setdefault(plan.worker_id, []).append(plan)

    placeholders = ", ".join(f"'{item}'" for item in SETTLING_TYPES)
    payouts = connection.execute(
        sa.text(
            "SELECT id, worker_id, payout_type, date, period_start, period_end, cash_paid_amount"
            f" FROM worker_payouts WHERE cancelled_at IS NULL AND payout_type IN ({placeholders})"
            " ORDER BY date ASC, id ASC"
        )
    ).fetchall()
    settling_worker = {int(row.id): int(row.worker_id or 0) for row in payouts}

    # К какому своему выключенному плану выплата уже относилась.
    history: dict[int, list[SimpleNamespace]] = {}
    for row in connection.execute(
        sa.text(
            "SELECT DISTINCT worker_payout_id, planned_expense_id FROM planned_expense_payments"
            " WHERE worker_payout_id IS NOT NULL ORDER BY planned_expense_id"
        )
    ):
        plan = plans_by_id.get(int(row.planned_expense_id))
        payout_id = int(row.worker_payout_id)
        if plan and not plan.is_active and settling_worker.get(payout_id) == plan.worker_id:
            history.setdefault(payout_id, []).append(plan)

    # Все автоматические отметки — производные от выплат: сносим и собираем заново.
    # Вместе с ними уходят отметки перенесённых, погашенных и незарплатных выплат.
    connection.execute(sa.text("DELETE FROM planned_expense_payments WHERE worker_payout_id IS NOT NULL"))

    settled: dict[tuple[int, date], Decimal] = {}
    for row in connection.execute(sa.text("SELECT planned_expense_id, due_date, amount FROM planned_expense_payments")):
        key = (int(row.planned_expense_id), _as_date(row.due_date))
        settled[key] = settled.get(key, ZERO) + Decimal(str(row.amount or 0))

    created = 0
    for payout in payouts:
        # Свой прежний план — первым: при равной дате выплата остаётся на нём.
        plans = [
            *(_active_view(plan) for plan in history.get(int(payout.id), [])),
            *active_by_worker.get(int(payout.worker_id or 0), []),
        ]
        left = Decimal(str(payout.cash_paid_amount or 0))
        payout_date = _as_date(payout.date)
        if not plans or left <= ZERO or payout_date is None:
            continue

        period_start = _as_date(payout.period_start)
        period_end = _as_date(payout.period_end)
        has_period = bool(period_start and period_end)
        window_start = period_start or (payout_date - timedelta(days=45))
        window_end = period_end or (payout_date + timedelta(days=14))
        if window_end < window_start:
            window_start = window_end = payout_date

        ordered = sorted(
            (
                (priority, plan, due_date)
                for priority, plan in enumerate(plans)
                for due_date in payment_dates_in_range(plan, window_start, window_end, limit=24)
            ),
            key=lambda item: (abs((item[2] - payout_date).days), item[2] > payout_date, item[2], item[0]),
        )
        pairs = [(plan, due_date) for _, plan, due_date in ordered]
        # Без периода — только ближайший платёж, даже закрытый: в соседний месяц
        # выплата не перекатывается. С периодом — всё открытое внутри него.
        if not has_period:
            pairs = pairs[:1]
        open_pairs = [pair for pair in pairs if pair[0].amount - settled.get((pair[0].id, pair[1]), ZERO) > ZERO]

        for plan, due_date in open_pairs:
            if left <= ZERO:
                break
            key = (plan.id, due_date)
            amount = min(left, plan.amount - settled.get(key, ZERO))
            if amount <= ZERO:
                continue
            connection.execute(
                sa.text(
                    "INSERT INTO planned_expense_payments"
                    " (planned_expense_id, due_date, paid_date, amount, worker_payout_id, note, created_at)"
                    " VALUES (:planned_expense_id, :due_date, :paid_date, :amount, :worker_payout_id,"
                    " :note, :created_at)"
                ),
                {
                    "planned_expense_id": plan.id,
                    "due_date": due_date.isoformat(),
                    "paid_date": payout_date.isoformat(),
                    "amount": str(amount),
                    "worker_payout_id": int(payout.id),
                    "note": f"auto_worker_payout:{int(payout.id)}",
                    "created_at": datetime.utcnow().isoformat(sep=" "),
                },
            )
            settled[key] = settled.get(key, ZERO) + amount
            left -= amount
            created += 1
    print(f"[0023] Погашений зарплаты пересобрано: {created}")


def downgrade() -> None:
    # Период, проставленный покупкам, и пересобранные погашения — производные
    # данные: приложение собирает погашения заново при любом изменении выплаты.
    # Сносим автоматические погашения активных планов, ручные и историю не трогаем.
    op.execute(
        sa.text(
            "DELETE FROM planned_expense_payments WHERE worker_payout_id IS NOT NULL"
            " AND planned_expense_id IN (SELECT id FROM planned_expenses WHERE is_active = :active)"
        ).bindparams(active=True)
    )
