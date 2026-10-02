"""Field-level policies: independence, gapped positions, unset fields,
copy with confirmation, user overrides."""

import pytest
from sqlalchemy import select

from app import models as m
from app import pipeline, policies
from app.policies import assign_positions
from conftest import apple_data


def test_assign_positions_rewrites_as_few_rows_as_possible():
    old = {"a": 1000, "b": 2000, "c": 3000}
    new = assign_positions(old, ["b", "a", "c"])
    assert [k for k, _ in sorted(new.items(), key=lambda kv: kv[1])] == ["b", "a", "c"]
    assert sum(new[k] != old[k] for k in old) == 1  # one row moved into a gap
    assert assign_positions(old, ["a", "b", "c", "d"])["d"] > 3000
    tight = assign_positions({"a": 1, "b": 2}, ["b", "a"])  # no gap left → renumber
    assert tight["b"] < tight["a"]


def _order(session, field, t="en", n="zh-TW"):
    return [s["source"] for s in policies.get(session, t, n, field)["steps"]]


def test_changing_one_field_leaves_every_other_field_alone(session):
    before = {p.field: p.version for p in session.execute(select(m.SourcePolicy).where(
        m.SourcePolicy.target_language == "en", m.SourcePolicy.native_language == "zh-TW")).scalars()}
    p = policies.get(session, "en", "zh-TW", "example_sentences")
    steps = sorted(p["steps"], key=lambda s: s["source"] != "kaikki")  # Kaikki first
    policies.put(session, "en", "zh-TW", "example_sentences",
                 {"strategy": p["strategy"], "max_items": p["max_items"], "steps": steps})
    session.commit()
    assert _order(session, "example_sentences") == ["kaikki", "tatoeba", "oewn", "ai_translate"]
    assert _order(session, "example_translation") == ["tatoeba", "ai_translate"]
    after = {p.field: p.version for p in session.execute(select(m.SourcePolicy).where(
        m.SourcePolicy.target_language == "en", m.SourcePolicy.native_language == "zh-TW")).scalars()}
    assert {f for f in after if after[f] != before[f]} == {"example_sentences"}
    # the other direction is untouched too
    assert _order(session, "example_sentences", "en", "fr") == ["tatoeba", "kaikki", "oewn",
                                                                 "ai_translate"]


def test_unsupported_source_is_rejected(session):
    with pytest.raises(policies.PolicyError, match="不提供"):
        policies.put(session, "en", "zh-TW", "verb_past",
                     {"strategy": "FIRST_VALID", "steps": [{"source": "cmudict"}]})


def test_stale_version_is_rejected(session):
    p = policies.get(session, "en", "zh-TW", "ipa")
    with pytest.raises(policies.PolicyError, match="其他人更新"):
        policies.put(session, "en", "zh-TW", "ipa", {"strategy": "FIRST_VALID", "steps": []},
                     expected_version=p["version"] + 5)


def test_copy_needs_confirmation_and_drops_unsupported_sources(session):
    plan = policies.copy_to(session, "en", "zh-TW", "synonyms", ["antonyms", "verb_past"], False)
    assert plan["confirmed"] is False
    vp = next(x for x in plan["plan"] if x["field"] == "verb_past")
    assert {d["source"] for d in vp["dropped"]} == {"oewn", "datamuse", "ai_translate"}
    assert _order(session, "verb_past") == ["kaikki"]  # nothing applied yet
    policies.copy_to(session, "en", "zh-TW", "synonyms", ["antonyms"], True)
    # AI only fills synonyms and related words, so antonyms don't take it.
    assert _order(session, "antonyms") == [x for x in _order(session, "synonyms")
                                           if x != "ai_translate"]


def test_unset_field_calls_no_source(session, fakes):
    apple_data(fakes)
    policies.put(session, "en", "zh-TW", "ipa", {"strategy": "FIRST_VALID", "steps": []})
    reports = pipeline.process_word(session, "en", "zh-TW", "apple", ["ipa"], "fill_missing",
                                    materialize_after=False)
    assert reports[-1].status == "unset"
    assert not any(f == "ipa" for a in fakes.values() for _, f in a.calls)


def test_disabling_first_source_starts_from_the_second(session, fakes):
    apple_data(fakes)
    p = policies.get(session, "en", "zh-TW", "synonyms")
    steps = [dict(s, enabled=s["source"] != "oewn") for s in p["steps"]]
    policies.put(session, "en", "zh-TW", "synonyms", {"strategy": p["strategy"],
                                                      "max_items": p["max_items"], "steps": steps})
    r = pipeline.process_word(session, "en", "zh-TW", "apple", ["synonyms"], "fill_missing",
                              materialize_after=False)[-1]
    assert [i["source"] for i in r.items] == ["kaikki"]
    assert ("apple", "synonyms") not in fakes["oewn"].calls


def test_user_override_wins_over_reimport(session, fakes):
    apple_data(fakes)
    session.add(m.UserOverride(target_language="en", native_language="zh-TW", lemma="apple",
                               field="ipa", items=[{"ipa": "/ˈæpl̩/", "source": "user",
                                                    "key": "u"}]))
    session.flush()
    for mode in ("fill_missing", "force_refresh", "reresolve"):
        r = pipeline.process_word(session, "en", "zh-TW", "apple", ["ipa"], mode,
                                  materialize_after=False)[-1]
        assert r.status == "user_override" and r.items[0]["ipa"] == "/ˈæpl̩/"
