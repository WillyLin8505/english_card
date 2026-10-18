# -*- coding: utf-8 -*-
"""Unit tests for CEFR enrich beginner-cap packing (no vision / no network)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lexicon" / "backend"))
sys.path.insert(0, str(ROOT / "lexicon" / "tools"))


class _EmptyScalars:
    def first(self):
        return None


class _FakeSession:
    def scalars(self, *_a, **_k):
        return _EmptyScalars()


def test_pack_tags_caps_beginners_and_keeps_higher_bands():
    # Import after path setup; images.TAGS_MAX is used by the helper.
    import enrich_cefr_tags as ect

    def tag(word, cefr, score=0.9, pos="noun"):
        return {"word": word, "pos": pos, "cefr": cefr, "modelLevel": cefr, "score": score}

    tags = [
        tag("cup", "A1", 0.99),
        tag("plate", "A1", 0.98),
        tag("bowl", "A1", 0.97),
        tag("mug", "A1", 0.96),
        tag("fork", "A1", 0.95),
        tag("saucer", "A2", 0.94),
        tag("napkin", "A2", 0.93),
        tag("tray", "A2", 0.92),
        tag("ladle", "A2", 0.91),
        tag("simmer", "B2", 0.85, pos="verb"),
        tag("ornate", "C1", 0.84, pos="adjective"),
        tag("briskly", "C2", 0.83, pos="adverb"),
    ]
    out = ect.pack_tags_with_beginner_cap(
        _FakeSession(), tags, tags_max=18, beginner_max=3, per_level=3
    )
    words = {t["word"] for t in out}
    levels = ect.band_counts(_FakeSession(), out)
    assert levels["A1"] == 3
    assert levels["A2"] == 3
    assert levels["B2"] == 1 and levels["C1"] == 1 and levels["C2"] == 1
    assert {"simmer", "ornate", "briskly"} <= words
    assert "mug" not in words and "fork" not in words and "ladle" not in words


def test_pack_tags_prefers_higher_bands_when_near_tags_max():
    import enrich_cefr_tags as ect

    def tag(word, cefr, score=0.9):
        return {"word": word, "pos": "noun", "cefr": cefr, "modelLevel": cefr, "score": score}

    # 3 per band would be 18; add extra beginners with high scores that must not
    # displace the single C2 when tags_max is tight.
    tags = (
        [tag(f"a1_{i}", "A1", 0.99) for i in range(6)]
        + [tag(f"a2_{i}", "A2", 0.98) for i in range(6)]
        + [tag("rare_widget", "C2", 0.70)]
    )
    out = ect.pack_tags_with_beginner_cap(
        _FakeSession(), tags, tags_max=10, beginner_max=3, per_level=3
    )
    words = {t["word"] for t in out}
    assert "rare_widget" in words
    assert ect.band_counts(_FakeSession(), out)["A1"] <= 3
    assert ect.band_counts(_FakeSession(), out)["A2"] <= 3
    assert len(out) <= 10
