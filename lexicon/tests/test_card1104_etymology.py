"""card #1104 (問題回報 #1612): etymology translation skipped headings and split accented words."""
from backend.app.adapters.ai import _paren_foreign_roots
from backend.app.adapters.kaikki import is_junk_etymology


def test_headings_and_tree_labels_are_junk():
    for t in ("Abbreviations", "Abbreviation.", "PIE word", "]", "Latin -ereinflu.", "French bonredup."):
        assert is_junk_etymology(t), t
    for t in ("From peruse + -al.", "Past participle of partir.", "Literally, “not bad”."):
        assert not is_junk_etymology(t), t


def test_accented_roots_are_wrapped_whole():
    assert _paren_foreign_roots("源於古英語 pēa 加 pāvō") == "源於古英語 （pēa） 加 （pāvō）"
