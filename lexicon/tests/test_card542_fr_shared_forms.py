"""Card #542 (問題回報 #582): a French conjugation another frequent verb shares
(suivre's « suis » = être) is not a query / match form."""
import pytest

from app.adapters import local
from app.adapters.base import Context

# Kaikki entries by word: (pos, form_of bases, tags, gloss)
KAIKKI = {
    "suis": [("verb", ["être"], ["first-person", "indicative", "present", "singular"], "… of être"),
             ("verb", ["suivre"], ["first-person", "indicative", "present", "singular"], "… of suivre")],
    "vis": [("noun", [], ["feminine"], "screw"),
            ("verb", ["vivre"], ["first-person", "indicative", "present", "singular"], "… of vivre"),
            ("verb", ["voir"], ["first-person", "historic", "past", "singular"], "… past historic of voir")],
    "fonde": [("verb", ["fonder"], ["indicative", "present", "singular"], "inflection of fonder:"),
              ("verb", ["fondre"], ["present", "singular", "subjunctive"], "… present subjunctive of fondre")],
    "fondons": [("verb", ["fonder"], ["first-person", "indicative", "plural", "present"], "… of fonder"),
                ("verb", ["fondre"], ["first-person", "indicative", "plural", "present"], "… of fondre")],
    "été": [("verb", ["être"], ["participle", "past"], "past participle of être"),
            ("verb", ["aller"], ["Louisiana", "participle", "past"], "past participle of aller")],
    "polis": [("verb", ["poli"], ["masculine", "plural"], "masculine plural of poli"),
              ("verb", ["polir"], ["first-person", "indicative", "present", "singular"], "… of polir")],
    "aime": [("verb", ["aimer"], ["indicative", "present", "singular"], "… of aimer")],
    "aimé": [("verb", ["aimer"], ["participle", "past"], "past participle of aimer")],
    "sommes": [("verb", ["être"], ["first-person", "indicative", "plural", "present"], "… of être"),
               ("verb", ["sommer"], ["indicative", "present", "singular"], "… of sommer")],
    "poli": [("verb", ["polir"], ["participle", "past"], "past participle of polir"),
             ("adj", [], [], "polite")],
    # verb lemmas: one meaning of their own
    "être": [("verb", [], [], "to be")], "suivre": [("verb", [], [], "to follow")],
    "vivre": [("verb", [], [], "to live")], "voir": [("verb", [], [], "to see")],
    "fonder": [("verb", [], [], "to found")], "fondre": [("verb", [], [], "to melt")],
    "aller": [("verb", [], [], "to go")], "polir": [("verb", [], [], "to polish")],
    "aimer": [("verb", [], [], "to love")], "sommer": [("verb", [], [], "to summon")],
}
ZIPF = {"être": 7.5, "suivre": 5.2, "vivre": 5.7, "voir": 6.5, "fonder": 4.4, "fondre": 4.4,
        "aller": 6.8, "polir": 3.0, "poli": 4.0, "aimer": 6.0, "aimé": 4.5, "sommer": 2.5}


@pytest.fixture(autouse=True)
def fake_kaikki(monkeypatch):
    def lookup(language, word, path=None):
        return [{"word": word, "pos": pos,
                 "senses": [{"form_of": [{"word": b} for b in bases], "tags": tags + (["form-of"] if bases else []),
                             "glosses": [gloss]}]}
                for pos, bases, tags, gloss in KAIKKI.get(word, [])]
    from app import kaikki_index
    monkeypatch.setattr(kaikki_index, "lookup", lookup)
    monkeypatch.setattr(local, "fr_zipf", lambda w: ZIPF.get(w, 0.0))
    local._fr_form_verbs.cache_clear()
    local._fr_verb_lemma.cache_clear()
    yield
    local._fr_form_verbs.cache_clear()
    local._fr_verb_lemma.cache_clear()


def test_rarer_verb_loses_the_shared_conjugation():
    assert local.fr_shared_verb_forms("suivre", ["suis", "suit", "suivons"]) == {"suis"}
    # the far more frequent verb keeps it
    assert local.fr_shared_verb_forms("être", ["suis", "sommes", "été"]) == frozenset()


def test_past_historic_subjunctive_and_regional_uses_are_no_competitors():
    assert local.fr_shared_verb_forms("vivre", ["vis", "vit"]) == frozenset()   # voir: past historic
    assert local.fr_shared_verb_forms("fonder", ["fonde"]) == frozenset()       # fondre: subjunctive only
    assert local.fr_shared_verb_forms("être", ["été"]) == frozenset()           # aller: Louisiana


def test_verbs_of_equal_frequency_both_lose_the_form():
    assert local.fr_shared_verb_forms("fonder", ["fondons"]) == {"fondons"}
    assert local.fr_shared_verb_forms("fondre", ["fondons"]) == {"fondons"}


def test_own_base_and_participle_entries_are_not_other_verbs():
    assert local.fr_shared_verb_forms("polir", ["polis"]) == frozenset()   # poli = polir's participle
    assert local.fr_shared_verb_forms("aimé", ["aime"]) == frozenset()     # aimé conjugates aimer
    assert local.fr_shared_verb_forms("sommer", ["sommes"]) == {"sommes"}


def test_word_forms_and_verb_only_forms_leave_the_shared_form_out():
    ctx = Context("fr", "en", "suivre", "suivre", resolved={
        "fr_present_1s": [{"form": "suis"}], "fr_present_3s": [{"form": "suit"}],
        "fr_past_participle": [{"form": "suivi"}]})
    assert local.word_forms(ctx) == {"suivre", "suit", "suivi"}
    assert local._verb_only_forms(ctx) == {"suit", "suivi"}
    en = Context("en", "zh-TW", "follow", "follow", resolved={"verb_past": [{"form": "followed"}]})
    assert "followed" in local.word_forms(en)


def test_usage_pos_fr_treats_a_shared_form_as_absent():
    ctx = Context("fr", "en", "suivre", "suivre", resolved={
        "fr_present_1s": [{"form": "suis"}], "fr_present_3s": [{"form": "suit"}]})
    forms, only = local.word_forms(ctx), local._verb_only_forms(ctx)
    assert local._usage_pos_fr("Je suis content.", forms, only) == "other"
    assert local._usage_pos_fr("Il suit le chemin.", forms, only) == "verb"
