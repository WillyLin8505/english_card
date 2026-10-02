"""Read models for the admin pages: word detail, coverage, dashboard,
audio library. Everything is per direction (target + native)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import catalog, config
from . import models as m
from .adapters import http
from .text import example_key, normalize_lemma

OK = catalog.DONE


def _values(s, t, n, lemma):
    return {fv.field: fv for fv in s.execute(select(m.FieldValue).where(
        m.FieldValue.target_language == t, m.FieldValue.native_language == n,
        m.FieldValue.lemma == lemma)).scalars()}


def issues_for(t: str, n: str, fvs: dict) -> list[dict]:
    """Every missing native item, named: 「例句 #3 缺翻譯」, 「同義詞 fruit 缺繁中詞義」…"""
    nz = catalog.LANGUAGES[n]["zh"]
    out = []

    def items(f):
        return fvs[f].items if f in fvs else []

    def add(field_key, target, message, kind="missing"):
        out.append({"field": field_key, "target": target, "message": message, "kind": kind})

    senses = items("definition")
    have = {i.get("sense_key") or i.get("slot") for i in items("native_definition")}
    for k, sn in enumerate(senses, 1):
        if sn.get("sense_key") not in have:
            add("native_definition", sn.get("sense_key"),
                f"詞義 #{k}（{sn.get('pos', '')}：{sn.get('gloss', '')[:40]}）缺{nz}釋義")
    exs = items("example_sentences")
    tr = {i.get("example_key") or i.get("slot") for i in items("example_translation")}
    for k, ex in enumerate(exs, 1):
        if (ex.get("key") or example_key(ex.get("text", ""))) not in tr:
            add("example_translation", ex.get("key"), f"例句 #{k} 缺翻譯")
    for rel in catalog.RELATION_FIELDS + ["derived_terms"]:
        nat = "derived_native_meaning" if rel == "derived_terms" else f"{rel}_native"
        got = {(i.get("word") or i.get("slot") or "").lower() for i in items(nat)}
        label = catalog.FIELD[rel].label.replace("清單", "")
        for it in items(rel):
            w = it.get("word", "")
            if w.lower() not in got:
                add(nat, w, f"{label} {w} 缺{nz}詞義")
    parts = (items("morphemes") or [{}])[0].get("parts", [])
    got = {i.get("slot") for i in items("morphemes_native")}
    for k, p in enumerate(parts):
        if len(parts) > 1 and f"{k}:{p.get('part', '')}" not in got:
            add("morphemes_native", p.get("part"), f"構詞部件 {p.get('part')} 缺{nz}意思")
    if items("etymology_text") and not items("etymology_native"):
        add("etymology_native", None, f"詞源說明缺{nz}版本")
    for f, fv in fvs.items():
        if fv.status == "failed":
            add(f, None, f"{catalog.FIELD[f].label} 擷取失敗", "failed")
        elif fv.status == "missing" and f not in ("native_definition", "example_translation"):
            add(f, None, f"{catalog.FIELD[f].label} 缺值")
    return out


