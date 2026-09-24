"""Remember which salary plans a payout settled, apart from its settlement marks.

Revision ID: 20260924_0028
Revises: 20260923_0027
Create Date: 2026-09-24 00:00:00.000000

"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260924_0028"
down_revision: Union[str, Sequence[str], None] = "20260923_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Список планов на самой выплате: "[]" — ни к какому плану, NULL — связь не
    # подтверждена. Здесь заполняем только подтверждённое отметками; какие NULL
    # остаются на проверку, решает следующая миграция 0029.
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

    # 1. Подтверждённая принадлежность — только то, что видно по отметкам.
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
    for payout_id, plan_ids in plans_by_payout.items():
        connection.execute(
            sa.text("UPDATE worker_payouts SET settled_plan_ids = :plans WHERE id = :id"),
            {"plans": json.dumps(sorted(plan_ids)), "id": payout_id},
        )


def downgrade() -> None:
    op.drop_column("worker_payouts", "settled_plan_ids")
