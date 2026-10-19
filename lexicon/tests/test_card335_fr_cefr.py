"""Card #335 (問題回報 #332 decision C): French CEFR = the AI-reviewed
3000-word list, else max(wordfreq, Lexique lemma) frequency estimate."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.adapters.local import fr_cefr_source, fr_reviewed, fr_zipf, word_level, _zipf  # noqa: E402


def test_reviewed_list_overrides_frequency():
    assert len(fr_reviewed()) == 3000
    # wordfreq alone put these at A2/B1 (subtitle/web frequency).
    for w in ("chat", "pomme", "fromage", "fenêtre", "mardi"):
        assert word_level(w, "fr") == "A1" and fr_cefr_source(w) == "ai_reviewed"
    # Frequent but abstract / news words are not A1.
    assert word_level("gouvernement", "fr") == "B1"


def test_unlisted_word_uses_lexique_lemma_frequency():
    assert "cahier" not in fr_reviewed() and fr_cefr_source("cahier") == "frequency_estimate"
    # The lemma counts all its forms, so it is never rarer than one spelling.
    assert fr_zipf("cahier") >= _zipf("cahier", "fr")


def test_english_unchanged():
    assert fr_cefr_source("apple") == "frequency_estimate"
    assert word_level("apple", "en") == "A1"
