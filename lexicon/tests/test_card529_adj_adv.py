"""Card #529 / 問題回報 #567: _usage_pos tells the adjective from the adverb
for words listed as both (pretty, fast, hard, late, well)."""
import pytest

from app.adapters.local import _usage_pos


@pytest.mark.parametrize("word,sentence,expected", [
    ("pretty", "Tom and Mary are pretty proud.", "adv"),
    ("pretty", "Tom has a pretty good idea who burned his house down.", "adv"),
    ("pretty", "I did pretty well.", "adv"),
    ("pretty", "She is pretty.", "adj"),
    ("pretty", "Your classmate's clothes are very pretty.", "adj"),
    ("pretty", 'It means "pretty", right?', None),
    ("fast", "He runs fast.", "adv"),
    ("fast", "The baby was fast asleep in her mother's arms.", "adv"),
    ("fast", "You walk too fast for me to keep up with you.", "adv"),
    ("fast", "This car is fast.", "adj"),
    ("hard", "He studied hard in order to get into college.", "adv"),
    ("hard", "The test was hard.", "adj"),
    ("late", "She arrived late.", "adv"),
    ("late", "It is getting late.", "adj"),
    ("late", "We had a late lunch.", "adj"),
    ("well", "Neither team played well in the game.", "adv"),
    ("well", "I don't feel well.", "adj"),
    ("right", "Turn right.", "adv"),
    ("right", "You are right.", "adj"),
    ("long", "We had long hard days.", None),
    ("left", "There are few positions left open for you.", None),
    ("okay", '"Okay, okay," said the doctor.', None),
])
def test_adj_or_adv(word, sentence, expected):
    assert _usage_pos(sentence, {word}, frozenset(), word) == expected


def test_closed_class_adverb_unchanged():
    # still/even keep the adverb-slot rule: 「is still here」 is not the adjective.
    assert _usage_pos("He is still here.", {"still"}, frozenset(), "still") is None
