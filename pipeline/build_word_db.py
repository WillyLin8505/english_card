#!/usr/bin/env python3
"""Build word-detail-view JSON for a list of words.

Usage:
    python pipeline/build_word_db.py --words apple,example,happy --out data/cache/word_db.json
    python pipeline/build_word_db.py --word-file vocab.txt --out data/cache/word_db.json --verbose

Run pipeline/download_data.py first to populate data/raw/ (CMUdict,
WordNet). Datamuse and Tatoeba need live network and are skipped
automatically wherever that fails; pass --no-network to skip them
outright (e.g. inside this sandbox, where both are blocked).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.merge import build_word_detail
from pipeline.sources.cmudict_adapter import CMUdictAdapter
from pipeline.sources.datamuse_adapter import DatamuseAdapter
from pipeline.sources.kaikki_adapter import KaikkiAdapter
from pipeline.sources.tatoeba_adapter import TatoebaAdapter
from pipeline.sources.wordlist_adapter import LocalWordlistAdapter
from pipeline.sources.wordnet_adapter import WordNetAdapter

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"


def build_adapters(*, use_network: bool = True) -> dict:
    adapters: dict = {}

    cmudict_path = DATA_RAW / "cmudict.dict"
    if cmudict_path.exists():
        cmu = CMUdictAdapter(cmudict_path)
        adapters["cmudict"] = cmu
        adapters["kaikki_wordlist"] = LocalWordlistAdapter(cmu.words())
    else:
        logging.warning("missing %s — run pipeline/download_data.py first", cmudict_path)

    nltk_data_path = DATA_RAW / "nltk_data"
    if (nltk_data_path / "corpora" / "wordnet").exists():
        adapters["wordnet"] = WordNetAdapter(str(nltk_data_path))
    else:
        logging.warning("missing wordnet corpus under %s", nltk_data_path)

    kaikki_dump = DATA_RAW / "kaikki_subset.jsonl"
    if kaikki_dump.exists():
        adapters["kaikki"] = KaikkiAdapter(kaikki_dump)
    else:
        logging.warning(
            "missing %s — Kaikki has no live per-word API; see "
            "download_data.py --filter-kaikki",
            kaikki_dump,
        )

    if use_network:
        adapters["datamuse"] = DatamuseAdapter()
        adapters["tatoeba"] = TatoebaAdapter()

    return adapters


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--words", help="comma-separated word list")
    ap.add_argument("--word-file", help="text file, one word per line")
    ap.add_argument("--out", required=True, help="output JSON path")
    ap.add_argument(
        "--no-network", action="store_true", help="skip Datamuse/Tatoeba (offline sources only)"
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    words: list[str] = []
    if args.words:
        words.extend(w.strip() for w in args.words.split(",") if w.strip())
    if args.word_file:
        words.extend(
            w.strip() for w in Path(args.word_file).read_text(encoding="utf-8").splitlines() if w.strip()
        )
    if not words:
        ap.error("provide --words and/or --word-file")

    adapters = build_adapters(use_network=not args.no_network)

    results = {}
    for word in words:
        wd = build_word_detail(word, adapters)
        results[word] = wd.to_json()
        covered = sum(1 for k, v in results[word].items() if k.endswith("_source") and v)
        logging.info("%s: %d/9 categories resolved", word, covered)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(results)} word(s) to {out_path}")


if __name__ == "__main__":
    main()
