"""問題回報 #288 (card #285): a partial run must not leave dependents' ``missing``
lists naming slots the word no longer has."""

from sqlalchemy import select

from app import pipeline
from app import models as m
from app.adapters.base import Context
from conftest import apple_data


def _fv(session, field):
    return session.execute(select(m.FieldValue).where(
        m.FieldValue.lemma == "apple", m.FieldValue.field == field)).scalar_one()


def test_stale_missing_rule():
    ctx = Context("en", "zh-TW", "apple", "apple")
    ctx.resolved["definition"] = [{"pos": "noun", "gloss": "A fruit.", "sense_key": "s1"},
                                  {"pos": "noun", "gloss": "A tree.", "sense_key": "s2"}]
    items = [{"slot": "s1", "sense_key": "s1", "text": "蘋果"}]
    # a stale key is dropped; s2 is a real gap and stays
    assert pipeline.stale_missing("native_definition", ctx, "partial", ["old1", "s2"], items) \
        == ("partial", ["s2"], ["old1"])
    # every listed key stale, every expected sense filled → complete
    items.append({"slot": "s2", "sense_key": "s2", "text": "蘋果樹"})
    assert pipeline.stale_missing("native_definition", ctx, "partial", ["old1"], items) \
        == ("complete", [], ["old1"])
    # nothing stale → untouched; per-level fields are never touched
    assert pipeline.stale_missing("native_definition", ctx, "partial", ["s2"], items[:1]) is None
    assert pipeline.stale_missing("example_sentences", ctx, "partial", ["Z9"], []) is None
    assert pipeline.stale_missing("native_definition", ctx, "complete", ["old1"], items) is None


def test_partial_run_refreshes_dependents(session, fakes):
    apple_data(fakes)
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")
    nd = _fv(session, "native_definition")
    assert nd.status == "complete"
    # a sense that was re-keyed since (問題回報 #288): the old key lingers in missing
    nd.status, nd.missing = "partial", ["deadbeef0000"]
    et = _fv(session, "example_translation")
    assert et.missing == ["ex2"]  # a real gap must survive the refresh
    et.missing = ["ex2", "deadbeef0001"]
    session.flush()

    pipeline.process_word(session, "en", "zh-TW", "apple", ["definition"], "fill_missing")

    session.expire_all()
    nd = _fv(session, "native_definition")
    assert (nd.status, nd.missing) == ("complete", [])
    et = _fv(session, "example_translation")
    # example_translation does not depend on definition: left as it was
    assert et.missing == ["ex2", "deadbeef0001"]

    pipeline.process_word(session, "en", "zh-TW", "apple", ["example_sentences"], "fill_missing")
    session.expire_all()
    et = _fv(session, "example_translation")
    assert (et.status, et.missing) == ("partial", ["ex2"])
