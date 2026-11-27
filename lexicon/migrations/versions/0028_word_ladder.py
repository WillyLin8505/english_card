"""Word ladder: meaning groups (A1-C2 same-meaning words), shared by their members (card #1451)."""
from alembic import op
import sqlalchemy as sa

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ladder_groups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('language', sa.String(16), nullable=False, server_default='en'),
        sa.Column('pos', sa.String(16), nullable=False, server_default=''),
        sa.Column('zh', sa.String(128), nullable=False, server_default=''),
        sa.Column('gloss_en', sa.Text(), nullable=False, server_default=''),
        sa.Column('head_word', sa.String(128), nullable=False, server_default=''),
        sa.Column('batch', sa.String(64), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        'ladder_members',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('ladder_groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('word', sa.String(128), nullable=False),
        sa.Column('pos', sa.String(16), nullable=False, server_default=''),
        sa.Column('cefr', sa.String(4)),
        sa.Column('zh', sa.String(128), nullable=False, server_default=''),
        sa.Column('zh_ai', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('added_by', sa.String(16), nullable=False, server_default='qwen'),
        sa.Column('ordinal', sa.Integer(), nullable=False, server_default='0'),
        sa.UniqueConstraint('group_id', 'word', 'pos', name='uq_ladder_member'),
    )
    op.create_index('ix_ladder_members_word', 'ladder_members', ['word'])


def downgrade():
    op.drop_index('ix_ladder_members_word', 'ladder_members')
    op.drop_table('ladder_members')
    op.drop_table('ladder_groups')
