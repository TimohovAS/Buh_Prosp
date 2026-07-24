"""Persist work diary material source items and enterprise billing defaults.

Revision ID: 20260724_0012
Revises: 20260724_0011
Create Date: 2026-07-24 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260724_0012"
down_revision: Union[str, Sequence[str], None] = "20260724_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("enterprise") as batch_op:
        batch_op.add_column(
            sa.Column(
                "work_diary_material_billing_multiplier",
                sa.Numeric(8, 4),
                nullable=False,
                server_default="1.2",
            )
        )

    with op.batch_alter_table("work_diary_materials") as batch_op:
        batch_op.add_column(sa.Column("source_item_type", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("source_item_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("unit_price_snapshot", sa.Numeric(14, 2), nullable=True))

    # Existing rows already contain a total and quantity, so preserve their effective unit price.
    op.execute(
        sa.text(
            """
            UPDATE work_diary_materials
            SET unit_price_snapshot = amount / quantity
            WHERE quantity IS NOT NULL
              AND quantity > 0
            """
        )
    )

    # A single invoice item is unambiguous even when the saved description was extended by import metadata.
    op.execute(
        sa.text(
            """
            UPDATE work_diary_materials
            SET source_item_type = 'expense_item',
                source_item_id = (
                    SELECT expense_items.id
                    FROM expense_items
                    WHERE expense_items.expense_id = work_diary_materials.expense_id
                    LIMIT 1
                ),
                unit_price_snapshot = COALESCE(
                    (
                        SELECT expense_items.unit_price
                        FROM expense_items
                        WHERE expense_items.expense_id = work_diary_materials.expense_id
                        LIMIT 1
                    ),
                    unit_price_snapshot
                )
            WHERE source = 'expense'
              AND source_item_id IS NULL
              AND (
                  SELECT COUNT(*)
                  FROM expense_items
                  WHERE expense_items.expense_id = work_diary_materials.expense_id
              ) = 1
            """
        )
    )

    # Recover exact invoice item links where the saved snapshot still matches the source row.
    op.execute(
        sa.text(
            """
            UPDATE work_diary_materials
            SET source_item_type = 'expense_item',
                source_item_id = (
                    SELECT expense_items.id
                    FROM expense_items
                    WHERE expense_items.expense_id = work_diary_materials.expense_id
                      AND expense_items.name = work_diary_materials.description
                    ORDER BY expense_items.line_no, expense_items.id
                    LIMIT 1
                ),
                unit_price_snapshot = COALESCE(
                    (
                        SELECT expense_items.unit_price
                        FROM expense_items
                        WHERE expense_items.expense_id = work_diary_materials.expense_id
                          AND expense_items.name = work_diary_materials.description
                        ORDER BY expense_items.line_no, expense_items.id
                        LIMIT 1
                    ),
                    unit_price_snapshot
                )
            WHERE source = 'expense'
              AND EXISTS (
                  SELECT 1
                  FROM expense_items
                  WHERE expense_items.expense_id = work_diary_materials.expense_id
                    AND expense_items.name = work_diary_materials.description
              )
            """
        )
    )

    # The same deterministic fallback applies to expenses backed by one fiscal-receipt item.
    op.execute(
        sa.text(
            """
            UPDATE work_diary_materials
            SET source_item_type = 'receipt_item',
                source_item_id = (
                    SELECT purchase_receipt_items.id
                    FROM purchase_receipt_items
                    JOIN purchase_receipts
                      ON purchase_receipts.id = purchase_receipt_items.receipt_id
                    WHERE purchase_receipts.expense_id = work_diary_materials.expense_id
                    LIMIT 1
                ),
                unit_price_snapshot = COALESCE(
                    (
                        SELECT purchase_receipt_items.unit_price
                        FROM purchase_receipt_items
                        JOIN purchase_receipts
                          ON purchase_receipts.id = purchase_receipt_items.receipt_id
                        WHERE purchase_receipts.expense_id = work_diary_materials.expense_id
                        LIMIT 1
                    ),
                    unit_price_snapshot
                )
            WHERE source = 'expense'
              AND source_item_id IS NULL
              AND (
                  SELECT COUNT(*)
                  FROM purchase_receipt_items
                  JOIN purchase_receipts
                    ON purchase_receipts.id = purchase_receipt_items.receipt_id
                  WHERE purchase_receipts.expense_id = work_diary_materials.expense_id
              ) = 1
            """
        )
    )

    # Expenses created from fiscal receipts keep their item rows in a separate table.
    op.execute(
        sa.text(
            """
            UPDATE work_diary_materials
            SET source_item_type = 'receipt_item',
                source_item_id = (
                    SELECT purchase_receipt_items.id
                    FROM purchase_receipt_items
                    JOIN purchase_receipts
                      ON purchase_receipts.id = purchase_receipt_items.receipt_id
                    WHERE purchase_receipts.expense_id = work_diary_materials.expense_id
                      AND purchase_receipt_items.name = work_diary_materials.description
                    ORDER BY purchase_receipt_items.line_no, purchase_receipt_items.id
                    LIMIT 1
                ),
                unit_price_snapshot = COALESCE(
                    (
                        SELECT purchase_receipt_items.unit_price
                        FROM purchase_receipt_items
                        JOIN purchase_receipts
                          ON purchase_receipts.id = purchase_receipt_items.receipt_id
                        WHERE purchase_receipts.expense_id = work_diary_materials.expense_id
                          AND purchase_receipt_items.name = work_diary_materials.description
                        ORDER BY purchase_receipt_items.line_no, purchase_receipt_items.id
                        LIMIT 1
                    ),
                    unit_price_snapshot
                )
            WHERE source = 'expense'
              AND source_item_id IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM purchase_receipt_items
                  JOIN purchase_receipts
                    ON purchase_receipts.id = purchase_receipt_items.receipt_id
                  WHERE purchase_receipts.expense_id = work_diary_materials.expense_id
                    AND purchase_receipt_items.name = work_diary_materials.description
              )
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("work_diary_materials") as batch_op:
        batch_op.drop_column("unit_price_snapshot")
        batch_op.drop_column("source_item_id")
        batch_op.drop_column("source_item_type")
    with op.batch_alter_table("enterprise") as batch_op:
        batch_op.drop_column("work_diary_material_billing_multiplier")
