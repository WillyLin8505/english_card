"""Card #1219: French conjugation table fields from Kaikki tags (no AI)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import fr_conj  # noqa: E402
from app.adapters import kaikki  # noqa: E402


def ff(*tags):
    return kaikki.form_field("verb", set(tags), "fr")


def test_every_simple_tense_gets_its_field():
    assert ff("first-person", "singular", "indicative", "present") == "fr_present_1s"
    assert ff("imperfect", "indicative", "plural", "third-person") == "fr_imperfect_3p"
    assert ff("future", "indicative", "plural", "second-person") == "fr_future_2p"
    assert ff("conditional", "singular", "third-person") == "fr_conditional_3s"
    assert ff("present", "subjunctive", "plural", "third-person") == "fr_subjunctive_3p"
    assert ff("historic", "indicative", "past", "singular", "third-person") == "fr_passe_simple_3s"
    assert ff("imperative", "second-person", "singular") == "fr_imperative_2s"
    assert ff("first-person", "imperative", "plural") == "fr_imperative_1p"


def test_compound_and_literary_tenses_are_skipped():
    assert ff("imperfect", "multiword-construction", "subjunctive") is None
    assert ff("imperfect", "first-person", "singular", "subjunctive") is None
    assert ff("anterior", "indicative", "past", "singular", "third-person") is None


def test_ipa_is_not_a_spelling():
    # parler's first-person singular carried «paʁl» (and asseoir «/a.swa.jɑ̃/»)
    assert not kaikki.fr_spelling_ok("paʁl")
    assert not kaikki.fr_spelling_ok("/a.swa.jɑ̃/")
    assert kaikki.fr_spelling_ok("lèverai") and kaikki.fr_spelling_ok("aujourd'hui")


def test_group_and_model():
    assert fr_conj.verb_group("parler", {}) == "1"
    assert fr_conj.verb_group("aller", {}) == "3"
    assert fr_conj.verb_group("finir", {"fr_present_participle": ["finissant"]}) == "2"
    assert fr_conj.verb_group("partir", {"fr_present_participle": ["partant"]}) == "3"
    assert fr_conj.first_group_model("manger", {"fr_present_1s": ["mange"]}) == "manger"
    assert fr_conj.first_group_model("lever", {"fr_present_1s": ["lève"]}) == "lever"
    assert fr_conj.first_group_model("payer", {"fr_present_1s": ["paye", "paie"]}) == "payer"
    assert fr_conj.first_group_model("appeler", {"fr_present_1s": ["appelle"]}) == "appeler"


def test_before_vowel_masculine_and_pronominal():
    assert kaikki.form_field("adj", {"before-vowel", "masculine", "singular"}, "fr") == "fr_masculine_before_vowel"
    assert fr_conj.is_pronominal([], "se lever") and not fr_conj.is_pronominal([], "lever")
