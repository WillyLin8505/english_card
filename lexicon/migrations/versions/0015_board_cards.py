"""排程看板: recurring cards, card order, and the AIs (bots) that pull cards

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-15 09:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('agent_tasks', sa.Column('kind', sa.String(16), nullable=False, server_default='once'))
    op.add_column('agent_tasks', sa.Column('interval_minutes', sa.Integer()))
    op.add_column('agent_tasks', sa.Column('next_run_at', sa.DateTime(timezone=True)))
    op.add_column('agent_tasks', sa.Column('last_run_at', sa.DateTime(timezone=True)))
    op.add_column('agent_tasks', sa.Column('last_result', sa.Text()))
    op.add_column('agent_tasks', sa.Column('metric', sa.String(32)))
    op.add_column('agent_tasks', sa.Column('position', sa.Float(), nullable=False, server_default='0'))
    op.create_table(
        'agents',
        sa.Column('name', sa.String(64), primary_key=True),
        sa.Column('kind', sa.String(16), nullable=False, server_default='ai'),
        sa.Column('last_seen', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('note', sa.Text()),
    )


def downgrade() -> None:
    op.drop_table('agents')
    for c in ('position', 'metric', 'last_result', 'last_run_at', 'next_run_at', 'interval_minutes', 'kind'):
        op.drop_column('agent_tasks', c)
