"""Add a material billing multiplier to work diary entries.

Revision ID: 20260724_0011
Revises: 20260717_0010
Create Date: 2026-07-24 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260724_0011"
down_revision: Union[str, Sequence[str], None] = "20260717_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.add_column(
            sa.Column(
                "material_billing_multiplier",
                sa.Numeric(8, 4),
                nullable=False,
                server_default="1.2",
            )
        )

    # Keep already invoiced entries at their original effective amount.
    op.execute(
        sa.text(
            """
            UPDATE work_diary_entries
            SET material_billing_multiplier = 1.0
            WHERE EXISTS (
                SELECT 1
                FROM work_diary_invoice_allocations AS allocation
                JOIN income ON income.id = allocation.income_id
                WHERE allocation.work_diary_entry_id = work_diary_entries.id
                  AND income.status != 'cancelled'
            )
            """
        )
    )
    op.create_index(
        "ix_work_diary_invoice_allocations_id",
        "work_diary_invoice_allocations",
        ["id"],
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_work_diary_invoice_allocations_id"))
    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.drop_column("material_billing_multiplier")
