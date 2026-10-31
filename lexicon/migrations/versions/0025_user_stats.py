"""Per-user usage numbers for the admin users page (card #911)."""
from alembic import op
import sqlalchemy as sa

revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_stats',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('albums', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('reviews_total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reviews_7d', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('photos_taken', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('photos_opened', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('app_version', sa.String(32)),
        sa.Column('last_seen', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('user_stats')
