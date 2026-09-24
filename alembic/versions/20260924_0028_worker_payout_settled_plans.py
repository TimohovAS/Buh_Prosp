"""Remember which salary plans a payout settled, apart from its settlement marks.

Revision ID: 20260924_0028
Revises: 20260923_0027
Create Date: 2026-09-24 00:00:00.000000

"""

import json
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from backend.planned_expenses_service import payment_dates_in_range


revision: str = "20260924_0028"
down_revision: Union[str, Sequence[str], None] = "20260923_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SETTLING_TYPES = ("regular", "weekly", "monthly", "purchase")


def _as_date(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _plan_view(row) -> SimpleNamespace:
    """План глазами раскладки: выключенный считаем действующим в его датах."""
    return SimpleNamespace(
        id=int(row.id),
        worker_id=int(row.worker_id),
        was_active=bool(row.is_active),
        amount=Decimal(str(row.amount or 0)),
        period=row.period,
        payment_day=row.payment_day,
        payment_day_of_week=row.payment_day_of_week,
        start_date=_as_date(row.start_date),
        end_date=_as_date(row.end_date),
        is_active=True,
    )


def _nearest_plans(plans: list[SimpleNamespace], payout) -> list[SimpleNamespace]:
    """Планы, чей платёж выплата закрыла бы: ближайший, а с периодом — все в нём."""
    payout_date = _as_date(payout.date)
    period_start = _as_date(payout.period_start)
    period_end = _as_date(payout.period_end)
    window_start = period_start or (payout_date - timedelta(days=45))
    window_end = period_end or (payout_date + timedelta(days=14))
    if window_end < window_start:
        window_start = window_end = payout_date
    pairs = [
        (plan, due_date)
        for plan in plans
        for due_date in payment_dates_in_range(plan, window_start, window_end, limit=24)
    ]
    if not pairs:
        return []
    if period_start and period_end:
        return list({plan.id: plan for plan, _ in pairs}.values())
    nearest = min(abs((due_date - payout_date).days) for _, due_date in pairs)
    closest = [(plan, due_date) for plan, due_date in pairs if abs((due_date - payout_date).days) == nearest]
    first_date = min(due_date for _, due_date in closest)
    return list({plan.id: plan for plan, due_date in closest if due_date == first_date}.values())


def upgrade() -> None:
    op.add_column("worker_payouts", sa.Column("settled_plan_ids", sa.Text(), nullable=True))
    connection = op.get_bind()

    # Отметки удалённых планов: при повторной выдаче ID они перешли бы к чужому плану.
    orphans = connection.execute(
        sa.text(
            "DELETE FROM planned_expense_payments WHERE planned_expense_id NOT IN (SELECT id FROM planned_expenses)"
        )
    ).rowcount
    if orphans:
        print(f"[0028] Удалено отметок погашения несуществующих планов: {orphans}")

    # 1. Принадлежность, которую видно по сохранившимся отметкам.
    plans_by_payout: dict[int, set[int]] = {}
    for row in connection.execute(
        sa.text(
            "SELECT DISTINCT pep.worker_payout_id, pep.planned_expense_id"
            " FROM planned_expense_payments pep"
            " JOIN worker_payouts wp ON wp.id = pep.worker_payout_id"
            " JOIN planned_expenses pe ON pe.id = pep.planned_expense_id"
            " WHERE pe.worker_id = wp.worker_id"
        )
    ):
        plans_by_payout.setdefault(int(row.worker_payout_id), set()).add(int(row.planned_expense_id))

    # 2. У сторнированных выплат отметки пропали ещё в момент сторно, у переведённых
    # в командировочные — при смене типа: истории, кроме дат самих планов, нет.
    # Если на дату выплаты приходится платёж только выключенных планов, выплата
    # относилась к ним. Если рядом платёж и действующего плана — выбор неоднозначен:
    # такие выплаты перечисляем, их принадлежность задаётся вручную.
    plans_by_worker: dict[int, list[SimpleNamespace]] = {}
    for row in connection.execute(
        sa.text(
            "SELECT id, worker_id, amount, period, payment_day, payment_day_of_week,"
            " start_date, end_date, is_active FROM planned_expenses WHERE worker_id IS NOT NULL ORDER BY id"
        )
    ):
        plan = _plan_view(row)
        plans_by_worker.setdefault(plan.worker_id, []).append(plan)

    inferred = 0
    unresolved: list[tuple[int, str, str, list[int]]] = []
    for payout in connection.execute(
        sa.text(
            "SELECT id, worker_id, payout_type, date, period_start, period_end, cancelled_at"
            " FROM worker_payouts WHERE worker_id IS NOT NULL ORDER BY id"
        )
    ).fetchall():
        payout_id = int(payout.id)
        salary_type = payout.payout_type in SETTLING_TYPES
        # Действующие зарплатные выплаты уже разложены — их принадлежность в отметках.
        if payout_id in plans_by_payout or (salary_type and payout.cancelled_at is None):
            continue
        plans = plans_by_worker.get(int(payout.worker_id)) or []
        if not any(not plan.was_active for plan in plans) or _as_date(payout.date) is None:
            continue
        nearest = _nearest_plans(plans, payout)
        switched_off = [plan.id for plan in nearest if not plan.was_active]
        active = [plan.id for plan in nearest if plan.was_active]
        if not switched_off:
            continue
        if salary_type and not active:
            plans_by_payout[payout_id] = set(switched_off)
            inferred += 1
        elif active:
            # Выбор важен только там, где рядом и выключенный, и действующий план.
            unresolved.append((payout_id, str(payout.payout_type), str(payout.date), sorted(switched_off + active)))

    for payout_id, plan_ids in plans_by_payout.items():
        connection.execute(
            sa.text("UPDATE worker_payouts SET settled_plan_ids = :plans WHERE id = :id"),
            {"plans": json.dumps(sorted(plan_ids)), "id": payout_id},
        )

    if inferred:
        print(f"[0028] Принадлежность восстановлена по датам планов: {inferred}")
    if unresolved:
        print(
            "[0028] Не определить однозначно, к какому плану относится выплата "
            "(рядом платежи выключенного и действующего плана). Если выплату "
            "восстановят из сторно или вернут в зарплатные, задайте план вручную: "
            "PUT /api/workers/payouts/{id}/settled-plans"
        )
        for payout_id, payout_type, payout_date, plan_ids in unresolved:
            print(f"  выплата #{payout_id} ({payout_type}, {payout_date}): планы-кандидаты {plan_ids}")


def downgrade() -> None:
    op.drop_column("worker_payouts", "settled_plan_ids")
