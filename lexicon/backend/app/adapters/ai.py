"""AI 翻譯: the local Qwen3-VL tagging service's POST /translate.

Only used after every listed source has come up empty (it is always the
last step of the default policies). Every value is marked is_ai, with the
model and prompt version in source_record_id.
"""

from __future__ import annotations

import re

from .. import catalog, config
from ..text import example_key, repair_learner_gloss
from . import http
from .base import Candidate, Context, SourceAdapter

# A relation word's cached translation may only be reused for another relation
# of the same category (問題回報 #253): "synonyms"/"related"/… need the sense
# that actually matches the relation, so a translation cached from one of
# those is reused only among them; "near_homophones"/"similar_spelling" only
# want *some* common meaning as a hint, so sharing within that group is safe,
# but crossing groups leaked a homophone's dominant sense onto an unrelated
# synonym (cringe's synonym "fawn" showing 小鹿 "fawn (deer)" because "phone"'s
# near-homophone "fawn" had already cached that text).
RELATION_MEANING = {"synonyms", "antonyms", "hypernyms", "hyponyms", "related", "derived_terms"}
RELATION_FORM = {"homophones", "near_homophones", "similar_spelling"}


def _activity(ctx: Context, kind: str, items: list[dict]) -> str:
    """What this request is for, shown on the admin's 排程 page (URL-encoded:
    a header carries Latin-1 only)."""
    import urllib.parse
    label = {"word": "詞義翻譯", "sentence": "例句翻譯", "bundle": "批次翻譯",
             "morphemes": "構詞部件翻譯"}.get(kind, kind)
    return urllib.parse.quote(f"{ctx.lemma}：{label}，{len(items)} 項")


