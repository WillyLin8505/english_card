"""Alternate search phrase for nouns whose pictures were all rejected (#238)."""
from alembic import op
import sqlalchemy as sa

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('image_fetch_tasks', sa.Column('search_query', sa.Text()))
    op.add_column('image_fetch_tasks', sa.Column(
        'rejected_retries', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('image_fetch_tasks', 'rejected_retries')
    op.drop_column('image_fetch_tasks', 'search_query')
