"""Data sources from spec-01 section 6 (英文學習資料來源), one function each.

Every source returns ``(data, meta)``:
  data  normalized fields this source can supply for the word, e.g.
        {"senses": [...], "ipa": [...], "examples": [...]}
  meta  {"status": "ok" | "not_found" | "error", "error": str, "counts": {...}}

Network responses are cached in data/cache/sources/<source>/ so re-fetching
a word is instant; pass refresh=True to ask the service again.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "sources"
CMUDICT = ROOT / "data" / "raw" / "cmudict.dict"
CEFR = ROOT / "app" / "assets" / "cefr_en.json"
UA = "EnglishCardWordbase/1.0 (personal vocabulary database)"

sys.path.insert(0, str(ROOT / "pipeline"))
from ipa import arpabet_to_ipa  # noqa: E402

# Who each source is, and the licence its data comes under (spec section 5:
# 來源追蹤 — 各欄位來源、授權).
SOURCES = {
    "kaikki": {"name": "Kaikki／Wiktionary", "license": "CC BY-SA 4.0／GFDL",
               "url": "https://kaikki.org/dictionary/English/"},
    "oewn": {"name": "Open English WordNet", "license": "CC BY 4.0", "url": "https://en-word.net/"},
    "cmudict": {"name": "CMUdict", "license": "BSD-2-Clause",
                "url": "https://github.com/cmusphinx/cmudict"},
    "datamuse": {"name": "Datamuse", "license": "Datamuse API 使用條款",
                 "url": "https://www.datamuse.com/api/"},
    "tatoeba": {"name": "Tatoeba", "license": "CC BY 2.0 FR（逐句）", "url": "https://tatoeba.org/"},
    "wordlist": {"name": "本機字表比對", "license": "由 CMUdict＋CEFR-J 字表計算",
                 "url": ""},
}

_gates = {name: threading.Semaphore(3) for name in ("kaikki", "datamuse", "tatoeba")}


def _safe(word: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", word.lower()).strip("_")[:60] or "_"


def fetch(source: str, word: str, url: str, refresh: bool = False, lines: bool = False
          ) -> tuple[object | None, int | None, str | None]:
    """GET with a disk cache: (data, HTTP status, error). A 404 is not an error."""
    cache = CACHE / source / f"{_safe(word)}__{hashlib.sha1(url.encode()).hexdigest()[:12]}.json"
    if cache.exists() and not refresh:
        c = json.loads(cache.read_text(encoding="utf-8"))
        return c["data"], c["status"], c.get("error")
    data, status, error = None, None, None
    with _gates.get(source, threading.Semaphore(3)):
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as r:
                    status = r.status
                    body = r.read().decode("utf-8")
                data = ([json.loads(x) for x in body.splitlines() if x.strip()] if lines
                        else json.loads(body))
                error = None
                break
            except urllib.error.HTTPError as e:
                status, error = e.code, (None if e.code == 404 else f"HTTP {e.code}")
                if e.code in (400, 404):
                    break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
                error = f"{type(e).__name__}: {e}"
            time.sleep(1.5 * (attempt + 1))
        time.sleep(0.2)
    if error is None or status == 404:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"url": url, "status": status, "error": error, "data": data},
                                    ensure_ascii=False), encoding="utf-8")
    return data, status, error


# ── Kaikki／Wiktionary ─────────────────────────────────────────────────

AFFIX_TEMPLATES = {"affix", "af", "prefix", "pre", "suffix", "suf", "compound", "com",
                   "confix", "con", "surf", "blend"}
FORM_SKIP = {"table-tags", "inflection-template", "class", "romanization"}


def _clean_etymology(text: str) -> str:
    text = re.sub(r"^Etymology tree\n(?:.*\n)*?(?=[A-Z][a-z]+ [a-z])", "", text or "")
    first = text.strip().split("\n")[0]
    return first[:400]


def kaikki(word: str, refresh: bool = False):
    w = word.strip()
    url = ("https://kaikki.org/dictionary/English/meaning/"
           f"{urllib.parse.quote(w[0])}/{urllib.parse.quote(w[:2])}/{urllib.parse.quote(w)}.jsonl")
    raw, status, error = fetch("kaikki", w, url, refresh, lines=True)
    if error:
        return {}, {"status": "error", "error": error}
    entries = [e for e in (raw or []) if e.get("lang") == "English"]
    if not entries:
        return {}, {"status": "not_found"}
    out: dict[str, list] = {k: [] for k in (
        "pos", "senses", "meaning_zh", "ipa", "audio", "synonyms", "homophones", "forms",
        "derivations", "morphology", "etymology", "examples")}
    seen: dict[str, set] = {k: set() for k in out}

    def add(field, key, item):
        if key and key not in seen[field]:
            seen[field].add(key)
            out[field].append(item)

    usage = quotations = 0
    for e in entries:
        pos = e.get("pos", "")
        add("pos", pos, pos)
        for s in e.get("senses", []):
            gloss = (s.get("glosses") or [""])[-1]
            if gloss and "form-of" not in s.get("tags", []) or (gloss and not out["senses"]):
                add("senses", pos + gloss, {"pos": pos, "gloss": gloss})
            for syn in s.get("synonyms", []):
                add("synonyms", (syn.get("word") or "").lower(), syn.get("word"))
            for ex in s.get("examples", []):
                text = (ex.get("text") or "").strip()
                if ex.get("type") == "quotation" or ex.get("ref"):
                    quotations += 1
                    continue
                # A usage sentence, not a list of compounds: uses the word, reads as a sentence.
                if w.split()[0].lower()[:4] not in text.lower() or len(text.split()) < 3 \
                        or " " in text:
                    continue
                usage += 1
                add("examples", text.lower(), {"text": text})
        for syn in e.get("synonyms", []):
            add("synonyms", (syn.get("word") or "").lower(), syn.get("word"))
        for snd in e.get("sounds", []):
            accent = [t for t in snd.get("tags", [])]
            if snd.get("ipa"):
                add("ipa", snd["ipa"], {"ipa": snd["ipa"], "accent": accent})
            url_ = snd.get("mp3_url") or snd.get("ogg_url")
            if url_:
                add("audio", url_, {"url": url_, "file": snd.get("audio"), "accent": accent,
                                    "license": "Wikimedia Commons（依檔案授權）"})
            if snd.get("homophone"):
                add("homophones", snd["homophone"].lower(),
                    {"word": snd["homophone"], "type": "同音"})
        for fm in e.get("forms", []):
            tags = set(fm.get("tags", []))
            form = fm.get("form", "")
            if form and form != w and not tags & FORM_SKIP and not form.startswith("-"):
                add("forms", form + pos, {"form": form, "tags": sorted(tags), "pos": pos})
        for d in e.get("derived", []):
            dw = d.get("word", "")
            # 詞性衍生 (happy → happiness): single words, not the phrases
            # Wiktionary also lists as "derived terms".
            if dw and " " not in dw and "-" not in dw and dw.lower() != w.lower():
                add("derivations", dw.lower(), dw)
        for t in e.get("etymology_templates", []):
            if t.get("name") in AFFIX_TEMPLATES:
                parts = [re.sub(r"<[^>]*>", "", v) for k, v in sorted(
                    t.get("args", {}).items(), key=lambda kv: (len(kv[0]), kv[0]))
                    if k.isdigit() and k != "1" and v]
                if parts:
                    add("morphology", "+".join(parts), {"parts": parts, "kind": t["name"]})
        ety = _clean_etymology(e.get("etymology_text", ""))
        if ety:
            add("etymology", ety, ety)
        for tr in e.get("translations", []):
            # Mandarin only (other Chinese languages share the code "zh");
            # written "蘋果 /苹果" = Traditional / Simplified.
            if tr.get("lang") not in ("Chinese Mandarin", "Mandarin"):
                continue
            trad, _, simp = (tr.get("word") or "").partition("/")
            trad, simp = trad.strip(), simp.strip() or trad.strip()
            if trad:
                add("meaning_zh", trad + pos, {"trad": trad, "simp": simp, "pos": pos,
                                                "sense": tr.get("sense", "")})
    out["derivations"] = out["derivations"][:30]
    return ({k: v for k, v in out.items() if v},
            {"status": "ok", "counts": {"entries": len(entries), "usage_examples": usage,
                                        "quotations": quotations}})


# ── Open English WordNet ───────────────────────────────────────────────

# wn keeps one module-level SQLite connection, which can't cross threads,
# so every WordNet lookup runs on this one thread.
_oewn_thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="oewn")
_oewn_db = None


def oewn(word: str, refresh: bool = False):
    try:
        import wn  # noqa: F401
    except ImportError:
        return {}, {"status": "error", "error": "需要 pip install wn"}
    return _oewn_thread.submit(_oewn_lookup, word).result()


def _oewn_lookup(word: str):
    global _oewn_db
    import wn
    if _oewn_db is None:
        try:
            _oewn_db = wn.Wordnet("oewn:2024")
        except Exception:  # noqa: BLE001 — first run: download it (~30 MB)
            wn.download("oewn:2024")
            _oewn_db = wn.Wordnet("oewn:2024")
    wordnet = _oewn_db
    synsets = wordnet.synsets(word)
    if not synsets:
        return {}, {"status": "not_found"}
    pos_names = {"n": "noun", "v": "verb", "a": "adj", "s": "adj", "r": "adv"}
    out = {"pos": [], "senses": [], "synonyms": [], "derivations": [], "examples": []}
    for ss in synsets:
        pos = pos_names.get(ss.pos, ss.pos)
        if pos not in out["pos"]:
            out["pos"].append(pos)
        out["senses"].append({"pos": pos, "gloss": ss.definition() or ""})
        for lemma in ss.lemmas():
            if lemma.lower() != word.lower() and lemma not in out["synonyms"]:
                out["synonyms"].append(lemma)
        for ex in ss.examples():
            if len(out["examples"]) < 10 and all(ex != x["text"] for x in out["examples"]):
                out["examples"].append({"text": ex})
    for wd in wordnet.words(word):
        for s in wd.senses():
            for t in s.get_related("derivation"):
                lemma = t.word().lemma()
                if lemma.lower() != word.lower() and lemma not in out["derivations"]:
                    out["derivations"].append(lemma)
    return {k: v for k, v in out.items() if v}, {"status": "ok",
                                                 "counts": {"synsets": len(synsets)}}


# ── CMUdict ────────────────────────────────────────────────────────────

_cmu: dict[str, str] | None = None
_by_phones: dict[str, list[str]] = {}
_cmu_lock = threading.Lock()


def _load_cmu() -> dict[str, str]:
    global _cmu
    with _cmu_lock:
        if _cmu is None:
            cmu: dict[str, str] = {}
            with open(CMUDICT, encoding="utf-8") as fh:
                for line in fh:
                    parts = line.split("#")[0].split(None, 1)
                    if len(parts) != 2:
                        continue
                    w = re.sub(r"\(\d+\)$", "", parts[0].lower())
                    phones = parts[1].strip()
                    if w not in cmu:
                        cmu[w] = phones
                        _by_phones.setdefault(re.sub(r"\d", "", phones), []).append(w)
            _cmu = cmu
    return _cmu


def cmudict(word: str, refresh: bool = False):
    cmu = _load_cmu()
    parts = word.lower().split()
    phones = [cmu.get(p) for p in parts]
    if not all(phones):
        return {}, {"status": "not_found"}
    ipa = "/" + " ".join((arpabet_to_ipa(p) or "?").strip("/") for p in phones) + "/"
    out = {"ipa": [{"ipa": ipa, "accent": ["US"]}], "phonemes": [" | ".join(phones)]}
    if len(parts) == 1:
        homs = sorted({w for w in _by_phones.get(re.sub(r"\d", "", phones[0]), [])
                       if w != parts[0] and "'" not in w})
        if homs:
            out["homophones"] = [{"word": h, "type": "同音"} for h in homs[:15]]
    return out, {"status": "ok"}


# ── Datamuse ───────────────────────────────────────────────────────────

def datamuse(word: str, refresh: bool = False):
    base = "https://api.datamuse.com/words?"

    def ask(rel, n):
        data, _, error = fetch("datamuse", word, base + urllib.parse.urlencode({rel: word, "max": n}),
                               refresh)
        if error:
            raise RuntimeError(error)
        return [d["word"] for d in data or [] if d.get("word") and d["word"].lower() != word.lower()]

    try:
        out = {
            "synonyms": ask("rel_syn", 15),
            "means_like": ask("ml", 10),
            "homophones": [{"word": x, "type": "同音"} for x in ask("rel_hom", 10)]
            + [{"word": x, "type": "近音"} for x in ask("sl", 10)],
            "similar_spelling": ask("sp", 10),
        }
    except RuntimeError as e:
        return {}, {"status": "error", "error": str(e)}
    out = {k: v for k, v in out.items() if v}
    return out, {"status": "ok" if out else "not_found"}


# ── Tatoeba ────────────────────────────────────────────────────────────

_cc = None


def to_taiwan(text: str) -> str | None:
    """Simplified → Taiwan Traditional (OpenCC s2twp), if installed."""
    global _cc
    try:
        if _cc is None:
            import opencc
            _cc = opencc.OpenCC("s2twp")
        return _cc.convert(text)
    except ImportError:
        return None


def tatoeba(word: str, refresh: bool = False):
    # Exact form for a single word ("potted" must not match "pots"); a
    # phrase is matched as a phrase, inflections allowed ("poured coffee").
    q = f'"{word}"' if " " in word else f"={word}"
    base = "https://api.tatoeba.org/v1/sentences?"
    common = {"lang": "eng", "q": q, "sort": "relevance", "is_unapproved": "no"}
    plain, _, err1 = fetch("tatoeba", word, base + urllib.parse.urlencode({**common, "limit": 10}),
                           refresh)
    with_zh, _, err2 = fetch("tatoeba", word, base + urllib.parse.urlencode({
        **common, "trans:lang": "cmn", "showtrans": "matching", "limit": 20}), refresh)
    if err1 and err2:
        return {}, {"status": "error", "error": err1}
    plain = plain if isinstance(plain, dict) else {}
    with_zh = with_zh if isinstance(with_zh, dict) else {}
    examples: dict[int, dict] = {}
    scripts = {"Hant": 0, "Hans": 0}
    for s in with_zh.get("data", []):
        zh = next((t for t in s.get("translations", []) if t.get("lang") == "cmn"), None)
        if not zh:
            continue
        script = zh.get("script") if zh.get("script") in ("Hant", "Hans") else "Hans"
        scripts[script] += 1
        item = {"text": s["text"], "id": s["id"], "license": s.get("license"),
                "owner": s.get("owner"), "translation": zh["text"], "script": script}
        if script == "Hans":
            converted = to_taiwan(zh["text"])
            if converted:
                item["translation_tw"] = converted
        examples[s["id"]] = item
    for s in plain.get("data", []):
        examples.setdefault(s["id"], {"text": s["text"], "id": s["id"],
                                      "license": s.get("license"), "owner": s.get("owner")})
    # Traditional translations first (the app is for Taiwan), then
    # converted Simplified, then untranslated.
    ordered = sorted(examples.values(), key=lambda e: (
        0 if e.get("script") == "Hant" else 1 if e.get("translation") else 2))
    counts = {"sentences": plain.get("paging", {}).get("total", 0),
              "with_mandarin": with_zh.get("paging", {}).get("total", 0), **scripts}
    return ({"examples": ordered[:12]} if ordered else {},
            {"status": "ok" if ordered else "not_found", "counts": counts})


# ── Local word list (拼字相近) ─────────────────────────────────────────

_wordlist: list[str] | None = None
_cefr: dict | None = None


def cefr_list() -> dict:
    global _cefr
    if _cefr is None:
        _cefr = json.loads(CEFR.read_text(encoding="utf-8"))["words"]
    return _cefr


def _edit1(a: str, b: str) -> bool:
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]]
                               and a[d[1]] == b[d[0]])
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def wordlist(word: str, refresh: bool = False):
    """The spec's "Kaikki 字表＋自行比對": the full Kaikki word list is a
    3 GB dump, so this compares against CMUdict + CEFR-J headwords (126k
    words) instead — words one edit away, common words first."""
    global _wordlist
    if _wordlist is None:
        _wordlist = sorted(w for w in set(_load_cmu()) | set(cefr_list()) if w.isalpha())
    w = word.lower()
    if " " in w:
        return {}, {"status": "not_found", "note": "片語不比對"}
    skip = {w + "s", w + "es", w + "ed", w + "d", w + "ing"}
    hits = [x for x in _wordlist if abs(len(x) - len(w)) <= 1 and _edit1(w, x) and x not in skip]
    common = cefr_list()
    hits.sort(key=lambda x: (x not in common, x))
    return ({"similar_spelling": hits[:15]} if hits else {}), {"status": "ok" if hits else "not_found"}


FETCHERS = {"kaikki": kaikki, "oewn": oewn, "cmudict": cmudict, "datamuse": datamuse,
            "tatoeba": tatoeba, "wordlist": wordlist}


def extras(word: str) -> dict:
    """Word frequency (wordfreq) and CEFR level (CEFR-J list) — shown with
    the entry, not ranked sources."""
    out: dict = {}
    try:
        from wordfreq import zipf_frequency
        out["zipf"] = round(zipf_frequency(word, "en"), 2)
    except ImportError:
        pass
    hit = cefr_list().get(word.lower())
    if hit:
        levels = list(hit[1].values())
        out["cefr"] = min(levels, key=lambda l: "A1A2B1B2C1C2".index(l))
    return out
