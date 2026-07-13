"""Move work diary billing rates from projects to workers.

Revision ID: 20260712_0007
Revises: 20260710_0006
Create Date: 2026-07-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260712_0007"
down_revision: Union[str, Sequence[str], None] = "20260710_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workers") as batch_op:
        batch_op.add_column(sa.Column("billing_hourly_rate", sa.Numeric(14, 2), nullable=False, server_default="0"))

    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.add_column(
            sa.Column(
                "team_billing_hourly_rate_snapshot",
                sa.Numeric(14, 2),
                nullable=False,
                server_default="0",
            )
        )

    # Preserve the amount shown before this migration for existing diary entries.
    op.execute(
        sa.text(
            """
            UPDATE work_diary_entries
            SET team_billing_hourly_rate_snapshot = COALESCE(
                (
                    SELECT meta.billing_hourly_rate * COUNT(entry_workers.worker_id)
                    FROM work_diary_project_meta AS meta
                    LEFT JOIN work_diary_entry_workers AS entry_workers
                        ON entry_workers.entry_id = work_diary_entries.id
                    WHERE meta.project_id = work_diary_entries.project_id
                    GROUP BY meta.project_id
                ),
                0
            )
            """
        )
    )

    with op.batch_alter_table("work_diary_project_meta") as batch_op:
        batch_op.drop_column("billing_hourly_rate")


def downgrade() -> None:
    with op.batch_alter_table("work_diary_project_meta") as batch_op:
        batch_op.add_column(sa.Column("billing_hourly_rate", sa.Numeric(14, 2), nullable=True, server_default="0"))

    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.drop_column("team_billing_hourly_rate_snapshot")

    with op.batch_alter_table("workers") as batch_op:
        batch_op.drop_column("billing_hourly_rate")