def word(s: Session, t: str, n: str, lemma_in: str) -> dict:
    lemma = normalize_lemma(lemma_in, t)
    fvs = _values(s, t, n, lemma)
    lexemes = s.execute(select(m.Lexeme).where(m.Lexeme.language == t,
                                               m.Lexeme.normalized == lemma)).scalars().all()
    if not fvs and not lexemes:
        raise KeyError(lemma)
    overrides = {o.field for o in s.execute(select(m.UserOverride.field).where(
        m.UserOverride.target_language == t, m.UserOverride.native_language == n,
        m.UserOverride.lemma == lemma)).all()}
    lookups: dict[str, list] = {}
    for lk in s.execute(select(m.SourceLookup).where(
            m.SourceLookup.target_language == t, m.SourceLookup.lemma == lemma,
            m.SourceLookup.native_language.in_(("*", n)))).scalars():
        lookups.setdefault(lk.field, []).append({"source": lk.source, "status": lk.status,
                                                 "count": lk.count, "error": lk.error,
                                                 "at": lk.looked_up_at})
    fields = []
    for f in catalog.fields_for(t):
        fv = fvs.get(f.key)
        fields.append({"field": f.key, "label": f.label, "block": f.block, "scope": f.scope,
                       "status": fv.status if fv else "not_run", "items": fv.items if fv else [],
                       "missing": fv.missing if fv else [], "override": f.key in overrides,
                       "policy_version": fv.policy_version if fv else None,
                       "resolved_at": fv.resolved_at if fv else None,
                       "lookups": sorted(lookups.get(f.key, []), key=lambda x: x["source"])})
    ids = [lx.id for lx in lexemes]
    sense_ids = {}
    for sn in s.execute(select(m.Sense).where(m.Sense.lexeme_id.in_(ids))).scalars() if ids else []:
        sense_ids[sn.sense_key] = sn.id

    def items(f):
        return fvs[f].items if f in fvs else []

    nd = {i.get("sense_key") or i.get("slot"): i for i in items("native_definition")}
    senses = [{"n": k, "sense_key": i.get("sense_key"), "sense_id": sense_ids.get(i.get("sense_key")),
               "pos": i.get("pos"), "gloss": i.get("gloss"), "labels": i.get("labels") or [],
               "source": i.get("source"), "native": nd.get(i.get("sense_key")),
               "status": "ok" if i.get("sense_key") in nd else "missing"}
              for k, i in enumerate(items("definition"), 1)]
    et = {i.get("example_key") or i.get("slot"): i for i in items("example_translation")}
    lv = {i.get("example_key"): i.get("level") for i in items("example_difficulty")}
    esn = {i.get("example_key"): i.get("sense_key") for i in items("example_sense")}
    examples = []
    for k, i in enumerate(items("example_sentences"), 1):
        key = i.get("key") or example_key(i.get("text", ""))
        examples.append({"n": k, "key": key, "text": i.get("text"), "source": i.get("source"),
                         "level": lv.get(key), "sense_key": esn.get(key) or i.get("sense_key"),
                         "translation": et.get(key),
                         "status": "ok" if key in et else "missing"})
    # The learner app consumes sentences by CEFR band.  Keep the API
    # deterministic and place bilingual pairs before untranslated fallbacks.
    level_order = {level: n for n, level in enumerate(("A1", "A2", "B1", "B2", "C1", "C2"))}
    examples.sort(key=lambda ex: (level_order.get(ex["level"], 6),
                                  ex["translation"] is None, ex["n"]))
    for k, ex in enumerate(examples, 1):
        ex["n"] = k
    relations = {}
    for rel in catalog.RELATION_FIELDS + ["derived_terms"]:
        nat = "derived_native_meaning" if rel == "derived_terms" else f"{rel}_native"
        means = {(i.get("word") or i.get("slot") or "").lower(): i for i in items(nat)}
        extra = {}
        if rel == "derived_terms":
            extra = {i["word"].lower(): i for i in items("derivation_relation") if i.get("word")}
            dpos = {i["word"].lower(): i.get("pos") for i in items("derived_pos") if i.get("word")}
        rows = []
        for i in items(rel):
            w = i.get("word", "")
            target_lx = s.execute(select(m.Lexeme.id, m.Lexeme.status, m.Lexeme.cefr,
                                         m.Lexeme.zipf).where(
                m.Lexeme.language == t, m.Lexeme.normalized == normalize_lemma(w, t))).first()
            zipf = target_lx.zipf if target_lx and target_lx.zipf is not None else i.get("zipf")
            cefr = target_lx.cefr if target_lx and target_lx.cefr else i.get("cefr")
            rows.append({"word": w, "pos": (dpos.get(w.lower()) if rel == "derived_terms" else None)
                         or i.get("pos"), "source": i.get("source"), "note": i.get("note"),
                         "difference": i.get("difference"), "score": i.get("score"),
                         "zipf": zipf, "rarity": i.get("rarity"), "cefr": cefr,
                         "cefr_source": ("lexicon" if target_lx and target_lx.cefr else
                                         i.get("cefr_source")),
                         "hide_by_default": bool(i.get("hide_by_default") or
                                                 (zipf is not None and zipf < 2.5)),
                         "relation": extra.get(w.lower()), "native": means.get(w.lower()),
                         "lexeme_id": target_lx.id if target_lx else None,
                         "linked": target_lx.status if target_lx else None,
                         "status": "ok" if w.lower() in means else "missing"})
        if rows:
            relations[rel] = {"label": catalog.FIELD[rel].label, "items": rows}
    bd = (items("morphemes") or [None])[0]
    morphemes = None
    if bd:
        nat = {i.get("slot"): i for i in items("morphemes_native")}
        morphemes = {"summary": bd.get("summary"), "method": bd.get("method"),
                     "source": bd.get("source"), "ai": bool(bd.get("ai")),
                     "parts": [{**p, "native": nat.get(f"{k}:{p.get('part', '')}")}
                               for k, p in enumerate(bd.get("parts", []))]}
    target_fields = [x for x in fields if x["scope"] == "target" and x["status"] != "unset"]
    native_fields = [x for x in fields if x["scope"] == "native" and x["status"] != "unset"]
    issues = issues_for(t, n, fvs)
    # Every level needs three example sentences; one still short after every
    # source (AI last) answered is marked 「缺漏」 all the same.
    ex_status = getattr(fvs.get("example_sentences"), "status", None)
    tr_done = getattr(fvs.get("example_translation"), "status", None) in catalog.DONE
    for level in level_order:
        at_level = [ex for ex in examples if ex["level"] == level]
        paired = sum(ex["translation"] is not None for ex in at_level)
        if len(at_level) < 3 and ex_status not in ("user_override", "not_applicable", "unset"):
            issues.append({"field": "example_sentences", "target": level,
                           "message": f"缺漏：{level} 例句只有 {len(at_level)} 句，至少要 3 句"
                                      + ("（來源已查遍）" if ex_status == catalog.SHORT else ""),
                           "kind": "missing"})
        if paired < min(3, len(at_level)) and not tr_done:
            issues.append({"field": "example_translation", "target": level,
                           "message": f"{level} 中英對照只有 {paired} 組，會先顯示已有翻譯的句子",
                           "kind": "missing"})
    # Synonyms and related words are filled per level too (catalog.LEVELED).
    for rel in ("synonyms", "related"):
        fv = fvs.get(rel)
        if fv is None or fv.status == "unset" or fv.status in catalog.DONE:
            continue
        least = catalog.LEVELED[rel][0]
        for level in level_order:
            got = sum(1 for i in fv.items if (i.get("slot") or i.get("cefr")) == level)
            if got < least:
                issues.append({"field": rel, "target": level, "kind": "missing",
                               "message": f"缺漏：{level} {catalog.FIELD[rel].label}只有 {got} 個，"
                                          f"至少要 {least} 個"
                                          + ("（來源已查遍）" if fv.status == catalog.SHORT else "")})
    # Two recordings a word, British and American (catalog.AUDIO_ACCENTS).
    fv = fvs.get("audio")
    if t == "en" and fv is not None and fv.status not in ("unset", "user_override"):
        have = {i.get("slot") for i in fv.items}
        names = {"UK": "英式", "US": "美式"}
        for acc in catalog.AUDIO_ACCENTS:
            if acc not in have:
                issues.append({"field": "audio", "target": acc, "kind": "missing",
                               "message": f"缺漏：沒有{names[acc]}真人發音"
                                          + ("（來源已查遍）" if fv.status == catalog.SHORT else "")})
    return {
        "lemma": lemma, "display": lexemes[0].lemma if lexemes else lemma_in,
        "target_language": t, "native_language": n,
        "lexemes": [{"id": lx.id, "pos": lx.pos, "status": lx.status, "cefr": lx.cefr,
                     "zipf": lx.zipf} for lx in lexemes],
        "fields": fields, "senses": senses, "examples": examples, "relations": relations,
        "morphemes": morphemes,
        "audio": word_audio(s, [lx.id for lx in lexemes]),
        **word_images(s, [lx.id for lx in lexemes], n),
        "issues": issues,
        "summary": {
            "target": {"complete": sum(x["status"] in OK for x in target_fields),
                       "total": len(target_fields)},
            "native": {"complete": sum(x["status"] in OK for x in native_fields),
                       "total": len(native_fields)}},
    }


