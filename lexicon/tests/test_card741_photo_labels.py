from app.photo_labels import LABEL_BUDGET, pick_labels, pos_counts


def _grid(words):
    cells = {}
    for pos, cefr, word, source, fit in words:
        w = {"word": word, "concept_id": "c1", "anchor": None, "source": source}
        if fit is not None:
            w["fit"] = fit
        cells.setdefault((pos, cefr), []).append(w)
    return {"cells": [{"pos": p, "cefr": c, "words": ws} for (p, c), ws in cells.items()]}


def _rich():
    items = [("noun", "A1", f"n{i}", "photo", None) for i in range(6)]
    items += [("noun", "B1", f"m{i}", "photo", None) for i in range(4)]
    items += [("verb", "A1", "run", "photo", None), ("verb", "B1", "sprint", "related", 0.9),
              ("adjective", "A2", "big", "photo", None), ("adjective", "B1", "vast", "related", 0.7),
              ("phrase", "B1", "in a row", "photo", None),
              ("adverb", "B1", "quickly", "related", 0.9), ("adverb", "B1", "often", "related", 0.5)]
    return _grid(items)


def test_a1_is_almost_all_nouns():
    labels = pick_labels(_rich(), "A1")
    c = pos_counts(labels)
    assert len(labels) <= LABEL_BUDGET["A1"]
    assert c["noun"] >= len(labels) - 1
    assert all(x["cefr"] in ("A1", "A2") for x in labels)   # nothing above A2 for an A1 learner


def test_higher_level_has_more_other_parts_of_speech():
    g = _rich()
    share = lambda lv: 1 - pos_counts(pick_labels(g, lv)).get("noun", 0) / len(pick_labels(g, lv))
    assert share("A1") < share("B1") <= share("C1") + 1e-9
    c = pos_counts(pick_labels(g, "C1"))
    assert 0.5 <= c["noun"] / sum(c.values()) <= 0.75


def test_adverb_needs_fit_and_other_related_need_fit():
    labels = pick_labels(_rich(), "C1")
    words = {x["word"] for x in labels}
    assert "often" not in words and "quickly" in words
    assert pos_counts(labels).get("adverb", 0) <= 1


def test_no_adverb_means_empty_and_pos_on_every_label():
    g = _grid([("noun", "A1", "dog", "photo", None), ("adverb", "A1", "badly", "related", None)])
    labels = pick_labels(g, "B1")
    assert [x["word"] for x in labels] == ["dog"]
    assert all("pos" in x and "_rank" not in x for x in labels)


def test_photo_words_come_first_and_unknown_level_defaults():
    g = _grid([("noun", "B1", "a", "related", 0.9), ("noun", "B1", "b", "photo", None)])
    assert pick_labels(g, None)[0]["word"] == "b"
