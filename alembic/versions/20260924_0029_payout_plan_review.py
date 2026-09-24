"""Leave only unconfirmed plan ownership of old payouts for manual review.

Revision ID: 20260924_0029
Revises: 20260924_0028
Create Date: 2026-09-24 00:00:00.000000

"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from backend.planned_expenses_service import plans_for_payout_day


revision: str = "20260924_0029"
down_revision: Union[str, Sequence[str], None] = "20260924_0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _as_date(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def upgrade() -> None:
    # "[]" — выплата ни к какому плану не относится, NULL — связь не подтверждена
    # отметкой и её решает человек. Без отметки принадлежность не доказать: у
    # сторнированных выплат отметки пропали ещё в момент сторно, у переведённых в
    # командировочные — при смене типа, а одна дата платежа — лишь догадка. Поэтому
    # ничего не угадываем: NULL остаётся только там, где день выплаты приходится на
    # выключенный план, — выбор между ним и остальными важен лишь в этом случае.
    # Миграция одинаково приводит в порядок и новую базу, и базу, где уже прошла
    # прежняя 0028 и оставила NULL почти у всех выплат.
    connection = op.get_bind()
    plans_by_worker: dict[int, list[SimpleNamespace]] = {}
    for row in connection.execute(
        sa.text(
            "SELECT id, worker_id, amount, period, payment_day, payment_day_of_week, start_date, end_date, is_active"
            " FROM planned_expenses WHERE worker_id IS NOT NULL ORDER BY id"
        )
    ):
        plans_by_worker.setdefault(int(row.worker_id), []).append(
            SimpleNamespace(
                id=int(row.id),
                amount=Decimal(str(row.amount or 0)),
                period=row.period,
                payment_day=row.payment_day,
                payment_day_of_week=row.payment_day_of_week,
                start_date=_as_date(row.start_date),
                end_date=_as_date(row.end_date),
                is_active=bool(row.is_active),
            )
        )

    review: list[tuple[int, str, str, bool, list[int]]] = []
    for payout in connection.execute(
        sa.text(
            "SELECT id, worker_id, payout_type, date, period_start, period_end, cancelled_at"
            " FROM worker_payouts WHERE settled_plan_ids IS NULL ORDER BY date, id"
        )
    ).fetchall():
        plans = plans_by_worker.get(int(payout.worker_id or 0)) or []
        candidates = plans_for_payout_day(plans, payout) if payout.date else []
        if any(not plan.is_active for plan in candidates):
            review.append(
                (
                    int(payout.id),
                    str(payout.payout_type),
                    str(payout.date)[:10],
                    payout.cancelled_at is not None,
                    sorted(plan.id for plan in candidates),
                )
            )
            continue
        connection.execute(
            sa.text("UPDATE worker_payouts SET settled_plan_ids = '[]' WHERE id = :id"), {"id": int(payout.id)}
        )

    if review:
        print(
            "[0029] Старые выплаты, чья связь с выключенным планом зарплаты не подтверждена:"
            " по одной дате её не доказать, поэтому решение за человеком. Список можно"
            " посмотреть в любой момент: GET /api/workers/payouts/plan-review; план задаётся"
            " через PUT /api/workers/payouts/{id}/settled-plans (пустой список — ни к какому)."
        )
        for payout_id, payout_type, payout_date, cancelled, plan_ids in review:
            state = ", сторнирована" if cancelled else ""
            print(f"  выплата #{payout_id} ({payout_type}{state}, {payout_date}): планы-кандидаты {plan_ids}")


def downgrade() -> None:
    # Пустой список и NULL значат одно и то же для раскладки; различие нужно только
    # проверке. Возвращаем NULL выплатам без планов, как было после 0028.
    op.execute("UPDATE worker_payouts SET settled_plan_ids = NULL WHERE settled_plan_ids = '[]'")
