"""Processing one headword for one language direction.

For each requested field, in dependency order:
  1. a user override wins outright;
  2. no enabled policy step → 「未設定」 (nothing is inherited or called);
  3. otherwise each enabled step, in order, is asked while the strategy
     still wants more: adapter lookup → normalize → validate → min
     confidence / max results → Resolver;
  4. candidates (every source's evidence), the adopted value and its
     provenance are stored — unless this is a dry run.
Then the adopted values are projected into the dictionary tables.

Candidates of target-language fields are shared by every native
language ('*'); adopted values are kept per direction, so one
direction's policy never overwrites another's.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import catalog
from . import models as m
from . import policies
from .adapters import ADAPTERS, Candidate, Context, SourceError
from .adapters.base import localize
from .adapters.local import LEVELS, sentence_level, word_forms, word_level
from .adapters.tatoeba import length_level
from .resolver import Resolver, status_of
from .text import example_key, normalize_lemma

MODES = {"fill_missing": "缺值補齊", "force_refresh": "強制刷新", "validate_only": "只驗證",
         "dry_run": "乾跑", "reresolve": "重新解析"}

# field → fields it needs first
DEPENDS: dict[str, list[str]] = {
    "definition": ["pos"],
    "native_definition": ["definition"],
    "usage_labels": ["definition"],
    "stress": ["ipa"],
    "derivation_relation": ["derived_terms"],
    "derived_pos": ["derived_terms"],
    "derived_native_meaning": ["derived_terms"],
    "etymology_native": ["etymology_text"],
    "morphemes": ["origin_language", "etymology_text"],
    "morphemes_native": ["morphemes"],
    "root": ["morphemes"],
    "prefix": ["morphemes"],
    "suffix": ["morphemes"],
    "example_sentences": catalog.FORM_FIELDS,
    "example_difficulty": ["example_sentences"],
    "example_sense": ["example_sentences", "definition"],
    "example_translation": ["example_sentences"],
    "image_alt_native": ["sense_image"],
    **{f"{r}_native": [r] for r in catalog.RELATION_FIELDS},
}


def field_order(target: str, wanted: list[str] | None = None) -> list[str]:
    """Requested fields plus their dependencies, dependencies first."""
    available = [f.key for f in catalog.fields_for(target)]
    need = set(wanted or available)
    stack = list(need)
    while stack:
        f = stack.pop()
        for d in DEPENDS.get(f, []):
            if d in available and d not in need:
                need.add(d)
                stack.append(d)
    out: list[str] = []
    seen: set[str] = set()

    def visit(f):
        if f in seen:
            return
        seen.add(f)
        for d in DEPENDS.get(f, []):
            if d in need:
                visit(d)
        out.append(f)

    for f in available:
        if f in need:
            visit(f)
    return out


def expected_slots(field_key: str, ctx: Context) -> set[str] | None:
    if field_key == "definition":
        pos = {i["pos"] for i in ctx.items("pos") if i.get("pos")}
        return pos or None
    if field_key == "native_definition":
        return {i["sense_key"] for i in ctx.items("definition") if i.get("sense_key")}
    if field_key in catalog.RELATION_NATIVE:
        return {i["word"].lower() for i in ctx.items(catalog.RELATION_NATIVE[field_key])}
    if field_key in ("derived_native_meaning", "derivation_relation", "derived_pos"):
        return {i["word"].lower() for i in ctx.items("derived_terms")}
    if field_key in ("example_translation", "example_difficulty", "example_sense"):
        return {i.get("key") or example_key(i.get("text", ""))
                for i in ctx.items("example_sentences")}
    if field_key == "morphemes_native":
        return {f"{i}:{p.get('part', '')}" for bd in ctx.items("morphemes")[:1]
                for i, p in enumerate(bd.get("parts", []))}
    if field_key == "image_alt_native":
        return {i.get("key") for i in ctx.items("sense_image")}
    if field_key in catalog.LEVELED:
        return set(LEVELS)
    if field_key == "audio" and ctx.target == "en":
        return set(catalog.AUDIO_ACCENTS)
    return None


def not_applicable(field_key: str, ctx: Context) -> str | None:
    """Why this field can't apply to the word, if it can't."""
    pos_needed = catalog.FORM_POS.get(field_key)
    if pos_needed:
        have = {i.get("pos") for i in ctx.items("pos")}
        if have and pos_needed not in have:
            return "不是" + {"verb": "動詞", "noun": "名詞", "adj": "形容詞"}[pos_needed]
    if field_key == "example_sense" and field_key_done(ctx, "definition") \
            and not ctx.items("definition"):
        return "沒有詞義可對應（片語沒有字典釋義）"
    f = catalog.FIELD.get(field_key)
    deps = DEPENDS.get(field_key, [])
    if f and f.scope == "native" and deps and all(
            field_key_done(ctx, d) and not ctx.items(d) for d in deps):
        return "沒有需要翻譯的內容"
    return None


def field_key_done(ctx: Context, field_key: str) -> bool:
    """The field was looked at in this run or before."""
    return field_key in ctx.resolved


def level_candidates(cands: list[Candidate], field_key: str, ctx: Context) -> None:
    """Put each example / relation word in its CEFR level's slot, so every
    level A1–C2 is filled on its own (catalog.LEVELED). Sentences are
    leveled on the words around the headword; relation words on their own
    level."""
    forms = word_forms(ctx)
    words = {c.value.get("word", "").lower() for c in cands}
    kept: list[tuple[set, str]] = []
    for c in cands:
        if field_key == "example_sentences":
            text = c.value.get("text", "")
            level = sentence_level(text, forms) if ctx.target == "en" else length_level(text)
            c.value = {**c.value, "level": level}
            # Near repeats take no place of their own (「A rolling stone gathers
            # no moss」 is a saying / is a proverb): the same translation, 80%
            # of the words shared, or one word swapped in a longer sentence.
            toks = set(re.findall(r"[a-zà-ÿ']+", text.lower()))
            tr = str(c.value.get("translation") or "").strip()

            def repeats(k, t):
                return bool((tr and tr == t) or toks and (
                    len(toks & k) / len(toks | k) >= 0.8
                    or (len(toks | k) >= 6 and len(toks ^ k) <= 2)))
            if c.valid and any(repeats(k, t) for k, t in kept):
                c.valid, c.invalid_reason = False, "與另一句例句幾乎相同"
            elif c.valid:
                kept.append((toks, tr))
        else:
            level = word_level(c.value.get("word", ""), ctx.target)
            c.value = {**c.value, "cefr": level}
            noise = _relation_noise(c.value.get("word", "").lower(), forms, ctx.lemma, words)
            if noise and c.valid:
                c.valid, c.invalid_reason = False, noise
        c.slot = level
    if field_key != "example_sentences":
        # Within a level, the most related words first (sources list them
        # by frequency).
        cands.sort(key=lambda c: -c.confidence)


def _relation_noise(w: str, forms: frozenset[str], lemma: str, words: set[str]) -> str | None:
    """Why a relation word isn't worth learning next to the headword."""
    if w in forms:
        return "詞條本身的詞形"
    if "-" in w:
        return "連字號複合詞"
    if len(lemma) >= 5 and " " not in w and _edits(w, lemma) <= 2:
        return "詞條的拼字變體"
    for suffix in ("s", "es", "d", "ed", "ing"):
        if w.endswith(suffix) and w[: -len(suffix)] in words:
            return "另一個關係詞的詞形"
    if w.endswith("ing") and w[:-3] + "e" in words:
        return "另一個關係詞的詞形"
    return None


