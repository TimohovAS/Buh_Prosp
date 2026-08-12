"""Add confirmed bank accounts for clients.

Revision ID: 20260807_0015
Revises: 20260728_0014
Create Date: 2026-08-07 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260807_0015"
down_revision: Union[str, Sequence[str], None] = "20260728_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_bank_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("account_number", sa.String(length=18), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_number", name="uq_client_bank_accounts_account_number"),
    )
    op.create_index(
        op.f("ix_client_bank_accounts_client_id"),
        "client_bank_accounts",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_bank_accounts_id"),
        "client_bank_accounts",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_client_bank_accounts_id"), table_name="client_bank_accounts")
    op.drop_index(op.f("ix_client_bank_accounts_client_id"), table_name="client_bank_accounts")
    op.drop_table("client_bank_accounts")
