"""Card difficulty on the 排程 board (card #156): 1 簡單 · 2 中等 · 3 困難 · 4 極難,
on tasks and on 問題回報 (an open issue is a card too), with a one-line reason."""
from alembic import op
import sqlalchemy as sa

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('agent_tasks', 'issue_reports'):
        op.add_column(table, sa.Column('difficulty', sa.SmallInteger()))
        op.add_column(table, sa.Column('difficulty_reason', sa.Text()))


def downgrade():
    for table in ('agent_tasks', 'issue_reports'):
        op.drop_column(table, 'difficulty_reason')
        op.drop_column(table, 'difficulty')
