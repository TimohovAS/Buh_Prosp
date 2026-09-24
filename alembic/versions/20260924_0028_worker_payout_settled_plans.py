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
    # Отметки погашения — производные данные: при сторно или смене типа выплаты
    # они исчезают, и узнать, к какому плану выплата относилась, было бы неоткуда.
    # Храним это на самой выплате; уже существующие отметки переносим сюда.
    op.add_column("worker_payouts", sa.Column("settled_plan_ids", sa.Text(), nullable=True))

    connection = op.get_bind()
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
