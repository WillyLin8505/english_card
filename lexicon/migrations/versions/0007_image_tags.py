"""AI labels on every sense picture

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-30 10:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('image_assets', sa.Column('tags', postgresql.JSONB(), nullable=True))
    op.add_column('image_assets', sa.Column('tag_status', sa.String(length=16), nullable=False,
                                            server_default='pending'))
    op.add_column('image_assets', sa.Column('tag_model', sa.String(length=64), nullable=True))
    op.add_column('image_assets', sa.Column('tagged_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for c in ('tagged_at', 'tag_model', 'tag_status', 'tags'):
        op.drop_column('image_assets', c)
