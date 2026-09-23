"""Track obligations by scheme segment and preserve closing deadlines.

Revision ID: 20260923_0025
Revises: 20260922_0024
Create Date: 2026-09-23 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260923_0025"
down_revision: Union[str, Sequence[str], None] = "20260922_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tax_scheme_periods") as batch_op:
        batch_op.add_column(sa.Column("closing_deadline", sa.Date(), nullable=True))

    with op.batch_alter_table("monthly_obligations") as batch_op:
        batch_op.add_column(sa.Column("tax_scheme_period_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            op.f("ix_monthly_obligations_tax_scheme_period_id"), ["tax_scheme_period_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_monthly_obligations_tax_scheme_period_id_tax_scheme_periods",
            "tax_scheme_periods",
            ["tax_scheme_period_id"],
            ["id"],
        )

    # Repair data produced by revision 0024 before segment-aware generation existed.
    # The two closing rows for 01.01-20.09 were present but inactive; restore them
    # with the exact balance and deadline from decisions K/2026-05 and K/2026-06.
    connection = op.get_bind()
    legacy_period_id = connection.scalar(
        sa.text(
            "SELECT p.id FROM tax_scheme_periods p "
            "JOIN tax_schemes s ON s.id = p.tax_scheme_id "
            "WHERE s.code = 'legacy' AND p.period_end = '2026-09-20' LIMIT 1"
        )
    )
    primary_period_id = connection.scalar(
        sa.text(
            "SELECT p.id FROM tax_scheme_periods p "
            "JOIN tax_schemes s ON s.id = p.tax_scheme_id "
            "WHERE s.code = 'primary_activity' AND p.period_start = '2026-09-21' LIMIT 1"
        )
    )
    if legacy_period_id is not None:
        connection.execute(
            sa.text("UPDATE tax_scheme_periods SET closing_deadline = '2026-10-07' WHERE id = :period_id"),
            {"period_id": legacy_period_id},
        )
        connection.execute(
            sa.text(
                "UPDATE monthly_obligations SET "
                "tax_scheme_period_id = :period_id, "
                "amount = CASE "
                "  WHEN payment_type_id = (SELECT id FROM payment_types WHERE code = 'tax') THEN 3414.77 "
                "  WHEN payment_type_id = (SELECT id FROM payment_types WHERE code = 'pio') THEN 8207.52 "
                "  ELSE amount END, "
                "accrual_period_start = '2026-09-01', accrual_period_end = '2026-09-20', "
                "deadline = '2026-10-07', is_active = 1 "
                "WHERE year = 2026 AND month = 9 "
                "AND tax_scheme_id = (SELECT tax_scheme_id FROM tax_scheme_periods WHERE id = :period_id) "
                "AND payment_type_id IN (SELECT id FROM payment_types WHERE code IN ('tax', 'pio')) "
                "AND status IN ('unpaid', 'overdue')"
            ),
            {"period_id": legacy_period_id},
        )
        connection.execute(
            sa.text(
                "UPDATE monthly_obligations SET tax_scheme_period_id = :period_id "
                "WHERE tax_scheme_period_id IS NULL AND tax_scheme_id = "
                "(SELECT tax_scheme_id FROM tax_scheme_periods WHERE id = :period_id) "
                "AND (year < 2026 OR (year = 2026 AND month <= 8))"
            ),
            {"period_id": legacy_period_id},
        )
    if primary_period_id is not None:
        connection.execute(
            sa.text(
                "UPDATE monthly_obligations SET tax_scheme_period_id = :period_id "
                "WHERE tax_scheme_period_id IS NULL AND tax_scheme_id = "
                "(SELECT tax_scheme_id FROM tax_scheme_periods WHERE id = :period_id) "
                "AND year = 2026 AND month >= 9"
            ),
            {"period_id": primary_period_id},
        )


def downgrade() -> None:
    with op.batch_alter_table("monthly_obligations") as batch_op:
        batch_op.drop_constraint("fk_monthly_obligations_tax_scheme_period_id_tax_scheme_periods", type_="foreignkey")
        batch_op.drop_index(op.f("ix_monthly_obligations_tax_scheme_period_id"))
        batch_op.drop_column("tax_scheme_period_id")

    with op.batch_alter_table("tax_scheme_periods") as batch_op:
        batch_op.drop_column("closing_deadline")
