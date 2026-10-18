"""Require three classified image labels in every CEFR band.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-04 21:20:00
"""
from alembic import op


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


def upgrade() -> None:
    checks = " OR ".join(
        "(SELECT count(*) FROM jsonb_array_elements(coalesce(a.tags::jsonb, '[]'::jsonb)) t "
        f"WHERE upper(coalesce(t->>'cefr', t->>'modelLevel', '')) = '{level}') < 3"
        for level in LEVELS
    )
    op.execute(f"""
        UPDATE image_assets AS a
        SET tag_status = 'pending'
        WHERE a.status = 'ready'
          AND (
            a.tags IS NULL
            OR EXISTS (
              SELECT 1
              FROM jsonb_array_elements(coalesce(a.tags::jsonb, '[]'::jsonb)) t
              WHERE upper(coalesce(t->>'cefr', t->>'modelLevel', ''))
                    NOT IN ('A1','A2','B1','B2','C1','C2')
            )
            OR {checks}
          )
    """)


def downgrade() -> None:
    # Only rows that already satisfy the old "enough scored labels" rule can
    # safely be called done again. Incomplete rows remain pending.
    op.execute("""
        UPDATE image_assets AS a
        SET tag_status = 'done'
        WHERE a.status = 'ready' AND a.tag_status = 'pending'
          AND jsonb_array_length(coalesce(a.tags::jsonb, '[]'::jsonb)) >= 8
          AND NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(a.tags::jsonb) t
            WHERE t->'score' IS NULL
          )
    """)
