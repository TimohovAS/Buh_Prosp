"""Settle a planned salary by amount instead of a paid or not paid mark.

Revision ID: 20260921_0021
Revises: 20260921_0020
Create Date: 2026-09-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260921_0021"
down_revision: Union[str, Sequence[str], None] = "20260921_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Прежняя отметка означала «оплачено целиком»: у отметки от выплаты берём
# фактически выданное, у поставленной вручную — плановую сумму.
BACKFILL_FROM_PAYOUT = """
    UPDATE planned_expense_payments
    SET amount = (
        SELECT COALESCE(wp.cash_paid_amount, 0)
        FROM worker_payouts wp
        WHERE wp.id = planned_expense_payments.worker_payout_id
    )
    WHERE worker_payout_id IS NOT NULL
"""

BACKFILL_FROM_PLAN = """
    UPDATE planned_expense_payments
    SET amount = (
        SELECT COALESCE(pe.amount, 0)
        FROM planned_expenses pe
        WHERE pe.id = planned_expense_payments.planned_expense_id
    )
    WHERE worker_payout_id IS NULL
"""


def upgrade() -> None:
    op.add_column(
        "planned_expense_payments",
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )
    op.execute(BACKFILL_FROM_PAYOUT)
    op.execute(BACKFILL_FROM_PLAN)
    op.create_index(
        "ix_planned_expense_payments_occurrence",
        "planned_expense_payments",
        ["planned_expense_id", "due_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_planned_expense_payments_occurrence", table_name="planned_expense_payments")
    op.drop_column("planned_expense_payments", "amount")
