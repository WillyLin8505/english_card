"""Proves the priority/fallback logic against spec-01-data-sources.html
section 3, independent of any real adapter — every adapter here is a
tiny stub so this test only depends on pipeline/priority.py + merge.py."""

from pipeline.merge import build_word_detail, resolve
from pipeline.sources.base import SourceAdapter


class StubAdapter:
    """A bare object (deliberately NOT a SourceAdapter subclass) that only
    exposes the get_* methods it was given, each returning a fixed value
    regardless of the word argument. Any get_* not passed in simply does
    not exist on the instance, so `getattr(adapter, name, None)` in
    merge.resolve() correctly sees it as "no data" and moves on to the
    next source in priority order — the same behaviour a real adapter
    gets for free by not overriding a base-class no-op method."""

    def __init__(self, name, **answers):
        self.name = name
        for method_name, value in answers.items():
            setattr(self, method_name, (lambda v: (lambda word: v))(value))


def test_first_priority_source_wins_when_it_has_data():
    kaikki = StubAdapter("kaikki", get_lexical={"definitions": [{"pos": "noun", "gloss": "kaikki def"}]})
    wordnet = StubAdapter("wordnet", get_lexical={"definitions": [{"pos": "noun", "gloss": "wordnet def"}]})
    result, source = resolve("example", "lexical", {"kaikki": kaikki, "wordnet": wordnet})
    assert source == "kaikki"
    assert result["definitions"][0]["gloss"] == "kaikki def"


def test_falls_back_to_second_priority_when_first_is_empty():
    # lexical priority is [kaikki, wordnet]; kaikki has no answer here.
    kaikki = StubAdapter("kaikki")
    wordnet = StubAdapter("wordnet", get_lexical={"definitions": [{"pos": "noun", "gloss": "wordnet def"}]})
    result, source = resolve("example", "lexical", {"kaikki": kaikki, "wordnet": wordnet})
    assert source == "wordnet"
    assert result["definitions"][0]["gloss"] == "wordnet def"


def test_falls_back_when_source_missing_entirely():
    wordnet = StubAdapter("wordnet", get_lexical={"definitions": [{"pos": "noun", "gloss": "wordnet def"}]})
    result, source = resolve("example", "lexical", {"wordnet": wordnet})
    assert source == "wordnet"


def test_falls_back_when_source_raises():
    class Boom(SourceAdapter):
        def get_lexical(self, word):
            raise RuntimeError("network down")

    wordnet = StubAdapter("wordnet", get_lexical={"definitions": [{"pos": "noun", "gloss": "ok"}]})
    result, source = resolve("example", "lexical", {"kaikki": Boom(), "wordnet": wordnet})
    assert source == "wordnet"


def test_returns_none_when_no_source_has_data():
    result, source = resolve("example", "lexical", {"kaikki": StubAdapter("kaikki")})
    assert result is None
    assert source is None


def test_homophones_priority_is_cmudict_then_datamuse_then_kaikki():
    # spec: 同音字／發音相近 -> ① CMUdict ② Datamuse ③ Kaikki
    cmudict = StubAdapter("cmudict", get_homophones=["flower"])
    datamuse = StubAdapter("datamuse", get_homophones=["flowre-typo"])
    result, source = resolve("flour", "homophones", {"cmudict": cmudict, "datamuse": datamuse})
    assert source == "cmudict"
    assert result == ["flower"]


def test_build_word_detail_assembles_full_record_with_provenance():
    adapters = {
        "kaikki": StubAdapter(
            "kaikki",
            get_lexical={"definitions": [{"pos": "noun", "gloss": "a typical instance"}]},
            get_pronunciation={"ipa": "/ɪɡˈzæmpəl/", "arpabet": None},
            get_word_audio={"url": "https://example.invalid/example.mp3"},
            get_inflections=[{"form": "examples", "label": "plural"}],
            get_morphology={"root": "exempl", "affixes": ["-um"]},
        ),
        "wordnet": StubAdapter(
            "wordnet", get_synonyms=["instance", "illustration"]
        ),
        "cmudict": StubAdapter("cmudict", get_homophones=None),
        "tatoeba": StubAdapter(
            "tatoeba",
            get_example_sentences=[
                {"en": "This is an example.", "zh": "這是一個例子。", "audio_url": "https://x/a.mp3"}
            ],
        ),
    }

    wd = build_word_detail("example", adapters)
    data = wd.to_json()

    assert data["word"] == "example"
    assert data["definitions"][0]["gloss"] == "a typical instance"
    assert data["definitions_source"] == "kaikki"
    assert data["ipa"] == "/ɪɡˈzæmpəl/"
    assert data["ipa_source"] == "kaikki"
    assert data["synonyms"] == ["instance", "illustration"]
    assert data["synonyms_source"] == "wordnet"
    assert data["homophones"] == []
    assert data["homophones_source"] is None
    assert data["example_sentences"][0]["zh"] == "這是一個例子。"
    assert data["example_sentences"][0]["source"] == "tatoeba"
    assert data["root"] == "exempl"
    assert data["affixes"] == ["-um"]


def test_build_word_detail_handles_no_adapters_gracefully():
    wd = build_word_detail("example", {})
    data = wd.to_json()
    assert data["word"] == "example"
    assert data["definitions"] == []
    assert data["definitions_source"] is None
