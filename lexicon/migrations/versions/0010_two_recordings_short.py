"""Two recordings a word (UK + US) and the 「缺漏」 status

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-30 23:30:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # English audio: Kaikki, then Commons for the accent Kaikki lacks; the
    # system voice is a playback fallback (tts_fallback), not a recording.
    for (pid,) in bind.execute(sa.text(
            "SELECT id FROM source_policies WHERE target_language = 'en' AND field = 'audio'")).all():
        steps = dict(bind.execute(sa.text(
            "SELECT source, position FROM source_policy_steps WHERE policy_id = :p"),
            {"p": pid}).all())
        bind.execute(sa.text("DELETE FROM source_policy_steps WHERE policy_id = :p"
                             " AND source = 'system_tts'"), {"p": pid})
        if 'wikimedia_commons' not in steps:
            pos = steps.get('kaikki', 0) + 500
            while pos in steps.values():
                pos += 1
            bind.execute(sa.text(
                "INSERT INTO source_policy_steps (policy_id, source, position, enabled, timeout_s,"
                " retries, min_confidence, max_results, continue_on_failure)"
                " VALUES (:p, 'wikimedia_commons', :pos, true, 20, 1, 0, NULL, true)"),
                {"p": pid, "pos": pos})
        bind.execute(sa.text("UPDATE source_policies SET strategy = 'MERGE_UNIQUE',"
                             " version = version + 1 WHERE id = :p"), {"p": pid})
    # Levels left under three after every source answered were marked
    # complete; they are 「缺漏」 now.
    bind.execute(sa.text(
        "UPDATE field_values SET status = 'short' WHERE status = 'complete'"
        " AND field IN ('example_sentences', 'synonyms', 'related')"
        " AND missing::text NOT IN ('[]', 'null', '')"))


def downgrade() -> None:
    pass
