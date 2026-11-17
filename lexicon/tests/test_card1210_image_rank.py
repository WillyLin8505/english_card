"""Card #1210: a representative picture only ranks -1 when it is a top, scored hit."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from serve_app import image_rank  # noqa: E402


def _b(role, ordinal, score):
    return SimpleNamespace(role=role, ordinal=ordinal, semantic_score=score)


def test_good_representative_stays_first():
    assert image_rank(_b('representative', 0, 0.95)) == -1


def test_weak_or_deep_representative_ranks_by_ordinal():
    assert image_rank(_b('representative', 22, 0.5)) == 22   # img 31401
    assert image_rank(_b('representative', 6, 0.95)) == 6    # img 527
    assert image_rank(_b('representative', 1, None)) == 1


def test_context_unchanged():
    assert image_rank(_b('context', 4, 0.9)) == 4
