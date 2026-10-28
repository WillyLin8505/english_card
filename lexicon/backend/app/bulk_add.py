"""批量加入要學的單字 (card #753): 後台版的 App 卡 #745.

check()   — say what would happen to each typed word (nothing is written).
confirm() — new words become an import job (the existing 補資料 flow: translation,
            examples, audio, pictures; AI parts go to Qwen through that flow),
            words already in the lexicon are put on the 「owner 想學」 word list.
"""

from __future__ import annotations

import difflib
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import jobs, models as m
from .text import normalize_lemma

LIMIT = 3000  # owner 10/29 (was 500)
WANTED_LIST = "owner 想學"
_WRONG = {"misspelling", "pronunciation-spelling", "obsolete", "nonstandard"}
_MISSPELLING = re.compile(r"(?:[Mm]isspelling|[Ss]pelling|[Ff]orm) of ([^\W\d_][\w' -]*?)(?:[.,;:(]|$)")
_SPLIT =re.compile(r"[\n\r\t,，、;；]+")


def split_words(text: str, language: str = "en") -> list[str]:
    """One word per line, or split by comma, 、, Tab, semicolon (Excel paste).
    Blanks and repeats (any case) are dropped."""
    seen, out = set(), []
    for raw in _SPLIT.split(text or ""):
        k = normalize_lemma(raw, language)
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _full(s: Session, target: str, norm: str) -> list[m.Lexeme]:
    return list(s.execute(select(m.Lexeme).where(
        m.Lexeme.language == target, m.Lexeme.status == "full",
        m.Lexeme.normalized == norm).order_by(m.Lexeme.id)).scalars())


def _info(s: Session, lex: list[m.Lexeme], native: str) -> dict:
    meaning = s.execute(select(m.SenseTranslation.text).join(
        m.Sense, m.Sense.id == m.SenseTranslation.sense_id).where(
        m.Sense.lexeme_id.in_([x.id for x in lex]),
        m.SenseTranslation.native_language == native).order_by(
        m.Sense.ordinal).limit(1)).scalar_one_or_none()
    return {"word": lex[0].normalized, "pos": "/".join(dict.fromkeys(x.pos for x in lex)),
            "cefr": next((x.cefr for x in lex if x.cefr), None), "meaning": meaning or ""}


def _typo(s: Session, target: str, norm: str) -> str | None:
    """A close spelling of a word the lexicon has (recieve → receive)."""
    if " " in norm or len(norm) < 4 or not norm.isalpha():
        return None
    try:
        from . import kaikki_index
        entries = [e for e in kaikki_index.lookup(target, norm) or [] if e.get("pos") != "name"]
    except Exception:  # noqa: BLE001
        entries = []
    if entries:
        # Wiktionary lists common misspellings and says what they should be.
        fixes, real = [], False
        for e in entries:
            for sn in e.get("senses") or []:
                gloss = " ".join(sn.get("glosses") or [])
                found = _MISSPELLING.search(gloss) if _WRONG & set(sn.get("tags") or []) else None
                if found:
                    fixes.append(normalize_lemma(found.group(1), target))
                else:
                    real = True
        if real or not fixes:
            return None  # a real word the lexicon just does not hold yet
        return fixes[0]
    cands = s.execute(select(m.Lexeme.normalized).where(
        m.Lexeme.language == target, m.Lexeme.status == "full",
        m.Lexeme.normalized.op("%")(norm)).order_by(
        func.similarity(m.Lexeme.normalized, norm).desc()).limit(20)).scalars().all()
    best, score = None, 0.0
    for c in dict.fromkeys(cands):
        r = difflib.SequenceMatcher(None, norm, c).ratio()
        if r > score and abs(len(c) - len(norm)) <= 2 and c[0] == norm[0]:
            best, score = c, r
    return best if score >= 0.8 else None


def classify(s: Session, word: str, target: str, native: str) -> dict:
    norm = normalize_lemma(word, target)
    item = {"typed": norm, "word": norm, "status": "new", "pos": "", "cefr": None,
            "meaning": "", "suggestion": None, "include": True, "phrase": " " in norm}
    lex = _full(s, target, norm)
    if lex:
        return {**item, **_info(s, lex, native), "status": "existing"}
    # An inflected form (brewed): the lexeme that lists it.
    base = s.execute(select(m.Lexeme).join(m.Form, m.Form.lexeme_id == m.Lexeme.id).where(
        m.Lexeme.language == target, m.Lexeme.status == "full",
        m.Form.normalized == norm).order_by(m.Lexeme.id).limit(1)).scalar_one_or_none()
    if base is None and " " not in norm:
        from .adapters.base import inflection_bases
        for b in inflection_bases(norm, target):
            hit = _full(s, target, b)
            if hit:
                base = hit[0]
                break
    if base is not None and base.normalized != norm:
        return {**item, **_info(s, _full(s, target, base.normalized), native), "status": "variant"}
    sug = _typo(s, target, norm)
    if sug:
        return {**item, "status": "typo", "suggestion": sug, "include": False}
    return item


def check(s: Session, text: str, target: str, native: str) -> dict:
    words = split_words(text, target)
    items, taken = [], set()
    for w in words[:LIMIT]:
        it = classify(s, w, target, native)
        if it["status"] in ("existing", "variant"):
            # brewed + brewing → one brew
            if it["word"] in taken:
                it["status"], it["include"] = "duplicate", False
            taken.add(it["word"])
        items.append(it)
    return {"items": items, "over_limit": max(0, len(words) - LIMIT), "limit": LIMIT}


def confirm(s: Session, items: list[dict], target: str, native: str,
            idempotency_key: str | None = None) -> dict:
    """items: [{word, include}]. Existence is re-checked here, never trusted."""
    new, have, skipped, seen = [], [], 0, set()
    for it in items[:LIMIT]:
        w = normalize_lemma(str(it.get("word", "")), target)
        if not w or not it.get("include", True) or w in seen or len(w) > 64:
            skipped += 1
            continue
        seen.add(w)
        (have if _full(s, target, w) else new).append(w)
    skipped += max(0, len(items) - LIMIT)
    job_ids: list[int] = []
    if new:
        shards = jobs.create_shards(s, {
            "target_language": target, "native_language": native, "mode": "fill_missing",
            "words": new, "parallelism": min(4, len(new)),
            "note": f"批量加入 {len(new)} 個新字（卡 #753）"}, idempotency_key)
        job_ids = [j.id for j in shards]
    wl = s.execute(select(m.Wordlist).where(m.Wordlist.language == target,
                                            m.Wordlist.name == WANTED_LIST)).scalar_one_or_none()
    wanted = list(wl.words) if wl else []
    fresh = [w for w in have + new if w not in set(wanted)]
    if wl is None:
        s.add(m.Wordlist(language=target, name=WANTED_LIST, words=wanted + fresh))
    elif fresh:
        wl.words = wanted + fresh
    s.flush()
    return {"added": len(new), "existing": len(have), "skipped": skipped, "job_ids": job_ids,
            "wanted_list": WANTED_LIST, "wanted_total": len(wanted) + len(fresh)}
