"""排程: which AI is doing which request, and what the owner asked for

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-15 08:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agent_tasks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('detail', sa.Text()),
        sa.Column('status', sa.String(16), nullable=False, server_default='queued'),
        sa.Column('agent', sa.String(64)),
        sa.Column('requested_by', sa.String(64), nullable=False, server_default='owner'),
        sa.Column('progress', sa.Text()),
        sa.Column('issue_ids', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('history', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
    )
    op.create_index('ix_agent_tasks_status', 'agent_tasks', ['status', 'agent'])


def downgrade() -> None:
    op.drop_index('ix_agent_tasks_status', 'agent_tasks')
    op.drop_table('agent_tasks')
