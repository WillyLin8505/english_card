#!/usr/bin/env python3
"""One-time fetch of the offline datasets this pipeline needs.

    python pipeline/download_data.py

Downloads (from raw.githubusercontent.com — kaikki.org, api.datamuse.com
and tatoeba.org are blocked by the sandbox this pipeline was authored in,
so those three sources must be exercised from an environment with normal
internet access, e.g. your own machine or CI):

  - data/raw/cmudict.dict               CMUdict pronunciations (ARPABET)
  - data/raw/nltk_data/corpora/wordnet  Princeton WordNet via NLTK's data
                                         mirror — see wordnet_adapter.py
                                         for why this stands in for
                                         "Open English WordNet"

Kaikki has no per-word API. To use it, download the English extract
yourself from https://kaikki.org/dictionary/English/ and pre-filter it
down to just the words this app needs:

    python pipeline/download_data.py --filter-kaikki <full-dump.jsonl> --words apple,example,happy
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"

CMUDICT_URL = "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict"
WORDNET_ZIP_URL = "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip"


def fetch_cmudict() -> None:
    dest = DATA_RAW / "cmudict.dict"
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {CMUDICT_URL} -> {dest}")
    urlretrieve(CMUDICT_URL, dest)


def fetch_wordnet() -> None:
    corpora = DATA_RAW / "nltk_data" / "corpora"
    corpora.mkdir(parents=True, exist_ok=True)
    zip_path = corpora / "wordnet.zip"
    print(f"downloading {WORDNET_ZIP_URL} -> {zip_path}")
    urlretrieve(WORDNET_ZIP_URL, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(corpora)
    print(f"extracted to {corpora / 'wordnet'}")


def filter_kaikki(dump_path: str, words: list[str]) -> None:
    wanted = {w.strip().lower() for w in words if w.strip()}
    out_path = DATA_RAW / "kaikki_subset.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    with open(dump_path, encoding="utf-8") as f_in, out_path.open("w", encoding="utf-8") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("word", "").lower() in wanted:
                f_out.write(line + "\n")
                kept += 1
    print(f"kept {kept} entries matching {len(wanted)} words -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--skip-cmudict", action="store_true")
    ap.add_argument("--skip-wordnet", action="store_true")
    ap.add_argument(
        "--filter-kaikki", metavar="DUMP_PATH", help="filter a local full Kaikki JSONL dump"
    )
    ap.add_argument("--words", help="comma-separated words for --filter-kaikki")
    args = ap.parse_args()

    if args.filter_kaikki:
        if not args.words:
            ap.error("--filter-kaikki requires --words")
        filter_kaikki(args.filter_kaikki, args.words.split(","))
        return

    if not args.skip_cmudict:
        fetch_cmudict()
    if not args.skip_wordnet:
        fetch_wordnet()


if __name__ == "__main__":
    main()
