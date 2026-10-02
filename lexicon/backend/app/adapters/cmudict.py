"""CMUdict: US English ARPAbet phonemes with stress digits (not IPA).

Also computes homophones (same phonemes) and near homophones (one
similar-sounding phoneme swapped) locally, as the spec's 「CMUdict 本地計算」.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

from .. import config
from . import http
from .base import Candidate, Context, SourceAdapter, by_frequency

URL = "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict"
FALLBACK = config.REPO / "data" / "raw" / "cmudict.dict"

SIMILAR_GROUPS = [
    {"IH", "IY"}, {"EH", "AE"}, {"AA", "AO", "AH"}, {"UH", "UW"}, {"EY", "EH"}, {"OW", "AO"},
    {"P", "B"}, {"T", "D"}, {"K", "G"}, {"F", "V"}, {"S", "Z"}, {"TH", "DH"}, {"SH", "ZH"},
    {"CH", "JH"}, {"M", "N"}, {"N", "NG"}, {"L", "R"}, {"TH", "F"}, {"S", "SH"},
]
SIMILAR: dict[str, set[str]] = {}
for g in SIMILAR_GROUPS:
    for p in g:
        SIMILAR.setdefault(p, set()).update(g - {p})


class CMUdict(SourceAdapter):
    key = "cmudict"

    def __init__(self):
        self._lock = threading.Lock()
        self._path: Path | None = None
        self._pron: dict[str, list[str]] = {}
        self._by_phones: dict[tuple, list[str]] = {}

    def download_snapshot(self, language, snapshot_dir):
        dest = Path(snapshot_dir) / "cmudict.dict"
        tmp = dest.with_suffix(".part")
        size, _ = http.download("cmudict", URL, tmp)
        tmp.replace(dest)
        rows = sum(1 for line in dest.open(encoding="utf-8") if line.strip())
        return {"version": "master", "url": URL, "path": str(dest), "row_count": rows,
                "files": [dest]}

    def _load(self):
        path = Path(self.snapshot["path"]) if getattr(self, "snapshot", None) else FALLBACK
        with self._lock:
            if self._path == path:
                return
            pron: dict[str, list[str]] = {}
            by: dict[tuple, list[str]] = {}
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    parts = line.split("#")[0].split(None, 1)
                    if len(parts) != 2:
                        continue
                    w = re.sub(r"\(\d+\)$", "", parts[0].lower())
                    phones = parts[1].strip()
                    pron.setdefault(w, []).append(phones)
                    key = tuple(re.sub(r"\d", "", phones).split())
                    lst = by.setdefault(key, [])
                    if w not in lst:
                        lst.append(w)
            self._pron, self._by_phones, self._path = pron, by, path

    def fetch(self, ctx: Context):
        if ctx.target != "en":
            return None
        self._load()
        parts = ctx.lemma.split()
        prons = [self._pron.get(p) for p in parts]
        if not all(prons):
            return None
        return {"parts": parts, "prons": prons}

    def normalize(self, f: str, raw, ctx: Context) -> list[Candidate]:
        if not raw:
            return []
        C = []
        rid = ctx.lemma

        def add(value, key, conf=1.0):
            C.append(Candidate(f, "en", value, key, confidence=conf, source_record_id=rid))

        first = [p[0] for p in raw["prons"]]  # the main pronunciation of each part
        if f == "ipa":
            # Where Wiktionary has no IPA: the US phonemes written as IPA (a phrase's words joined).
            from ..arpabet import arpabet_to_ipa
            parts = [arpabet_to_ipa(p) for p in first]
            if all(parts):
                ipa = "/" + " ".join(p.strip("/") for p in parts) + "/"
                add({"ipa": ipa, "accent": "US", "from_phonemes": True}, ipa, conf=0.7)
            return C
        if f == "phonemes":
            add({"phonemes": " | ".join(first), "system": "ARPAbet"}, " | ".join(first))
            if len(raw["parts"]) == 1:
                for alt in raw["prons"][0][1:]:
                    add({"phonemes": alt, "system": "ARPAbet"}, alt, conf=0.8)
        elif f == "stress":
            digits = [d for d in re.findall(r"\d", " ".join(first))]
            if digits:
                primary = digits.index("1") + 1 if "1" in digits else None
                add({"pattern": " ".join(digits), "primary_syllable": primary},
                    " ".join(digits))
        elif f == "syllables":
            n = len(re.findall(r"\d", " ".join(first)))
            if n:
                add({"count": n}, str(n), conf=0.8)
        elif f in ("homophones", "near_homophones") and len(raw["parts"]) == 1:
            w = raw["parts"][0]
            phones = tuple(re.sub(r"\d", "", first[0]).split())
            if f == "homophones":
                for h in self._by_phones.get(phones, []):
                    if h != w and "'" not in h and _zipf(h) >= 2.0:
                        add({"word": h, "note": "同音", "phonemes": first[0]}, h)
            else:
                homs = set(self._by_phones.get(phones, []))
                found = {}
                for i, p in enumerate(phones):
                    for q in SIMILAR.get(p, ()):
                        variant = phones[:i] + (q,) + phones[i + 1:]
                        for h in self._by_phones.get(variant, []):
                            if h != w and h not in homs and "'" not in h and h not in found:
                                found[h] = f"{p}→{q}"
                ranked = sorted(found.items(), key=lambda kv: -_zipf(kv[0]))
                for h, diff in ranked:
                    if _zipf(h) < 2.5:
                        continue
                    add({"word": h, "note": "近音", "difference": diff,
                         "score": round(min(1.0, _zipf(h) / 6), 2)}, h, conf=0.8)
        if f in ("homophones", "near_homophones"):
            return by_frequency(C, "en")
        return C


def _zipf(word: str) -> float:
    try:
        from wordfreq import zipf_frequency
        return zipf_frequency(word, "en")
    except ImportError:
        return 3.0
