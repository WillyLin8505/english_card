"""A rare derivative no dictionary pronounces takes its parts' sounds
(問題回報 #291: frother, attester, loungey had no IPA from any source)."""

from __future__ import annotations

from app import kaikki_index
from app.adapters import Context
from app.adapters import local
from app.adapters.ecdict import ECDict
from app.adapters.local import LocalCalc, derived_affix_ipa

DICTIONARY = {
    # Wiktionary names the parts: suffix / ety :af / prefix templates.
    "frother": [{"word": "frother", "pos": "verb", "etymology_templates": [
                    {"name": "inh", "args": {"1": "en", "2": "enm", "3": "frotheren"}}]},
                {"word": "frother", "pos": "noun", "etymology_templates": [
                    {"name": "ety", "args": {"1": "en", "2": ":af", "3": "froth",
                                             "4": "-er<id:agent noun>"}}]}],
    "froth": [{"word": "froth", "pos": "noun", "sounds": [
        {"ipa": "/ˈfɹɒθ/", "tags": ["UK"]}, {"ipa": "[ˈfɹʷɒθ]", "tags": ["UK"]},
        {"ipa": "/ˈfɹɔθ/", "tags": ["US"]}]}],
    "attester": [{"word": "attester", "pos": "noun", "etymology_templates": [
        {"name": "suffix", "args": {"1": "en", "2": "attest", "3": "er", "id2": "agent noun"}}]}],
    "attest": [{"word": "attest", "pos": "verb", "sounds": [{"ipa": "/əˈtɛst/"}]}],
    "stepdad": [{"word": "stepdad", "pos": "noun", "etymology_templates": [
        {"name": "ety", "args": {"1": "en", "2": ":af", "3": "step-", "4": "dad"}}]}],
    "dad": [{"word": "dad", "pos": "noun", "sounds": [{"ipa": "/dæd/"}]}],
    "unhappy": [{"word": "unhappy", "pos": "adj", "etymology_templates": [
        {"name": "prefix", "args": {"1": "en", "2": "un", "3": "happy"}}]}],
    "happy": [{"word": "happy", "pos": "adj", "sounds": [{"ipa": "/ˈhæpi/"}]}],
    "backburner": [{"word": "backburner", "pos": "noun", "etymology_templates": [
        {"name": "compound", "args": {"1": "en", "2": "back", "3": "burner"}}]}],
    "back": [{"word": "back", "pos": "noun", "sounds": [{"ipa": "/bæk/"}]}],
    "burner": [{"word": "burner", "pos": "noun", "sounds": [
        {"ipa": "/ˈbɜːnə/", "tags": ["UK"]}, {"ipa": "/ˈbɝnɚ/", "tags": ["US"]}]}],
    "crumbly": [{"word": "crumbly", "pos": "adj", "etymology_templates": [
        {"name": "suffix", "args": {"1": "en", "2": "crumble", "3": "y"}}]}],
    "crumble": [{"word": "crumble", "pos": "verb", "sounds": [{"ipa": "/ˈkɹʌmbəl/"}]}],
    "watery": [{"word": "watery", "pos": "adj", "etymology_templates": [
        {"name": "suffix", "args": {"1": "en", "2": "water", "3": "y"}}]}],
    "water": [{"word": "water", "pos": "noun", "sounds": [
        {"ipa": "/ˈwɔːtə/", "tags": ["UK"]}, {"ipa": "/ˈwɔtɚ/", "tags": ["US"]}]}],
    "coniform": [{"word": "coniform", "pos": "adj", "etymology_templates": [
        {"name": "suffix", "args": {"1": "en", "2": "cone", "3": "iform"}}]}],
    "cone": [{"word": "cone", "pos": "noun", "sounds": [{"ipa": "/kəʊn/"}]}],
    "nationality": [{"word": "nationality", "pos": "noun", "etymology_templates": [
        {"name": "suffix", "args": {"1": "en", "2": "national", "3": "ity"}}]}],
    "national": [{"word": "national", "pos": "adj", "sounds": [{"ipa": "/ˈnæʃənəl/"}]}],
    "frotheren": [{"word": "frotheren", "pos": "verb"}],
    # A noun's prefix takes the main stress; a verb's base keeps it.
    "outgroup": [{"word": "outgroup", "pos": "noun", "etymology_templates": [
        {"name": "prefix", "args": {"1": "en", "2": "out", "3": "group"}}]}],
    "outrun": [{"word": "outrun", "pos": "verb", "etymology_templates": [
        {"name": "prefix", "args": {"1": "en", "2": "out", "3": "run"}}]}],
    "group": [{"word": "group", "pos": "noun", "sounds": [{"ipa": "/ɡɹuːp/"}]}],
    "run": [{"word": "run", "pos": "verb", "sounds": [{"ipa": "/ɹʌn/"}]}],
    "autoinflammation": [{"word": "autoinflammation", "pos": "noun", "etymology_templates": [
        {"name": "prefix", "args": {"1": "en", "2": "auto", "3": "inflammation"}}]}],
    "auto": [{"word": "auto", "pos": "noun", "sounds": [{"ipa": "/ˈɔːtəʊ/"}]}],
    "inflammation": [{"word": "inflammation", "pos": "noun",
                      "sounds": [{"ipa": "/ɪnfləˈmeɪʃən/"}]}],
    # No parts named: spelling alone (lounge + y, thug + y, un + bother).
    "loungey": [{"word": "loungey", "pos": "adj"}],
    "lounge": [{"word": "lounge", "pos": "noun", "sounds": [{"ipa": "/laʊndʒ/"}]}],
    "thuggy": [{"word": "thuggy", "pos": "adj"}],
    "thug": [{"word": "thug", "pos": "noun", "sounds": [{"ipa": "/θʌɡ/"}]}],
    "bother": [{"word": "bother", "pos": "verb", "sounds": [
        {"ipa": "/ˈbɒðə/", "tags": ["UK"]}, {"ipa": "/ˈbɑðɚ/", "tags": ["US"]}]}],
    # Combining forms Wiktionary files as suffixes (問題回報 #209: repairperson).
    "repairperson": [{"word": "repairperson", "pos": "noun", "etymology_templates": [
        {"name": "suffix", "args": {"1": "en", "2": "repair", "3": "person"}}]}],
    "repair": [{"word": "repair", "pos": "verb", "sounds": [
        {"ipa": "/ɹɪˈpɛə/", "tags": ["UK"]}, {"ipa": "/ɹɪˈpɛɹ/", "tags": ["US"]}]}],
    "soundproof": [{"word": "soundproof", "pos": "adj", "etymology_templates": [
        {"name": "suffix", "args": {"1": "en", "2": "sound", "3": "proof"}}]}],
    "sound": [{"word": "sound", "pos": "noun", "sounds": [{"ipa": "/saʊnd/"}]}],
    "wind": [{"word": "wind", "pos": "noun", "sounds": [{"ipa": "/wɪnd/"}]},
             {"word": "wind", "pos": "verb", "etymology_number": 2,
              "sounds": [{"ipa": "/waɪnd/"}]}],
}
ECDICT = {"windy": "/ˈwɪndi/"}
CMUDICT = {"zorb": "/zɔɹb/"}


