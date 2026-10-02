"""Local rules as the last source where dictionaries leave gaps

CEFR (a frequency estimate, marked so), a phrase's IPA (its words'), a
regular noun plural and a derived word's part of speech.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-30 09:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None

GAP = 1000
ADD = {"cefr": "local_calc", "ipa": "local_calc", "noun_plural": "local_calc",
       "derived_pos": "local_calc"}


def upgrade() -> None:
    bind = op.get_bind()
    for pid, field in bind.execute(sa.text(
            "SELECT id, field FROM source_policies WHERE target_language = 'en'"
            " AND field = ANY(:f)"), {"f": list(ADD)}).all():
        steps = bind.execute(sa.text(
            "SELECT source, position FROM source_policy_steps WHERE policy_id = :p"),
            {"p": pid}).all()
        if any(src == ADD[field] for src, _ in steps):
            continue
        last = max((pos for _, pos in steps), default=0)
        bind.execute(sa.text(
            "INSERT INTO source_policy_steps (policy_id, source, position, enabled, timeout_s,"
            " retries, min_confidence, max_results, continue_on_failure)"
            " VALUES (:p, :src, :pos, true, 20, 0, 0, NULL, true)"),
            {"p": pid, "src": ADD[field], "pos": last + GAP})
        bind.execute(sa.text("UPDATE source_policies SET version = version + 1 WHERE id = :p"),
                     {"p": pid})


def downgrade() -> None:
    pass
