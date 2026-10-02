#!/usr/bin/env python3
"""Builds the app's local CEFR vocabulary list (spec section 3: "CEFR 優先
由本機詞彙資料庫校正，不完全信任視覺模型自評").

    python pipeline/build_cefr_list.py            # -> app/assets/cefr_en.json

Sources (downloaded once into data/raw/):
  - CEFR-J Vocabulary Profile 1.5 (A1-B2) — free for research and
    commercial use with citation; copyright Tono Laboratory, TUFS.
  - Octanove Vocabulary Profile C1/C2 1.0 — CC BY-SA 4.0, Octanove Labs.
  Both from https://github.com/openlanguageprofiles/olp-en-cefrj
  - Word frequency (Zipf scale, 0-8) from the `wordfreq` package, if
    installed (pip install wordfreq); otherwise frequencies are omitted.
  - US IPA converted from CMUdict (BSD licence; spec section 6's second
    source for 發音音標), see pipeline/ipa.py.

Output: {"source": ..., "words": {"abandon": [zipf, {"verb": "B1"}, "/əˈbændən/"], ...}}
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from urllib.request import urlretrieve

try:
    from ipa import arpabet_to_ipa
except ImportError:  # run as a module: python -m pipeline.build_cefr_list
    from pipeline.ipa import arpabet_to_ipa

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
BASE = "https://raw.githubusercontent.com/openlanguageprofiles/olp-en-cefrj/master/"
CMUDICT_URL = "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict"
FILES = {
    "cefrj": "cefrj-vocabulary-profile-1.5.csv",
    "octanove": "octanove-vocabulary-profile-c1c2-1.0.csv",
}
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
POS = {
    "adjective": "adj.",
    "adverb": "adv.",
    "noun": "noun",
    "verb": "verb",
    "be-verb": "verb",
    "do-verb": "verb",
    "have-verb": "verb",
    "modal auxiliary": "verb",
}


def fetch() -> dict[str, Path]:
    paths = {}
    for key, name in FILES.items():
        dest = DATA_RAW / name
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            print(f"downloading {BASE + name} -> {dest}")
            urlretrieve(BASE + name, dest)
        paths[key] = dest
    cmu = DATA_RAW / "cmudict.dict"
    if not cmu.exists():
        print(f"downloading {CMUDICT_URL} -> {cmu}")
        urlretrieve(CMUDICT_URL, cmu)
    paths["cmudict"] = cmu
    return paths


def read_cmudict(path: Path) -> dict[str, str]:
    """word -> first listed pronunciation, as IPA. Multi-word entries
    ("cutting board") are joined from their words."""
    first: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.split("#")[0].split(None, 1)
            if len(parts) != 2 or "(" in parts[0]:
                continue
            first.setdefault(parts[0].lower(), parts[1].strip())
    out = {}
    for w, phones in first.items():
        ipa = arpabet_to_ipa(phones)
        if ipa:
            out[w] = ipa
    return out


def ipa_of(word: str, ipa: dict[str, str]) -> str | None:
    if word in ipa:
        return ipa[word]
    parts = [ipa.get(p) for p in word.split()]
    if len(parts) > 1 and all(parts):
        return "/" + " ".join(p.strip("/") for p in parts) + "/"
    return None


def read_rows(path: Path) -> list[tuple[str, str, str]]:
    """(headword, pos, level) rows; "a.m./A.M./am" headwords are split."""
    out = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            level = (row.get("CEFR") or "").strip().upper()
            if level not in LEVELS:
                continue
            pos = POS.get((row.get("pos") or "").strip().lower(), (row.get("pos") or "").strip())
            for w in (row.get("headword") or "").split("/"):
                w = w.strip().lower()
                if w:
                    out.append((w, pos, level))
    return out


def build(paths: dict[str, Path]) -> dict:
    words: dict[str, dict[str, str]] = {}
    for key in ("cefrj", "octanove"):
        for w, pos, level in read_rows(paths[key]):
            by_pos = words.setdefault(w, {})
            # The lower level wins when a list repeats a word + POS.
            if pos not in by_pos or LEVELS.index(level) < LEVELS.index(by_pos[pos]):
                by_pos[pos] = level
    try:
        from wordfreq import zipf_frequency
    except ImportError:
        zipf_frequency = None
    ipa = read_cmudict(paths["cmudict"])
    return {
        "source": "CEFR-J Wordlist 1.5 (Tono Laboratory, TUFS); Octanove Vocabulary Profile "
                  "C1/C2 1.0 (Octanove Labs, CC BY-SA 4.0); IPA from CMUdict"
                  + ("; frequency: wordfreq (Zipf)" if zipf_frequency else ""),
        "words": {
            w: [round(zipf_frequency(w, "en"), 2) if zipf_frequency else None, by_pos,
                ipa_of(w, ipa)]
            for w, by_pos in sorted(words.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(ROOT / "app" / "assets" / "cefr_en.json"))
    args = parser.parse_args()
    data = build(fetch())
    Path(args.out).write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(data['words'])} words -> {args.out}")


if __name__ == "__main__":
    main()
