"""Installed decks and language pair in user_stats for the admin users page (card #1002)."""
from alembic import op
import sqlalchemy as sa

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_stats', sa.Column('decks', sa.Text(), nullable=False, server_default='[]'))
    op.add_column('user_stats', sa.Column('languages', sa.Text(), nullable=False, server_default='{}'))


def downgrade():
    op.drop_column('user_stats', 'languages')
    op.drop_column('user_stats', 'decks')
