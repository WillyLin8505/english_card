"""Pipeline stage on cards and 問題回報 (card #916, lexicon/docs/PIPELINE.md).

NULL = older than the pipeline: old rows are never rewritten."""
from alembic import op
import sqlalchemy as sa

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None

TABLES = ('agent_tasks', 'issue_reports')


def upgrade():
    for t in TABLES:
        op.add_column(t, sa.Column('stage', sa.String(24)))
        op.add_column(t, sa.Column('stage_state', sa.String(12)))   # failed · note · NULL = moving normally
        op.add_column(t, sa.Column('stage_note', sa.Text()))
        op.add_column(t, sa.Column('stage_at', sa.DateTime(timezone=True)))


def downgrade():
    for t in TABLES:
        for c in ('stage_at', 'stage_note', 'stage_state', 'stage'):
            op.drop_column(t, c)
