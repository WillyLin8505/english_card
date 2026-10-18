"""Coarse words are kept and flagged 粗俗, not dropped (2026-10-15)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.text import sense_native  # noqa: E402


def test_vulgar_sense_keeps_coarse_chinese():
    assert sense_native("王八蛋", ["derogatory", "offensive", "vulgar"]) == ("王八蛋", True)
    assert sense_native("傻屌", ["derogatory", "slang"]) == ("傻屌", True)


def test_neutral_sense_still_filtered():
    assert sense_native("弱者、處於劣勢的人、屌絲", []) == ("弱者、處於劣勢的人", False)


def test_vulgar_label_without_profane_chinese():
    assert sense_native("混蛋", ["vulgar"]) == ("混蛋", True)
    assert sense_native("俚語詞", ["slang"]) == ("俚語詞", False)
