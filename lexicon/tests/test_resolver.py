"""The five merge strategies, deduplication and short-circuiting."""

from app.adapters import Candidate
from app.resolver import Resolver, status_of


def C(key, slot="", conf=1.0, source="x"):
    return Candidate("f", "en", {"v": key}, key, source=source, slot=slot, confidence=conf)


def keys(r):
    return [a.candidate.key for a in r.result()]


def test_first_valid_takes_first_source_and_stops_asking():
    r = Resolver("FIRST_VALID")
    assert r.wants_more()
    r.add(1000, "a", [])  # first source had nothing
    assert r.wants_more()
    r.add(2000, "b", [C("x"), C("y")])
    assert not r.wants_more()
    r.add(3000, "c", [C("z")])  # ignored even if called
    assert keys(r) == ["x", "y"]


def test_merge_unique_merges_in_order_without_duplicates():
    r = Resolver("MERGE_UNIQUE", limit=4)
    r.add(1000, "a", [C("x"), C("y")])
    assert r.wants_more()
    r.add(2000, "b", [C("y"), C("z"), C("w"), C("v")])
    assert keys(r) == ["x", "y", "z", "w"]  # y once, limit 4


def test_fill_missing_fills_each_slot_from_first_source_that_has_it():
    r = Resolver("FILL_MISSING", expected={"s1", "s2", "s3"})
    r.add(1000, "kaikki", [C("k1", "s1"), C("k1b", "s1")])
    assert r.missing() == {"s2", "s3"}
    r.add(2000, "oewn", [C("o1", "s1"), C("o2", "s2")])  # s1 already filled
    assert r.missing() == {"s3"}
    assert r.wants_more()
    r.add(3000, "ai", [C("a3", "s3")])
    assert not r.wants_more()
    assert keys(r) == ["k1", "k1b", "o2", "a3"]


def test_fill_missing_ignores_items_for_unknown_slots():
    r = Resolver("FILL_MISSING", expected={"s1"})
    r.add(1000, "a", [C("x", "other")])
    assert keys(r) == [] and r.missing() == {"s1"}


def test_fill_missing_without_known_slots_skips_ai_once_something_was_found():
    r = Resolver("FILL_MISSING")
    r.add(1000, "a", [C("x", "noun")])
    assert r.wants_more("dump")
    assert not r.wants_more("ai")


def test_best_score_keeps_highest_confidence_per_slot_ties_to_earlier():
    r = Resolver("BEST_SCORE")
    r.add(1000, "a", [C("a1", "s1", 0.6), C("a2", "s2", 0.9)])
    r.add(2000, "b", [C("b1", "s1", 0.8), C("b2", "s2", 0.9)])
    got = {a.candidate.slot: a.candidate.key for a in r.result()}
    assert got == {"s1": "b1", "s2": "a2"}


def test_append_limited_stops_at_limit():
    r = Resolver("APPEND_LIMITED", limit=3)
    r.add(1000, "a", [C("x"), C("y")])
    assert r.wants_more()
    r.add(2000, "b", [C("y"), C("z"), C("w")])
    assert not r.wants_more()
    assert keys(r) == ["x", "y", "z"]


def test_status():
    assert status_of([], set(), None, errors=2, asked=2) == "failed"
    assert status_of([], set(), None, errors=1, asked=2) == "missing"
    assert status_of([1], {"s2"}, {"s1", "s2"}, 0, 1) == "partial"
    assert status_of([1], set(), {"s1"}, 0, 1) == "complete"


def test_fill_missing_limit_keeps_one_item_per_slot_first():
    r = Resolver("FILL_MISSING", limit=3, expected={"noun", "verb"})
    r.add(1000, "kaikki", [C("n1", "noun"), C("n2", "noun"), C("n3", "noun"), C("v1", "verb")])
    assert keys(r) == ["n1", "n2", "v1"]


def test_per_level_slots_keep_three_to_five_and_ai_only_fills_short_levels():
    r = Resolver("APPEND_LIMITED", limit=30, expected={"A1", "A2", "C2"}, per_slot=(3, 5))
    r.add(1000, "tatoeba", [C(f"a{i}", "A1") for i in range(7)] + [C("b1", "A2")])
    assert keys(r).count("a0") == 1 and len([k for k in keys(r) if k.startswith("a")]) == 5
    assert r.missing() == {"A2", "C2"}
    assert r.wants_more("api") and r.wants_more("ai")
    r.add(2000, "kaikki", [C("b2", "A2"), C("b3", "A2"), C("c1", "C2"), C("c2", "C2"), C("c3", "C2")])
    assert r.missing() == set()
    assert not r.wants_more("ai"), "every level has three: no AI"


def test_a_second_recording_source_is_asked_only_for_the_missing_accent():
    from app.adapters import Candidate
    r = Resolver("MERGE_UNIQUE", 6, {"UK", "US"}, per_slot=(1, 1), only_missing=True)
    assert r.wants_more()
    r.add(1, "kaikki", [Candidate("audio", "en", {"url": u}, u, slot=s) for u, s in
                        (("a", "US"), ("b", "US"), ("c", "AU"))])
    assert [a.candidate.slot for a in r.adopted] == ["US", "AU"]  # one per accent
    assert r.missing() == {"UK"} and r.wants_more()
    r.add(2, "wikimedia_commons", [Candidate("audio", "en", {"url": "d"}, "d", slot="UK")])
    assert not r.missing() and not r.wants_more()
