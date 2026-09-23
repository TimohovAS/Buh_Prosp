"""Make obligation types and calculation rules configurable.

Revision ID: 20260923_0026
Revises: 20260923_0025
Create Date: 2026-09-23 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260923_0026"
down_revision: Union[str, Sequence[str], None] = "20260923_0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("payment_types") as batch_op:
        batch_op.alter_column("code", existing_type=sa.String(length=20), type_=sa.String(length=50))
        batch_op.add_column(sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table("year_decisions") as batch_op:
        batch_op.add_column(sa.Column("due_day", sa.Integer(), nullable=False, server_default="15"))
        batch_op.add_column(sa.Column("due_month_offset", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("prorate_partial_month", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("year_decisions") as batch_op:
        batch_op.drop_column("prorate_partial_month")
        batch_op.drop_column("due_month_offset")
        batch_op.drop_column("due_day")

    with op.batch_alter_table("payment_types") as batch_op:
        batch_op.drop_column("is_archived")
        batch_op.alter_column("code", existing_type=sa.String(length=50), type_=sa.String(length=20))
