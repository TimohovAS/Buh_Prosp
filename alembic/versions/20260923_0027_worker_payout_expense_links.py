"""Remember where a linked expense was filed before it moved to salary.

Revision ID: 20260923_0027
Revises: 20260923_0026
Create Date: 2026-09-23 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260923_0027"
down_revision: Union[str, Sequence[str], None] = "20260923_0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Привязка к работнику переносит расход в зарплатные категорию и проект;
    # прежние значения храним, чтобы отвязка вернула расход на место. У уже
    # привязанных выплат их нет — такие расходы при отвязке остаются как есть.
    op.add_column("worker_payouts", sa.Column("expense_links_before", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("worker_payouts", "expense_links_before")
