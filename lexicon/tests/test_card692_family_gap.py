"""Card #692 (問題回報 #556): the word-family ceiling holds only within FAMILY_GAP levels."""
from app.adapters.local import FAMILY_GAP, family_limited

A1, A2, B1, C1, C2 = 0, 1, 2, 4, 5


def test_gap_is_two_levels():
    assert FAMILY_GAP == 2


def test_within_gap_the_ceiling_applies():
    # within the gap (B2 is 1 above an A2 ceiling, B1 is 2 above A1): the ceiling wins
    assert family_limited("B2", 1) == "A2"
    assert family_limited("B1", 0) == "A1"


def test_beyond_gap_the_frequency_estimate_decides():
    # dogged: dog A1 ceiling, frequency C1 (gap 4) -> C1, not A1
    assert family_limited("C1", 0) == "C1"
    assert family_limited("B2", 0) == "B2"  # gap 3 is beyond the gap


def test_no_ceiling_keeps_frequency():
    assert family_limited("C2", None) == "C2"


def test_owner_kept_rare_rule_levels_beat_the_share_estimate(monkeypatch):
    """Problem report #868: the 8 rare parts of speech keep the rule level (B2)
    even though the share-based estimate is C2; other rare usages keep the #397 rule."""
    from app import quality
    keep = {7592, 11001, 14854, 24966, 30710, 41274, 49700, 43229}
    real_load = quality.load_json
    monkeypatch.setattr(quality, "load_json",
                        lambda name: {"keep_rule_level": sorted(keep)} if name == "rare_rule_keep.json"
                        else real_load(name))
    lxs = [{"id": 7592, "cefr": "C2", "rare_usage": True}, {"id": 99, "cefr": "C2", "rare_usage": True}]
    quality.apply_decisions({"lexemes": lxs}, {"set_cefr": {"7592": "B2", "99": "B2"}})
    assert lxs[0]["cefr"] == "B2" and lxs[0]["cefr_source"] == "quality_rule"
    assert lxs[1]["cefr"] == "C2"
