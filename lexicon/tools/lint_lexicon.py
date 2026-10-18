"""Lint the whole lexicon against docs/LEXICON_QUALITY_RULES.md.

    python lexicon/tools/lint_lexicon.py [pack.json | http://127.0.0.1:8123/api/lexicon]

Writes exports/quality/lexicon-lint-<date>.csv (one row per rule hit) and
quality/entry_flags.json ("word|pos" -> {rule: detail}); app_pack attaches
those flags to the entries as quality_flags. Nothing is deleted."""

from __future__ import annotations

import collections
import csv
import datetime as dt
import hashlib
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME / "backend"))
from app import quality  # noqa: E402


def load_pack(src: str) -> dict:
    if src.startswith("http"):
        with urllib.request.urlopen(src, timeout=600) as r:
            return json.loads(r.read())
    return json.loads(Path(src).read_text(encoding="utf-8"))


def main(argv: list[str]) -> dict:
    src = argv[0] if argv else "http://127.0.0.1:8123/api/lexicon"
    pack = load_pack(src)
    cefr_words = json.loads((HOME.parent / "app" / "assets" / "cefr_en.json")
                            .read_text(encoding="utf-8"))["words"]
    kdb = sqlite3.connect(f"file:{HOME / 'raw-data' / 'kaikki-index.sqlite3'}?mode=ro", uri=True)
    try:
        from wordfreq import zipf_frequency
    except ImportError:  # pragma: no cover
        zipf_frequency = None
    cache: dict[str, list] = {}

    def kaikki(word):
        if word not in cache:
            cache[word] = [json.loads(r[0]) for r in kdb.execute(
                "SELECT payload FROM entries WHERE language='en' AND normalized=?", (word,))]
        return cache[word]

    rows, flags = [], {}
    counts = collections.Counter()
    for lx in pack["lexemes"]:
        lemma, pos, cefr = lx["lemma"], lx["pos"], lx.get("cefr")
        entries = kaikki(lx["normalized"])
        zipf = lx.get("zipf")
        if zipf is None and zipf_frequency:
            zipf = zipf_frequency(lemma, "en")
        hit = quality.inclusion_flags(lemma, pos, entries, cefr_words)
        if hit and cefr:
            hit["excluded_has_cefr"] = cefr
        hit.update(quality.cefr_flags(lemma, pos, cefr, zipf, cefr_words, entries))
        if lx.get("status") == "full":
            seen = False
            for s in lx.get("senses") or []:
                if quality.sense_is_low(s, seen):
                    counts["sense_low_priority"] += 1
                elif s.get("native") and not s.get("native_ai"):
                    seen = True
            forms = [f.get("form") for f in lx.get("forms") or [] if f.get("form")]
            for e in lx.get("examples") or []:
                for f in quality.example_flags(e.get("text") or "", lemma, pos, forms):
                    counts["example_" + f] += 1
        if not hit:
            continue
        flags[f'{lx["normalized"]}|{pos}'] = hit
        for rule, detail in hit.items():
            counts[rule] += 1
            rows.append([lx["id"], lemma, pos, lx.get("status"), cefr, rule, detail])
    out = HOME / "exports" / "quality"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"lexicon-lint-{dt.date.today():%Y%m%d}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "lemma", "pos", "status", "cefr", "rule", "detail"])
        w.writerows(rows)
    quality.QUALITY_DIR.mkdir(exist_ok=True)
    (quality.QUALITY_DIR / "entry_flags.json").write_text(
        json.dumps(flags, ensure_ascii=False, sort_keys=True, indent=0), encoding="utf-8")
    # Record all evaluated entries, including clean ones. Bind the manifest
    # to these exact flags so stale/legacy exports fail closed in reconcile.
    (quality.QUALITY_DIR / "entry_flags.scope.json").write_text(json.dumps({
        "flags_sha256": hashlib.sha256(json.dumps(flags, sort_keys=True).encode()).hexdigest(),
        "keys": sorted({f'{lx["normalized"]}|{lx["pos"]}' for lx in pack["lexemes"]}),
    }, sort_keys=True), encoding="utf-8")
    summary = {"entries": len(pack["lexemes"]), "flagged_entries": len(flags),
               "csv": str(path), **dict(counts.most_common())}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary


if __name__ == "__main__":
    main(sys.argv[1:])
