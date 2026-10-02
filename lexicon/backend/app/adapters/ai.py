"""AI 翻譯: the local Qwen3-VL tagging service's POST /translate.

Only used after every listed source has come up empty (it is always the
last step of the default policies). Every value is marked is_ai, with the
model and prompt version in source_record_id.
"""

from __future__ import annotations

import re

from .. import catalog, config
from ..text import example_key
from . import http
from .base import Candidate, Context, SourceAdapter


class AITranslate(SourceAdapter):
    key = "ai_translate"

    def _raw_call(self, ctx: Context, kind: str, items: list[dict], lang_out: str | None = None):
        if not config.AI_KEY:
            raise http.SourceError("unavailable", "未設定 LEXICON_AI_KEY（影像辨識服務的金鑰）",
                                   retryable=False)
        payload = {"lang": ctx.target, "native": lang_out or ctx.native, "kind": kind,
                   "items": items}
        return http.post_json("ai_translate", config.AI_URL.rstrip("/") + "/translate", payload,
                              timeout=max(ctx.timeout, 600), headers={"X-API-Key": config.AI_KEY})

    def _call(self, ctx: Context, kind: str, items: list[dict], lang_out: str | None = None):
        if not config.AI_KEY:
            raise http.SourceError("unavailable", "未設定 LEXICON_AI_KEY（影像辨識服務的金鑰）",
                                   retryable=False)
        payload = {"lang": ctx.target, "native": lang_out or ctx.native, "kind": kind,
                   "items": items}
        data = http.post_json("ai_translate", config.AI_URL.rstrip("/") + "/translate", payload,
                              timeout=max(ctx.timeout, 600), headers={"X-API-Key": config.AI_KEY})
        tag = f"{data.get('model', 'model')}/{data.get('promptVersion', '')}"
        return {i["id"]: i["text"] for i in data.get("items", [])}, tag

    def lookup(self, f: str, ctx: Context) -> list[Candidate]:
        # Only the items still missing are sent (FILL_MISSING passes them).
        missing = ctx.memo.get(("missing_slots", f))
        C: list[Candidate] = []

        def want(slot):
            return missing is None or slot in missing

        if f == "native_definition":
            items = [{"id": s["sense_key"], "text": s.get("gloss", ""),
                      "context": f"{ctx.display or ctx.lemma} ({s.get('pos', '')})"}
                     for s in ctx.items("definition") if want(s.get("sense_key"))]
            got, tag = self._call(ctx, "gloss", items) if items else ({}, "")
            for sk, text in got.items():
                C.append(Candidate(f, ctx.native, {"sense_key": sk, "text": text, "ai": True},
                                   sk, slot=sk, confidence=0.6, source_record_id=tag))
        elif f == "example_translation":
            items = []
            for e in ctx.items("example_sentences"):
                k = e.get("key") or example_key(e.get("text", ""))
                if want(k):
                    items.append({"id": k, "text": e.get("text", "")})
            got, tag = self._call(ctx, "sentence", items[:15]) if items else ({}, "")
            for k, text in got.items():
                C.append(Candidate(f, ctx.native, {"example_key": k, "text": text, "ai": True},
                                   k, slot=k, confidence=0.6, source_record_id=tag))
        elif f == "derived_native_meaning" or f in catalog.RELATION_NATIVE:
            rel = "derived_terms" if f == "derived_native_meaning" else catalog.RELATION_NATIVE[f]
            label = catalog.FIELD[rel].label
            items = [{"id": i["word"].lower(), "text": i["word"],
                      "context": f"{label} of {ctx.display or ctx.lemma}"}
                     for i in ctx.items(rel) if i.get("word") and want(i["word"].lower())]
            got, tag = self._call(ctx, "word", items[:30]) if items else ({}, "")
            for w, text in got.items():
                C.append(Candidate(f, ctx.native, {"word": w, "text": text, "ai": True}, w,
                                   slot=w, confidence=0.6, source_record_id=tag))
        elif f == "etymology_native":
            ety = ctx.items("etymology_text")
            if ety:
                got, tag = self._call(ctx, "etymology", [{"id": "e", "text": ety[0]["text"]}])
                if got.get("e"):
                    C.append(Candidate(f, ctx.native, {"text": got["e"], "ai": True}, "e",
                                       confidence=0.6, source_record_id=tag))
        elif f == "morphemes":
            ety = (ctx.items("etymology_text") or [{}])[0].get("text", "")
            data = self._raw_call(ctx, "morphemes", [{"id": "w", "text": ctx.display or ctx.lemma,
                                                      "context": ety[:300]}], ctx.target)
            item = next(iter(data.get("items", [])), None)
            tag = f"{data.get('model', 'model')}/{data.get('promptVersion', '')}"
            if item and item.get("parts"):
                parts = [{"part": str(p.get("part", "")).strip(),
                          "text": str(p.get("part", "")).strip().strip("-"),
                          "kind": {"prefix": "prefix", "suffix": "suffix"}.get(
                              str(p.get("type", "")).lower(), "root"),
                          "meaning": str(p.get("meaning", "")).strip() or None,
                          "free": False, "origin": None} for p in item["parts"]]
                for p in parts:  # show affixes with their hyphen
                    if p["kind"] == "prefix" and not p["part"].endswith("-"):
                        p["part"] += "-"
                    if p["kind"] == "suffix" and not p["part"].startswith("-"):
                        p["part"] = "-" + p["part"]
                summary = " + ".join(p["part"] for p in parts)
                C.append(Candidate(f, ctx.target, {"parts": parts, "summary": summary,
                                                   "method": "ai", "ai": True},
                                   summary, confidence=0.5, source_record_id=tag))
        elif f == "morphemes_native":
            from .morph import part_slot
            word = ctx.display or ctx.lemma
            items = []
            for bd in ctx.items("morphemes")[:1]:
                for i, p in enumerate(bd.get("parts", [])):
                    slot = part_slot(i, p)
                    if want(slot):
                        what = {"prefix": "prefix", "suffix": "suffix"}.get(p.get("kind"), "root")
                        items.append({"id": slot, "text": p["part"],
                                      "context": f"{what} of '{word}'"
                                      + (f", meaning: {p['meaning']}" if p.get("meaning") else "")})
            got, tag = self._call(ctx, "part", items) if items else ({}, "")
            for slot, text in got.items():
                C.append(Candidate(f, ctx.native, {"slot": slot, "part": slot.split(":", 1)[-1],
                                                   "text": text, "ai": True}, slot, slot=slot,
                                   confidence=0.6, source_record_id=tag))
        elif f in catalog.LEVELED:
            # Only the CEFR levels the dictionaries left short of three; the
            # pipeline puts each result in the level it really is.
            from .local import LEVELS
            levels = sorted(missing or [], key=LEVELS.index)
            word = ctx.display or ctx.lemma
            sense = (ctx.items("definition") or [{}])[0]
            about = f"{sense.get('pos', '')}; meaning: {sense.get('gloss', '')}"[:150]
            if f == "example_sentences":
                items = [{"id": f"{lv}:{i}", "text": word, "context": f"CEFR {lv}; {about}"}
                         for lv in levels for i in range(3)]
                got, tag = self._call(ctx, "example", items, lang_out=ctx.target) if items \
                    else ({}, "")
                for text in dict.fromkeys(got.values()):
                    C.append(Candidate(f, ctx.target, {"text": text, "ai": True,
                                                       "ai_generated": True},
                                       example_key(text), confidence=0.5, source_record_id=tag))
            else:
                # One list spread over the levels (asked level by level, the
                # model repeats the same easy words).
                items = [{"id": "w", "text": word,
                          "context": f"levels needed: {', '.join(levels)}; {about}"[:200]}] \
                    if levels else []
                got, tag = self._call(ctx, f, items, lang_out=ctx.target) if items else ({}, "")
                from .base import zipf
                for text in got.values():
                    for w in re.split(r"[,;、，\n]+", text):
                        w = w.strip().strip(".").lower()
                        # Real words only: the model sometimes invents one.
                        if w and len(w.split()) <= 2 and zipf(w, ctx.target) >= 2.0:
                            C.append(Candidate(f, ctx.target, {"word": w, "ai": True}, w,
                                               confidence=0.5, source_record_id=tag))
        elif f == "definition":
            got, tag = self._call(ctx, "define", [{"id": "d", "text": ctx.display or ctx.lemma}],
                                  lang_out=ctx.target)
            pos = (ctx.items("pos") or [{}])[0].get("pos", "")
            if got.get("d"):
                from ..text import sense_key
                sk = sense_key(pos, got["d"])
                C.append(Candidate(f, ctx.target, {"pos": pos, "gloss": got["d"], "sense_key": sk,
                                                   "ai": True, "gloss_language": ctx.target},
                                   sk, slot=pos, confidence=0.5, source_record_id=tag))
        for c in C:
            c.source = self.key
            c.license, c.attribution = self.meta.license, self.meta.attribution
            reason = self.validate(c, ctx)
            if reason:
                c.valid, c.invalid_reason = False, reason
        return C
