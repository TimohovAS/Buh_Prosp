"""Add a manual billable amount override to work diary entries.

Revision ID: 20260717_0009
Revises: 20260713_0008
Create Date: 2026-07-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_0009"
down_revision: Union[str, Sequence[str], None] = "20260713_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.add_column(sa.Column("billable_amount_override", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.drop_column("billable_amount_override")
