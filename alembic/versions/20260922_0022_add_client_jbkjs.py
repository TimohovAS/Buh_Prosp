"""Store the public-funds user number on client records.

Revision ID: 20260922_0022
Revises: 20260921_0021
Create Date: 2026-09-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260922_0022"
down_revision: Union[str, Sequence[str], None] = "20260921_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("jbkjs", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("clients") as batch_op:
        batch_op.drop_column("jbkjs")