def _sources(monkeypatch, dictionary=DICTIONARY):
    monkeypatch.setattr(kaikki_index, "lookup",
                        lambda language, word, path=None: dictionary.get(word.lower(), []))
    monkeypatch.setattr(ECDict, "ipa", lambda self, word: ECDICT.get(word.lower()))
    monkeypatch.setattr(local, "_cmudict_ipa", lambda phrase: CMUDICT.get(phrase.lower()))


def _ipa(word):
    return [(v["ipa"], v["accent"]) for v in derived_affix_ipa(word)]


def test_wiktionary_named_parts(monkeypatch):
    _sources(monkeypatch)
    assert _ipa("frother") == [("/ˈfɹɒθə/", ["UK"]), ("/ˈfɹɔθɚ/", ["US"])]
    assert _ipa("attester") == [("/əˈtɛstə/", ["UK"]), ("/əˈtɛstɚ/", ["US"])]
    assert _ipa("stepdad") == [("/ˈstɛpˌdæd/", [])]  # a noun: step- takes the stress
    assert _ipa("unhappy") == [("/ˌʌnˈhæpi/", [])]
    assert _ipa("outgroup") == [("/ˈaʊtˌɡɹuːp/", [])]  # a noun: the prefix is stressed
    assert _ipa("outrun") == [("/ˌaʊtˈɹʌn/", [])]  # a verb: the base is
    # A word used as a prefix drops its own stress mark (no ˌˈ) and the base keeps the main one.
    assert _ipa("autoinflammation") == [("/ˌɔːtəʊɪnfləˈmeɪʃən/", [])]
    assert _ipa("backburner") == [("/ˈbækˌbɜːnə/", ["UK"]), ("/ˈbækˌbɝnɚ/", ["US"])]
    rows = derived_affix_ipa("frother")
    assert rows[0]["base"] == "froth + -er" and rows[0]["derived"] == "wiktionary"
    assert rows[0]["estimate"] and rows[0]["composed"]