def field_detail(s: Session, t: str, n: str, lemma_in: str, field_key: str) -> dict:
    lemma = normalize_lemma(lemma_in, t)
    nk = n if catalog.FIELD[field_key].scope == "native" else "*"
    cands = s.execute(select(m.FieldCandidate).where(
        m.FieldCandidate.target_language == t, m.FieldCandidate.lemma == lemma,
        m.FieldCandidate.native_language == nk, m.FieldCandidate.field == field_key)
        .order_by(m.FieldCandidate.source, m.FieldCandidate.id)).scalars().all()
    fv = s.execute(select(m.FieldValue).where(
        m.FieldValue.target_language == t, m.FieldValue.native_language == n,
        m.FieldValue.lemma == lemma, m.FieldValue.field == field_key)).scalar_one_or_none()
    prov = s.execute(select(m.FieldProvenance).where(
        m.FieldProvenance.field_value_id == fv.id)).scalars().all() if fv else []
    adopted = {p.candidate_id for p in prov}
    override = s.execute(select(m.UserOverride).where(
        m.UserOverride.target_language == t, m.UserOverride.native_language == n,
        m.UserOverride.lemma == lemma, m.UserOverride.field == field_key)).scalar_one_or_none()
    return {
        "field": field_key, "label": catalog.FIELD[field_key].label,
        "status": fv.status if fv else "not_run", "items": fv.items if fv else [],
        "override": {"items": override.items, "note": override.note,
                     "updated_at": override.updated_at} if override else None,
        "provenance": [{"source": p.source, "item_key": p.item_key, "position": p.position,
                        "strategy": p.strategy, "snapshot_id": p.snapshot_id,
                        "processed_at": p.processed_at} for p in prov],
        "candidates": [{"id": c.id, "source": c.source, "value": c.value, "key": c.item_key,
                        "slot": c.slot, "confidence": c.confidence, "valid": c.valid,
                        "invalid_reason": c.invalid_reason, "license": c.license,
                        "attribution": c.attribution, "source_record_id": c.source_record_id,
                        "retrieved_at": c.retrieved_at, "adopted": c.id in adopted,
                        "raw_value": c.raw_value} for c in cands],
    }


