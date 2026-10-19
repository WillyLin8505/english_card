"""Card #365 / 問題回報 #362: a French word's picture shows its own French label,
not the English label the vision model wrote; English labels that name no
word of the entry are not drawn."""
from app.views import french_labels


def _row(**over):
    row = {"lemma": "casque", "pos": "noun", "cefr": "B1", "english": "helmet",
           "gloss": "coiffure protégeant la tête"}
    row.update(over)
    return row


def test_named_label_becomes_french_word():
    tags = [{"word": "helmet", "point": [0.4, 0.3], "box": None, "score": 0.95},
            {"word": "chainmail", "point": [0.6, 0.6], "box": None, "score": 0.9}]
    out = french_labels(_row(), tags, [])
    assert [t["word"] for t in out["tags"]] == ["casque"]
    assert out["tags"][0]["cefr"] == "B1"
    assert out["tags"][0]["point"] == [0.4, 0.3]
    assert out["tags"][0]["native"] == "helmet"
    assert out["unmatched_tags"] == [{"word": "chainmail", "score": 0.9}]


def test_no_named_label_draws_nothing_but_lists_english():
    tags = [{"word": "stone", "point": [0.5, 0.5], "score": 0.9}]
    out = french_labels(_row(), tags, [])
    assert out["tags"] == []
    assert out["unmatched_tags"] == [{"word": "stone", "score": 0.9}]


def test_point_tag_preferred_over_pointless_one():
    tags = [{"word": "helmet", "point": None, "score": 0.99},
            {"word": "helmet", "point": [0.2, 0.2], "score": 0.85}]
    out = french_labels(_row(), tags, [])
    assert out["tags"][0]["point"] == [0.2, 0.2]


def test_dropped_named_label_keeps_reason_and_english_is_hidden():
    dropped = [{"word": "helmet", "score": 0.6, "dropReason": "under 80%"},
               {"word": "wall", "score": 0.3}]
    out = french_labels(_row(), [], dropped)
    assert out["dropped_tags"] == [{"word": "casque", "pos": "noun", "cefr": "B1",
                                    "native": "helmet", "score": 0.6, "dropReason": "under 80%"}]
    assert out["unmatched_tags"] == [{"word": "wall", "score": 0.3}]


def test_unknown_level_is_dropped():
    out = french_labels(_row(cefr=None), [{"word": "helmet", "point": [0.1, 0.1]}], [])
    assert out["tags"][0]["cefr"] is None
