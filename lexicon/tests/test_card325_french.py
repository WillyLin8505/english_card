"""Card #325: the French lexicon (fr→en) runs on the same schema and field
catalog as English; these are the language-specific seams it needed."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import catalog, qc  # noqa: E402
from app.adapters import commons, kaikki  # noqa: E402
from app.adapters.base import Candidate, Context, validate  # noqa: E402
from app.images import english_search_term  # noqa: E402
from app.pipeline import not_applicable  # noqa: E402


def test_french_fields_exist_only_for_french():
    fr = {f.key for f in catalog.fields_for("fr")}
    en = {f.key for f in catalog.fields_for("en")}
    assert "fr_present_1s" in fr and "fr_present_1s" not in en
    assert "verb_past" in en and "verb_past" not in fr
    # Everything else (definition, examples, images, QC fields) is shared.
    assert fr - {k for k in fr if k.startswith("fr_")} == en - {k for k in en if k in catalog.FORM_POS and not k.startswith("fr_")}


def test_french_policies_have_sources():
    for f in ("definition", "native_definition", "example_sentences", "cefr", "ipa", "audio",
              "fr_present_1s", "fr_feminine", "sense_image"):
        sources, _, _ = catalog.default_policy("fr", "en", f)
        assert sources, f
    assert catalog.default_policy("fr", "en", "cefr")[0] == ["local_calc"]
    assert catalog.default_policy("fr", "en", "native_definition")[0][0] == "kaikki"


class _Ctx:
    def __init__(self, pos):
        self._pos = pos
        self.resolved = set()

    def items(self, key):
        return [{"pos": p} for p in self._pos] if key == "pos" else []


def test_french_forms_not_applicable_by_pos():
    assert not_applicable("fr_present_1s", _Ctx(["noun"])) == "不是動詞"
    assert not_applicable("fr_present_1s", _Ctx(["verb"])) is None
    # Gender / number forms belong to nouns and adjectives alike.
    assert not_applicable("fr_feminine", _Ctx(["noun"])) is None
    assert not_applicable("fr_feminine", _Ctx(["adj"])) is None
    assert not_applicable("fr_feminine", _Ctx(["verb"])) == "不是形容詞／名詞"
    assert "fr_plural" in catalog.MAY_BE_EMPTY


def test_kaikki_form_field_french():
    assert kaikki.form_field("verb", {"first-person", "singular", "present", "indicative"}, "fr") == "fr_present_1s"
    assert kaikki.form_field("verb", {"participle", "past"}, "fr") == "fr_past_participle"
    assert kaikki.form_field("noun", {"feminine"}, "fr") == "fr_feminine"
    assert kaikki.form_field("adj", {"feminine", "plural"}, "fr") == "fr_feminine_plural"
    assert kaikki.form_field("noun", {"plural"}, "fr") == "fr_plural"


def test_french_recording_file_accents():
    assert kaikki.file_accent("Fr-Paris--chat.ogg") == ["FR"]
    assert kaikki.file_accent("Fr-ca-chat.ogg") == ["CA"]
    assert kaikki.file_accent("LL-Q150 (fra)-Lyokoï-chat.wav") == []
    assert kaikki.file_accent("En-uk-bottle.ogg") == ["UK"]
    assert "Fr-{}.ogg" in commons.AUDIO_TITLES_BY_LANGUAGE["fr"]


def test_english_search_term_for_french_senses():
    assert english_search_term("cat (feline)") == "cat"
    assert english_search_term("to eat") == "eat"
    assert english_search_term("house; home") == "house"
    assert english_search_term("big, large") == "big"
    assert english_search_term(None, "apple (fruit)") == "apple"
    assert english_search_term("a very long explanatory english gloss without commas") is None


def test_french_example_validation_uses_forms():
    ctx = Context("fr", "en", "chat", "chat")
    ok = Candidate("example_sentences", "fr", {"text": "Le chat dort sur le canapé."}, "k1")
    assert validate(ok, ctx) is None
    short = Candidate("example_sentences", "fr", {"text": "Un chat."}, "k2")
    assert validate(short, ctx) == "少於 3 個字，不像完整句子"
    other = Candidate("example_sentences", "fr", {"text": "Le chien dort sur le canapé."}, "k3")
    assert validate(other, ctx) == "例句沒有用到這個字或可信詞形"


def test_qc_latin_check_only_for_chinese_native():
    lx = {"id": 1, "status": "full", "normalized": "chat", "pos": "noun", "cefr": "A1",
          "senses": [{"id": 1, "native": "cat (feline)", "priority": "high"}],
          "pronunciations": [{"kind": "ipa", "value": "/ʃa/"}, {"kind": "audio", "value": "x.mp3"}]}
    fr_pack = {"target_language": "fr", "native_language": "en", "lexemes": [lx]}
    assert "sense.native_has_latin" not in qc.validate(fr_pack)
    zh_pack = {"target_language": "en", "native_language": "zh-TW", "lexemes": [dict(lx)]}
    assert "sense.native_has_latin" in qc.validate(zh_pack)


# ── Card #329: the 2000–3000 word list ──────────────────────────────────

def test_kaikki_index_path_per_language(tmp_path, monkeypatch):
    from app import config, kaikki_index
    monkeypatch.setattr(config, "KAIKKI_INDEX", tmp_path / "kaikki-index.sqlite3")
    assert kaikki_index.index_path("fr") == tmp_path / "kaikki-index.sqlite3"
    (tmp_path / "kaikki-index.fr.sqlite3").write_bytes(b"")
    assert kaikki_index.index_path("fr") == tmp_path / "kaikki-index.fr.sqlite3"
    assert kaikki_index.index_path("en") == tmp_path / "kaikki-index.sqlite3"


def test_french_usage_pos_in_sentence():
    from app.adapters.local import _usage_pos_fr
    forms = frozenset({"maison", "maisons"})
    assert _usage_pos_fr("Laissez-moi vous faire visiter notre maison.", forms, frozenset()) == "noun"
    assert _usage_pos_fr("Mes parents sont à la maison maintenant.", forms, frozenset()) == "noun"
    assert _usage_pos_fr("J'ai acheté une belle maison.", forms, frozenset()) == "noun"
    # un grand homme: the noun phrase goes on, so grand is the adjective.
    assert _usage_pos_fr("C'est un grand homme.", frozenset({"grand", "grands"}), frozenset()) is None
    assert _usage_pos_fr("Nous mangeons ensemble.", frozenset({"manger", "mangeons"}),
                         frozenset({"mangeons"})) == "verb"
    assert _usage_pos_fr("Il pleut.", forms, frozenset()) == "other"


def test_french_verb_only_forms_use_fr_fields():
    from app.adapters.local import _verb_only_forms

    class Ctx:
        lemma = "manger"

        def items(self, key):
            return {"fr_present_1p": [{"form": "mangeons"}],
                    "fr_plural": [{"form": "mangers"}]}.get(key, [])

    assert _verb_only_forms(Ctx()) == frozenset({"mangeons"})
