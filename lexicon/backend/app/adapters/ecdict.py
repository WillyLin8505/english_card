"""ECDICT: an English→Chinese dictionary (skywind3000/ECDICT, MIT), read from
raw-data/ecdict.csv through a local SQLite index. Each word's translation
lists its meanings per part of speech (「n. 银行, 堤, 岸\\n[医] 库」); the
Chinese is Simplified, so it is converted to Taiwan usage (OpenCC s2twp) and
then localized like every other source.

It sits between Kaikki and the AI in the native-meaning policies: relation
and derived words get the first meaning of their part of speech, and a
headword's first sense of each part of speech gets them when Kaikki's
translation tables have none (later senses stay with the AI, which reads the
gloss: a word-level dictionary can't tell which sense a meaning belongs to).
"""

from __future__ import annotations

import csv
import os
import re
import sqlite3
import threading

from .. import catalog, config
from ..text import opencc
from .base import Candidate, Context, SourceAdapter

CSV = config.RAW_DATA / "ecdict.csv"
INDEX = config.RAW_DATA / "ecdict.sqlite3"
# A separate file from INDEX on purpose (問題回報 #209): the admin server
# keeps INDEX open for the life of the process, and replacing an open file
# on Windows fails (os.replace -> PermissionError); a new, never-open file
# has nothing to conflict with.
PHONETIC_INDEX = config.RAW_DATA / "ecdict_phonetic.sqlite3"
DEFINITION_INDEX = config.RAW_DATA / "ecdict_definition.sqlite3"

# ECDICT's part-of-speech prefixes → the lexicon's.
POS = {"n": "noun", "v": "verb", "vt": "verb", "vi": "verb", "a": "adj", "adj": "adj",
       "ad": "adv", "adv": "adv", "prep": "prep", "conj": "conj", "pron": "pron",
       "int": "intj", "interj": "intj", "num": "num", "art": "det", "det": "det",
       "pl": "noun"}  # abbr. (GAC 加拿大地質協會) is no meaning of the word
_LINE = re.compile(r"^(?P<pos>[a-z]{1,6})\.\s*(?P<text>.+)$")
# Notes inside a meaning: （布质）, (马,鹰等), [诗歌用语], <口>, = between.
_NOTE = re.compile(r"[（(][^）)]*[）)]|\[[^\]]*\]|<[^>]*>|=\s*\S+")
_PAREN_NOTE = re.compile(r"[（(][^）)]*[）)]|<[^>]*>|=\s*\S+")
_SPLIT = re.compile(r"\s*[,，;；]\s*")
# usage labels, not subjects: 「[口] 钱」 is still an ordinary sense (#434)
_REGISTER_TAGS = frozenset({"口", "口语", "俚", "俚语", "非正式", "古语", "旧", "废", "罕",
                            "诗歌用语", "方言", "俗", "书面语", "婉", "美国", "英国",
                            "美国英语", "英国英语", "主美国英语", "主英国英语"})
_TAG = re.compile(r"\[([^\]]*)\]")


def _is_domain(part: str) -> bool:
    """A subject tag like [计] [医] [人名] — the words after it are not the ordinary sense."""
    return any(tag not in _REGISTER_TAGS for tag in _TAG.findall(part))
_FORM_NOTE = re.compile(r"的(过去式|过去分词|现在分词|复数|比较级|最高级|第三人称|变形)")

_lock = threading.Lock()


def build_index(csv_path=None, index_path=None) -> None:
    """word → translation, looked up case-insensitively (exact case first)."""
    csv_path, index_path = csv_path or CSV, index_path or INDEX
    tmp = f"{index_path}.{os.getpid()}.tmp"
    db = sqlite3.connect(tmp)
    db.execute("CREATE TABLE e (word TEXT, lower TEXT, translation TEXT)")
    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = ((r["word"], r["word"].lower(), r["translation"]) for r in csv.DictReader(f)
                if r.get("translation"))
        db.executemany("INSERT INTO e VALUES (?, ?, ?)", rows)
    db.execute("CREATE INDEX e_lower ON e (lower)")
    db.commit()
    db.close()
    os.replace(tmp, index_path)


def build_phonetic_index(csv_path=None, index_path=None) -> None:
    """word → phonetic, the small subset of ecdict.csv the pronunciation
    source needs (問題回報 #209). A separate file: see PHONETIC_INDEX."""
    csv_path, index_path = csv_path or CSV, index_path or PHONETIC_INDEX
    tmp = f"{index_path}.{os.getpid()}.tmp"
    db = sqlite3.connect(tmp)
    db.execute("CREATE TABLE p (word TEXT, lower TEXT, phonetic TEXT)")
    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = ((r["word"], r["word"].lower(), r["phonetic"]) for r in csv.DictReader(f)
                if r.get("phonetic"))
        db.executemany("INSERT INTO p VALUES (?, ?, ?)", rows)
    db.execute("CREATE INDEX p_lower ON p (lower)")
    db.commit()
    db.close()
    os.replace(tmp, index_path)


