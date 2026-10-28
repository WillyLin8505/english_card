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


def test_qwen_fit_verdicts_drop_misfits_and_cache(session, tmp_path, monkeypatch):
    s = session
    monkeypatch.setattr(photo_grid, "FIT_PATH", tmp_path / "fit.json")
    dog, bark, loyal = _lex(s, "dog", "noun", "A1"), _lex(s, "bark", "verb", "A2"), _lex(s, "loyal", "adj", "B1")
    _link(s, dog, bark, "related")
    _link(s, dog, loyal, "hyponyms")
    s.flush()
    tags = [{"word": "dog", "pos": "noun", "cefr": "A1", "point": [0.5, 0.5]}]
    grid = photo_grid.build_grid(s, tags)
    assert grid["fit_unchecked"] == 2
    assert sorted(photo_grid.related_words(grid)) == [("adjective", "loyal"), ("verb", "bark")]
    photo_grid.save_fit(7, {"verb|bark": 0.9, "adjective|loyal": 0.1})
    grid = photo_grid.build_grid(s, tags, photo_grid.load_fit(7))
    cell = {(c["pos"], c["cefr"]): c for c in grid["cells"]}
    assert cell[("verb", "A2")]["words"][0]["fit"] == 0.9
    assert cell[("adjective", "B1")]["words"] == []
    assert cell[("adjective", "B1")]["empty_reason"] == photo_grid.EMPTY_REASON
    assert grid["fit_unchecked"] == 0
    assert photo_grid.load_fit(8) == {}
