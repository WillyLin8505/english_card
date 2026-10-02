"""AI translation back as the last source of native-language fields

A release removed the AI step from every stored policy. Put it back, once,
at the end of each translation field's policy (catalog.AI_TRANSLATED),
where it only fills what the dictionaries lack and is marked as AI.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28 23:40:00
"""
from alembic import op
import sqlalchemy as sa

from app import catalog

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

GAP = 1000


def upgrade() -> None:
    bind = op.get_bind()
    policies = bind.execute(sa.text(
        "SELECT id, target_language, native_language, field FROM source_policies")).all()
    for pid, target, native, field in policies:
        if field not in catalog.AI_TRANSLATED or target not in catalog.LANGUAGES \
                or native not in catalog.LANGUAGES \
                or not catalog.supports("ai_translate", target, native, field)[0]:
            continue
        steps = bind.execute(sa.text(
            "SELECT source, position FROM source_policy_steps WHERE policy_id = :p"),
            {"p": pid}).all()
        if any(src == "ai_translate" for src, _ in steps):
            continue
        last = max((pos for _, pos in steps), default=0)
        bind.execute(sa.text(
            "INSERT INTO source_policy_steps (policy_id, source, position, enabled, timeout_s,"
            " retries, min_confidence, max_results, continue_on_failure)"
            " VALUES (:p, 'ai_translate', :pos, true, 120, 1, 0, NULL, true)"),
            {"p": pid, "pos": last + GAP})
        bind.execute(sa.text("UPDATE source_policies SET version = version + 1 WHERE id = :p"),
                     {"p": pid})


def downgrade() -> None:
    pass