def coverage(s: Session, t: str, n: str, q: str | None = None, only: str | None = None,
             limit: int = 100, offset: int = 0) -> dict:
    rows = s.execute(select(m.FieldValue.lemma, m.FieldValue.field, m.FieldValue.status).where(
        m.FieldValue.target_language == t, m.FieldValue.native_language == n)).all()
    per_word: dict[str, dict] = {}
    per_field: dict[str, dict] = {}
    for lemma, f, st in rows:
        if f not in catalog.FIELD:
            continue
        scope = catalog.FIELD[f].scope
        w = per_word.setdefault(lemma, {"lemma": lemma, "target": [0, 0], "native": [0, 0],
                                        "failed": 0, "missing": 0, "override": 0})
        pf = per_field.setdefault(f, {"field": f, "label": catalog.FIELD[f].label,
                                      "block": catalog.FIELD[f].block, "scope": scope,
                                      "counts": {}})
        pf["counts"][st] = pf["counts"].get(st, 0) + 1
        if st in ("unset", "unavailable"):
            continue
        w[scope][1] += 1
        if st in OK:
            w[scope][0] += 1
        w["failed"] += st == "failed"
        w["missing"] += st in ("missing", "partial", catalog.SHORT)
        w["override"] += st == "user_override"
    words = sorted(per_word.values(), key=lambda x: x["lemma"])
    if q:
        ql = q.lower()
        words = [w for w in words if ql in w["lemma"]]
    if only == "incomplete":
        words = [w for w in words if w["failed"] or w["missing"]]
    elif only == "failed":
        words = [w for w in words if w["failed"]]
    for pf in per_field.values():
        c = pf["counts"]
        relevant = sum(v for k, v in c.items() if k not in ("unset", "unavailable"))
        pf["rate"] = round(sum(c.get(k, 0) for k in OK) / relevant, 3) if relevant else None
    fields = sorted(per_field.values(), key=lambda x: [f.key for f in catalog.FIELDS].index(
        x["field"]))
    return {"target_language": t, "native_language": n, "total_words": len(per_word),
            "words": words[offset: offset + limit], "matched": len(words), "fields": fields}


