"""Anonymous app events for retention numbers (card #914)."""
from alembic import op
import sqlalchemy as sa

revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'app_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('install_id', sa.String(40), nullable=False),
        sa.Column('event', sa.String(24), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('install_id', 'event', 'day', name='uq_app_event'),
    )
    op.create_index('ix_app_events_event_day', 'app_events', ['event', 'day'])


def downgrade():
    op.drop_index('ix_app_events_event_day', table_name='app_events')
    op.drop_table('app_events')
