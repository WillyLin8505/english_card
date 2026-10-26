"""Card #645: photo label grid (詞性 x CEFR), concepts share their anchor."""
from app import models as m, photo_grid


def _lex(s, word, pos, cefr, zh=True):
    lex = m.Lexeme(language="en", lemma=word, normalized=word, pos=pos, status="full", cefr=cefr)
    s.add(lex)
    s.flush()
    sense = m.Sense(lexeme_id=lex.id, sense_key="1")
    s.add(sense)
    s.flush()
    if zh:
        s.add(m.SenseTranslation(sense_id=sense.id, native_language="zh-TW", text="x", source="t"))
    return lex


def _syn(s, a, b, strength=0.9, source="oewn"):
    s.add(m.LexemeRelation(lexeme_id=a.id, relation="synonyms", target_lexeme_id=b.id,
                           target_word=b.normalized, strength=strength, source=source))


def test_grid_shape_and_shared_anchor(session):
    s = session
    happy, joyful, elated = _lex(s, "happy", "adj", "A1"), _lex(s, "joyful", "adj", "B2"), _lex(s, "elated", "adj", "C1")
    nozh = _lex(s, "blithe", "adj", "C2", zh=False)
    loose = _lex(s, "sad", "adj", "A1")
    _syn(s, happy, joyful)
    _syn(s, elated, happy)  # reverse direction counts too
    _syn(s, happy, nozh)
    _syn(s, happy, loose, strength=0.5)
    s.flush()
    tags = [{"word": "happy", "pos": "adjective", "cefr": "A1", "point": [0.2, 0.3], "box": None},
            {"word": "dog", "pos": "noun", "cefr": "A1", "point": [0.6, 0.6], "box": None}]
    grid = photo_grid.build_grid(s, tags)
    assert grid["rows"] == photo_grid.ROWS and grid["levels"] == photo_grid.LEVELS
    assert len(grid["cells"]) == 30
    cell = {(c["pos"], c["cefr"]): c["words"] for c in grid["cells"]}
    assert [w["word"] for w in cell[("adjective", "A1")]] == ["happy"]
    assert [w["word"] for w in cell[("adjective", "B2")]] == ["joyful"]
    assert [w["word"] for w in cell[("adjective", "C1")]] == ["elated"]
    assert cell[("adjective", "C2")] == []  # no Chinese meaning -> not offered
    assert cell[("adjective", "A2")] == []  # nothing for the photo -> stays empty
    ids = {w["concept_id"] for k in (("adjective", "A1"), ("adjective", "B2"), ("adjective", "C1"))
           for w in cell[k]}
    assert len(ids) == 1
    anchors = [w["anchor"] for k in (("adjective", "A1"), ("adjective", "B2"), ("adjective", "C1"))
               for w in cell[k]]
    assert all(a["point"] == [0.2, 0.3] for a in anchors)
    assert cell[("noun", "A1")][0]["word"] == "dog" and cell[("noun", "A1")][0]["concept_id"] != next(iter(ids))
    assert {w["source"] for w in cell[("adjective", "B2")]} == {"lexicon"}


def test_cell_limit_and_unplaceable_pos(session):
    tags = [{"word": f"w{i}", "pos": "noun", "cefr": "B1", "point": [0.1, 0.1]} for i in range(5)]
    tags.append({"word": "in", "pos": "preposition", "cefr": "A1", "point": [0.1, 0.1]})
    tags.append({"word": "look up", "pos": "verb", "cefr": "B1", "point": [0.1, 0.1]})
    cell = {(c["pos"], c["cefr"]): c["words"] for c in photo_grid.build_grid(session, tags)["cells"]}
    assert len(cell[("noun", "B1")]) == photo_grid.CELL_MAX
    assert [w["word"] for w in cell[("phrase", "B1")]] == ["look up"]
    assert sum(len(w) for w in cell.values()) == photo_grid.CELL_MAX + 1
