"""Decks (卡片集／圖片集) and their items (card #323)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'decks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('slug', sa.String(64), nullable=False, unique=True),
        sa.Column('kind', sa.String(8), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('cefr', sa.String(8)),
        sa.Column('topic', sa.Text()),
        sa.Column('description', sa.Text()),
        sa.Column('author', sa.Text()),
        sa.Column('cover_asset_id', sa.Integer(), sa.ForeignKey('image_assets.id', ondelete='SET NULL')),
        sa.Column('target_language', sa.String(16), nullable=False, server_default='en'),
        sa.Column('published', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        'deck_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('deck_id', sa.Integer(), sa.ForeignKey('decks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('lemma', sa.Text()),
        sa.Column('pos', sa.String(32)),
        sa.Column('cefr', sa.String(8)),
        sa.Column('asset_id', sa.Integer(), sa.ForeignKey('image_assets.id', ondelete='CASCADE')),
        sa.Column('labels', sa.JSON().with_variant(JSONB(), 'postgresql')),
    )
    op.create_index('ix_deck_items_deck_id', 'deck_items', ['deck_id'])


def downgrade():
    op.drop_index('ix_deck_items_deck_id', table_name='deck_items')
    op.drop_table('deck_items')
    op.drop_table('decks')
