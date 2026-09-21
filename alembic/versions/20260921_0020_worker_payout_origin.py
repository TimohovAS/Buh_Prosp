"""Tell calculated worker payouts apart from expense links and allow cancelling.

Revision ID: 20260921_0020
Revises: 20260921_0019
Create Date: 2026-09-21 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260921_0020"
down_revision: Union[str, Sequence[str], None] = "20260921_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Привязанную выплату раньше узнавали по равенству начисленного и выданного, но
# у полностью выплаченной зарплаты суммы равны тоже. Признак проставляем один
# раз здесь: у записей, созданных привязкой, нет ни дней, ни ставок.
BACKFILL_EXPENSE_LINK = """
    UPDATE worker_payouts
    SET origin = 'expense_link'
    WHERE COALESCE(work_days, 0) = 0
      AND COALESCE(trip_days, 0) = 0
      AND COALESCE(lodging_nights, 0) = 0
      AND COALESCE(regular_day_rate, 0) = 0
      AND COALESCE(weekly_rate, 0) = 0
      AND COALESCE(monthly_rate, 0) = 0
      AND COALESCE(trip_work_day_rate, 0) = 0
      AND COALESCE(trip_per_diem_rate, 0) = 0
      AND COALESCE(trip_food_rate, 0) = 0
      AND COALESCE(trip_advance_day_rate, 0) = 0
      AND COALESCE(lodging_amount, 0) = 0
      AND COALESCE(advance_paid, 0) = 0
      AND COALESCE(gross_amount, 0) = COALESCE(cash_paid_amount, 0)
"""


def upgrade() -> None:
    op.add_column(
        "worker_payouts",
        sa.Column("origin", sa.String(length=20), nullable=False, server_default="calculated"),
    )
    op.add_column("worker_payouts", sa.Column("cancelled_at", sa.DateTime(), nullable=True))
    op.execute(BACKFILL_EXPENSE_LINK)


def downgrade() -> None:
    op.drop_column("worker_payouts", "cancelled_at")
    op.drop_column("worker_payouts", "origin")
