"""Defer word image downloads to a parallel worker queue.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-01 22:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_fetch_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_language", sa.String(length=16), nullable=False),
        sa.Column("native_language", sa.String(length=16), nullable=False),
        sa.Column("lemma", sa.String(length=128), nullable=False),
        sa.Column("fields", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("target_language", "native_language", "lemma",
                            name="uq_image_fetch_task_word"),
    )
    op.create_index("ix_image_fetch_tasks_status", "image_fetch_tasks",
                    ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_image_fetch_tasks_status", table_name="image_fetch_tasks")
    op.drop_table("image_fetch_tasks")
