"""-er / -est forms English does not use (card #465, issue #459)."""
import pytest

from app.adapters.kaikki import degree_entry_unused, degree_pos_minor


def adj(head, senses=1, tags=None):
    return {"pos": "adj", "head_templates": [{"name": "en-adj", "args": head}],
            "senses": [{"tags": tags or []} for _ in range(senses)]}


def other(pos, senses):
    return {"pos": pos, "senses": [{} for _ in range(senses)]}


@pytest.mark.parametrize("word, entry, rest, unused", [
    ("anxious", adj({"1": "more,er"}, 4), [], True),          # anxiouser
    ("perfect", adj({"1": "-", "2": "er,more"}, 19), [], True),  # perfecter
    ("game", adj({"1": "er"}, 3), [other("noun", 23)], True),  # gamer
    ("stick", adj({"1": "er"}, 1), [other("noun", 51)], True),  # sticker
    ("trig", adj({"1": "er"}, 5, ["dialectal"]), [other("noun", 2)], True),  # trigger
    ("fly", adj({"1": "er"}, 4), [other("noun", 35)], True),   # flier: not an -ly word
    ("happy", adj({"1": "er,more"}, 8), [other("verb", 2)], False),
    ("odd", adj({"1": "-,er"}, 14), [other("noun", 2)], False),  # odder: usually not comparable
    ("pale", adj({"1": "er"}, 3), [other("noun", 10)], False),
    ("likely", adj({"1": "more,er"}, 7), [], False),          # -ly keeps likelier (#463)
    ("fit", adj({"1": "er"}, 5), [other("noun", 16)], False),  # reviewed: fitter
])
def test_degree_entry_unused(word, entry, rest, unused):
    assert degree_entry_unused(word, entry, [entry, *rest]) is unused


# Card #472 (issue #470): more / most of a word that is not really an adjective.
@pytest.mark.parametrize("word, entry, rest, minor", [
    ("tea", adj({}, 2), [other("noun", 19), other("verb", 3)], True),      # more tea
    ("tomato", adj({}, 1), [other("noun", 5), other("verb", 2)], True),    # most tomato
    ("street", adj({}, 1), [other("noun", 13), other("verb", 5)], True),   # more street
    ("apply", adj({}, 1), [other("verb", 10)], True),                      # -ly verb, not likely
    ("trig", adj({"1": "er"}, 5, ["dialectal"]), [other("noun", 2)], True),
    ("orange", adj({"1": "er,more"}, 2), [other("noun", 14), other("verb", 2)], False),  # colour
    ("likely", adj({"1": "more,er"}, 7), [other("adv", 3)], False),
    ("fun", adj({"1": "more,er"}, 2), [other("noun", 2), other("verb", 1)], False),
    ("plastic", adj({}, 10), [other("noun", 8)], False),
    ("fit", adj({"1": "er"}, 5), [other("noun", 16)], False),             # reviewed keep
    ("anxious", adj({"1": "more,er"}, 4), [], False),  # more anxious stays; anxiouser is #465's
])
def test_degree_pos_minor(word, entry, rest, minor):
    assert degree_pos_minor(word, entry, [entry, *rest]) is minor
