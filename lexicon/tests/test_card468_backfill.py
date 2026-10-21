"""問題回報 #462 (card #468): a headword's relation-word Chinese that stayed
in ``missing`` because the word was no entry yet (cold → could) is filled
once that word is materialized as a full entry — field_values and
relation_translations alike, from the lexicon, without AI."""

from __future__ import annotations

from sqlalchemy import select

from app import models as m
from app import relation_backfill as rb
from app.materialize import materialize


def _seed(s, word, poses, **extra):
    s.add(m.FieldValue(target_language="en", lemma=word, native_language="zh-TW", field="pos",
                       status="complete", items=[{"key": p, "pos": p} for p in poses]))
    s.add(m.FieldValue(target_language="en", lemma=word, native_language="zh-TW", field="definition",
                       status="complete", items=[{"key": f"{word}-{p}", "sense_key": f"{word}-{p}",
                                                  "pos": p, "gloss": f"{word} as {p}"} for p in poses]))
    for field, items in extra.items():
        s.add(m.FieldValue(target_language="en", lemma=word, native_language="zh-TW", field=field,
                           status="complete", items=items))
    s.flush()


def _fv(s, lemma, field):
    return s.execute(select(m.FieldValue).where(
        m.FieldValue.target_language == "en", m.FieldValue.lemma == lemma,
        m.FieldValue.field == field)).scalar_one()


def _setup(session):
    # cold's related words were resolved while 「could」 was no entry: its slot is missing.
    _seed(session, "cold", ["adj"], related=[{"key": "could", "slot": "could", "word": "could",
                                              "pos": "verb", "source": "datamuse"}])
    session.add(m.FieldValue(target_language="en", lemma="cold", native_language="zh-TW",
                             field="related_native", status="missing", items=[], missing=["could"]))
    session.flush()
    materialize(session, "en", "cold")  # could is a stub, the relation row exists
    rel = session.execute(select(m.LexemeRelation).where(
        m.LexemeRelation.relation == "related")).scalar_one()
    assert rel.target_word == "could"
    assert session.execute(select(m.RelationTranslation)).first() is None
    return rel


def test_word_import_fills_waiting_relation_slots(session):
    rel = _setup(session)
    assert rb.backfill_for_word(session, "en", "could") == []  # not an entry yet: nothing
    _seed(session, "could", ["verb"], native_definition=[
        {"key": "could-verb", "sense_key": "could-verb", "slot": "could-verb", "text": "能",
         "source": "kaikki"}])
    materialize(session, "en", "could")
    added = rb.backfill_for_word(session, "en", "could")
    assert [(a["head"], a["word"], a["text"]) for a in added] == [("cold", "could", "能")]
    fv = _fv(session, "cold", "related_native")
    assert fv.status == "complete" and fv.missing == []
    assert [(i["word"], i["text"], i["source"]) for i in fv.items] == [("could", "能", "lexicon")]
    rt = session.execute(select(m.RelationTranslation).where(
        m.RelationTranslation.relation_id == rel.id)).scalar_one()
    assert (rt.text, rt.native_language, rt.is_ai) == ("能", "zh-TW", False)
    # a second run has nothing left to fill
    assert rb.backfill_for_word(session, "en", "could") == []
    assert rb.backfill_all(session, "en") == []


def test_sweep_fills_every_waiting_slot_and_backs_up(session):
    rel = _setup(session)
    _seed(session, "could", ["verb"], native_definition=[
        {"key": "could-verb", "sense_key": "could-verb", "slot": "could-verb", "text": "能",
         "source": "kaikki"}])
    materialize(session, "en", "could")
    backup = {}
    assert len(rb.backfill_all(session, "en", backup, write=False)) == 1
    assert backup == {} and _fv(session, "cold", "related_native").missing == ["could"]
    added = rb.backfill_all(session, "en", backup)
    assert len(added) == 1 and len(backup["field_values"]) == 1
    assert backup["field_values"][0]["missing"] == ["could"]
    assert len(backup["inserted_rt"]) == 1
    assert session.get(m.RelationTranslation, backup["inserted_rt"][0]).relation_id == rel.id


def test_sync_adds_translation_rows_the_field_value_already_has(session):
    rel = _setup(session)
    fv = _fv(session, "cold", "related_native")
    fv.items, fv.status, fv.missing = [{"key": "could", "slot": "could", "word": "could",
                                        "text": "能", "source": "ecdict"}], "complete", []
    session.flush()
    found = rb.sync_relation_translations(session, "en", "zh-TW", write=False)
    assert [(f["head"], f["word"], f["text"]) for f in found] == [("cold", "could", "能")]
    assert session.execute(select(m.RelationTranslation)).first() is None
    backup = {}
    rb.sync_relation_translations(session, "en", "zh-TW", backup)
    rt = session.execute(select(m.RelationTranslation).where(
        m.RelationTranslation.relation_id == rel.id)).scalar_one()
    assert (rt.text, rt.source, rt.is_ai) == ("能", "ecdict", False)
    assert backup["inserted_rt"] == [rt.id]
    assert rb.sync_relation_translations(session, "en", "zh-TW") == []


def test_sync_skips_a_meaning_copied_from_the_headword(session):
    _setup(session)
    session.add(m.FieldValue(target_language="en", lemma="cold", native_language="zh-TW",
                             field="native_definition", status="complete",
                             items=[{"sense_key": "cold-adj", "text": "冷的", "source": "ecdict"}]))
    fv = _fv(session, "cold", "related_native")
    fv.items, fv.status, fv.missing = [{"key": "could", "slot": "could", "word": "could",
                                        "text": "冷的", "source": "ai_translate", "ai": True}], \
        "complete", []
    session.flush()
    assert rb.sync_relation_translations(session, "en", "zh-TW") == []
    assert session.execute(select(m.RelationTranslation)).first() is None
