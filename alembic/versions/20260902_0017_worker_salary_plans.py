"""Create hidden salary plans from worker pay settings.

Revision ID: 20260902_0017
Revises: 20260902_0016
Create Date: 2026-09-02 12:00:00.000000

"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260902_0017"
down_revision: Union[str, Sequence[str], None] = "20260902_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTO_WORKER_SALARY_NOTE = "auto:worker_salary_plan"


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    workers = sa.Table("workers", metadata, autoload_with=bind)
    planned_expenses = sa.Table("planned_expenses", metadata, autoload_with=bind)
    current_date = date.today()

    rows = (
        bind.execute(
            sa.select(
                workers.c.id,
                workers.c.name,
                workers.c.pay_scheme,
                workers.c.weekly_rate,
                workers.c.monthly_rate,
                workers.c.default_project_id,
                workers.c.default_category_id,
            ).where(workers.c.is_active.is_(True))
        )
        .mappings()
        .all()
    )

    for worker in rows:
        if worker["pay_scheme"] == "monthly":
            amount = Decimal(str(worker["monthly_rate"] or 0))
            period = "monthly"
            start_date = date(current_date.year, current_date.month, 1)
            payment_day = 5
            payment_day_of_week = None
        elif worker["pay_scheme"] == "weekly":
            amount = Decimal(str(worker["weekly_rate"] or 0))
            period = "weekly"
            start_date = current_date - timedelta(days=current_date.weekday())
            payment_day = None
            payment_day_of_week = 0
        else:
            continue
        if amount <= 0:
            continue

        existing_id = bind.scalar(
            sa.select(planned_expenses.c.id)
            .where(planned_expenses.c.worker_id == worker["id"])
            .order_by(planned_expenses.c.id.asc())
            .limit(1)
        )
        if existing_id is not None:
            bind.execute(
                planned_expenses.update()
                .where(planned_expenses.c.id == existing_id)
                .values(amount=amount, is_active=True)
            )
            continue

        bind.execute(
            planned_expenses.insert().values(
                name=f"Зарплата — {worker['name']}",
                amount=amount,
                currency="RSD",
                category_id=worker["default_category_id"],
                project_id=worker["default_project_id"],
                worker_id=worker["id"],
                period=period,
                payment_day=payment_day,
                payment_day_of_week=payment_day_of_week,
                start_date=start_date,
                end_date=None,
                reminder_days=3,
                is_active=True,
                note=AUTO_WORKER_SALARY_NOTE,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    planned_expenses = sa.Table("planned_expenses", metadata, autoload_with=bind)
    bind.execute(planned_expenses.delete().where(planned_expenses.c.note == AUTO_WORKER_SALARY_NOTE))
