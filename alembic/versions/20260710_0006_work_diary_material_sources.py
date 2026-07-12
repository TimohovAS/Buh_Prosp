"""Work diary: material sources, numeric quantities, weather codes, overtime setting.

Revision ID: 20260710_0006
Revises: 20260710_0005
Create Date: 2026-07-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260710_0006"
down_revision: Union[str, Sequence[str], None] = "20260710_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WEATHER_CODES = {
    "Сунчано": "sunny",
    "Облачно": "cloudy",
    "Киша": "rain",
    "Снег": "snow",
    "Ветар": "wind",
    "Магла": "fog",
}


def upgrade() -> None:
    op.add_column(
        "enterprise",
        sa.Column("work_diary_overtime_multiplier", sa.Numeric(6, 4), nullable=True, server_default="1.26"),
    )
    op.execute(
        sa.text(
            "UPDATE enterprise SET work_diary_overtime_multiplier = 1.26 WHERE work_diary_overtime_multiplier IS NULL"
        )
    )

    # Коэффициент 1.14 был перенесен из старой программы по ошибке; законный минимум РС — 1.26.
    op.execute(sa.text("UPDATE work_diary_entries SET overtime_multiplier = 1.26 WHERE overtime_multiplier = 1.14"))
    for label, code in WEATHER_CODES.items():
        op.execute(
            sa.text("UPDATE work_diary_entries SET weather = :code WHERE weather = :label").bindparams(
                code=code, label=label
            )
        )
    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.alter_column("weather", type_=sa.String(length=20), existing_type=sa.String(length=100))

    # Количество: свободный текст -> число. Запятая -> точка, пустое -> NULL,
    # остальное конвертируется CAST-ом при пересборке таблицы (ведущее число или 0).
    op.execute(
        sa.text(
            "UPDATE work_diary_materials SET quantity = REPLACE(TRIM(quantity), ',', '.') WHERE quantity IS NOT NULL"
        )
    )
    op.execute(sa.text("UPDATE work_diary_materials SET quantity = NULL WHERE TRIM(COALESCE(quantity, '')) = ''"))
    with op.batch_alter_table("work_diary_materials") as batch_op:
        batch_op.alter_column("quantity", type_=sa.Numeric(12, 3), existing_type=sa.String(length=100))
        batch_op.add_column(sa.Column("unit", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("source", sa.String(length=20), nullable=False, server_default="stock"))
        batch_op.add_column(sa.Column("expense_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_work_diary_materials_expense_id_expenses",
            "expenses",
            ["expense_id"],
            ["id"],
        )
        batch_op.create_index(op.f("ix_work_diary_materials_expense_id"), ["expense_id"], unique=False)
    op.execute(sa.text("UPDATE work_diary_materials SET quantity = NULL WHERE quantity = 0"))


def downgrade() -> None:
    with op.batch_alter_table("work_diary_materials") as batch_op:
        batch_op.drop_index(op.f("ix_work_diary_materials_expense_id"))
        batch_op.drop_constraint("fk_work_diary_materials_expense_id_expenses", type_="foreignkey")
        batch_op.drop_column("expense_id")
        batch_op.drop_column("source")
        batch_op.drop_column("unit")
        batch_op.alter_column("quantity", type_=sa.String(length=100), existing_type=sa.Numeric(12, 3))

    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.alter_column("weather", type_=sa.String(length=100), existing_type=sa.String(length=20))
    for label, code in WEATHER_CODES.items():
        op.execute(
            sa.text("UPDATE work_diary_entries SET weather = :label WHERE weather = :code").bindparams(
                code=code, label=label
            )
        )

    with op.batch_alter_table("enterprise") as batch_op:
        batch_op.drop_column("work_diary_overtime_multiplier")