def build_definition_index(csv_path=None, index_path=None) -> None:
    """word → English definition (WordNet lines), for matching a Chinese
    meaning to a sense (問題回報 #601). A separate file: see PHONETIC_INDEX."""
    csv_path, index_path = csv_path or CSV, index_path or DEFINITION_INDEX
    tmp = f"{index_path}.{os.getpid()}.tmp"
    db = sqlite3.connect(tmp)
    db.execute("CREATE TABLE d (word TEXT, lower TEXT, definition TEXT)")
    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = ((r["word"], r["word"].lower(), r["definition"]) for r in csv.DictReader(f)
                if r.get("definition") and r.get("translation"))
        db.executemany("INSERT INTO d VALUES (?, ?, ?)", rows)
    db.execute("CREATE INDEX d_lower ON d (lower)")
    db.commit()
    db.close()
    os.replace(tmp, index_path)


_WN_POS = {"n": "noun", "v": "verb", "a": "adj", "s": "adj", "r": "adv"}
_STOP = frozenset("a an the of or and to in on for with by as at from that which who is are be "
                  "being been it its one something someone especially usually often used use "
                  "act state quality person people thing things whose any some more most".split())


def _content_words(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z]+", (text or "").lower()):
        if len(w) < 3 or w in _STOP:
            continue
        for suf in ("ing", "ed", "es", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                w = w[: -len(suf)]
                break
        out.add(w)
    return out


# ── ECDICT "phonetic" column → IPA (問題回報 #209) ──────────────────────
#
# ECDICT's phonetic column is a traditional (Daniel Jones / EPD-style)
# British phonemic respelling, not clean IPA: ' and , / . mark stress with
# ASCII punctuation, : is the length mark, (r) is the optional linking r,
# and some rows carry a second ", alternative" pronunciation or are
# corrupted (embedded Chinese accent labels, stray backslashes/carets,
# Cyrillic look-alikes for ə and ɛ from a lossy re-encoding upstream). Only
# a clean single-pronunciation row converts; anything left over after the
# substitutions below is refused rather than guessed at.
_ECDICT_SUB = {"'": "ˈ", ":": "ː", "є": "ɛ", "ә": "ə"}
_ECDICT_OUT_RE = re.compile(r"^[a-zæŋɑɒɔəɛɡɪʃʌʒˈˌː]+$")


def _ecdict_ipa(raw: str | None) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    out = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in (" ", "-"):
            break  # a second, truncated alternative pronunciation follows
        if c in (",", "."):
            # Only a leading ,/. is secondary stress (,melәn'kәuljә); one
            # appearing later always starts a second alternative, stress or
            # not (connotative "...tiv, kә'nәutәtiv"; pre-eminent
            # "...nənt,prɪ'ɛmənənt") — never joined onto the first.
            if i != 0:
                break
            out.append("ˌ")
        elif c == "(":
            close = s.find(")", i)
            if close == -1:
                return None
            i = close
        elif c in _ECDICT_SUB:
            out.append(_ECDICT_SUB[c])
        else:
            out.append(c)
        i += 1
    body = "".join(out)
    if not body or not _ECDICT_OUT_RE.fullmatch(body):
        return None
    return f"/{body}/"


def meanings(translation: str) -> list[tuple[str | None, list[str]]]:
    """(part of speech, meanings) per line; domain lines ([医], [网络]…) and
    form notes (run的过去式) are left out."""
    out = []
    for line in translation.replace("\\n", "\n").split("\n"):
        line = line.strip()
        m = _LINE.match(line)
        if not m or _FORM_NOTE.search(line):
            continue
        pos = POS.get(m.group("pos"), "")
        if pos == "":
            continue  # an unknown prefix: not worth a guess
        words = []
        tagged = False
        # the notes that are not tags go first, so a comma inside one stays inside it
        for part in _SPLIT.split(_PAREN_NOTE.sub("", m.group("text"))):
            # 問題回報 #434: "art. [计] 累加器" is computing, not the article's sense;
            # a domain tag ends the ordinary senses of the line (register tags stay)
            if _is_domain(part):
                tagged = True
            if tagged:
                continue
            part = _NOTE.sub("", part).strip(" .…·")
            if part and re.search(r"[㐀-鿿]", part) and part not in words:
                words.append(part)
        if words:
            out.append((pos, words))
    return out


class ECDict(SourceAdapter):
    key = "ecdict"

    def __init__(self):
        self._db = None
        self._pdb = None
        self._ddb = None

    def _conn(self):
        if self._db is None:
            with _lock:
                if self._db is None:
                    if not INDEX.exists():
                        if not CSV.exists():
                            return None
                        build_index(CSV, INDEX)
                    self._db = sqlite3.connect(str(INDEX), check_same_thread=False)
        return self._db

    def _pconn(self):
        if self._pdb is None:
            with _lock:
                if self._pdb is None:
                    if not PHONETIC_INDEX.exists():
                        if not CSV.exists():
                            return None
                        build_phonetic_index(CSV, PHONETIC_INDEX)
                    self._pdb = sqlite3.connect(str(PHONETIC_INDEX), check_same_thread=False)
        return self._pdb

    def translation(self, word: str) -> str | None:
        db = self._conn()
        if db is None:
            return None
        rows = db.execute("SELECT word, translation FROM e WHERE lower = ?",
                          (word.strip().lower(),)).fetchall()
        exact = [t for w, t in rows if w == word.strip()]
        return (exact or [t for _, t in rows] or [None])[0]

    def ipa(self, word: str) -> str | None:
        db = self._pconn()
        if db is None:
            return None
        rows = db.execute("SELECT word, phonetic FROM p WHERE lower = ? AND phonetic != ''",
                          (word.strip().lower(),)).fetchall()
        exact = [p for w, p in rows if w == word.strip()]
        for raw in exact or [p for _, p in rows]:
            ipa = _ecdict_ipa(raw)
            if ipa:
                return ipa
        return None

    def meaning_items(self, word: str, pos=None) -> list[str]:
        """Every meaning of [word] in [pos], in Taiwan usage, dictionary order."""
        lines = meanings(self.translation(word) or "")
        wanted = {pos} if isinstance(pos, str) else set(pos or ())
        picked = [ws for p, ws in lines if not wanted or p in wanted]
        if not picked:
            return []
        return [opencc("s2twp", w) or w for w in picked[0]]

    def all_meaning_items(self, word: str) -> list[str]:
        out = []
        for _, words in meanings(self.translation(word) or ""):
            for w in words:
                tw = opencc("s2twp", w) or w
                if tw not in out:
                    out.append(tw)
        return out

    def agreed_pointer_meaning(self, lemma: str, pos: str | None, gloss: str | None) -> str | None:
        """When a sense's gloss only names other words, and those words share
        one ECDICT meaning that this headword also lists (napkin's 「尿布」).

        None for a real definition, a long parenthetical, or words that disagree.
        """
        from ..text import synonym_pointer_lemmas
        words = [w for w in (synonym_pointer_lemmas(gloss) or [])
                 if w != (lemma or "").strip().lower()]
        if not words:
            return None
        firsts = []
        for w in words:
            text = self.meaning(w, pos) or self.meaning(w, loose=True)
            if not text:
                return None
            firsts.append(text)
        if len(set(firsts)) != 1:
            return None
        agreed = firsts[0]
        # The named meaning may sit on another part of speech (foment's 熱敷 is
        # listed on the verb, while the gloss "Fomentation." is a noun sense).
        if agreed not in self.all_meaning_items(lemma):
            return None
        return agreed

    def _dconn(self):
        if self._ddb is None:
            with _lock:
                if self._ddb is None:
                    if not DEFINITION_INDEX.exists():
                        if not CSV.exists():
                            return None
                        build_definition_index(CSV, DEFINITION_INDEX)
                    self._ddb = sqlite3.connect(str(DEFINITION_INDEX), check_same_thread=False)
        return self._ddb

    def english_definitions(self, word: str, pos: str) -> list[str]:
        """ECDICT's English (WordNet) definitions of [word] in [pos]."""
        db = self._dconn()
        if db is None:
            return []
        row = db.execute("SELECT definition FROM d WHERE lower = ? ORDER BY word = ? DESC",
                         (word.strip().lower(), word.strip())).fetchone()
        out = []
        for line in (row[0] if row else "").split("
"):
            m = re.match(r"^\(?([nvasr])\)?\.?\s+(.+)$", line.strip())
            if m and _WN_POS.get(m.group(1)) == pos:
                out.append(m.group(2))
        return out

    def homograph_conflict(self, lemma: str, pos: str | None, gloss: str | None) -> bool:
        """ECDICT lists a spelling's meanings with no etymology (tear 淚 / 撕,
        cop 警察 / 紗管, 問題回報 #601), and the first one is the common
        word's. True when [lemma] has several Kaikki etymologies in [pos] and
        ECDICT's own English definition fits another etymology's glosses
        clearly better than this sense's: the Chinese then belongs to the
        other word, and the sense is left to Kaikki or the AI."""
        if not pos or not gloss:
            return False
        from .. import kaikki_index
        from .kaikki import POS
        entries = [e for e in kaikki_index.lookup("en", lemma) or []
                   if str(e.get("word", "")) == lemma and POS.get(str(e.get("pos") or "")) == pos]
        if len({str(e.get("etymology_number") or "") for e in entries}) < 2:
            return False
        wn = {w for d in self.english_definitions(lemma, pos)[:3] for w in _content_words(d)}
        wn.discard(lemma.lower())
        if not wn:
            return False
        own_ety = None
        best_other = 0
        for e in entries:
            glosses = [((x.get("glosses") or [""])[0]).strip() for x in e.get("senses") or []][:4]
            score = max((len(wn & _content_words(g)) for g in glosses), default=0)
            if gloss.strip() in glosses:
                own_ety = score
            else:
                best_other = max(best_other, score)
        return own_ety is not None and best_other >= 2 and best_other > own_ety

    def meaning(self, word: str, pos=None, loose: bool = False) -> str | None:
        """The first meaning of [word] in [pos] (one or several parts of
        speech), with the second when the first is one character (跑、奔跑):
        later ones drift (comprehensive 廣泛的, not also 有理解力的). A [loose]
        guess takes the first line when none matches."""
        lines = meanings(self.translation(word) or "")
        wanted = {pos} if isinstance(pos, str) else set(pos or ())
        line = next((ws for p, ws in lines if not wanted or p in wanted), None)
        if line is None and loose and lines:
            line = lines[0][1]
        if not line:
            return None
        text = "、".join(line[:2] if len(line[0]) == 1 else line[:1])
        return opencc("s2twp", text) or None

    def normalize(self, f, raw, ctx: Context) -> list[Candidate]:
        if f == "ipa" and ctx.target == "en":
            # Target-language field, independent of the native direction
            # (unlike the Chinese meanings below): a last resort after
            # Kaikki/CMUdict/local rules all have nothing (問題回報 #209).
            ipa = self.ipa(ctx.lemma)
            if not ipa:
                return []
            return [Candidate(f, "en", {"ipa": ipa, "from_ecdict": True}, ipa, confidence=0.55,
                              source_record_id=ctx.lemma)]
        if ctx.target != "en" or ctx.native != "zh-TW":
            return []
        C = []

        def add(value, key, slot, conf):
            C.append(Candidate(f, ctx.native, value, key, slot=slot, confidence=conf,
                               source_record_id=value.get("word") or ctx.lemma))

        if f == "native_definition":
            # The dictionary's first meaning of a part of speech belongs on
            # that part of speech's main sense, not on an earlier archaic or
            # taxonomic sense that learners do not see first.
            from ..text import native_sense_keys
            defs = ctx.items("definition")
            wanted = native_sense_keys(defs)
            firsts = {}
            glosses = {}
            for d in defs:
                if d.get("pos") and d.get("sense_key") and d["sense_key"] in wanted:
                    firsts.setdefault(d["pos"], d["sense_key"])
                    glosses.setdefault(d["pos"], d.get("gloss"))
            for pos, key in firsts.items():
                text = self.meaning(ctx.lemma, pos)
                if text and not self.homograph_conflict(ctx.lemma, pos, glosses.get(pos)):
                    add({"sense_key": key, "text": text}, key, key, 0.7)
            # A later sense that only names another word (「A nappy (UK), a
            # diaper (American).」) takes that word's meaning when the
            # dictionary already lists it. Otherwise the AI translates the
            # headword and writes 紙巾 for a diaper.
            for d in defs:
                key = d.get("sense_key")
                if not key or key not in wanted or firsts.get(d.get("pos")) == key:
                    continue
                pointed = self.agreed_pointer_meaning(ctx.lemma, d.get("pos"), d.get("gloss"))
                if pointed:
                    add({"sense_key": key, "text": pointed}, key, key, 0.7)
        elif f == "derived_native_meaning" or f in catalog.RELATION_NATIVE:
            rel = "derived_terms" if f == "derived_native_meaning" else catalog.RELATION_NATIVE[f]
            missing = ctx.memo.get(("missing_slots", f))
            head_pos = [i["pos"] for i in ctx.items("pos") if i.get("pos")]
            for item in ctx.items(rel):
                w = item.get("word") or ""
                if not w or (missing is not None and w.lower() not in missing):
                    continue
                text = (self.meaning(w, item["pos"]) if item.get("pos")
                        else self.meaning(w, head_pos, loose=True))
                if text:
                    add({"word": w, "text": text}, w.lower(), w.lower(), 0.7)
        return C
