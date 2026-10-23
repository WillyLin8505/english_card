"""A regular inflection the dictionary gives no sound for takes its base
word's IPA plus the suffix's sound (問題回報 #24: drizzled had no IPA)."""

from __future__ import annotations

from app import kaikki_index
from app.adapters import Context
from app.adapters.local import LocalCalc, inflected_ipa, linked_base_ipa

DICTIONARY = {
    "drizzled": [{"word": "drizzled", "pos": "verb",
                  "senses": [{"form_of": [{"word": "drizzle"}]}]}],
    "drizzle": [{"word": "drizzle", "pos": "verb", "sounds": [{"ipa": "/ˈdɹɪzəl/"}]}],
    "spotted": [{"word": "spotted", "pos": "verb", "senses": [{"form_of": [{"word": "spot"}]}]}],
    "spot": [{"word": "spot", "pos": "noun",
              "sounds": [{"ipa": "/spɒt/", "tags": ["Received-Pronunciation"]},
                         {"ipa": "[spɑʔ]"}]}],
    "buses": [{"word": "buses", "pos": "noun", "senses": [{"form_of": [{"word": "bus"}]}]}],
    "bus": [{"word": "bus", "pos": "noun", "sounds": [{"ipa": "/bʌs/"}]}],
    "leaves": [{"word": "leaves", "pos": "noun", "senses": [{"form_of": [{"word": "leaf"}]}]}],
    "leaf": [{"word": "leaf", "pos": "noun", "sounds": [{"ipa": "/liːf/"}]}],
    "fed": [{"word": "fed", "pos": "verb", "senses": [{"form_of": [{"word": "feed"}]}]}],
    "feed": [{"word": "feed", "pos": "verb", "sounds": [{"ipa": "/fiːd/"}]}],
}


def _dictionary(monkeypatch):
    monkeypatch.setattr(kaikki_index, "lookup",
                        lambda language, word, path=None: DICTIONARY.get(word.lower(), []))


def test_regular_inflections_take_the_suffix_sound(monkeypatch):
    _dictionary(monkeypatch)
    assert [v["ipa"] for v in inflected_ipa("drizzled")] == ["/ˈdɹɪzəld/"]
    spotted = inflected_ipa("spotted")
    assert [(v["ipa"], v["accent"]) for v in spotted] == [("/ˈspɒtɪd/", ["UK"])]  # not [spɑʔ]
    assert [v["ipa"] for v in inflected_ipa("buses")] == ["/ˈbʌsɪz/"]
    assert inflected_ipa("leaves") == []  # /f/ → /v/: not just a suffix
    assert inflected_ipa("fed") == []  # irregular spelling
    assert inflected_ipa("drizzle") == []  # not an inflection


def test_alt_of_copies_the_base_pronunciation(monkeypatch):
    dictionary = {
        "panick": [{"word": "panick", "pos": "verb",
                    "senses": [{"alt_of": [{"word": "panic"}]}]}],
        "panic": [{"word": "panic", "pos": "noun", "sounds": [
            {"ipa": "/ˈpænɪk/", "tags": ["US"]},
            {"ipa": "[ˈpʰænɪk]"},
            {"ipa": "/ˈpænɪk/", "tags": ["UK"]}]}],
        "chainmail": [{"word": "chainmail", "pos": "noun",
                       "senses": [{"alt_of": [{"word": "chain mail"}]}]}],
        "blague": [{"word": "blague", "pos": "noun",
                    "senses": [{"glosses": ["a joke"]}]}],
        "upperclassmen": [{"word": "upperclassmen", "pos": "noun",
                           "senses": [{"form_of": [{"word": "upperclassman"}]}]}],
        "mixed": [{"word": "mixed", "pos": "noun", "senses": [
            {"alt_of": [{"word": "mix"}]}, {"glosses": ["a blend"]}]}],
        "backburner": [
            {"word": "backburner", "pos": "noun",
             "senses": [{"alt_of": [{"word": "back burner"}]}]},
            {"word": "backburner", "pos": "verb",
             "senses": [{"glosses": ["To postpone"]}]},
        ],
    }
    monkeypatch.setattr(kaikki_index, "lookup",
                        lambda language, word, path=None: dictionary.get(word.lower(), []))
    monkeypatch.setattr("app.adapters.local._cmudict_ipa",
                        lambda phrase: {"chain mail": "/tʃeɪn meɪl/",
                                        "back burner": "/bæk ˈbɝnɚ/"}.get(phrase))
    assert [v["ipa"] for v in linked_base_ipa("panick")] == ["/ˈpænɪk/"]
    assert linked_base_ipa("panick")[0]["base"] == "panic"
    assert [v["ipa"] for v in linked_base_ipa("chainmail")] == ["/tʃeɪn meɪl/"]
    assert [v["ipa"] for v in linked_base_ipa("backburner")] == ["/bæk ˈbɝnɚ/"]
    assert linked_base_ipa("blague") == []
    assert linked_base_ipa("upperclassmen") == []
    assert linked_base_ipa("mixed") == []
    cands = LocalCalc().normalize("ipa", None, Context("en", "zh-TW", "panick", "panick"))
    assert [(c.value["ipa"], c.value["base"]) for c in cands] == [("/ˈpænɪk/", "panic")]


def test_local_calc_offers_it_as_ipa(monkeypatch):
    _dictionary(monkeypatch)
    cands = LocalCalc().normalize("ipa", None, Context("en", "zh-TW", "drizzled", "drizzled"))
    assert [(c.value["ipa"], c.value["composed"], c.value["base"]) for c in cands] \
        == [("/ˈdɹɪzəld/", True, "drizzle")]


def test_stress_suffix_ipa_card551():
    from app.adapters.local import stress_suffix_ipa
    got = {v["ipa"] for v in stress_suffix_ipa("chaotically")}
    assert "/keɪˈɒtɪkli/" in got
    assert any(v.endswith("aɪˈzeɪʃən/") for v in (x["ipa"] for x in stress_suffix_ipa("neutralisation")))
    assert stress_suffix_ipa("anticlimactically") == []
    assert stress_suffix_ipa("table") == []