class AITranslate(SourceAdapter):
    key = "ai_translate"
    BATCH_SIZE = 80

    def _raw_call(self, ctx: Context, kind: str, items: list[dict], lang_out: str | None = None):
        if not config.AI_KEY:
            raise http.SourceError("unavailable", "未設定 LEXICON_AI_KEY（影像辨識服務的金鑰）",
                                   retryable=False)
        payload = {"lang": ctx.target, "native": lang_out or ctx.native, "kind": kind,
                   "items": items}
        return http.post_json("ai_translate", config.AI_URL.rstrip("/") + "/translate", payload,
                              timeout=max(ctx.timeout, 600), headers={"X-API-Key": config.AI_KEY,
                                       "X-Activity": _activity(ctx, kind, items)})

    def _call(self, ctx: Context, kind: str, items: list[dict], lang_out: str | None = None):
        if not config.AI_KEY:
            raise http.SourceError("unavailable", "未設定 LEXICON_AI_KEY（影像辨識服務的金鑰）",
                                   retryable=False)
        payload = {"lang": ctx.target, "native": lang_out or ctx.native, "kind": kind,
                   "items": items}
        data = http.post_json("ai_translate", config.AI_URL.rstrip("/") + "/translate", payload,
                              timeout=max(ctx.timeout, 600), headers={"X-API-Key": config.AI_KEY,
                                       "X-Activity": _activity(ctx, kind, items)})
        tag = f"{data.get('model', 'model')}/{data.get('promptVersion', '')}"
        return {i["id"]: i["text"] for i in data.get("items", [])}, tag

    def _text_request(self, f: str, ctx: Context):
        """Return the uniform text request used by native-language fields."""
        missing = ctx.memo.get(("missing_slots", f))

        def want(slot):
            return missing is None or slot in missing

        if f == "native_definition":
            from ..text import main_native_sense_key, sense_skipped_for_native
            defs = [s for s in ctx.items("definition") if want(s.get("sense_key"))]
            main_key = main_native_sense_key(defs)
            # The main sense is requested first. Obscure non-main senses are
            # left without a forced translation.
            defs.sort(key=lambda s: s.get("sense_key") != main_key)
            defs = [s for s in defs if not sense_skipped_for_native(s, main_key)]
            return "gloss", [{"id": s["sense_key"], "text": s.get("gloss", ""),
                              "context": f"{ctx.display or ctx.lemma} ({s.get('pos', '')})"}
                             for s in defs]
        if f == "example_translation":
            # The sense gloss stops a batch from copying one collocation
            # (sanitary napkin → 衛生棉) onto sentences of another sense.
            senses = {s.get("sense_key"): s for s in ctx.items("definition")}
            bound = {i.get("example_key"): i.get("sense_key") for i in ctx.items("example_sense")}
            native = {s.get("sense_key"): s.get("text") for s in ctx.items("native_definition")
                      if s.get("text")}
            items = []
            for e in ctx.items("example_sentences"):
                key = e.get("key") or example_key(e.get("text", ""))
                if not want(key):
                    continue
                sense_key = e.get("sense_key") or bound.get(key)
                gloss = native.get(sense_key) or (senses.get(sense_key) or {}).get("gloss") or ""
                item = {"id": key, "text": e.get("text", "")}
                if gloss:
                    item["context"] = f"{ctx.display or ctx.lemma} means: {gloss}"[:200]
                items.append(item)
            return "sentence", items[:15]
        if f == "derived_native_meaning" or f in catalog.RELATION_NATIVE:
            rel = "derived_terms" if f == "derived_native_meaning" \
                else catalog.RELATION_NATIVE[f]
            sense = (ctx.items("definition") or [{}])[0]
            context = (f"vocabulary connected to {ctx.display or ctx.lemma}; "
                       f"{sense.get('pos', '')}: {sense.get('gloss', '')}")[:200]
            category = "form" if rel in RELATION_FORM else "meaning"
            return "word", [{"id": i["word"].lower(), "text": i["word"],
                             "context": context, "category": category}
                            for i in ctx.items(rel)
                            if i.get("word") and want(i["word"].lower())][:30]
        if f == "etymology_native":
            ety = ctx.items("etymology_text")
            return "etymology", ([{"id": "e", "text": ety[0]["text"]}] if ety else [])
        if f == "morphemes_native":
            from .morph import part_slot
            word = ctx.display or ctx.lemma
            items = []
            for breakdown in ctx.items("morphemes")[:1]:
                for index, part in enumerate(breakdown.get("parts", [])):
                    slot = part_slot(index, part)
                    if want(slot):
                        what = {"prefix": "prefix", "suffix": "suffix"}.get(
                            part.get("kind"), "root")
                        items.append({"id": slot, "text": part["part"],
                                      "context": f"{what} of '{word}'"
                                      + (f", meaning: {part['meaning']}"
                                         if part.get("meaning") else "")})
            return "part", items
        return None

    def _reuse(self, ctx: Context, kind: str, items: list[dict]) -> dict[str, str]:
        """Translations the lexicon already stores for the same text, by item id:
        a relation word translated for another headword, or the same example
        sentence. They passed validation and to_taiwan() when stored, so they
        need no second model call (about a quarter of the relation words)."""
        s = ctx.session
        if s is None or not items or kind not in ("word", "sentence"):
            return {}
        from sqlalchemy import text as sql
        from sqlalchemy.exc import SQLAlchemyError
        from ..text import normalize_lemma
        try:
            # A savepoint: a failed lookup must not abort the word's transaction.
            with s.begin_nested():
                return self._reuse_rows(s, sql, normalize_lemma, ctx, kind, items)
        except SQLAlchemyError:
            return {}  # the model translates them instead

    @staticmethod
    def _reuse_rows(s, sql, normalize_lemma, ctx: Context, kind: str, items: list[dict]):
        if kind == "word":
            keys = {i["id"]: normalize_lemma(i.get("text", ""), ctx.target) for i in items}
            result: dict[str, str] = {}
            # A cached translation is only reused within its own relation
            # category (問題回報 #253) — meaning relations need the sense that
            # matches the relation, while spelling/sound relations just want
            # a common gloss and would otherwise leak that gloss onto a
            # meaning relation of an unrelated sense.
            by_category: dict[str, list[dict]] = {}
            for i in items:
                by_category.setdefault(i.get("category") or "meaning", []).append(i)
            relations = {"meaning": sorted(RELATION_MEANING), "form": sorted(RELATION_FORM)}
            for category, group in by_category.items():
                group_keys = {i["id"]: keys[i["id"]] for i in group}
                rows = s.execute(sql("""
                    SELECT l.normalized AS key, rt.text, count(*) AS n
                    FROM relation_translations rt
                    JOIN lexeme_relations lr ON lr.id = rt.relation_id
                    JOIN lexemes l ON l.id = lr.target_lexeme_id
                    WHERE l.language = :t AND l.normalized = ANY(:keys)
                      AND rt.native_language = :n AND length(trim(rt.text)) > 0
                      AND lr.relation = ANY(:relations)
                    GROUP BY 1, 2 ORDER BY n DESC"""),
                    {"t": ctx.target, "n": ctx.native, "keys": sorted(set(group_keys.values())),
                     "relations": relations.get(category, sorted(RELATION_MEANING))})
                best: dict[str, str] = {}
                for row in rows:
                    best.setdefault(row.key, row.text)  # the most common translation
                result.update({item_id: best[key] for item_id, key in group_keys.items()
                               if key in best})
            return result
        keys = {i["id"]: i.get("text", "").strip() for i in items}
        rows = s.execute(sql("""
            SELECT e.text AS key, et.text, count(*) AS n
            FROM example_translations et JOIN examples e ON e.id = et.example_id
            WHERE e.text = ANY(:keys) AND et.native_language = :n
              AND length(trim(et.text)) > 0
            GROUP BY 1, 2 ORDER BY n DESC"""),
            {"n": ctx.native, "keys": sorted(set(keys.values()))})
        best: dict[str, str] = {}
        for row in rows:
            best.setdefault(row.key, row.text)  # the most common translation
        return {item_id: best[key] for item_id, key in keys.items() if key in best}

    def _text_call(self, f: str, ctx: Context, kind: str, items: list[dict]):
        cached = ctx.memo.get(("ai_translate_batch", f))
        if cached is not None:
            return cached
        return self._call(ctx, kind, items) if items else ({}, "")

    def prefetch(self, ctx: Context, fields: list[str]) -> int:
        """Translate missing native fields in shared requests of at most 80 items.

        Results stay in the per-word Context. If a bundle request fails, the
        caller leaves this cache empty and normal per-field calls remain the
        fallback path.
        """
        flat, owners, deduplicated = [], {}, {}
        for field_key in fields:
            spec = self._text_request(field_key, ctx)
            if not spec:
                continue
            kind, items = spec
            for item in items:
                identity = (kind, item.get("text", ""), item.get("context", ""))
                request_id = deduplicated.get(identity)
                if request_id is None:
                    request_id = f"b{len(flat)}"
                    deduplicated[identity] = request_id
                    owners[request_id] = []
                    flat.append({**item, "id": request_id, "task": kind})
                owners[request_id].append((field_key, item["id"]))
        by_field = {field_key: {} for field_key in fields}
        reused_fields = set()
        for task in ("word", "sentence"):
            for request_id, text in self._reuse(
                    ctx, task, [i for i in flat if i["task"] == task]).items():
                for field_key, item_id in owners.get(request_id, []):
                    by_field.setdefault(field_key, {})[item_id] = text
                    reused_fields.add(field_key)
                owners.pop(request_id, None)
        flat = [i for i in flat if i["id"] in owners]
        if not flat:
            for field_key in fields:
                ctx.memo[("ai_translate_batch", field_key)] = (
                    by_field.get(field_key, {}),
                    "reused" if field_key in reused_fields else "")
            return 0
        tags = []
        for start in range(0, len(flat), self.BATCH_SIZE):
            got, tag = self._call(ctx, "bundle", flat[start:start + self.BATCH_SIZE])
            tags.append(tag)
            for request_id, text in got.items():
                for field_key, item_id in owners.get(request_id, []):
                    by_field.setdefault(field_key, {})[item_id] = text
        combined_tag = "+".join(dict.fromkeys(tags))
        for field_key in fields:
            ctx.memo[("ai_translate_batch", field_key)] = (
                by_field.get(field_key, {}),
                combined_tag + ("+reused" if field_key in reused_fields else ""))
        return (len(flat) + self.BATCH_SIZE - 1) // self.BATCH_SIZE

    @staticmethod
    def _repair_outlaw(items: list[dict], got: dict) -> dict:
        """Stop a fresh model call from storing outlaw as 通姦者, or Icelandic as 愛爾蘭語."""
        english = {i.get("id"): i.get("text") or "" for i in items}
        out = {}
        for key, text in got.items():
            fixed = repair_learner_gloss(english.get(key) or english.get(str(key), ""), text)
            out[key] = fixed if fixed is not None else text
        return out

    def lookup(self, f: str, ctx: Context) -> list[Candidate]:
        # Only the items still missing are sent (FILL_MISSING passes them).
        missing = ctx.memo.get(("missing_slots", f))
        C: list[Candidate] = []

        if f == "native_definition":
            from ..text import accept_native_gloss
            kind, items = self._text_request(f, ctx)
            got, tag = self._text_call(f, ctx, kind, items)
            got = self._repair_outlaw(items, got)
            for sk, text in got.items():
                text = accept_native_gloss(text) if ctx.native == "zh-TW" else text
                if not text:
                    continue
                C.append(Candidate(f, ctx.native, {"sense_key": sk, "text": text, "ai": True},
                                   sk, slot=sk, confidence=0.6, source_record_id=tag))
        elif f == "example_translation":
            kind, items = self._text_request(f, ctx)
            got, tag = self._text_call(f, ctx, kind, items)
            got = self._repair_outlaw(items, got)
            for k, text in got.items():
                C.append(Candidate(f, ctx.native, {"example_key": k, "text": text, "ai": True},
                                   k, slot=k, confidence=0.6, source_record_id=tag))
        elif f == "derived_native_meaning" or f in catalog.RELATION_NATIVE:
            kind, items = self._text_request(f, ctx)
            got, tag = self._text_call(f, ctx, kind, items)
            got = self._repair_outlaw(items, got)
            from ..text import accept_native_gloss
            for w, text in got.items():
                if ctx.native == "zh-TW":
                    text = accept_native_gloss(text)
                if not text:
                    continue
                C.append(Candidate(f, ctx.native, {"word": w, "text": text, "ai": True}, w,
                                   slot=w, confidence=0.6, source_record_id=tag))
        elif f == "etymology_native":
            kind, items = self._text_request(f, ctx)
            if items:
                got, tag = self._text_call(f, ctx, kind, items)
                got = self._repair_outlaw(items, got)
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
            kind, items = self._text_request(f, ctx)
            got, tag = self._text_call(f, ctx, kind, items)
            got = self._repair_outlaw(items, got)
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
