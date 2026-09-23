"""Add reusable, effective-dated tax schemes.

Revision ID: 20260922_0024
Revises: 20260922_0023
Create Date: 2026-09-22 12:00:00.000000

"""

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260922_0024"
down_revision: Union[str, Sequence[str], None] = "20260922_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tax_schemes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_tax_schemes_id"), "tax_schemes", ["id"], unique=False)
    op.create_table(
        "tax_scheme_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tax_scheme_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tax_scheme_id"], ["tax_schemes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tax_scheme_id", "period_start", name="uq_tax_scheme_period_start"),
    )
    op.create_index(op.f("ix_tax_scheme_periods_id"), "tax_scheme_periods", ["id"], unique=False)
    op.create_index(op.f("ix_tax_scheme_periods_period_start"), "tax_scheme_periods", ["period_start"], unique=False)
    op.create_index(op.f("ix_tax_scheme_periods_tax_scheme_id"), "tax_scheme_periods", ["tax_scheme_id"], unique=False)

    with op.batch_alter_table("year_decisions") as batch_op:
        batch_op.add_column(sa.Column("tax_scheme_id", sa.Integer(), nullable=True))
        batch_op.create_index(op.f("ix_year_decisions_tax_scheme_id"), ["tax_scheme_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_year_decisions_tax_scheme_id_tax_schemes", "tax_schemes", ["tax_scheme_id"], ["id"]
        )

    with op.batch_alter_table("monthly_obligations") as batch_op:
        batch_op.add_column(sa.Column("tax_scheme_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("accrual_period_start", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("accrual_period_end", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.create_index(op.f("ix_monthly_obligations_tax_scheme_id"), ["tax_scheme_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_monthly_obligations_tax_scheme_id_tax_schemes",
            "tax_schemes",
            ["tax_scheme_id"],
            ["id"],
        )

    connection = op.get_bind()
    decision_count = connection.scalar(sa.text("SELECT COUNT(*) FROM year_decisions")) or 0
    if decision_count:
        now = datetime.utcnow()
        result = connection.execute(
            sa.text(
                "INSERT INTO tax_schemes "
                "(code, name, description, is_archived, created_at, updated_at) "
                "VALUES (:code, :name, :description, 0, :created_at, :updated_at)"
            ),
            {
                "code": "legacy",
                "name": "Текущая схема",
                "description": "Схема, автоматически созданная из существующих налоговых решений",
                "created_at": now,
                "updated_at": now,
            },
        )
        scheme_id = result.lastrowid
        connection.execute(
            sa.text("UPDATE year_decisions SET tax_scheme_id = :scheme_id WHERE tax_scheme_id IS NULL"),
            {"scheme_id": scheme_id},
        )
        connection.execute(
            sa.text(
                "UPDATE monthly_obligations SET tax_scheme_id = "
                "(SELECT tax_scheme_id FROM year_decisions WHERE year_decisions.id = monthly_obligations.decision_id) "
                "WHERE decision_id IS NOT NULL"
            )
        )
        first_period = connection.scalar(sa.text("SELECT MIN(period_start) FROM year_decisions"))
        connection.execute(
            sa.text(
                "INSERT INTO tax_scheme_periods "
                "(tax_scheme_id, period_start, period_end, note, created_at) "
                "VALUES (:scheme_id, :period_start, NULL, :note, :created_at)"
            ),
            {
                "scheme_id": scheme_id,
                "period_start": first_period,
                "note": "Перенесено из существующих настроек",
                "created_at": now,
            },
        )


def downgrade() -> None:
    with op.batch_alter_table("monthly_obligations") as batch_op:
        batch_op.drop_constraint("fk_monthly_obligations_tax_scheme_id_tax_schemes", type_="foreignkey")
        batch_op.drop_index(op.f("ix_monthly_obligations_tax_scheme_id"))
        batch_op.drop_column("is_active")
        batch_op.drop_column("accrual_period_end")
        batch_op.drop_column("accrual_period_start")
        batch_op.drop_column("tax_scheme_id")

    with op.batch_alter_table("year_decisions") as batch_op:
        batch_op.drop_constraint("fk_year_decisions_tax_scheme_id_tax_schemes", type_="foreignkey")
        batch_op.drop_index(op.f("ix_year_decisions_tax_scheme_id"))
        batch_op.drop_column("tax_scheme_id")

    op.drop_index(op.f("ix_tax_scheme_periods_tax_scheme_id"), table_name="tax_scheme_periods")
    op.drop_index(op.f("ix_tax_scheme_periods_period_start"), table_name="tax_scheme_periods")
    op.drop_index(op.f("ix_tax_scheme_periods_id"), table_name="tax_scheme_periods")
    op.drop_table("tax_scheme_periods")
    op.drop_index(op.f("ix_tax_schemes_id"), table_name="tax_schemes")
    op.drop_table("tax_schemes")
