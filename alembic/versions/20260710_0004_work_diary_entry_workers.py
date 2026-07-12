"""work diary entry workers

Revision ID: 20260710_0004
Revises: 20260710_0003
Create Date: 2026-07-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260710_0004"
down_revision: Union[str, Sequence[str], None] = "20260710_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_diary_entry_workers",
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["work_diary_entries.id"]),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"]),
        sa.PrimaryKeyConstraint("entry_id", "worker_id"),
    )
    op.create_index(
        op.f("ix_work_diary_entry_workers_worker_id"),
        "work_diary_entry_workers",
        ["worker_id"],
        unique=False,
    )
    op.execute(
        sa.text(
            """
            INSERT INTO work_diary_entry_workers (entry_id, worker_id)
            SELECT id, worker_id
            FROM work_diary_entries
            WHERE worker_id IS NOT NULL
            """
        )
    )
    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.drop_index(op.f("ix_work_diary_entries_worker_id"))
        batch_op.drop_column("worker_id")


def downgrade() -> None:
    with op.batch_alter_table("work_diary_entries") as batch_op:
        batch_op.add_column(sa.Column("worker_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_work_diary_entries_worker_id_workers",
            "workers",
            ["worker_id"],
            ["id"],
        )
        batch_op.create_index(op.f("ix_work_diary_entries_worker_id"), ["worker_id"], unique=False)
    op.execute(
        sa.text(
            """
            UPDATE work_diary_entries
            SET worker_id = (
                SELECT MIN(worker_id)
                FROM work_diary_entry_workers
                WHERE entry_id = work_diary_entries.id
            )
            """
        )
    )
    op.drop_index(op.f("ix_work_diary_entry_workers_worker_id"), table_name="work_diary_entry_workers")
    op.drop_table("work_diary_entry_workers")
