"""Store statement income and expense totals for bank import files.

Revision ID: 20260902_0016
Revises: 20260807_0015
Create Date: 2026-09-02 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260902_0016"
down_revision: Union[str, Sequence[str], None] = "20260807_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bank_import_files") as batch_op:
        batch_op.add_column(sa.Column("income_amount", sa.Numeric(14, 2), nullable=True))
        batch_op.add_column(sa.Column("expense_amount", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bank_import_files") as batch_op:
        batch_op.drop_column("expense_amount")
        batch_op.drop_column("income_amount")
