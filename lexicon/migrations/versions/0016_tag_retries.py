"""Persist tagging failures and bounded retry scheduling (#212)."""
from alembic import op
import sqlalchemy as sa

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade():
    # Tagging workers hold a transaction open for the length of each model
    # call (up to the /tag endpoint's 300-600s timeout), taking locks on
    # image_assets for that long. Never wait behind one of those: fail fast
    # so the caller can retry in a short loop instead of blocking other work.
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.add_column('image_assets', sa.Column('tag_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('image_assets', sa.Column('tag_error', sa.Text()))
    op.add_column('image_assets', sa.Column('tag_retry_at', sa.DateTime(timezone=True)))


def downgrade():
    for name in ('tag_retry_at', 'tag_error', 'tag_attempts'):
        op.drop_column('image_assets', name)
