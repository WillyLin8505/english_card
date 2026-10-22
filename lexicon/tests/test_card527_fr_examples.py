"""Card #527 / 問題回報 #562: example_flags sees accented French words, elisions and
« » quotes; the gender letters m / f never count as a form of the headword."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import quality as q  # noqa: E402
from app.adapters import tatoeba  # noqa: E402
from app.adapters.base import Context  # noqa: E402


def test_accented_forms_are_found():
    assert q.example_flags("Pourquoi es-tu mouillée ?", "mouillé", "adj", ["mouillée"]) == []
    assert q.example_flags("L'élève est en retard.", "élève", "noun") == []
    assert q.example_flags("Cette symphonie est un chef-d'œuvre.", "œuvre", "noun") == []
    assert q.example_flags("Avez-vous vu l'arc-en-ciel ce matin ?", "arc", "noun") == []
    assert q.example_flags("Combien d'ex-épouses Tom a-t-il ?", "ex", "noun") == []


def test_gender_letter_is_not_the_word():
    # « m'aider » / « M. Johnson » reached fils when « m » was among the query forms.
    assert "missing_lemma" in q.example_flags("Pourriez-vous m'aider quand je déménagerai ?",
                                              "fils", "noun", ["fils"])
    assert "missing_lemma" in q.example_flags("Permettez-moi de vous présenter M. Johnson.",
                                              "fils", "noun", ["fils"])
    assert "missing_lemma" in q.example_flags("F est égal à 15 en hexadécimal.", "craie", "noun")
    assert "missing_lemma" in q.example_flags("Ouais, montre-nous tes f... phrases...", "craie", "noun")
    assert q.example_flags("Mon fils a trois ans.", "fils", "noun", ["fils"]) == []


def test_french_sentence_shape():
    assert q.example_flags("Élise est arrivée hier.", "arriver", "verb", ["arrivée"]) == []
    assert q.example_flags("« Où est la gare ? »", "gare", "noun") == []
    assert "not_sentence" in q.example_flags("la gare du nord", "gare", "noun")


def test_english_unchanged():
    assert q.example_flags("She tore the letter in half.", "tear", "verb", ["tore"]) == []
    assert "missing_lemma" in q.example_flags("The cat sat on the mat.", "dog", "noun")
    assert q.example_flags("Don't tell-tale on your brother.", "tale", "noun") == []
    assert "missing_lemma" in q.example_flags("I don't know.", "don", "noun")  # no elision in English


def test_tatoeba_drops_french_sentences_without_the_word():
    ctx = Context("fr", "en", "fils", "fils")
    ctx.resolved["fr_gender"] = [{"form": "m"}]
    ctx.resolved["pos"] = [{"pos": "noun"}]
    raw = {"mode": "snapshot", "sentences": [
        {"id": 1, "text": "Pourriez-vous m'aider quand je déménagerai ?", "owner": None,
         "translations": [{"id": 11, "text": "Can you help me when I move?"}]},
        {"id": 2, "text": "Mon fils a trois ans.", "owner": None,
         "translations": [{"id": 12, "text": "My son is three."}]},
        {"id": 3, "text": "un fils", "owner": None, "translations": []},
    ]}
    cands = tatoeba.Tatoeba().normalize("example_sentences", raw, ctx)
    assert [c.value["text"] for c in cands] == ["Mon fils a trois ans."]
