"""#384 / 問題回報 #379: a French sense's picture word can be reviewed. chef1
「article, principal point」 must not search or label pictures with article;
croix1 「a representation of a cross」 is the cross itself."""

import json

import pytest

from app import images, search_terms


def _fr_word(session, m, lemma, meaning, ordinal=0, sense_key=None):
    lx = session.query(m.Lexeme).filter_by(language="fr", normalized=lemma, pos="noun").first()
    if lx is None:
        lx = m.Lexeme(language="fr", lemma=lemma, normalized=lemma, pos="noun", status="full")
        session.add(lx)
        session.flush()
    se = m.Sense(lexeme_id=lx.id, sense_key=sense_key or f"fr-{lemma}-{ordinal}", ordinal=ordinal)
    session.add(se)
    session.flush()
    if meaning:
        session.add(m.SenseTranslation(sense_id=se.id, native_language="en", text=meaning, source="kaikki"))
    session.flush()
    return se


@pytest.fixture
def reviewed_file(tmp_path, monkeypatch):
    path = tmp_path / "search_terms.json"

    def write(table):
        path.write_text(json.dumps({"_note": "test", "fr": table}), encoding="utf-8")
        search_terms._cache.update(mtime=None, data={})

    monkeypatch.setattr(search_terms, "FILE", path)
    search_terms._cache.update(mtime=None, data={})
    yield write
    search_terms._cache.update(mtime=None, data={})


def test_automatic_term_without_a_file(reviewed_file):
    assert search_terms.reviewed("fr", "chef", "noun", "k1") == (False, None)
    assert search_terms.sense_search_term("fr", "chef", "noun", "k1", "article, principal point") == "article"
    assert search_terms.sense_label_terms("fr", "chef", "noun", "k1", "article, principal point") == [
        "article", "principal point"]


def test_reviewed_none_and_reviewed_term(reviewed_file):
    reviewed_file({"chef|noun|k1": {"term": None, "auto": "article"},
                   "croix|noun|k2": {"term": "Cross", "auto": "representation"}})
    assert search_terms.reviewed("fr", "chef", "noun", "k1") == (True, None)
    assert search_terms.sense_search_term("fr", "chef", "noun", "k1", "article, principal point") is None
    assert search_terms.sense_label_terms("fr", "chef", "noun", "k1", "article, principal point") == []
    assert search_terms.sense_search_term("fr", "croix", "noun", "k2", "a representation of a cross") == "cross"
    assert search_terms.sense_label_terms("fr", "croix", "noun", "k2", "a representation of a cross") == ["cross"]
    # English headwords are never looked up; an unknown key keeps the automatic term.
    assert search_terms.reviewed("en", "chef", "noun", "k1") == (False, None)
    assert search_terms.sense_search_term("fr", "chef", "noun", "other", "article, principal point") == "article"


def test_file_edit_is_picked_up_without_restart(reviewed_file):
    reviewed_file({"chef|noun|k1": {"term": None}})
    assert search_terms.reviewed("fr", "chef", "noun", "k1") == (True, None)
    reviewed_file({"chef|noun|k1": {"term": "chief"}})
    assert search_terms.reviewed("fr", "chef", "noun", "k1") == (True, "chief")


def test_label_word_and_meaning_index_follow_the_review(session, reviewed_file):
    from app import models as m
    from app.meaning_labels import meaning_index
    chef1 = _fr_word(session, m, "chef", "article, principal point", ordinal=1, sense_key="k-chef1")
    croix1 = _fr_word(session, m, "croix", "a representation of a cross", ordinal=1, sense_key="k-croix1")
    chat = _fr_word(session, m, "chat", "cat (feline)", sense_key="k-chat")
    assert images.label_word(session, chef1.id, "fr", "chef") == "article"
    assert images.label_word(session, croix1.id, "fr", "croix") == "representation"
    reviewed_file({"chef|noun|k-chef1": {"term": None}, "croix|noun|k-croix1": {"term": "cross"}})
    assert images.label_word(session, chef1.id, "fr", "chef") is None
    assert images.label_word(session, croix1.id, "fr", "croix") == "cross"
    assert images.label_word(session, chat.id, "fr", "chat") == "cat"
    sense_label, by_meaning = meaning_index(session, "fr")
    assert chef1.id not in sense_label
    assert sense_label[croix1.id] == ["cross"]
    assert by_meaning[("cross", "noun")] == (croix1.lexeme_id, croix1.id)
    assert ("article", "noun") not in by_meaning
    assert ("representation", "noun") not in by_meaning
