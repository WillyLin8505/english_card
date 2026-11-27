"""ladder_groups: explicit sense identity (ssid) so import never merges by member overlap (card #1468)."""
from alembic import op
import sqlalchemy as sa

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('ladder_groups', sa.Column('ssid', sa.String(64), nullable=False, server_default=''))
    op.create_index('uq_ladder_group_ssid', 'ladder_groups', ['language', 'pos', 'ssid'], unique=True,
                    postgresql_where=sa.text("ssid <> ''"))


def downgrade():
    op.drop_index('uq_ladder_group_ssid', table_name='ladder_groups')
    op.drop_column('ladder_groups', 'ssid')
