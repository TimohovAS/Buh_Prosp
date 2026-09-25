"""Pay a worker per day in work diaries and reconcile payouts with diary accruals.

Revision ID: 20260925_0030
Revises: 20260924_0029
Create Date: 2026-09-25 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260925_0030"
down_revision: Union[str, Sequence[str], None] = "20260924_0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_diary_worker_days",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("pay_mode", sa.String(length=20), nullable=False, server_default="hourly"),
        sa.Column("day_rate", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("day_rate_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trip_pricing_mode", sa.String(length=30), nullable=True),
        sa.Column("per_diem_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("food_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("lodging_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("worker_id", "date", name="uq_work_diary_worker_day"),
    )
    op.create_index("ix_work_diary_worker_days_id", "work_diary_worker_days", ["id"])
    op.create_index("ix_work_diary_worker_days_worker_id", "work_diary_worker_days", ["worker_id"])
    op.create_index("ix_work_diary_worker_days_date", "work_diary_worker_days", ["date"])

    # Существующие записи остаются почасовыми: строк начислений за день для них нет,
    # а новые поля выезда выключены — себестоимость и фактуры не меняются.
    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.add_column(sa.Column("is_trip", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("travel_hours", sa.Numeric(6, 2), nullable=True))
        batch_op.add_column(sa.Column("travel_km", sa.Numeric(8, 1), nullable=True))

    with op.batch_alter_table("work_diary_entry_workers") as batch_op:
        batch_op.add_column(sa.Column("hourly_rate_snapshot", sa.Numeric(14, 2), nullable=True))
    # Историческая ставка каждого работника не сохранялась, только сумма по бригаде.
    # Берём текущую карточку: у почасовой записи итог считается от ставки бригады,
    # а эта доля нужна лишь для раскладки труда по работникам.
    op.execute(
        sa.text(
            """
            UPDATE work_diary_entry_workers
            SET hourly_rate_snapshot = ROUND(
                COALESCE(
                    (SELECT workers.regular_day_rate FROM workers WHERE workers.id = work_diary_entry_workers.worker_id),
                    0
                ) / 8.0,
                2
            )
            """
        )
    )

    # Ни одна прежняя выплата не считается сопоставленной с дневником: связь ставит
    # только человек, по совпадению суммы или даты она не угадывается.
    with op.batch_alter_table("worker_payouts") as batch_op:
        batch_op.add_column(sa.Column("diary_reconciled", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("worker_payouts") as batch_op:
        batch_op.drop_column("diary_reconciled")
    with op.batch_alter_table("work_diary_entry_workers") as batch_op:
        batch_op.drop_column("hourly_rate_snapshot")
    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.drop_column("travel_km")
        batch_op.drop_column("travel_hours")
        batch_op.drop_column("is_trip")
    op.drop_index("ix_work_diary_worker_days_date", table_name="work_diary_worker_days")
    op.drop_index("ix_work_diary_worker_days_worker_id", table_name="work_diary_worker_days")
    op.drop_index("ix_work_diary_worker_days_id", table_name="work_diary_worker_days")
    op.drop_table("work_diary_worker_days")