def dashboard(s: Session) -> dict:
    pairs = []
    stats = s.execute(text("""
        SELECT target_language, native_language, count(DISTINCT lemma) AS words,
          count(*) FILTER (WHERE status IN ('complete','user_override','none','not_applicable')) AS ok,
          count(*) FILTER (WHERE status IN ('missing','partial','short')) AS missing,
          count(*) FILTER (WHERE status = 'failed') AS failed,
          count(*) FILTER (WHERE status NOT IN ('unset','unavailable','skipped')) AS relevant,
          field
        FROM field_values GROUP BY target_language, native_language, field""")).all()
    agg: dict[tuple, dict] = {}
    for r in stats:
        key = (r.target_language, r.native_language)
        a = agg.setdefault(key, {"words": 0, "target": [0, 0], "native": [0, 0], "missing": 0,
                                 "failed": 0, "fields": {}})
        a["words"] = max(a["words"], r.words)
        if r.field not in catalog.FIELD:
            continue
        scope = catalog.FIELD[r.field].scope
        a[scope][0] += r.ok
        a[scope][1] += r.relevant
        a["missing"] += r.missing
        a["failed"] += r.failed
        a["fields"][r.field] = (r.ok, r.relevant)
    for (t, n), a in sorted(agg.items()):
        f = a["fields"]

        def rate(key):
            ok, rel = f.get(key, (0, 0))
            return round(ok / rel, 3) if rel else None

        pairs.append({"target_language": t, "native_language": n, "words": a["words"],
                      "target_rate": round(a["target"][0] / a["target"][1], 3) if a["target"][1] else None,
                      "native_rate": round(a["native"][0] / a["native"][1], 3) if a["native"][1] else None,
                      "example_pairing_rate": rate("example_translation"),
                      "derived_meaning_rate": rate("derived_native_meaning"),
                      "missing": a["missing"], "failed": a["failed"]})
    running = s.execute(select(m.ImportJob).where(m.ImportJob.status.in_(
        ("queued", "running", "pausing", "cancelling", "paused"))).order_by(m.ImportJob.id.desc())
    ).scalars().all()
    since = datetime.now(timezone.utc) - timedelta(days=1)
    health = []
    for r in s.execute(text("""
            SELECT source, count(*) FILTER (WHERE status = 'succeeded') AS ok,
                   count(*) FILTER (WHERE status = 'missing') AS missing,
                   count(*) FILTER (WHERE status = 'failed') AS failed,
                   max(looked_up_at) AS last
            FROM source_lookups WHERE looked_up_at > :since GROUP BY source"""),
            {"since": since}).all():
        if r.source in catalog.SOURCES and not catalog.SOURCES[r.source].implemented:
            continue  # no adapter yet: nothing to report on
        total = r.ok + r.missing + r.failed
        health.append({"source": r.source, "name": catalog.SOURCES[r.source].name
                       if r.source in catalog.SOURCES else r.source, "ok": r.ok,
                       "missing": r.missing, "failed": r.failed,
                       "error_rate": round(r.failed / total, 3) if total else 0, "last": r.last,
                       "breaker_open": http._open_until.get(r.source, 0) > datetime.now().timestamp()})
    usage = [{"source": u.source, "day": u.day, "requests": u.requests, "errors": u.errors,
              "cache_hits": u.cache_hits, "avg_ms": int(u.ms_total / u.requests) if u.requests else 0}
             for u in s.execute(select(m.ApiUsage).order_by(m.ApiUsage.day.desc(),
                                                            m.ApiUsage.source).limit(60)).scalars()]
    db_bytes = s.execute(text("SELECT pg_database_size(current_database())")).scalar()
    audio_bytes = s.execute(select(func.coalesce(func.sum(m.AudioAsset.size_bytes), 0))).scalar()
    counts = {k: s.execute(select(func.count()).select_from(t)).scalar() for k, t in (
        ("lexemes", m.Lexeme), ("senses", m.Sense), ("examples", m.Example),
        ("audio", m.AudioAsset), ("candidates", m.FieldCandidate))}
    image_bytes = s.execute(select(func.coalesce(func.sum(m.ImageAsset.size_bytes), 0))).scalar()
    # 已核准圖片覆蓋率: the senses pictures are fetched for (a noun's first two)
    # that have an approved one.
    img = s.execute(text("""
        SELECT count(*) AS eligible,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM sense_images si WHERE si.sense_id = sn.id
                                              AND si.review_status = 'approved')) AS approved,
               (SELECT count(*) FROM sense_images WHERE review_status = 'pending') AS pending
        FROM senses sn JOIN lexemes l ON l.id = sn.lexeme_id
        WHERE l.status = 'full' AND l.pos = 'noun' AND sn.ordinal < 2""")).one()
    return {"pairs": pairs, "running_jobs": [
        {"id": j.id, "status": j.status, "target_language": j.target_language,
         "native_language": j.native_language, "checkpoint": j.checkpoint, "total": j.total}
        for j in running], "source_health": health, "api_usage": usage,
            "storage": {"database_bytes": db_bytes, "audio_bytes": int(audio_bytes),
                        "image_bytes": int(image_bytes)},
            "images": {"eligible_senses": img.eligible, "approved_senses": img.approved,
                       "pending": img.pending,
                       "coverage": round(img.approved / img.eligible, 3) if img.eligible else None},
            "counts": counts}


