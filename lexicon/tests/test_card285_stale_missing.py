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
    # 問題回報 #210: a complete gloss whose word gained a sense is partial again
    ctx.resolved["definition"].append({"pos": "noun", "gloss": "A city.", "sense_key": "s3"})
    assert pipeline.stale_missing("native_definition", ctx, "complete", [], items) \
        == ("partial", ["s3"], [])


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


def test_fill_missing_keeps_accepted_slot():
    """問題回報 #210: re-resolving must not drop an obscure sense's existing
    Chinese just because that sense is no longer asked for."""
    from types import SimpleNamespace
    from app.resolver import Resolver
    res = Resolver("FILL_MISSING", None, {"s1"}, accept={"s1", "s2"})
    c1 = SimpleNamespace(slot="s1", key="k1", valid=True, confidence=1)
    c2 = SimpleNamespace(slot="s2", key="k2", valid=True, confidence=1)
    c3 = SimpleNamespace(slot="s9", key="k9", valid=True, confidence=1)
    res.add(0, "ai_translate", [c1, c2, c3])
    assert sorted(a.candidate.slot for a in res.adopted) == ["s1", "s2"]
    assert res.missing() == set()


def test_failed_ai_retry_keeps_stored_candidates(session, fakes):
    """Card #511 (問題回報 #210): Qwen paused (502) during a re-resolution
    used to delete every AI Chinese the word had; they must survive."""
    apple_data(fakes)
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")
    ai_rows = lambda: {r.slot for r in session.execute(select(m.FieldCandidate).where(
        m.FieldCandidate.lemma == "apple", m.FieldCandidate.field == "native_definition",
        m.FieldCandidate.source == "ai_translate")).scalars()}
    assert ai_rows() == {"s2"}
    # the word gains a sense (a real gap → AI is asked again), and AI is down
    fakes["kaikki"].data["definition"].append(
        ({"pos": "noun", "gloss": "A city.", "sense_key": "s3", "gloss_language": "en"}, "s3", "noun"))
    pipeline.process_word(session, "en", "zh-TW", "apple", ["definition"], "force_refresh")
    fakes["ai_translate"].fail = {"*"}
    for _ in range(2):  # the second run starts from a `failed` lookup row
        calls = len(fakes["ai_translate"].calls)
        pipeline.process_word(session, "en", "zh-TW", "apple", None, "reresolve")
        assert len(fakes["ai_translate"].calls) > calls
        session.expire_all()
        assert ai_rows() == {"s2"}
        nd = _fv(session, "native_definition")
        assert {i.get("sense_key") for i in nd.items} >= {"s1", "s2"}
    # AI back: only the gap is asked for, the kept s2 is not re-translated
    fakes["ai_translate"].fail = set()
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "reresolve")
    session.expire_all()
    assert ai_rows() == {"s2", "s3"}
