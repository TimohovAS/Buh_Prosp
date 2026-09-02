"""Split client contact into person, phone, email and website.

Revision ID: 20260902_0018
Revises: 20260902_0017
Create Date: 2026-09-02 16:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260902_0018"
down_revision: Union[str, Sequence[str], None] = "20260902_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("clients") as batch_op:
        batch_op.add_column(sa.Column("phone", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("email", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("website", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("clients") as batch_op:
        batch_op.drop_column("website")
        batch_op.drop_column("email")
        batch_op.drop_column("phone")
