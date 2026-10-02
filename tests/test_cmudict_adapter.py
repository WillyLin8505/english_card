from conftest import FIXTURES

from pipeline.sources.cmudict_adapter import CMUdictAdapter


def make_adapter():
    return CMUdictAdapter(FIXTURES / "cmudict_sample.dict")


def test_pronunciation_returns_arpabet_not_ipa():
    adapter = make_adapter()
    result = adapter.get_pronunciation("example")
    assert result == {"ipa": None, "arpabet": "IH0 G Z AE1 M P AH0 L"}


def test_pronunciation_unknown_word_returns_none():
    adapter = make_adapter()
    assert adapter.get_pronunciation("zzzznotaword") is None


def test_homophones_exact_phoneme_match():
    adapter = make_adapter()
    assert adapter.get_homophones("flour") == ["flower"]
    assert adapter.get_homophones("flower") == ["flour"]
    assert adapter.get_homophones("made") == ["maid"]


def test_homophones_none_when_no_match():
    adapter = make_adapter()
    assert adapter.get_homophones("example") is None


def test_words_lists_all_entries():
    adapter = make_adapter()
    assert "happy" in adapter.words()
    assert "flour" in adapter.words()
