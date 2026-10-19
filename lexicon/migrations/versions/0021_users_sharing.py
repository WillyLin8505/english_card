"""Accounts, shared decks, blocks and reports (card #324)."""
from alembic import op
import sqlalchemy as sa

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('provider', sa.String(8), nullable=False),
        sa.Column('provider_sub', sa.String(255), nullable=False, unique=True),
        sa.Column('email', sa.String(255)),
        sa.Column('password_hash', sa.Text()),
        sa.Column('nickname', sa.String(40), nullable=False),
        sa.Column('native_lang', sa.String(16)),
        sa.Column('level', sa.String(8)),
        sa.Column('blocked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        'user_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_user_tokens_user_id', 'user_tokens', ['user_id'])
    op.create_table(
        'user_blocks',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('blocked_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'deck_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('deck_id', sa.Integer(), sa.ForeignKey('decks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reporter_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_deck_reports_deck_id', 'deck_reports', ['deck_id'])
    op.add_column('decks', sa.Column('owner_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL')))
    op.add_column('decks', sa.Column('share_status', sa.String(12), nullable=False, server_default='private'))
    op.add_column('decks', sa.Column('downloads', sa.Integer(), nullable=False, server_default='0'))
    op.create_index('ix_decks_owner_user_id', 'decks', ['owner_user_id'])


def downgrade():
    op.drop_index('ix_decks_owner_user_id', table_name='decks')
    op.drop_column('decks', 'downloads')
    op.drop_column('decks', 'share_status')
    op.drop_column('decks', 'owner_user_id')
    op.drop_table('deck_reports')
    op.drop_table('user_blocks')
    op.drop_table('user_tokens')
    op.drop_table('users')
