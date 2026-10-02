"""Examples, synonyms and related words filled per CEFR level

Each level A1–C2 keeps 3–5 of them (catalog.LEVELED). Stored policies get
AI as their last source (it only fills levels still short) and room for
six levels of five (30).

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-29 21:30:00
"""
from alembic import op
import sqlalchemy as sa

from app import catalog

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

GAP = 1000


def upgrade() -> None:
    bind = op.get_bind()
    policies = bind.execute(sa.text(
        "SELECT id, target_language, native_language, field, max_items FROM source_policies"
        " WHERE field = ANY(:f)"), {"f": list(catalog.LEVELED)}).all()
    for pid, target, native, field, max_items in policies:
        if target not in catalog.LANGUAGES or native not in catalog.LANGUAGES:
            continue
        if max_items is None or max_items < 30:
            bind.execute(sa.text("UPDATE source_policies SET max_items = 30 WHERE id = :p"),
                         {"p": pid})
        steps = bind.execute(sa.text(
            "SELECT source, position FROM source_policy_steps WHERE policy_id = :p"),
            {"p": pid}).all()
        if not any(src == "ai_translate" for src, _ in steps) \
                and catalog.supports("ai_translate", target, native, field)[0]:
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
