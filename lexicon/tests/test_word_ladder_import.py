"""Card #1451: the importer shares a meaning group between its member words and is rerunnable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import import_word_ladder as iw


def test_senses_of_converts_prototype_candidates():
    e = {"word": "idea", "pos": "noun", "senses": [{"gloss": "g", "candidates": [{"w": "plan", "level": "A1"}]}]}
    (gloss, zh, ws), = list(iw.senses_of(e))
    assert gloss == "g" and ws[0]["cefr"] == "A1" and ws[0]["pos"] == "noun"


def test_norm_pos():
    assert iw.norm_pos("adj.") == "adj" and iw.norm_pos("Verb") == "verb"


# --- card #1468: checked_batch format (senses[].members + ssid), validation, no overlap merging ---
def _e(word, ssid, members, sid=1):
    return {"word": word, "pos": "verb", "senses": [{"ssid": ssid, "senseId": sid, "zh": "z", "members": [{"w": m, "pos": "verb", "zh": "x"} for m in members]}]}


def test_senses_of_reads_members():
    (gloss, zh, ws), = list(iw.senses_of(_e("like", "oewn-1-v", ["want", "wish"])))
    assert [x["w"] for x in ws] == ["want", "wish"] and zh == "z"


def test_validate_rejects_bad_files():
    assert iw.validate_entries([_e("like", "oewn-1-v", ["want"])]) == []
    assert iw.validate_entries([{"word": "x", "pos": "verb", "senses": [{"zh": "z", "members": [{"w": "a"}]}]}])  # no key
    assert iw.validate_entries([{"word": "x", "pos": "verb", "senses": [{"zh": "z"}]}])  # nothing
    assert iw.validate_entries([{"word": "x", "pos": "verb", "senses": [{"ssid": "s", "zh": "z", "members": [{"pos": "n"}]}]}])
    # hand-made sense (group / senseId only) and reference-only sense are fine
    assert iw.validate_entries([{"word": "x", "pos": "noun", "senses": [{"group": "g_new_x_1", "members": [{"w": "a"}]},
                                                                         {"senseId": 5, "members": [{"w": "b"}]}, {"ssid": "s"}]}]) == []
    assert iw.validate_entries([{"word": "", "senses": []}])
    assert iw.validate_entries([_e("a", "s", ["b"], 1), _e("c", "s", ["d"], 2)]) == []  # senseId is per source word


def test_same_members_different_ssid_stay_apart_and_rerun_is_idempotent():
    from app import db, models as m
    from sqlalchemy import select, func
    s = db.SessionLocal()
    try:
        st = {"groups": 0, "merged": 0, "members_new": 0, "members_upd": 0}
        a = _e("zzcard1468a", "zz-card1468-1", ["zzm1", "zzm2"], 9001)
        b = _e("zzcard1468a", "zz-card1468-2", ["zzm1", "zzm2"], 9002)  # identical members, other meaning
        for e in (a, b, a):
            iw.import_entry(s, e, "t", st)
        n = s.scalar(select(func.count()).select_from(m.LadderGroup).where(m.LadderGroup.ssid.like("zz-card1468-%")))
        assert n == 2 and st["groups"] == 2 and st["merged"] == 1
    finally:
        s.rollback()
        s.close()
