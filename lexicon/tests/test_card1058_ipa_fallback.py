from app.materialize import ipa_fallback

JAN = [{"ipa": "/a/", "pos": "name"}, {"ipa": "/b/", "pos": "verb"}]


def test_name_is_noun():
    assert ipa_fallback(JAN, "noun") == [JAN[0]]


def test_other_pos_when_none_of_its_own():
    assert ipa_fallback([{"ipa": "/x/", "pos": "adj"}], "noun") == [{"ipa": "/x/", "pos": "adj"}]


def test_empty_ipa_ignored():
    assert ipa_fallback([{"ipa": " ", "pos": "noun"}], "noun") == []