def word_audio(s: Session, lexeme_ids: list[int]) -> list[dict]:
    """The word's recorded pronunciations, playable on the word page."""
    if not lexeme_ids:
        return []
    out, seen = [], set()
    for p, a, lx in s.execute(select(m.Pronunciation, m.AudioAsset, m.Lexeme).join(
            m.AudioAsset, m.AudioAsset.id == m.Pronunciation.audio_asset_id).join(
            m.Lexeme, m.Lexeme.id == m.Pronunciation.lexeme_id).where(
            m.Pronunciation.lexeme_id.in_(lexeme_ids)).order_by(
            m.Pronunciation.is_default.desc(), m.Pronunciation.ordinal)).all():
        if a.id in seen:
            continue
        seen.add(a.id)
        out.append({"id": a.id, "lexeme_id": lx.id, "pos": lx.pos, "accent": a.accent or p.accent,
                    "default": p.is_default, "status": a.status, "source": a.source,
                    "source_page": a.source_page, "license": a.license,
                    "attribution": a.attribution, "duration_s": a.duration_s,
                    "on_disk": bool(a.path) and (config.MEDIA / a.path).exists()})
    return out


def word_images(s: Session, lexeme_ids: list[int], native: str) -> dict:
    """Approved sense pictures with the AI labels on them (the meanings
    looked up in the lexicon), and how many still wait for review."""
    if not lexeme_ids:
        return {"images": [], "images_pending": 0}
    rows = s.execute(text("""
        SELECT si.id, si.sense_id, si.review_status, si.semantic_score, sn.ordinal, l.pos,
               d.text AS gloss, t.text AS native, a.id AS asset_id, a.width, a.height, a.author,
               a.license_code, a.license_url, a.page_url, a.attribution, a.tags, a.tag_status,
               a.dropped_tags
        FROM sense_images si JOIN senses sn ON sn.id = si.sense_id
        JOIN lexemes l ON l.id = sn.lexeme_id JOIN image_assets a ON a.id = si.image_asset_id
        LEFT JOIN definitions d ON d.sense_id = sn.id AND d.language = l.language
        LEFT JOIN sense_translations t ON t.sense_id = sn.id AND t.native_language = :n
        WHERE sn.lexeme_id = ANY(:ids) ORDER BY l.id, sn.ordinal, si.ordinal, si.id"""),
        {"ids": lexeme_ids, "n": native}).mappings().all()
    words = {tg["word"].lower() for r in rows for tg in (r["tags"] or []) if tg.get("word")}
    means = {}
    if words:
        for w, text_ in s.execute(text("""
            SELECT DISTINCT ON (l.normalized) l.normalized, t.text FROM lexemes l
            JOIN senses sn ON sn.lexeme_id = l.id
            JOIN sense_translations t ON t.sense_id = sn.id AND t.native_language = :n
            WHERE l.normalized = ANY(:w) AND l.status = 'full'
            ORDER BY l.normalized, l.id, sn.ordinal"""), {"w": list(words), "n": native}).all():
            means[w] = text_.split("、")[0]
    images = [{**{k: r[k] for k in r.keys() if k != "tags"},
               "tags": [{**tg, "native": means.get(tg["word"].lower())} for tg in (r["tags"] or [])]}
              for r in rows if r["review_status"] == "approved"]
    return {"images": images,
            "images_pending": sum(1 for r in rows if r["review_status"] == "pending")}


