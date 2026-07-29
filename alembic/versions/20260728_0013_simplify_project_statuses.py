"""Simplify project statuses to active and completed.

Revision ID: 20260728_0013
Revises: 20260724_0012
Create Date: 2026-07-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260728_0013"
down_revision: Union[str, Sequence[str], None] = "20260724_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE projects
            SET status = CASE
                WHEN status IN ('completed', 'archived') THEN 'completed'
                ELSE 'active'
            END
            """
        )
    )


def downgrade() -> None:
    # The previous lead/archived distinction cannot be reconstructed reliably.
    pass
