"""本機構詞分析: word parts from the local prefix / suffix / root table
(app.morph_data) and the analyzer (app.morphology)."""

from __future__ import annotations

from .. import morph_data as md
from ..morphology import Evidence, Part, analyze
from .base import Candidate, Context, SourceAdapter


def evidence(ctx: Context) -> Evidence:
    """What the etymology fields already say about the word."""
    origin = next((i.get("code") for i in ctx.items("origin_language") if i.get("code")), None)
    # Only the first etymology is this word: flower's second (「one who
    # flows」) is marked flow + -er, which says nothing about the flower.
    ety = ctx.items("etymology_text")[:1]
    without_affix = bool(ety) and all(i.get("affix_templates") == 0 for i in ety)
    return Evidence(origin, without_affix)


def breakdown_value(parts: list[Part], method: str) -> dict:
    return {"parts": [{"part": p.shown, "text": p.text, "kind": p.kind, "meaning": p.en,
                       "free": p.free, "origin": p.origin} for p in parts],
            "summary": " + ".join(p.shown for p in parts), "method": method}


def part_slot(i: int, part: dict) -> str:
    return f"{i}:{part.get('part', '')}"


def entry_for(part: dict) -> md.Morph | None:
    """The table entry a stored part came from (matching its meaning)."""
    kind = part.get("kind")
    if part.get("free") or kind not in ("prefix", "suffix", "root"):
        return None
    options = md.lookup(kind, part.get("text") or part.get("part", ""))
    if kind == "root" and not options:
        options = md.PREFIX.get(part.get("text", ""), [])  # ex in ex-ter-ior
    return next((e for e in options if e.en == part.get("meaning")), options[0] if options else None)


class MorphLocal(SourceAdapter):
    key = "morph_local"

    def download_snapshot(self, language, snapshot_dir):
        return {"version": f"{len(md.ALL)} entries", "row_count": len(md.ALL),
                "details": {"prefixes": len(md.PREFIX), "suffixes": len(md.SUFFIX),
                            "roots": len(md.ROOT)}}

    def normalize(self, f: str, raw, ctx: Context) -> list[Candidate]:
        if ctx.target != "en":
            return []
        word = ctx.display or ctx.lemma
        if f == "morphemes":
            a = analyze(word, evidence(ctx))
            if a.unknown or (a.method == "mono" and a.score < 0.9):
                # No parts we can vouch for (croissant, veranda): one root, the word.
                return [Candidate(f, "en", breakdown_value(
                    [Part(word, "root", word, free=True)], "whole"), word,
                    confidence=0.5, raw_value={"score": round(a.score, 3)})]
            conf = 0.7 if a.method == "mono" else round(min(0.95, a.score - 0.15), 3)
            return [Candidate(f, "en", breakdown_value(a.parts, a.method), a.summary,
                              confidence=conf, raw_value={
                                  "score": round(a.score, 3),
                                  "alternatives": [" + ".join(p.shown for p in alt)
                                                   for alt in a.alternatives]})]
        if f in ("root", "prefix", "suffix"):
            out = []
            for bd in ctx.items("morphemes")[:1]:
                for p in bd.get("parts", []):
                    if p.get("kind") == f:
                        out.append(Candidate(f, "en", {"morpheme": p["part"],
                                                       "meaning": p.get("meaning")},
                                             p["part"].lower(), confidence=0.8))
            return out
        if f == "morphemes_native" and ctx.native == "zh-TW":
            missing = ctx.memo.get(("missing_slots", f))
            out = []
            for bd in ctx.items("morphemes")[:1]:
                for i, p in enumerate(bd.get("parts", [])):
                    slot = part_slot(i, p)
                    if missing is not None and slot not in missing:
                        continue
                    e = entry_for(p)
                    if e is not None:
                        out.append(Candidate(f, "zh-TW", {"slot": slot, "part": p["part"],
                                                          "text": e.zh}, slot, slot=slot,
                                             source_record_id=f"{e.kind}:{e.form}"))
            return out
        return []