def audio_library(s: Session, status: str | None = None, q: str | None = None,
                  limit: int = 200) -> dict:
    query = select(m.AudioAsset).order_by(m.AudioAsset.id.desc())
    if status:
        query = query.where(m.AudioAsset.status == status)
    assets = s.execute(query.limit(2000)).scalars().all()
    users: dict[int, list] = {}
    for p, lx in s.execute(select(m.Pronunciation, m.Lexeme).join(
            m.Lexeme, m.Lexeme.id == m.Pronunciation.lexeme_id).where(
            m.Pronunciation.audio_asset_id.is_not(None))).all():
        lst = users.setdefault(p.audio_asset_id, [])
        if not any(u["lexeme_id"] == lx.id for u in lst):
            lst.append({"lexeme_id": lx.id, "lemma": lx.lemma, "pos": lx.pos,
                        "default": p.is_default})
    rows = []
    for a in assets:
        used = users.get(a.id, [])
        if q and not any(q.lower() in u["lemma"].lower() for u in used) \
                and q.lower() not in (a.source_url or "").lower():
            continue
        on_disk = bool(a.path) and (config.MEDIA / a.path).exists()
        rows.append({"id": a.id, "language": a.language, "accent": a.accent, "speaker": a.speaker,
                     "source": a.source, "source_url": a.source_url, "source_page": a.source_page,
                     "license": a.license, "attribution": a.attribution, "mime": a.mime,
                     "duration_s": a.duration_s, "sample_rate": a.sample_rate,
                     "channels": a.channels, "size_bytes": a.size_bytes, "sha256": a.sha256,
                     "path": a.path, "status": a.status, "error": a.error, "on_disk": on_disk,
                     "used_by": used, "orphan": not used})
    known = {a.path for a in assets if a.path}
    stray = []
    root = config.MEDIA / "audio"
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file() and not p.name.startswith(".tmp-"):
                rel = p.relative_to(config.MEDIA).as_posix()
                if rel not in known:
                    stray.append(rel)
    # Words whose adopted audio items have no ready file.
    missing = []
    for lemma, t, items in s.execute(select(m.FieldValue.lemma, m.FieldValue.target_language,
                                            m.FieldValue.items).where(
            m.FieldValue.field == "audio")).all():
        urls = [i.get("url") for i in items if i.get("url")]
        if not urls and not any(i.get("tts") for i in items):
            continue
        ready = s.execute(select(func.count()).select_from(m.AudioAsset).where(
            m.AudioAsset.source_url.in_(urls), m.AudioAsset.status == "ready")).scalar() if urls else 0
        if urls and not ready:
            missing.append({"lemma": lemma, "language": t, "urls": urls[:3]})
    return {"assets": rows[:limit], "total": len(rows),
            "orphans": [r["id"] for r in rows if r["orphan"]],
            "stray_files": stray[:200], "missing": missing[:200],
            "failed": sum(1 for r in rows if r["status"] == "failed")}
