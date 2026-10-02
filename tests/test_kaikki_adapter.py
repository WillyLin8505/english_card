from conftest import FIXTURES

from pipeline.sources.kaikki_adapter import KaikkiAdapter


def make_adapter():
    return KaikkiAdapter(FIXTURES / "kaikki_sample.jsonl")


def test_lexical():
    adapter = make_adapter()
    result = adapter.get_lexical("example")
    assert result["definitions"][0]["pos"] == "noun"
    assert "representative" in result["definitions"][0]["gloss"]


def test_pronunciation_prefers_ipa():
    adapter = make_adapter()
    result = adapter.get_pronunciation("happy")
    assert result == {"ipa": "/ˈhæp.i/", "arpabet": None}


def test_word_audio():
    adapter = make_adapter()
    result = adapter.get_word_audio("example")
    assert result["url"].endswith(".mp3")


def test_synonyms():
    adapter = make_adapter()
    assert adapter.get_synonyms("example") == ["instance", "illustration"]


def test_inflections_excludes_headword_and_table_tags():
    adapter = make_adapter()
    result = adapter.get_inflections("example")
    assert result == [{"form": "examples", "label": "plural"}]


def test_derivations():
    adapter = make_adapter()
    result = adapter.get_derivations("happy")
    words = [d["word"] for d in result]
    assert "happiness" in words
    assert "unhappy" in words


def test_morphology_suffix_template():
    adapter = make_adapter()
    result = adapter.get_morphology("happy")
    assert result["root"] == "hap"
    assert result["affixes"] == ["-y"]


def test_example_sentences():
    adapter = make_adapter()
    result = adapter.get_example_sentences("example")
    assert result[0]["en"] == "This is an example sentence."
    assert result[0]["zh"] is None


def test_unknown_word_returns_none_everywhere():
    adapter = make_adapter()
    assert adapter.get_lexical("zzznotaword") is None
    assert adapter.get_synonyms("zzznotaword") is None
    assert adapter.get_morphology("zzznotaword") is None
