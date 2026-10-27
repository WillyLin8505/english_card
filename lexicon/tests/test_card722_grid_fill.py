"""Card #722: empty grid cells are filled from the word web around the shown words."""
from app import photo_grid
from tests.test_card645_photo_grid import _lex


def _link(s, a, b, relation, strength=0.9):
    from app import models as m
    s.add(m.LexemeRelation(lexeme_id=a.id, relation=relation, target_lexeme_id=b.id,
                           target_word=b.normalized, strength=strength, source="t"))


def test_empty_cells_get_related_word_or_reason(session):
    s = session
    dog, bark, loyal = _lex(s, "dog", "noun", "A1"), _lex(s, "bark", "verb", "A2"), _lex(s, "loyal", "adj", "B1")
    far = _lex(s, "far", "adv", "C1")
    _link(s, dog, bark, "related")
    _link(s, dog, loyal, "hyponyms")
    _link(s, bark, far, "related")  # two loose steps: too far
    s.flush()
    grid = photo_grid.build_grid(s, [{"word": "dog", "pos": "noun", "cefr": "A1", "point": [0.5, 0.5]}])
    cell = {(c["pos"], c["cefr"]): c for c in grid["cells"]}
    assert [(w["word"], w["source"]) for w in cell[("verb", "A2")]["words"]] == [("bark", "related")]
    assert cell[("verb", "A2")]["words"][0]["anchor"]["point"] == [0.5, 0.5]
    assert cell[("adjective", "B1")]["words"][0]["word"] == "loyal"
    assert cell[("adverb", "C1")]["words"] == []
    assert cell[("adverb", "C1")]["empty_reason"] == photo_grid.EMPTY_REASON
    assert "empty_reason" not in cell[("noun", "A1")]
