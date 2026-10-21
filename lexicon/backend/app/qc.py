"""Quality contracts over an app pack (QUALITY_SYSTEM_DESIGN.md P1).

Pure functions over the pack dict that /api/lexicon serves, so the same
checks run in tests, in the pack build, and in the guard (before/after
snapshots). Violations are grouped by rule, never per word.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from .adapters.base import ARPABET
from .text import native_latin_issue

LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
ESTIMATE_SOURCES = {"frequency_estimate", "estimate", "local_calc", "ai_reviewed"}
GOLDEN = Path(__file__).resolve().parents[2] / "quality" / "golden"


def _is_arpabet(value: str) -> bool:
    """A pronunciation value that is bare ARPAbet (e.g. 'S T IY1 P'), not
    IPA — issue #188: this must never end up under kind='ipa'."""
    v = (value or "").strip("/[] ")
    return bool(v) and bool(ARPABET.match(v))


def _index(pack: dict):
    lexemes = pack.get("lexemes") or []
    by_id = {lx["id"]: lx for lx in lexemes}
    redirects = {int(k): int(v) for k, v in (pack.get("redirects") or {}).items()}
    for lx in lexemes:
        if lx.get("redirect_to"):
            redirects[lx["id"]] = int(lx["redirect_to"])
    return by_id, redirects


def _has_zh(sense: dict | None) -> bool:
    return bool(sense and (sense.get("native") or "").strip())


def main_sense(lx: dict) -> dict | None:
    """The sense an app card shows first: the first non-low sense."""
    senses = lx.get("senses") or []
    return next((s for s in senses if s.get("priority") != "low"), senses[0] if senses else None)


def strip_stubs(pack: dict) -> dict:
    """Decision 1: the pack carries only full entries and redirect pointers
    whose target is a full entry. Relations pointing at a removed stub keep
    the word text but drop the dangling lexeme_id. Idempotent."""
    by_id, redirects = _index(pack)
    full_ids = {lx["id"] for lx in pack["lexemes"] if lx.get("status") == "full"}
    keep = []
    for lx in pack["lexemes"]:
        if lx.get("status") == "full":
            # A full entry never points at an entry that left the pack.
            if lx.get("redirect_to") and int(lx["redirect_to"]) not in full_ids:
                lx.pop("redirect_to", None)
            for r in lx.get("relations") or []:
                if r.get("lexeme_id") is not None and r["lexeme_id"] not in full_ids:
                    r.pop("lexeme_id", None)
            keep.append(lx)
        elif lx.get("redirect_to") and int(lx["redirect_to"]) in full_ids:
            keep.append({k: lx[k] for k in lx
                         if k in ("id", "lemma", "normalized", "pos", "status",
                                  "redirect_to", "card", "cefr", "cefr_source")})
    pack["lexemes"] = keep
    pack["redirects"] = {str(k): v for k, v in redirects.items() if v in full_ids}
    return {"kept_full": len(full_ids),
            "kept_pointers": sum(1 for lx in keep if lx.get("redirect_to")),
            "dropped": len(by_id) - len(keep)}



