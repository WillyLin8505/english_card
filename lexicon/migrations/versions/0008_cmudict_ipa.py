"""CMUdict phonemes as IPA where Wiktionary has none

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-30 14:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for (pid,) in bind.execute(sa.text(
            "SELECT id FROM source_policies WHERE target_language = 'en' AND field = 'ipa'")).all():
        steps = dict(bind.execute(sa.text(
            "SELECT source, position FROM source_policy_steps WHERE policy_id = :p"),
            {"p": pid}).all())
        if 'cmudict' in steps:
            continue
        # Right after Kaikki (before the local phrase rule), in a free gap.
        pos = steps.get('kaikki', 0) + 500
        while pos in steps.values():
            pos += 1
        bind.execute(sa.text(
            "INSERT INTO source_policy_steps (policy_id, source, position, enabled, timeout_s,"
            " retries, min_confidence, max_results, continue_on_failure)"
            " VALUES (:p, 'cmudict', :pos, true, 20, 0, 0, NULL, true)"), {"p": pid, "pos": pos})
        bind.execute(sa.text("UPDATE source_policies SET version = version + 1 WHERE id = :p"),
                     {"p": pid})


def downgrade() -> None:
    pass
