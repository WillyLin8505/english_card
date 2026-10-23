"""App report screenshot on 問題回報 (issue #667, card #592)."""
from alembic import op
import sqlalchemy as sa

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('issue_reports', sa.Column('screenshot', sa.Text()))


def downgrade():
    op.drop_column('issue_reports', 'screenshot')