def validate(pack: dict) -> dict[str, list]:
    """Contract violations: rule -> list of evidence (ids)."""
    by_id, redirects = _index(pack)
    v: dict[str, list] = defaultdict(list)
    # Latin letters are residue only in a Chinese pack; a French pack's
    # native text is English (card #325).
    zh_native = str(pack.get("native_language") or "zh-TW").startswith("zh")
    full = [lx for lx in pack.get("lexemes") or [] if lx.get("status") == "full"]
    for lx in pack.get("lexemes") or []:
        if lx.get("status") == "stub" and not lx.get("redirect_to"):
            v["entry.stub_in_pack"].append(lx["id"])
        if lx.get("status") == "stub" and lx.get("cefr"):
            v["entry.stub_has_cefr"].append(lx["id"])
    for lx in full:
        ms = main_sense(lx)
        if not lx.get("senses"):
            v["entry.full_without_senses"].append(lx["id"])
        elif not _has_zh(ms):
            v["sense.main_without_chinese"].append(lx["id"])
        elif ms.get("native_ai"):
            v["sense.main_is_ai"].append(lx["id"])
        # Every sense, not only the main one (問題回報 #187: a word's later
        # senses carried no native meaning, or one leaking English/residue —
        # table「背gammon遊戲」, ship「船、船舶、CP」).
        for sense in lx.get("senses") or []:
            if not _has_zh(sense):
                v["sense.native_empty"].append(lx["id"])
                continue
            latin = native_latin_issue(sense.get("native")) if zh_native else None
            if latin:
                v["sense.native_has_latin"].append([lx["id"], latin])
        if lx.get("pos") in (None, "", "unknown"):
            v["entry.pos_unknown"].append(lx["id"])
        prons = lx.get("pronunciations") or []
        ipa_values = [p.get("value") for p in prons if p.get("kind") == "ipa" and p.get("value")]
        if any(_is_arpabet(val) for val in ipa_values):
            v["pronunciation.ipa_is_arpabet"].append(lx["id"])
        if not ipa_values:
            v["entry.full_without_ipa"].append(lx["id"])
        if not any(p.get("kind") == "audio" for p in prons):
            v["entry.full_without_audio"].append(lx["id"])
        if lx.get("cefr") and lx.get("cefr_source") in ESTIMATE_SOURCES:
            # Flagged via cefr_source (app reads it); nothing else required.
            pass
        for r in lx.get("relations") or []:
            rid = r.get("lexeme_id")
            if rid is not None and rid not in by_id and rid not in redirects:
                v["relation.dangling_link"].append([lx["id"], rid])
    for rid, to in redirects.items():
        tgt = by_id.get(to)
        if not tgt or tgt.get("status") != "full":
            v["redirect.target_not_full"].append([rid, to])
    for im in pack.get("catalog_images") or []:
        tags = im.get("tags") or []
        if len(tags) < 3:
            v["photo.fewer_than_3_tags"].append(im["id"])
        for t in tags:
            lid = t.get("lexeme_id")
            lx = by_id.get(lid)
            if lid in redirects:
                v["photo_tag.on_redirect"].append([im["id"], lid])
                lx = by_id.get(redirects[lid])
            if not lx or lx.get("status") != "full":
                v["photo_tag.lexeme_not_full"].append([im["id"], lid])
                continue
            sense = next((s for s in lx.get("senses") or [] if s.get("id") == t.get("sense_id")), None)
            if sense is None:
                v["photo_tag.sense_missing"].append([im["id"], lid])
            elif not _has_zh(sense):
                v["photo_tag.sense_without_chinese"].append([im["id"], lid])
            elif sense.get("priority") == "low":
                v["photo_tag.sense_low_priority"].append([im["id"], lid])
            if (t.get("cefr") or None) != (lx.get("cefr") or None):
                v["photo_tag.level_differs_from_card"].append([im["id"], lid])
        for lb in im.get("labels") or []:
            lx = by_id.get(redirects.get(lb.get("lexeme_id"), lb.get("lexeme_id")))
            if lx and (lb.get("cefr") or None) != (lx.get("cefr") or None):
                v["photo_label.level_differs_from_card"].append([im["id"], lb.get("lexeme_id")])
    return dict(v)


CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


def _levels_under(tags: list | None, need: int) -> list[str]:
    """CEFR levels that have fewer than `need` tags on one picture (card #448)."""
    counts = {level: 0 for level in CEFR_LEVELS}
    for t in tags or []:
        if t.get("cefr") in counts:
            counts[t["cefr"]] += 1
    return [level for level in CEFR_LEVELS if counts[level] < need]


def metrics(pack: dict, violations: dict | None = None) -> dict:
    violations = validate(pack) if violations is None else violations
    lexemes = pack.get("lexemes") or []
    full = [lx for lx in lexemes if lx.get("status") == "full"]
    images = pack.get("catalog_images") or []
    tags = [t for im in images for t in im.get("tags") or []]
    out = {
        "lexemes_in_pack": len(lexemes),
        "full": len(full),
        "stub_entries": sum(1 for lx in lexemes if lx.get("status") == "stub" and not lx.get("redirect_to")),
        "pointer_entries": sum(1 for lx in lexemes if lx.get("redirect_to")),
        "full_cefr_estimated": sum(1 for lx in full if lx.get("cefr") and lx.get("cefr_source") in ESTIMATE_SOURCES),
        "catalog_images": len(images),
        "photo_tags": len(tags),
        # Card #448 standard (5 per CEFR level). Informational only: not a v.* rule,
        # so compare() does not gate on it until the owner decides to switch.
        "photos_level_under_5": sum(1 for im in images if _levels_under(im.get("tags"), 5)),
        "pack_mb": round(len(json.dumps(pack, ensure_ascii=False).encode()) / 1e6, 1),
    }
    out.update({f"v.{k}": len(x) for k, x in sorted(violations.items())})
    return out


# ---- golden set ----------------------------------------------------------

def load_golden(name: str = "v1") -> dict:
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))


