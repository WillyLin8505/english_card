"""問題回報: issues found while testing and requirements not built yet

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-30 23:30:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'issue_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(16), nullable=False, server_default='bug'),
        sa.Column('status', sa.String(16), nullable=False, server_default='open'),
        sa.Column('severity', sa.String(8), nullable=False, server_default='medium'),
        sa.Column('area', sa.String(16), nullable=False, server_default='app'),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('detail', sa.Text()),
        sa.Column('steps', sa.Text()),
        sa.Column('expected', sa.Text()),
        sa.Column('actual', sa.Text()),
        sa.Column('resolution', sa.Text()),
        sa.Column('options', postgresql.JSONB()),
        sa.Column('decision', sa.Text()),
        sa.Column('target_language', sa.String(16)),
        sa.Column('native_language', sa.String(16)),
        sa.Column('lemma', sa.Text()),
        sa.Column('code_ref', sa.Text()),
        sa.Column('spec_ref', sa.Text()),
        sa.Column('reporter', sa.String(32), nullable=False, server_default='manual'),
        sa.Column('history', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('resolved_at', sa.DateTime(timezone=True)),
    )
    op.create_index('ix_issue_reports_status', 'issue_reports', ['status', 'kind'])


def downgrade() -> None:
    op.drop_index('ix_issue_reports_status', 'issue_reports')
    op.drop_table('issue_reports')
