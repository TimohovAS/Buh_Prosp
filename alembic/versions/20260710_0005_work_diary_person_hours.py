"""Clarify work diary duration and team rate columns.

Revision ID: 20260710_0005
Revises: 20260710_0004
Create Date: 2026-07-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260710_0005"
down_revision: Union[str, Sequence[str], None] = "20260710_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.alter_column("hours", new_column_name="duration_hours")
        batch_op.alter_column("regular_hours", new_column_name="regular_duration_hours")
        batch_op.alter_column("overtime_hours", new_column_name="overtime_duration_hours")
        batch_op.alter_column("hourly_rate_snapshot", new_column_name="team_hourly_rate_snapshot")


def downgrade() -> None:
    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.alter_column("duration_hours", new_column_name="hours")
        batch_op.alter_column("regular_duration_hours", new_column_name="regular_hours")
        batch_op.alter_column("overtime_duration_hours", new_column_name="overtime_hours")
        batch_op.alter_column("team_hourly_rate_snapshot", new_column_name="hourly_rate_snapshot")