def evaluate_golden(pack: dict, golden: dict) -> dict:
    """Per-check pass counts. Photo checks: every tag on a full entry with a
    Chinese, non-low sense, tag level = card level, plus explicit expected
    Chinese for known photos. Word checks: present as full entry, CEFR equals
    the CEFR-J/Octanove list, main sense has Chinese."""
    by_id, redirects = _index(pack)
    by_word = defaultdict(list)
    for lx in pack.get("lexemes") or []:
        if lx.get("status") == "full":
            by_word[lx["normalized"]].append(lx)
    images = {im["id"]: im for im in pack.get("catalog_images") or []}
    res: Counter = Counter()
    fails: dict[str, list] = defaultdict(list)

    def check(name, ok, evidence):
        res[name + ".total"] += 1
        if ok:
            res[name + ".pass"] += 1
        else:
            fails[name].append(evidence)

    for p in golden.get("photos", []):
        im = images.get(p["id"])
        check("photo.present", im is not None, p["id"])
        if im is None:
            continue
        shown = {}
        for t in im.get("tags") or []:
            lx = by_id.get(redirects.get(t.get("lexeme_id"), t.get("lexeme_id")))
            sense = next((s for s in (lx or {}).get("senses") or [] if s.get("id") == t.get("sense_id")), None)
            ok = bool(lx and lx.get("status") == "full" and _has_zh(sense) and sense.get("priority") != "low")
            check("photo.tag_valid", ok, [p["id"], t.get("lexeme_id")])
            check("photo.tag_level_is_card_level", lx is not None and t.get("cefr") == lx.get("cefr"),
                  [p["id"], (lx or {}).get("lemma")])
            if lx:
                shown[lx["normalized"]] = (sense or {}).get("native") or ""
        for word, zh in (p.get("expect") or {}).items():
            check("photo.expected_sense", zh in shown.get(word, ""), [p["id"], word, shown.get(word)])
        check("photo.min_tags", len(im.get("tags") or []) >= p.get("min_tags", 3), p["id"])
    for w in golden.get("words", []):
        entries = by_word.get(w["word"], [])
        check("word.present_full", bool(entries), w["word"])
        if not entries:
            continue
        # golden pos labels come from cefr_en.json ("adj.", "adv.", with a
        # trailing period); pack lexeme pos never has one ("adj", "adv") -
        # strip it so homographs (e.g. calm verb/adj/noun) pick the right
        # entry instead of silently falling back to entries[0].
        want_pos = (w.get("pos") or "").rstrip(".")
        lx = next((e for e in entries if e.get("pos") == want_pos), entries[0])
        check("word.cefr_matches_list", lx.get("cefr") == w["cefr"], [w["word"], lx.get("cefr"), w["cefr"]])
        check("word.main_sense_chinese", _has_zh(main_sense(lx)), w["word"])
    names = {k.rsplit(".", 1)[0] for k in res}
    summary = {n: round(res[n + ".pass"] / res[n + ".total"], 4) for n in sorted(names)}
    return {"rates": summary, "counts": dict(res), "fails": {k: v[:30] for k, v in fails.items()}}


# ---- guard -----------------------------------------------------------------

# Metrics where a higher number is worse (violations, stubs). Others are info.
def compare(before: dict, after: dict, tolerance: int = 0) -> list[str]:
    """Regressions between two snapshots: any violation count that grew, or
    any golden pass rate that fell."""
    bad = []
    bm, am = before["metrics"], after["metrics"]
    for k in sorted(set(bm) | set(am)):
        if not k.startswith("v.") or am.get(k, 0) <= bm.get(k, 0) + tolerance:
            continue
        # Per-entry rules: imports keep adding entries while a run is in
        # flight, so only entries that existed before count (same population).
        rule = k[2:]
        ids_b, ids_a = before.get("entry_ids"), after.get("entry_ids")
        if ids_b is not None and ids_a is not None and rule in (before.get("v_ids") or {}):
            base = set(ids_b)
            nb = len(set(map(_key, before["v_ids"].get(rule, []))) & base)
            na = len(set(map(_key, (after.get("v_ids") or {}).get(rule, []))) & base)
            if na <= nb + tolerance:
                continue
            bad.append(f"{k}: {nb} -> {na} (same entries)")
            continue
        if k.startswith(("v.sense.", "v.entry.")) and k != "v.entry.stub_in_pack":
            rb = bm.get(k, 0) / max(1, bm.get("full", 1))
            ra = am.get(k, 0) / max(1, am.get("full", 1))
            if ra <= rb + 1e-9:
                continue
        bad.append(f"{k}: {bm.get(k, 0)} -> {am.get(k, 0)}")
    br, ar = before["golden"]["rates"], after["golden"]["rates"]
    for k in sorted(set(br) | set(ar)):
        if ar.get(k, 0.0) + 1e-9 < br.get(k, 0.0):
            bad.append(f"golden {k}: {br.get(k)} -> {ar.get(k)}")
    return bad


def _key(x):
    """Entry id of a violation item (an id, or [entry_id, ...])."""
    return x[0] if isinstance(x, list) else x


def snapshot(pack: dict, golden: dict | None = None) -> dict:
    v = validate(pack)
    per_entry = {k: x for k, x in v.items()
                 if k.startswith(("sense.", "entry.", "pronunciation.")) and k != "entry.stub_in_pack"}
    return {"metrics": metrics(pack, v), "golden": evaluate_golden(pack, golden or load_golden()),
            "samples": {k: x[:10] for k, x in v.items()},
            "entry_ids": [lx["id"] for lx in pack.get("lexemes") or [] if lx.get("status") == "full"],
            "v_ids": per_entry}