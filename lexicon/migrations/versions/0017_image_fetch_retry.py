"""Back off and requeue image_fetch_tasks on a persistent 429/503 instead of
counting them completed (#99, root cause from #98)."""
from alembic import op
import sqlalchemy as sa

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('image_fetch_tasks', sa.Column('retry_at', sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column('image_fetch_tasks', 'retry_at')
