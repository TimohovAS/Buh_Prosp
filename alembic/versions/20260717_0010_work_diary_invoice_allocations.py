"""Link work diary entries to outgoing invoices.

Revision ID: 20260717_0010
Revises: 20260717_0009
Create Date: 2026-07-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_0010"
down_revision: Union[str, Sequence[str], None] = "20260717_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_diary_invoice_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("work_diary_entry_id", sa.Integer(), nullable=False),
        sa.Column("income_id", sa.Integer(), nullable=False),
        sa.Column("income_item_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("source_amount_snapshot", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["work_diary_entry_id"], ["work_diary_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["income_id"], ["income.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["income_item_id"], ["income_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "work_diary_entry_id",
            "income_id",
            name="uq_work_diary_invoice_allocation_entry_income",
        ),
    )
    op.create_index(
        "ix_work_diary_invoice_allocations_work_diary_entry_id",
        "work_diary_invoice_allocations",
        ["work_diary_entry_id"],
    )
    op.create_index(
        "ix_work_diary_invoice_allocations_income_id",
        "work_diary_invoice_allocations",
        ["income_id"],
    )
    op.create_index(
        "ix_work_diary_invoice_allocations_income_item_id",
        "work_diary_invoice_allocations",
        ["income_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_work_diary_invoice_allocations_income_item_id",
        table_name="work_diary_invoice_allocations",
    )
    op.drop_index("ix_work_diary_invoice_allocations_income_id", table_name="work_diary_invoice_allocations")
    op.drop_index(
        "ix_work_diary_invoice_allocations_work_diary_entry_id",
        table_name="work_diary_invoice_allocations",
    )
    op.drop_table("work_diary_invoice_allocations")
