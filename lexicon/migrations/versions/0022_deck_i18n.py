"""Deck title/topic/description/author per native language (問題回報 #537, card #515)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('decks', sa.Column('i18n', sa.JSON().with_variant(JSONB(), 'postgresql')))


def downgrade():
    op.drop_column('decks', 'i18n')
