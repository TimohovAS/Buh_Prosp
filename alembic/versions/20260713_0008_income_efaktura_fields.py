"""Add optional eFaktura references to income invoices.

Revision ID: 20260713_0008
Revises: 20260712_0007
Create Date: 2026-07-13 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260713_0008"
down_revision: Union[str, Sequence[str], None] = "20260712_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("income") as batch_op:
        batch_op.add_column(sa.Column("efaktura_contract_number", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("efaktura_order_reference", sa.String(length=200), nullable=True))
        batch_op.add_column(
            sa.Column("efaktura_framework_agreement_number", sa.String(length=200), nullable=True)
        )
        batch_op.add_column(sa.Column("efaktura_object_code", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("efaktura_buyer_reference", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("efaktura_payment_reference", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("efaktura_payment_model", sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("income") as batch_op:
        batch_op.drop_column("efaktura_payment_model")
        batch_op.drop_column("efaktura_payment_reference")
        batch_op.drop_column("efaktura_buyer_reference")
        batch_op.drop_column("efaktura_object_code")
        batch_op.drop_column("efaktura_framework_agreement_number")
        batch_op.drop_column("efaktura_order_reference")
        batch_op.drop_column("efaktura_contract_number")
