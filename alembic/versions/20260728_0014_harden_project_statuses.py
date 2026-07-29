"""Constrain project statuses to active and completed.

Revision ID: 20260728_0014
Revises: 20260728_0013
Create Date: 2026-07-28 00:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260728_0014"
down_revision: Union[str, Sequence[str], None] = "20260728_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE projects
            SET status = CASE
                WHEN status = 'completed' THEN 'completed'
                ELSE 'active'
            END
            """
        )
    )
    with op.batch_alter_table("projects") as batch_op:
        batch_op.create_check_constraint(
            "ck_projects_status",
            "status IN ('active', 'completed')",
        )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint("ck_projects_status", type_="check")
