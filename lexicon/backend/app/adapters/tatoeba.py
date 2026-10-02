"""Tatoeba: example sentences and their translations.

With an imported snapshot (the per-language bulk exports, see Source
Snapshots) everything is looked up in PostgreSQL. Without one, the
adapter falls back to the Tatoeba API and says so in its results.
Sentence audio is never stored (spec).
"""

from __future__ import annotations

import bz2
import csv
import io
import urllib.parse
from pathlib import Path

from sqlalchemy import text as sql

from .. import catalog
from ..text import CJK, example_key, fold, looks_simplified, opencc
from . import http
from .base import Candidate, Context, SourceAdapter
from .local import LEVELS, sentence_level, word_forms

CODE3 = {"en": "eng", "fr": "fra", "zh-TW": "cmn"}
EXPORTS = "https://downloads.tatoeba.org/exports/per_language"
API = "https://api.tatoeba.org/v1/sentences?"
LICENSE = "CC BY 2.0 FR"


def _order(e: dict) -> tuple:
    return (0 if e.get("translations") else 1, abs(len(e["text"]) - 45), e["id"])


class Tatoeba(SourceAdapter):
    key = "tatoeba"

    # ── snapshot: bulk exports into PostgreSQL ──

    def download_snapshot(self, language, snapshot_dir):
        target, _, native = language.partition(":")
        if not native:
            raise ValueError("Tatoeba 快照需要「目標語言:母語」，例如 en:zh-TW")
        t3, n3 = CODE3[target], CODE3[native]
        files = {
            "target": f"{EXPORTS}/{t3}/{t3}_sentences_detailed.tsv.bz2",
            "native": f"{EXPORTS}/{n3}/{n3}_sentences_detailed.tsv.bz2",
            "links": f"{EXPORTS}/{t3}/{t3}-{n3}_links.tsv.bz2",
        }
        paths = []
        for name, url in files.items():
            dest = Path(snapshot_dir) / url.rsplit("/", 1)[1]
            tmp = dest.with_suffix(".part")
            http.download("tatoeba", url, tmp, timeout=300)
            tmp.replace(dest)
            paths.append(dest)
        return {"version": "weekly export", "url": f"{EXPORTS}/{t3}/", "path": str(snapshot_dir),
                "files": paths, "details": {"target": t3, "native": n3,
                                            "files": [p.name for p in paths]}}

    def import_snapshot(self, session, snapshot_id: int, files: list[Path]) -> int:
        """COPY the exports into tatoeba_sentences / tatoeba_links."""
        conn = session.connection().connection  # psycopg connection
        rows = 0
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE IF NOT EXISTS _tt_s (id bigint, lang text, text text,"
                        " owner text) ON COMMIT DROP")
            cur.execute("CREATE TEMP TABLE IF NOT EXISTS _tt_l (a bigint, b bigint) ON COMMIT DROP")
            for p in files:
                links = "_links" in p.name
                with bz2.open(p, "rt", encoding="utf-8", newline="") as fh, cur.copy(
                        "COPY _tt_l (a, b) FROM STDIN" if links
                        else "COPY _tt_s (id, lang, text, owner) FROM STDIN") as cp:
                    for rec in csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE):
                        if links:
                            cp.write_row((int(rec[0]), int(rec[1])))
                        elif len(rec) >= 3:
                            owner = rec[3] if len(rec) > 3 and rec[3] != "\\N" else None
                            cp.write_row((int(rec[0]), rec[1], rec[2], owner))
                        rows += 1
            cur.execute("INSERT INTO tatoeba_sentences (id, lang, text, owner, snapshot_id)"
                        " SELECT id, lang, text, owner, %s FROM _tt_s"
                        " ON CONFLICT (id) DO UPDATE SET text = EXCLUDED.text,"
                        " owner = EXCLUDED.owner, snapshot_id = EXCLUDED.snapshot_id",
                        (snapshot_id,))
            cur.execute("INSERT INTO tatoeba_links (a, b) SELECT DISTINCT a, b FROM _tt_l"
                        " ON CONFLICT DO NOTHING")
        return rows

    def local(self, ctx: Context) -> bool:
        snap = getattr(self, "snapshots", {}) or {}
        return f"{ctx.target}:{ctx.native}" in snap and ctx.session is not None

    # ── lookup ──

    def fetch(self, ctx: Context):
        if self.local(ctx):
            return self._local(ctx)
        return self._api(ctx)

    def raw(self, ctx):
        k = (self.key, ctx.target, ctx.native, ctx.lemma)
        if k not in ctx.memo:
            ctx.memo[k] = self.fetch(ctx)
        return ctx.memo[k]

    def _local(self, ctx: Context):
        t3, n3 = CODE3[ctx.target], CODE3[ctx.native]
        params = {"t3": t3, "n3": n3}
        if " " in ctx.lemma:
            q, params["q"] = "phraseto_tsquery('simple', :q)", ctx.lemma
        else:  # the headword or any of its forms (calendars, hung, applied)
            forms = sorted(f for f in word_forms(ctx) if " " not in f)
            q = " || ".join(f"plainto_tsquery('simple', :f{i})" for i in range(len(forms)))
            params.update({f"f{i}": f for i, f in enumerate(forms)})
        # Up to 150 sentences per length band, translated ones first, so long
        # sentences (the C1–C2 levels) are never crowded out by short ones.
        rows = ctx.session.execute(sql(f"""
            WITH hits AS (
                SELECT s.id, s.text, s.owner,
                       EXISTS (SELECT 1 FROM tatoeba_links l JOIN tatoeba_sentences t ON t.id = l.b
                               WHERE l.a = s.id AND t.lang = :n3) AS has_tr,
                       width_bucket(length(s.text), ARRAY[30, 50, 70, 90, 110]) AS band
                FROM tatoeba_sentences s
                WHERE s.lang = :t3 AND length(s.text) <= 150
                  AND to_tsvector('simple', s.text) @@ ({q})
            ), ranked AS (
                SELECT *, row_number() OVER (PARTITION BY band ORDER BY has_tr DESC, id) AS r
                FROM hits
            )
            SELECT h.id, h.text, h.owner, t.id AS tid, t.text AS ttext, t.owner AS towner
            FROM ranked h
            LEFT JOIN LATERAL (
                SELECT t.* FROM tatoeba_links l JOIN tatoeba_sentences t ON t.id = l.b
                WHERE l.a = h.id AND t.lang = :n3 ORDER BY t.id LIMIT 4) t ON true
            WHERE h.r <= 150
            ORDER BY (t.id IS NULL), abs(length(h.text) - 45), h.id"""), params).all()
        return {"mode": "snapshot", "sentences": _group(rows)}

    def _api(self, ctx: Context):
        t3, n3 = CODE3[ctx.target], CODE3[ctx.native]
        q = f'"{ctx.lemma}"' if " " in ctx.lemma else f"={ctx.lemma}"
        common = {"lang": t3, "q": q, "sort": "relevance", "is_unapproved": "no"}
        with_tr, _ = http.get("tatoeba", ctx.lemma, API + urllib.parse.urlencode(
            {**common, "trans:lang": n3, "showtrans": "matching", "limit": 100}),
            timeout=ctx.timeout, retries=ctx.retries, refresh=ctx.refresh)
        plain, _ = http.get("tatoeba", ctx.lemma, API + urllib.parse.urlencode(
            {**common, "limit": 50}), timeout=ctx.timeout, retries=ctx.retries,
            refresh=ctx.refresh)
        out: dict[int, dict] = {}
        for s in (with_tr or {}).get("data", []) if isinstance(with_tr, dict) else []:
            # Only direct translations: an indirect one translates another
            # translation ("They…" → 「我們…」 via a third sentence).
            trs = [{"id": t["id"], "text": t["text"], "owner": t.get("owner")}
                   for t in s.get("translations", [])
                   if t.get("lang") == n3 and t.get("is_direct", True) is not False]
            out[s["id"]] = {"id": s["id"], "text": s["text"], "owner": s.get("owner"),
                            "translations": trs}
        for s in (plain or {}).get("data", []) if isinstance(plain, dict) else []:
            out.setdefault(s["id"], {"id": s["id"], "text": s["text"], "owner": s.get("owner"),
                                     "translations": []})
        return {"mode": "api", "sentences": sorted(out.values(), key=_order)}

    def _exact(self, ctx: Context, text: str):
        """A translation for a sentence that came from another source."""
        if not self.local(ctx):
            return None
        rows = ctx.session.execute(sql("""
            SELECT s.id, s.text, s.owner, t.id AS tid, t.text AS ttext, t.owner AS towner
            FROM tatoeba_sentences s JOIN tatoeba_links l ON l.a = s.id
            JOIN tatoeba_sentences t ON t.id = l.b AND t.lang = :n3
            WHERE s.lang = :t3 AND md5(s.text) = md5(:text) AND s.text = :text LIMIT 4"""),
            {"text": text, "t3": CODE3[ctx.target], "n3": CODE3[ctx.native]}).all()
        g = _group(rows)
        return g[0] if g else None

    # ── normalize ──

    def normalize(self, f: str, raw, ctx: Context) -> list[Candidate]:
        C = []
        sentences = (raw or {}).get("sentences", [])
        mode = (raw or {}).get("mode")
        if f == "example_sentences":
            buckets = {level: [] for level in LEVELS}
            forms = word_forms(ctx)
            for s in sentences:
                if ctx.target != "zh-TW" and len(s["text"].split()) > catalog.MAX_EXAMPLE_WORDS:
                    continue
                level = sentence_level(s["text"], forms) if ctx.target == "en" \
                    else length_level(s["text"])
                buckets[level].append(s)
            # Exactly this order is offered to APPEND_LIMITED. Every level
            # takes up to five sentences that already have a translation;
            # untranslated ones only until the level has three, since each
            # of those needs an AI translation.
            ranked = []
            for level in LEVELS:
                group = sorted(buckets[level], key=lambda s: (abs(len(s["text"]) - 45), s["id"]))
                paired = [s for s in group if s.get("translations")][:5]
                bare = [s for s in group if not s.get("translations")][:max(0, 3 - len(paired))]
                ranked.extend((s, level) for s in paired + bare)
            for s, level in ranked:
                C.append(Candidate(f, ctx.target, {"text": s["text"], "tatoeba_id": s["id"],
                                                   "owner": s.get("owner"), "level": level,
                                                   "has_translation": bool(s.get("translations"))},
                                   example_key(s["text"]), source_record_id=str(s["id"]),
                                   confidence=1.0 if s.get("translations") else 0.9,
                                   attribution=f"Tatoeba #{s['id']}"
                                   + (f" by {s['owner']}" if s.get("owner") else ""),
                                   raw_value={"mode": mode}))
        elif f == "example_translation":
            by_id = {s["id"]: s for s in sentences}
            by_text = {fold(s["text"]): s for s in sentences}
            for item in ctx.items("example_sentences"):
                k = item.get("key") or example_key(item.get("text", ""))
                s = by_id.get(item.get("tatoeba_id")) or by_text.get(fold(item.get("text", "")))
                if (not s or not s.get("translations")) and item.get("text"):
                    s = self._exact(ctx, item["text"]) or s
                if not s or not s.get("translations"):
                    continue
                tr, converted = _pick_translation(s["translations"], ctx.native)
                if tr:
                    C.append(Candidate(f, ctx.native, {"example_key": k, "text": tr["text_out"],
                                                       "tatoeba_id": tr["id"],
                                                       "converted": converted},
                                       k, slot=k, source_record_id=f"{s['id']}→{tr['id']}",
                                       confidence=0.9 if converted else 1.0,
                                       attribution=f"Tatoeba #{tr['id']}"
                                       + (f" by {tr['owner']}" if tr.get("owner") else ""),
                                       raw_value={"original": tr["text"]}))
        return C


def length_level(text: str) -> str:
    n = len(text.split()) or len(text)
    return "A1" if n <= 6 else "A2" if n <= 10 else "B1" if n <= 15 else "B2" if n <= 22 \
        else "C1" if n <= 30 else "C2"


def _group(rows) -> list[dict]:
    out: dict[int, dict] = {}
    for r in rows:
        s = out.setdefault(r.id, {"id": r.id, "text": r.text, "owner": r.owner,
                                  "translations": []})
        if r.tid:
            s["translations"].append({"id": r.tid, "text": r.ttext, "owner": r.towner})
    return sorted(out.values(), key=_order)


def _pick_translation(trs: list[dict], native: str):
    """Traditional Chinese first for zh-TW; Simplified converted with
    OpenCC (s2twp) and marked."""
    if native != "zh-TW":
        tr = trs[0]
        return dict(tr, text_out=tr["text"]), False
    trad = [t for t in trs if CJK.search(t["text"]) and not looks_simplified(t["text"])]
    if trad:
        return dict(trad[0], text_out=trad[0]["text"]), False
    conv = opencc("s2twp", trs[0]["text"])
    if conv:
        return dict(trs[0], text_out=conv), True
    return None, False
