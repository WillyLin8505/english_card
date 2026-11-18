import pytest
from app.adapters.local import fr_adverbial_phrase


@pytest.mark.parametrize("text,own,expected", [
    ("Il va de mal en pis.", {"noun", "conj"}, True),
    ("Tant pis pour toi !", {"noun"}, True),
    ("Les vaches ont des pis.", {"noun"}, False),
    ("Tant pis, les pis des vaches.", {"noun"}, False),
    ("Tant pis pour toi !", {"noun", "adv"}, False),
    ("Pas étonnant qu'il ait tant pleuré.", {"verb"}, False),
])
def test_adverbial_phrase(text, own, expected):
    forms = {"pis", "pleuré"}
    assert fr_adverbial_phrase(text, forms, own) is expected
