"""Count purchases already linked to a worker against their planned salary.

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


# Покупки в счёт зарплаты появились раньше, чем частичное погашение, поэтому
# отметок за ними нет вовсе. Раскладываем их так же, как это делает приложение:
# выплаты переигрываются по дате, каждая берёт не больше остатка периода.
SETTLING_TYPES = ("regular", "weekly", "monthly", "purchase")
AUTO_NOTE = "auto_worker_payout:{payout_id}"


def _as_date(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _plan_stub(row) -> SimpleNamespace:
    """Минимум полей, которые нужны генератору дат платежей."""
    return SimpleNamespace(
        id=row.id,
        amount=Decimal(str(row.amount or 0)),
        period=row.period,
        payment_day=row.payment_day,
        payment_day_of_week=row.payment_day_of_week,
        start_date=_as_date(row.start_date),
        end_date=_as_date(row.end_date),
        is_active=bool(row.is_active),
    )


def upgrade() -> None:
    connection = op.get_bind()
    plans = [
        _plan_stub(row)
        for row in connection.execute(
            sa.text(
                "SELECT id, worker_id, amount, period, payment_day, payment_day_of_week,"
                " start_date, end_date, is_active"
                " FROM planned_expenses WHERE is_active = 1 AND worker_id IS NOT NULL"
            )
        )
    ]
    if not plans:
        return
    plans_by_worker: dict[int, list[SimpleNamespace]] = {}
    for row in connection.execute(
        sa.text("SELECT id, worker_id FROM planned_expenses WHERE is_active = 1 AND worker_id IS NOT NULL")
    ):
        plan = next((item for item in plans if item.id == row.id), None)
        if plan is not None:
            plans_by_worker.setdefault(int(row.worker_id), []).append(plan)

    settled: dict[tuple[int, date], Decimal] = {}
    for row in connection.execute(
        sa.text("SELECT planned_expense_id, due_date, amount FROM planned_expense_payments")
    ):
        key = (int(row.planned_expense_id), _as_date(row.due_date))
        settled[key] = settled.get(key, Decimal("0")) + Decimal(str(row.amount or 0))

    # Уже размеченные выплаты второй раз не считаем.
    marked = {
        int(row.worker_payout_id)
        for row in connection.execute(
            sa.text("SELECT DISTINCT worker_payout_id FROM planned_expense_payments WHERE worker_payout_id IS NOT NULL")
        )
    }

    placeholders = ", ".join(f"'{item}'" for item in SETTLING_TYPES)
    payouts = connection.execute(
        sa.text(
            "SELECT id, worker_id, payout_type, date, period_start, period_end, cash_paid_amount"
            f" FROM worker_payouts WHERE cancelled_at IS NULL AND payout_type IN ({placeholders})"
            " ORDER BY date ASC, id ASC"
        )
    ).fetchall()

    created = 0
    for payout in payouts:
        if int(payout.id) in marked:
            continue
        plans_for_worker = plans_by_worker.get(int(payout.worker_id or 0)) or []
        paid_amount = Decimal(str(payout.cash_paid_amount or 0))
        payout_date = _as_date(payout.date)
        if not plans_for_worker or paid_amount <= 0 or payout_date is None:
            continue

        period_start = _as_date(payout.period_start) or (payout_date - timedelta(days=45))
        period_end = _as_date(payout.period_end) or (payout_date + timedelta(days=14))
        if period_end < period_start:
            period_start = period_end = payout_date

        open_pairs = [
            (plan, due_date)
            for plan in plans_for_worker
            for due_date in payment_dates_in_range(plan, period_start, period_end, limit=24)
            if plan.amount - settled.get((plan.id, due_date), Decimal("0")) > 0
        ]
        if not open_pairs:
            continue
        plan, due_date = min(
            open_pairs,
            key=lambda pair: (abs((pair[1] - payout_date).days), pair[1] > payout_date, pair[1], pair[0].id),
        )
        key = (plan.id, due_date)
        remaining = plan.amount - settled.get(key, Decimal("0"))
        amount = min(paid_amount, remaining)
        connection.execute(
            sa.text(
                "INSERT INTO planned_expense_payments"
                " (planned_expense_id, due_date, paid_date, amount, worker_payout_id, note, created_at)"
                " VALUES (:planned_expense_id, :due_date, :paid_date, :amount, :worker_payout_id, :note, :created_at)"
            ),
            {
                "planned_expense_id": plan.id,
                "due_date": due_date.isoformat(),
                "paid_date": payout_date.isoformat(),
                "amount": str(amount),
                "worker_payout_id": int(payout.id),
                "note": AUTO_NOTE.format(payout_id=int(payout.id)),
                "created_at": datetime.utcnow().isoformat(sep=" "),
            },
        )
        settled[key] = settled.get(key, Decimal("0")) + amount
        created += 1
    print(f"[0023] Погашений зарплаты добавлено: {created}")


def downgrade() -> None:
    # Отметки, созданные этой миграцией, отличить от прочих автоматических нельзя,
    # а приложение пересобирает их само, поэтому откат ничего не удаляет.
    pass