def _edits(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def item_of(c: Candidate) -> dict:
    """What a resolved value looks like: the value plus its evidence."""
    out = dict(c.value)
    out.update({"key": c.key, "source": c.source, "slot": c.slot,
                "confidence": round(c.confidence, 3)})
    if c.source == "ai_translate":
        out["ai"] = True
    return out


@dataclass
class StepReport:
    source: str
    position: int
    status: str  # succeeded / missing / failed / skipped
    reason: str = ""
    ms: int = 0
    count: int = 0
    adopted: int = 0
    candidates: list = field(default_factory=list)
    error_kind: str | None = None
    raw_preview: object = None


@dataclass
class FieldReport:
    field: str
    status: str  # complete / partial / missing / failed / user_override / unset / skipped
    items: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    steps: list[StepReport] = field(default_factory=list)
    strategy: str | None = None


# ── Candidate storage ─────────────────────────────────────────────────

def _native_key(field_key: str, native: str) -> str:
    return native if catalog.FIELD[field_key].scope == "native" else "*"


def store_candidates(s: Session, ctx: Context, field_key: str, source: str, cands: list[Candidate],
                     status: str, error: str | None) -> dict[str, int]:
    nk = _native_key(field_key, ctx.native)
    s.execute(delete(m.FieldCandidate).where(
        m.FieldCandidate.target_language == ctx.target, m.FieldCandidate.lemma == ctx.lemma,
        m.FieldCandidate.native_language == nk, m.FieldCandidate.field == field_key,
        m.FieldCandidate.source == source))
    ids: dict[str, int] = {}
    seen = set()
    for c in cands:
        if c.key in seen:
            continue
        seen.add(c.key)
        row = m.FieldCandidate(
            target_language=ctx.target, lemma=ctx.lemma, native_language=nk, field=field_key,
            source=source, language=c.language, item_key=c.key[:500], slot=c.slot or "",
            value=c.value, source_record_id=str(c.source_record_id or "")[:500],
            confidence=c.confidence, license=c.license, attribution=c.attribution,
            raw_value=_small(c.raw_value), valid=c.valid, invalid_reason=c.invalid_reason,
            snapshot_id=c.snapshot_id, retrieved_at=c.retrieved_at)
        s.add(row)
        s.flush()
        ids[c.key] = row.id
    stmt = pg_insert(m.SourceLookup).values(
        target_language=ctx.target, lemma=ctx.lemma, native_language=nk, field=field_key,
        source=source, status=status, count=len(cands), error=error)
    s.execute(stmt.on_conflict_do_update(
        constraint="uq_lookup", set_={"status": status, "count": len(cands), "error": error,
                                      "looked_up_at": datetime.now(timezone.utc)}))
    return ids


def stored_candidates(s: Session, ctx: Context, field_key: str, source: str):
    """(candidates, lookup status) from an earlier lookup, or None."""
    nk = _native_key(field_key, ctx.native)
    look = s.execute(select(m.SourceLookup).where(
        m.SourceLookup.target_language == ctx.target, m.SourceLookup.lemma == ctx.lemma,
        m.SourceLookup.native_language == nk, m.SourceLookup.field == field_key,
        m.SourceLookup.source == source)).scalar_one_or_none()
    if look is None or look.status == "failed":
        return None
    rows = s.execute(select(m.FieldCandidate).where(
        m.FieldCandidate.target_language == ctx.target, m.FieldCandidate.lemma == ctx.lemma,
        m.FieldCandidate.native_language == nk, m.FieldCandidate.field == field_key,
        m.FieldCandidate.source == source).order_by(m.FieldCandidate.id)).scalars().all()
    cands = [Candidate(field_key, r.language, r.value, r.item_key, source=r.source, slot=r.slot,
                       source_record_id=r.source_record_id, confidence=r.confidence,
                       license=r.license, attribution=r.attribution, raw_value=r.raw_value,
                       retrieved_at=r.retrieved_at, valid=r.valid, invalid_reason=r.invalid_reason,
                       snapshot_id=r.snapshot_id) for r in rows]
    for c, r in zip(cands, rows):
        c._id = r.id
        localize(c, ctx)  # stored before the Taiwan-usage rule
    return cands, look.status


def _small(raw, limit: int = 4000):
    import json
    if raw is None:
        return None
    try:
        text = json.dumps(raw, ensure_ascii=False, default=str)
    except TypeError:
        return {"repr": str(raw)[:limit]}
    if len(text) <= limit:
        return raw if isinstance(raw, dict) else {"value": raw}
    return {"truncated": text[:limit]}


# ── One field ─────────────────────────────────────────────────────────

class Recorder:
    """Where attempts and errors go (a job, or nowhere for tests)."""

    def attempt(self, lemma, field_key, source, status, ms, count, error=None, kind=None,
                attempts=1, record_id=None):
        pass


def resolve_field(s: Session, ctx: Context, field_key: str, policy, steps, *, mode: str,
                  sources: list[str] | None = None, recorder: Recorder | None = None,
                  write: bool = True, with_raw: bool = False) -> FieldReport:
    recorder = recorder or Recorder()
    nk = ctx.native
    override = s.execute(select(m.UserOverride).where(
        m.UserOverride.target_language == ctx.target, m.UserOverride.lemma == ctx.lemma,
        m.UserOverride.native_language == nk, m.UserOverride.field == field_key)
    ).scalar_one_or_none()
    if override is not None:
        ctx.resolved[field_key] = override.items
        rep = FieldReport(field_key, "user_override", override.items)
        if write:
            _save_value(s, ctx, field_key, rep, policy, [])
        return rep
    enabled = [st for st in steps if st.enabled]
    if policy is None or not enabled:
        ctx.resolved[field_key] = []
        rep = FieldReport(field_key, "unset")
        if write:
            _save_value(s, ctx, field_key, rep, policy, [])
        return rep
    why = not_applicable(field_key, ctx)
    if why:  # nothing to ask for: a noun's past tense, a translation of nothing
        ctx.resolved[field_key] = []
        rep = FieldReport(field_key, "not_applicable", strategy=policy.strategy)
        rep.steps.append(StepReport("rule", 0, "skipped", reason=why))
        if write:
            _save_value(s, ctx, field_key, rep, policy, [])
        return rep
    existing = s.execute(select(m.FieldValue).where(
        m.FieldValue.target_language == ctx.target, m.FieldValue.lemma == ctx.lemma,
        m.FieldValue.native_language == nk, m.FieldValue.field == field_key)).scalar_one_or_none()
    if mode == "fill_missing" and existing is not None and existing.status in catalog.SETTLED \
            and existing.policy_version == policy.version:
        ctx.resolved[field_key] = existing.items
        return FieldReport(field_key, "skipped", existing.items, strategy=policy.strategy)
    if mode == "validate_only":
        return _validate_only(s, ctx, field_key, existing, policy)

    expected = expected_slots(field_key, ctx)
    res = Resolver(policy.strategy, policy.max_items, expected,
                   per_slot=catalog.TARGETED.get(field_key) if expected is not None else None,
                   only_missing=field_key == "audio")
    rep = FieldReport(field_key, "missing", strategy=policy.strategy)
    asked = errors = unavailable = 0
    stop = False
    for st in steps:
        src = catalog.SOURCES[st.source]
        step = StepReport(st.source, st.position, "skipped")
        rep.steps.append(step)
        if not st.enabled:
            step.reason = "已停用"
            continue
        if stop:
            step.reason = "前一個來源失敗且設定為不繼續"
            continue
        if sources is not None and st.source not in sources:
            step.reason = "此工作未選這個來源"
            continue
        ok, why = catalog.supports(st.source, ctx.target, ctx.native, field_key)
        if not ok:
            step.reason = f"不支援：{why}"
            recorder.attempt(ctx.lemma, field_key, st.source, "skipped", 0, 0, why, "unsupported")
            continue
        if not src.implemented:
            step.reason = "adapter 尚未實作"
            unavailable += 1
            recorder.attempt(ctx.lemma, field_key, st.source, "skipped", 0, 0, step.reason,
                             "not_implemented")
            continue
        if not res.wants_more(src.kind):
            step.reason = {"FIRST_VALID": "已有有效值", "APPEND_LIMITED": "已達上限",
                           "FILL_MISSING": "沒有缺項"}.get(policy.strategy, "不需要")
            recorder.attempt(ctx.lemma, field_key, st.source, "skipped", 0, 0, step.reason)
            continue
        if expected is not None and not expected:
            step.reason = "沒有需要處理的項目"
            continue
        ctx.memo[("missing_slots", field_key)] = res.missing() if expected is not None else None
        asked += 1
        started = time.time()
        cands, looked = None, None
        stored = []
        if mode == "reresolve":
            got = stored_candidates(s, ctx, field_key, st.source)
            if got is not None:
                cands, looked = got
                # Slots that appeared since (a new example sentence): ask the
                # source for those only, so nothing is fetched or translated twice.
                wanted = ctx.memo.get(("missing_slots", field_key))
                if wanted and policy.strategy == "FILL_MISSING":
                    left = set(wanted) - {c.slot for c in cands if c.valid}
                    if left:
                        ctx.memo[("missing_slots", field_key)] = left
                        stored, cands = cands, None
        try:
            if cands is None:
                ctx.timeout, ctx.retries = st.timeout_s, st.retries
                cands = ADAPTERS[st.source].lookup(field_key, ctx)
                snap = getattr(ADAPTERS[st.source], "snapshot", None)
                for c in cands:
                    c.snapshot_id = snap["id"] if snap else None
                cands = stored + [c for c in cands if c.key not in {x.key for x in stored}]
                looked = "succeeded" if any(c.valid for c in cands) else "missing"
                if write:
                    ids = store_candidates(s, ctx, field_key, st.source, cands, looked, None)
                    for c in cands:
                        c._id = ids.get(c.key)
        except SourceError as e:
            errors += 1
            step.status, step.reason, step.error_kind = "failed", str(e), e.kind
            step.ms = int((time.time() - started) * 1000)
            if write:
                store_candidates(s, ctx, field_key, st.source, [], "failed", str(e))
            recorder.attempt(ctx.lemma, field_key, st.source, "failed", step.ms, 0, str(e), e.kind,
                             attempts=st.retries + 1)
            if not st.continue_on_failure:
                stop = True
            continue
        except Exception as e:  # noqa: BLE001 — a parser bug must not kill the job
            errors += 1
            step.status, step.reason, step.error_kind = "failed", f"{type(e).__name__}: {e}", "parse"
            step.ms = int((time.time() - started) * 1000)
            recorder.attempt(ctx.lemma, field_key, st.source, "failed", step.ms, 0, step.reason,
                             "parse")
            if not st.continue_on_failure:
                stop = True
            continue
        step.ms = int((time.time() - started) * 1000)
        if field_key in catalog.LEVELED:
            level_candidates(cands, field_key, ctx)
        valid = [c for c in cands if c.valid and c.confidence >= st.min_confidence]
        if st.max_results:
            valid = valid[: st.max_results]
        step.count = len(valid)
        step.candidates = cands
        if with_raw:
            step.raw_preview = _raw_preview(ADAPTERS[st.source], ctx)
        step.adopted = res.add(st.position, st.source, valid)
        step.status = "succeeded" if valid else "missing"
        if not valid and cands:
            step.reason = "全部未通過驗證或低於最低可信度"
        recorder.attempt(ctx.lemma, field_key, st.source, step.status, step.ms, len(valid))
    adopted = res.result()
    if field_key == "audio":  # British first: the default recording
        order = {a: i for i, a in enumerate(catalog.AUDIO_ACCENTS)}
        adopted.sort(key=lambda a: order.get(a.candidate.slot, len(order)))
    missing = res.missing() if expected is not None else set()
    rep.items = [item_of(a.candidate) for a in adopted]
    rep.missing = sorted(missing)
    rep.status = status_of(adopted, missing, expected, errors, asked)
    if expected is not None and not expected:
        rep.status = "complete"  # nothing to fill (e.g. no examples → no translations)
    elif not adopted and asked == 0 and unavailable:
        rep.status = "unavailable"  # every source's adapter is still to be written
    elif not adopted and asked and not errors and field_key in catalog.MAY_BE_EMPTY:
        rep.status = "none"  # every source answered: this word has none (查無)
    elif rep.status in ("partial", "missing") and rep.missing and asked and not errors \
            and field_key in catalog.TARGETED:
        # Every source, AI last, was asked and answered, and a level is still
        # under three (or no British recording exists): 「缺漏」, with
        # rep.missing naming the levels / accents. Not asked again by fill_missing.
        rep.status = catalog.SHORT
    ctx.resolved[field_key] = rep.items
    if write:
        _save_value(s, ctx, field_key, rep, policy, adopted)
    return rep


def _raw_preview(adapter, ctx):
    k = (adapter.key, ctx.target, ctx.lemma)
    raw = ctx.memo.get(k)
    if raw is None:
        raw = ctx.memo.get((adapter.key, ctx.target, ctx.native, ctx.lemma))
    return _small(raw, 3000)


def _save_value(s: Session, ctx: Context, field_key: str, rep: FieldReport, policy, adopted):
    row = s.execute(select(m.FieldValue).where(
        m.FieldValue.target_language == ctx.target, m.FieldValue.lemma == ctx.lemma,
        m.FieldValue.native_language == ctx.native, m.FieldValue.field == field_key)
    ).scalar_one_or_none()
    if row is None:
        row = m.FieldValue(target_language=ctx.target, lemma=ctx.lemma,
                           native_language=ctx.native, field=field_key)
        s.add(row)
    row.status, row.items, row.missing = rep.status, rep.items, rep.missing
    row.policy_version = policy.version if policy else None
    row.resolved_at = datetime.now(timezone.utc)
    s.flush()
    s.execute(delete(m.FieldProvenance).where(m.FieldProvenance.field_value_id == row.id))
    for a in adopted:
        s.add(m.FieldProvenance(field_value_id=row.id, candidate_id=getattr(a.candidate, "_id", None),
                                source=a.source, item_key=a.candidate.key[:500],
                                snapshot_id=a.candidate.snapshot_id,
                                strategy=policy.strategy if policy else "", position=a.position))


def _validate_only(s, ctx, field_key, existing, policy) -> FieldReport:
    """Re-check stored candidates with the current rules; nothing is fetched."""
    rows = s.execute(select(m.FieldCandidate).where(
        m.FieldCandidate.target_language == ctx.target, m.FieldCandidate.lemma == ctx.lemma,
        m.FieldCandidate.native_language == _native_key(field_key, ctx.native),
        m.FieldCandidate.field == field_key)).scalars().all()
    changed = 0
    for r in rows:
        c = Candidate(field_key, r.language, r.value, r.item_key, source=r.source, slot=r.slot)
        reason = ADAPTERS[r.source].validate(c, ctx) if r.source in ADAPTERS else None
        if (reason is None) != r.valid or reason != r.invalid_reason:
            r.valid, r.invalid_reason = reason is None, reason
            changed += 1
    items = existing.items if existing else []
    ctx.resolved[field_key] = items
    status = existing.status if existing else "missing"
    rep = FieldReport(field_key, status, items, list(existing.missing) if existing else [],
                      strategy=policy.strategy if policy else None)
    rep.steps.append(StepReport("validate", 0, "succeeded", reason=f"{len(rows)} 個候選值，"
                                f"{changed} 個驗證結果改變", count=len(rows)))
    return rep


# ── One headword ──────────────────────────────────────────────────────

def load_existing(s: Session, ctx: Context):
    for fv in s.execute(select(m.FieldValue).where(
            m.FieldValue.target_language == ctx.target, m.FieldValue.lemma == ctx.lemma,
            m.FieldValue.native_language == ctx.native)).scalars():
        ctx.resolved.setdefault(fv.field, fv.items)


def process_word(s: Session, target: str, native: str, word: str, fields: list[str] | None,
                 mode: str, *, sources: list[str] | None = None, recorder: Recorder | None = None,
                 run_policies=None, materialize_after: bool = True) -> list[FieldReport]:
    lemma = normalize_lemma(word, target)
    ctx = Context(target, native, lemma, word.strip(), refresh=(mode == "force_refresh"),
                  session=s)
    load_existing(s, ctx)
    run_policies = run_policies or policies.load_for_run(s, target, native)
    write = mode != "dry_run"
    reports = []
    images_wanted = [f for f in AUTO_IMAGE_FIELDS if fields is None or f in fields]
    for f in field_order(target, fields):
        if f in AUTO_IMAGE_FIELDS:
            continue  # after the word is stored (they bind to sense ids)
        policy, steps = run_policies.get(f, (None, []))
        # Dependencies not asked for are only resolved when there's no value yet.
        if fields and f not in fields and f in ctx.resolved:
            continue
        reports.append(resolve_field(s, ctx, f, policy, steps, mode=mode, sources=sources,
                                     recorder=recorder, write=write))
    if write and mode != "validate_only" and " " in lemma and fields is None \
            and not ctx.items("definition") and not ctx.items("pos"):
        # A scene phrase from a photo (pour coffee, in the kitchen): no
        # dictionary has it, so it is no entry (spec: 一般單字、片語、慣用語).
        remove_word(s, target, lemma)
        if recorder:
            recorder.attempt(lemma, "pos", "rule", "skipped", 0, 0,
                             "不是字典詞條（情境片語），不建立", "not_lexical")
        return reports
    if write and mode != "validate_only" and materialize_after:
        from .materialize import materialize
        # Parallel word shards may create the same related-word stubs. Keep the
        # short projection phase serialized while all network/model work remains parallel.
        if s.bind is not None and s.bind.dialect.name == "postgresql":
            s.execute(sql_text("SELECT pg_advisory_xact_lock(770000002)"))
        materialize(s, target, lemma, word.strip())
        if images_wanted:
            from . import images
            images.enqueue_fetch(s, target, native, lemma, images_wanted)
            reports += [FieldReport(f, "queued", strategy="DEFERRED") for f in images_wanted]
    return reports


def remove_word(s: Session, target: str, lemma: str) -> None:
    """Take a headword out of the lexicon: its values, candidates, lookups,
    entries and wordlist places (not the admin's own overrides)."""
    for model in (m.FieldValue, m.FieldCandidate, m.SourceLookup):
        s.execute(delete(model).where(model.target_language == target, model.lemma == lemma))
    s.execute(delete(m.MissingLexemeRequest).where(
        m.MissingLexemeRequest.target_language == target, m.MissingLexemeRequest.lemma == lemma))
    s.execute(delete(m.Lexeme).where(m.Lexeme.language == target, m.Lexeme.normalized == lemma))
    for wl in s.execute(select(m.Wordlist).where(m.Wordlist.language == target)).scalars():
        kept = [w for w in wl.words if normalize_lemma(w, target) != lemma]
        if len(kept) != len(wl.words):
            wl.words = kept


# Pictures are searched and downloaded per sense after the word is stored.
# 情境圖片 are a sense's pictures after its representative one.
AUTO_IMAGE_FIELDS = ("sense_image", "context_image", "thumbnail")


def fetch_images(s: Session, ctx: Context, wanted: list[str], run_policies, recorder) -> list:
    """images.auto_fetch for this word, reported as the image fields."""
    policy, steps = run_policies.get("sense_image", (None, []))
    if not any(st.enabled and st.source == "wikimedia_commons" for st in steps):
        return []
    from . import images
    started = time.time()
    try:
        # Pictures per sense: the 詞義圖片 policy's item count (spec).
        # Pictures already labelled with this word first: nothing to download
        # for a word other pictures show.
        images.share_existing(s, ctx.target, ctx.lemma)
        got = images.auto_fetch(s, ctx.target, ctx.native, ctx.lemma,
                                per_sense=(policy.max_items if policy and policy.max_items else 3))
        error = "；".join(got["errors"][:3]) or None
    except Exception as e:  # noqa: BLE001 — a network failure must not lose the word
        got, error = {"senses": 0, "images": 0, "errors": [str(e)]}, f"{type(e).__name__}: {e}"
    ms = int((time.time() - started) * 1000)
    counts = s.execute(sql_text("""SELECT count(*) AS pictures,
          count(*) FILTER (WHERE si.role = 'context') AS context,
          (SELECT count(*) FROM lexemes x WHERE x.language = :t AND x.normalized = :w
             AND x.status = 'full' AND x.pos = 'noun') AS nouns
        FROM sense_images si JOIN senses sn ON sn.id = si.sense_id
        JOIN lexemes l ON l.id = sn.lexeme_id
        WHERE l.language = :t AND l.normalized = :w AND si.review_status <> 'rejected'"""),
        {"t": ctx.target, "w": ctx.lemma}).one()
    have = counts.pictures

    def status_for(f):
        n = counts.context if f == "context_image" else have
        if n:
            return "complete"
        if not counts.nouns:
            return "not_applicable"  # pictures are fetched for nouns
        if error and not got["senses"]:
            return "failed"
        return "none"  # no concept with a picture, or no second picture
    if recorder:
        recorder.attempt(ctx.lemma, "sense_image", "wikimedia_commons",
                         "succeeded" if got["images"] or have else ("failed" if error else "missing"),
                         ms, got["images"], error, "http" if error else None)
    out = []
    for f in wanted:
        rep = FieldReport(f, status_for(f), [{"images": have, "downloaded": got["images"]}] if have else [],
                          strategy=policy.strategy if policy else None)
        rep.steps.append(StepReport("wikimedia_commons", 1000, "succeeded" if have else "missing",
                                    reason=error or "", ms=ms, count=got["images"]))
        ctx.resolved[f] = rep.items
        _save_value(s, ctx, f, rep, policy, [])
        out.append(rep)
    return out


def next_retry(attempts: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=min(3600, 30 * 2 ** attempts))