def test_sounds_at_the_seam(monkeypatch):
    _sources(monkeypatch)
    assert _ipa("crumbly") == [("/ˈkɹʌmbli/", [])]  # syllabic -le loses its schwa
    # Linking r in the UK form, ɚ → əɹ in the US form.
    assert _ipa("watery") == [("/ˈwɔːtəɹi/", ["UK"]), ("/ˈwɔtəɹi/", ["US"])]


def test_combining_forms_filed_as_suffixes(monkeypatch):
    _sources(monkeypatch)
    assert _ipa("repairperson") == [("/ɹɪˈpɛəpɜːsən/", ["UK"]), ("/ɹɪˈpɛɹpɜɹsən/", ["US"])]
    assert _ipa("soundproof") == [("/ˈsaʊndpɹuːf/", [])]


def test_unknown_or_stress_moving_suffixes_are_left_alone(monkeypatch):
    _sources(monkeypatch)
    assert _ipa("coniform") == []  # -iform: not in the table
    assert _ipa("nationality") == []  # -ity moves the stress
    assert _ipa("froth") == []  # has no parts
    assert _ipa("milk frother") == []  # phrases are the phrase rule's job


def test_spelling_guess_needs_a_pronounced_base_and_no_dictionary_ipa(monkeypatch):
    _sources(monkeypatch)
    assert _ipa("loungey") == [("/ˈlaʊndʒi/", [])]
    assert _ipa("thuggy") == [("/ˈθʌɡi/", [])]
    assert _ipa("unbother") == [("/ˌʌnˈbɒðə/", ["UK"]), ("/ˌʌnˈbɑðɚ/", ["US"])]
    assert derived_affix_ipa("loungey")[0]["derived"] == "spelling"
    assert _ipa("windy") == []  # ECDICT pronounces it: that source is next in line
    assert _ipa("blague") == []  # a loanword: no parts, no guess
    assert _ipa("zorbing") == []  # -ing is an inflection, not derived here
    assert _ipa("zorby") == []  # a guessed base has to be a Wiktionary headword, not CMUdict only


def test_named_parts_may_come_from_cmudict(monkeypatch):
    _sources(monkeypatch, {**DICTIONARY, "zorby": [{"word": "zorby", "pos": "adj", "etymology_templates": [
        {"name": "suffix", "args": {"1": "en", "2": "zorb", "3": "y"}}]}]})
    assert _ipa("zorby") == [("/ˈzɔɹbi/", ["US"])]  # US only, from phonemes
    assert derived_affix_ipa("zorby")[0]["from_phonemes"] is True


def test_local_calc_offers_the_estimate_with_a_lower_confidence(monkeypatch):
    _sources(monkeypatch)
    ctx = Context(target="en", native="zh-TW", lemma="frother")
    cands = LocalCalc().lookup("ipa", ctx)
    assert [c.value["ipa"] for c in cands] == ["/ˈfɹɒθə/", "/ˈfɹɔθɚ/"]
    assert all(c.confidence == 0.5 and c.valid and c.source == "local_calc" for c in cands)
    assert LocalCalc().lookup("ipa", Context(target="en", native="zh-TW", lemma="froth")) == []
