"""work_diaries

Revision ID: 20260710_0003
Revises: 20260705_0002
Create Date: 2026-07-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260710_0003"
down_revision: Union[str, Sequence[str], None] = "20260705_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_diary_project_meta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("investor", sa.String(length=200), nullable=True),
        sa.Column("permit_number", sa.String(length=100), nullable=True),
        sa.Column("contractor", sa.String(length=200), nullable=True),
        sa.Column("place", sa.String(length=200), nullable=True),
        sa.Column("supervision", sa.String(length=200), nullable=True),
        sa.Column("object_name", sa.String(length=200), nullable=True),
        sa.Column("sector", sa.String(length=200), nullable=True),
        sa.Column("responsible_person", sa.String(length=200), nullable=True),
        sa.Column("billing_hourly_rate", sa.Numeric(14, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_work_diary_project_meta_project_id"),
    )
    op.create_index(op.f("ix_work_diary_project_meta_id"), "work_diary_project_meta", ["id"], unique=False)
    op.create_index(
        op.f("ix_work_diary_project_meta_project_id"),
        "work_diary_project_meta",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "work_diary_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("start_time", sa.String(length=5), nullable=True),
        sa.Column("end_time", sa.String(length=5), nullable=True),
        sa.Column("hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("regular_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("overtime_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("hourly_rate_snapshot", sa.Numeric(14, 2), nullable=False),
        sa.Column("overtime_multiplier", sa.Numeric(6, 4), nullable=False),
        sa.Column("per_diem", sa.Boolean(), nullable=True),
        sa.Column("per_diem_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("lodging_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("food_allowance", sa.Boolean(), nullable=True),
        sa.Column("food_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("weather", sa.String(length=100), nullable=True),
        sa.Column("temperature", sa.String(length=30), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_work_diary_entries_date"), "work_diary_entries", ["date"], unique=False)
    op.create_index(op.f("ix_work_diary_entries_id"), "work_diary_entries", ["id"], unique=False)
    op.create_index(op.f("ix_work_diary_entries_project_id"), "work_diary_entries", ["project_id"], unique=False)
    op.create_index(op.f("ix_work_diary_entries_worker_id"), "work_diary_entries", ["worker_id"], unique=False)

    op.create_table(
        "work_diary_materials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("quantity", sa.String(length=100), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["work_diary_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_work_diary_materials_entry_id"), "work_diary_materials", ["entry_id"], unique=False)
    op.create_index(op.f("ix_work_diary_materials_id"), "work_diary_materials", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_work_diary_materials_id"), table_name="work_diary_materials")
    op.drop_index(op.f("ix_work_diary_materials_entry_id"), table_name="work_diary_materials")
    op.drop_table("work_diary_materials")
    op.drop_index(op.f("ix_work_diary_entries_worker_id"), table_name="work_diary_entries")
    op.drop_index(op.f("ix_work_diary_entries_project_id"), table_name="work_diary_entries")
    op.drop_index(op.f("ix_work_diary_entries_id"), table_name="work_diary_entries")
    op.drop_index(op.f("ix_work_diary_entries_date"), table_name="work_diary_entries")
    op.drop_table("work_diary_entries")
    op.drop_index(op.f("ix_work_diary_project_meta_project_id"), table_name="work_diary_project_meta")
    op.drop_index(op.f("ix_work_diary_project_meta_id"), table_name="work_diary_project_meta")
    op.drop_table("work_diary_project_meta")
