"""Labels pass at a recognition score of 80% or more; all pictures re-tagged

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-01 09:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Labels the model checked and was under 80% sure of: kept for the image
    # library, used nowhere else.
    op.add_column('image_assets', sa.Column('dropped_tags', postgresql.JSONB(), nullable=True))
    # Every downloaded picture is labelled again under the new rule.
    op.execute("UPDATE image_assets SET tag_status = 'pending' WHERE status = 'ready'")


def downgrade() -> None:
    op.drop_column('image_assets', 'dropped_tags')
