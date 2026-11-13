"""Card #1186 (issue #1644): relation words skip abbreviation/variant glosses and take numerals for digits."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.adapters.local import META_GLOSS, NUMERAL_ZH  # noqa: E402


def test_card_examples_are_meta_glosses():
    assert META_GLOSS.search("一百八十度旋轉的縮寫")
    assert META_GLOSS.search("二靈的別字；「雙性人」的縮寫")
    assert META_GLOSS.search("印地語字母中的元音")
    assert META_GLOSS.search("祖父的簡稱")


def test_ordinary_glosses_are_kept():
    assert not META_GLOSS.search("一百八十度旋轉")
    assert not META_GLOSS.search("更好、比較好的")
    assert not META_GLOSS.search("硬碟")


def test_digits_map_to_numerals():
    assert NUMERAL_ZH["1"] == "一"
    assert NUMERAL_ZH["2"] == "二"
    assert NUMERAL_ZH["10"] == "十"
    assert "11" not in NUMERAL_ZH
