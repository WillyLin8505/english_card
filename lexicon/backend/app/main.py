"""Lexicon admin API (spec section 08): 127.0.0.1:8770, X-API-Key from
the environment on every request except /health.

    python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8770
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field as PField
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import adapters, catalog, config, db, exporter, jobs, pipeline, policies, snapshots, views
from . import models as m
from .adapters import Context
from .text import normalize_lemma

app = FastAPI(title="Lexicon admin", version="1.0",
              description="語言資料來源管理與擷取後台（spec-01 第 08 節）")
@app.middleware("http")
async def _api_prefix(request: Request, call_next):
    # The built admin UI (served at /ui/) calls /api/…, like the dev proxy.
    path = request.scope["path"]
    if path == "/api" or path.startswith("/api/"):
        request.scope["path"] = path[4:] or "/"
    return await call_next(request)


app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def require_key(x_api_key: str | None = Header(default=None)):
    if not config.API_KEY:
        raise HTTPException(500, "伺服器沒有設定 LEXICON_API_KEY（見 .env.example）")
    if not x_api_key or not secrets.compare_digest(x_api_key, config.API_KEY):
        raise HTTPException(401, "缺少或錯誤的 X-API-Key")


Auth = Depends(require_key)
DB = Depends(db.get_session)
from . import images, issues
images.register(app, Auth)
issues.register(app, Auth)


@app.exception_handler(policies.PolicyError)
@app.exception_handler(jobs.JobError)
@app.exception_handler(snapshots.SnapshotError)
@app.exception_handler(exporter.ExportError)
async def _bad_request(request: Request, exc: Exception):
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.on_event("startup")
def _startup():
    with db.session_scope() as s:
        policies.seed(s)
        seed_wordlists(s)
        adapters.configure(s)


def seed_wordlists(s: Session):
    path = Path(__file__).with_name("seed_words.txt")
    if not path.exists():
        return
    groups: dict[str, list[str]] = {}
    current = "未分類"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#"):
            current = line.lstrip("# ").strip()
        elif line:
            groups.setdefault(current, []).append(line)
    groups["全部種子單字"] = [w for ws in groups.values() for w in ws]
    for name, words in groups.items():
        exists = s.execute(select(m.Wordlist).where(m.Wordlist.language == "en",
                                                    m.Wordlist.name == name)).scalar_one_or_none()
        if exists is None:
            s.add(m.Wordlist(language="en", name=name, words=words))


# ── Meta ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True, "keyConfigured": bool(config.API_KEY)}


@app.get("/meta", dependencies=[Auth])
def meta():
    return {
        "languages": [{"code": k, **v} for k, v in catalog.LANGUAGES.items()],
        "pairs": [{"target_language": t, "native_language": n} for t, n in catalog.PAIRS],
        "blocks": [{"key": k, "label": v} for k, v in catalog.BLOCKS],
        "fields": [{"key": f.key, "label": f.label, "block": f.block, "scope": f.scope,
                    "languages": f.languages, "description": f.description} for f in catalog.FIELDS],
        "strategies": catalog.STRATEGIES, "modes": pipeline.MODES,
    }


@app.get("/sources", dependencies=[Auth])
def sources(s: Session = DB):
    snaps = {}
    for r in s.execute(select(m.SourceSnapshot).where(m.SourceSnapshot.active.is_(True))).scalars():
        snaps.setdefault(r.source, []).append(snapshots.snapshot_dict(r))
    out = []
    for key, src in catalog.SOURCES.items():
        out.append({"key": key, "name": src.name, "kind": src.kind, "license": src.license,
                    "attribution": src.attribution, "url": src.url, "note": src.note,
                    "implemented": src.implemented,
                    "supports": {t: {f: sorted(n) for f, n in fs.items()}
                                 for t, fs in src.supports.items()},
                    "active_snapshots": snaps.get(key, [])})
    return out


# ── Policies ──────────────────────────────────────────────────────────

class StepBody(BaseModel):
    source: str
    enabled: bool = True
    timeout_s: float = 20
    retries: int = 2
    min_confidence: float = 0
    max_results: int | None = None
    continue_on_failure: bool = True


class PolicyBody(BaseModel):
    strategy: str
    max_items: int | None = None
    steps: list[StepBody] = []
    expected_version: int | None = None


class TestBody(BaseModel):
    word: str
    draft: PolicyBody | None = None
    refresh: bool = False


class CopyBody(BaseModel):
    to_fields: list[str]
    confirm: bool = False


@app.get("/policies/{t}/{n}", dependencies=[Auth])
def policy_overview(t: str, n: str, s: Session = DB):
    return policies.overview(s, t, n)


@app.get("/policies/{t}/{n}/{field}", dependencies=[Auth])
def get_policy(t: str, n: str, field: str, s: Session = DB):
    return policies.get(s, t, n, field)


@app.put("/policies/{t}/{n}/{field}", dependencies=[Auth])
def put_policy(t: str, n: str, field: str, body: PolicyBody, s: Session = DB):
    return policies.put(s, t, n, field, body.model_dump(exclude={"expected_version"}),
                        body.expected_version)


@app.post("/policies/{t}/{n}/{field}/restore-default", dependencies=[Auth])
def restore_policy(t: str, n: str, field: str, s: Session = DB):
    return policies.restore_default(s, t, n, field)


@app.post("/policies/{t}/{n}/{field}/copy", dependencies=[Auth])
def copy_policy(t: str, n: str, field: str, body: CopyBody, s: Session = DB):
    return policies.copy_to(s, t, n, field, body.to_fields, body.confirm)


@app.post("/policies/{t}/{n}/{field}/test", dependencies=[Auth])
def test_policy(t: str, n: str, field: str, body: TestBody, s: Session = DB):
    """Run this one field's policy (saved, or the unsaved draft) for a word:
    every step's raw result, normalized candidates, validation failures and
    the adopted value. Nothing is written except the 「最近測試」 note."""
    policies.check_field(t, n, field)
    word = body.word.strip()
    if not word:
        raise policies.PolicyError("請輸入測試單字")
    saved = s.execute(select(m.SourcePolicy).where(
        m.SourcePolicy.target_language == t, m.SourcePolicy.native_language == n,
        m.SourcePolicy.field == field)).scalar_one_or_none()
    if body.draft is not None:
        clean = policies.validate_body(t, n, field, body.draft.model_dump())
        policy = SimpleNamespace(strategy=body.draft.strategy, max_items=body.draft.max_items,
                                 version=-1)
        steps = [SimpleNamespace(position=(i + 1) * policies.GAP, **st)
                 for i, st in enumerate(clean)]
    else:
        policy, steps = saved, policies.steps_of(s, saved)
    adapters.configure(s)
    ctx = Context(t, n, normalize_lemma(word, t), word, refresh=body.refresh, session=s)
    pipeline.load_existing(s, ctx)
    run_pols = policies.load_for_run(s, t, n)
    deps = []
    for dep in pipeline.field_order(t, [field]):
        if dep == field:
            continue
        if ctx.resolved.get(dep):
            deps.append({"field": dep, "label": catalog.FIELD[dep].label, "from": "stored",
                         "count": len(ctx.resolved[dep])})
            continue
        p, st = run_pols.get(dep, (None, []))
        r = pipeline.resolve_field(s, ctx, dep, p, st, mode="dry_run", write=False)
        deps.append({"field": dep, "label": catalog.FIELD[dep].label, "from": "resolved now",
                     "count": len(r.items), "status": r.status})
    rep = pipeline.resolve_field(s, ctx, field, policy, steps, mode="dry_run", write=False,
                                 with_raw=True)
    adopted = {(i.get("source"), i.get("key")) for i in rep.items}
    out_steps = []
    for st in rep.steps:
        out_steps.append({
            "source": st.source, "name": catalog.SOURCES[st.source].name
            if st.source in catalog.SOURCES else st.source, "position": st.position,
            "status": st.status, "reason": st.reason, "ms": st.ms, "valid_count": st.count,
            "adopted": st.adopted, "error_kind": st.error_kind, "raw": st.raw_preview,
            "candidates": [{**c.public(), "adopted": (st.source, c.key) in adopted}
                           for c in st.candidates],
        })
    result = {"word": word, "lemma": ctx.lemma, "field": field, "status": rep.status,
              "pairs": _bilingual_pairs(ctx, field, rep.items),
              "strategy": policy.strategy if policy else None, "items": rep.items,
              "missing": rep.missing, "steps": out_steps, "dependencies": deps,
              "draft": body.draft is not None}
    if saved is not None:
        saved.last_test = jsonable_encoder({
            "word": word, "at": datetime.now(timezone.utc).isoformat(),
            "status": rep.status, "adopted": len(rep.items), "draft": body.draft is not None,
            "errors": sum(1 for x in rep.steps if x.status == "failed"),
            "sources": [{"source": x.source, "status": x.status} for x in rep.steps]})
    return jsonable_encoder(result)


NATIVE_OF = {"native_definition": "definition", "example_translation": "example_sentences",
             "derived_native_meaning": "derived_terms", "etymology_native": "etymology_text",
             **{f"{r}_native": r for r in catalog.RELATION_FIELDS}}


def _bilingual_pairs(ctx: Context, field: str, items: list[dict]) -> list[dict]:
    """For a native-language field: each target item next to its adopted
    native text (or the gap), for the side-by-side preview."""
    if field == "morphemes_native":
        got = {i.get("slot"): i for i in items}
        out = []
        for bd in ctx.items("morphemes")[:1]:
            for n, p in enumerate(bd.get("parts", []), 1):
                it = got.get(f"{n - 1}:{p.get('part', '')}")
                out.append({"n": n, "slot": f"{n - 1}:{p.get('part', '')}",
                            "target": f"{p.get('part')}（{p.get('meaning') or p.get('kind')}）",
                            "native": it.get("text") if it else None,
                            "source": it.get("source") if it else None,
                            "ai": bool(it and it.get("ai"))})
        return out
    dep = NATIVE_OF.get(field)
    if dep is None:
        return []
    by_slot = {str(i.get("slot") or i.get("sense_key") or i.get("example_key")
                   or (i.get("word") or "").lower()): i for i in items}
    out = []
    for n, it in enumerate(ctx.items(dep), 1):
        if field == "native_definition":
            slot, text = it.get("sense_key"), f"[{it.get('pos', '')}] {it.get('gloss', '')}"
        elif field == "example_translation":
            slot, text = it.get("key"), it.get("text", "")
        elif field == "etymology_native":
            slot, text = "", it.get("text", "")
        else:
            slot, text = (it.get("word") or "").lower(), it.get("word", "")
        got = by_slot.get(str(slot or ""))
        out.append({"n": n, "slot": slot, "target": text,
                    "native": got.get("text") if got else None,
                    "source": got.get("source") if got else None,
                    "ai": bool(got and got.get("ai"))})
    return out


# ── Imports ───────────────────────────────────────────────────────────

class ImportBody(BaseModel):
    target_language: str
    native_language: str
    mode: str = "fill_missing"
    words: list[str] | None = None
    wordlist: str | None = None
    fields: list[str] | None = None
    sources: list[str] | None = None
    note: str = ""
    parallelism: int = PField(default=1, ge=1, le=8)


@app.post("/imports", dependencies=[Auth], status_code=201)
def create_import(body: ImportBody, s: Session = DB,
                  idempotency_key: str | None = Header(default=None)):
    shards = jobs.create_shards(s, body.model_dump(), idempotency_key)
    result = jobs.job_dict(shards[0])
    result.update({"shard_ids": [j.id for j in shards], "parallelism": len(shards),
                   "batch_total": sum(j.total for j in shards)})
    return result


@app.post("/imports/estimate", dependencies=[Auth])
def estimate_import(body: ImportBody, s: Session = DB):
    return jobs.estimate(s, body.model_dump())


@app.get("/imports", dependencies=[Auth])
def list_imports(status: str | None = None, limit: int = 50, s: Session = DB):
    q = select(m.ImportJob).order_by(m.ImportJob.id.desc()).limit(min(limit, 200))
    if status:
        q = q.where(m.ImportJob.status == status)
    return [jobs.job_dict(j) for j in s.execute(q).scalars()]


@app.get("/imports/{job_id}", dependencies=[Auth])
def get_import(job_id: int, s: Session = DB):
    try:
        return jobs.detail(s, job_id)
    except KeyError:
        raise HTTPException(404, "沒有這個工作")


@app.get("/imports/{job_id}/errors.csv", dependencies=[Auth])
def import_errors_csv(job_id: int, s: Session = DB):
    return Response(jobs.errors_csv(s, job_id), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="job-{job_id}-errors.csv"'})


def _control(job_id: int, action: str, s: Session):
    try:
        return jobs.job_dict(jobs.control(s, job_id, action))
    except KeyError:
        raise HTTPException(404, "沒有這個工作")


@app.post("/imports/{job_id}/pause", dependencies=[Auth])
def pause_import(job_id: int, s: Session = DB):
    return _control(job_id, "pause", s)


@app.post("/imports/{job_id}/resume", dependencies=[Auth])
def resume_import(job_id: int, s: Session = DB):
    return _control(job_id, "resume", s)


@app.post("/imports/{job_id}/cancel", dependencies=[Auth])
def cancel_import(job_id: int, s: Session = DB):
    return _control(job_id, "cancel", s)


@app.post("/imports/{job_id}/retry-failures", dependencies=[Auth], status_code=201)
def retry_import(job_id: int, s: Session = DB, idempotency_key: str | None = Header(default=None)):
    try:
        return jobs.job_dict(jobs.retry_failures(s, job_id, idempotency_key))
    except KeyError:
        raise HTTPException(404, "沒有這個工作")


# ── Words ─────────────────────────────────────────────────────────────

class RefreshBody(BaseModel):
    target_language: str
    native_language: str
    mode: str = "force_refresh"


class OverrideBody(BaseModel):
    items: list[dict[str, Any]]
    note: str = ""


@app.get("/words/{t}/{n}", dependencies=[Auth])
def search_words(t: str, n: str, q: str = "", limit: int = 30, s: Session = DB):
    """Prefix + fuzzy (pg_trgm) search over imported headwords."""
    ql = normalize_lemma(q, t)
    base = select(m.FieldValue.lemma).where(m.FieldValue.target_language == t,
                                            m.FieldValue.native_language == n).distinct()
    if ql:
        rows = s.execute(base.where(m.FieldValue.lemma.like(f"{ql}%")).limit(limit)).scalars().all()
        if len(rows) < limit:
            fuzzy = s.execute(select(m.Lexeme.normalized).where(
                m.Lexeme.language == t, m.Lexeme.status == "full",
                m.Lexeme.normalized.op("%")(ql)).order_by(
                func.similarity(m.Lexeme.normalized, ql).desc()).limit(limit)).scalars().all()
            rows += [r for r in dict.fromkeys(fuzzy) if r not in rows]
    else:
        rows = s.execute(base.order_by(m.FieldValue.lemma).limit(limit)).scalars().all()
    return rows[:limit]


@app.get("/words/{t}/{n}/{lemma}", dependencies=[Auth])
def get_word(t: str, n: str, lemma: str, s: Session = DB):
    try:
        return jsonable_encoder(views.word(s, t, n, lemma))
    except KeyError:
        raise HTTPException(404, "詞庫裡還沒有這個字（先建立擷取工作）")


@app.get("/words/{t}/{n}/{lemma}/fields/{field}", dependencies=[Auth])
def get_word_field(t: str, n: str, lemma: str, field: str, s: Session = DB):
    if field not in catalog.FIELD:
        raise HTTPException(404, "沒有這個欄位")
    return jsonable_encoder(views.field_detail(s, t, n, lemma, field))


@app.post("/words/{lexeme_id}/fields/{field}/refresh", dependencies=[Auth])
def refresh_field(lexeme_id: int, field: str, body: RefreshBody, s: Session = DB):
    lx = s.get(m.Lexeme, lexeme_id)
    if lx is None:
        raise HTTPException(404, "沒有這個詞條")
    if lx.language != body.target_language:
        raise HTTPException(422, "target_language 與詞條語言不符")
    policies.check_field(body.target_language, body.native_language, field)
    if body.mode not in ("force_refresh", "reresolve", "fill_missing"):
        raise HTTPException(422, "mode 必須是 force_refresh、reresolve 或 fill_missing")
    adapters.configure(s)
    reports = pipeline.process_word(s, body.target_language, body.native_language, lx.lemma,
                                    [field], body.mode)
    rep = next(r for r in reports if r.field == field)
    return jsonable_encoder({"field": field, "status": rep.status, "items": rep.items,
                             "missing": rep.missing,
                             "steps": [{"source": x.source, "status": x.status, "reason": x.reason,
                                        "count": x.count} for x in rep.steps]})


@app.put("/words/{t}/{n}/{lemma}/fields/{field}/override", dependencies=[Auth])
def put_override(t: str, n: str, lemma: str, field: str, body: OverrideBody, s: Session = DB):
    policies.check_field(t, n, field)
    norm = normalize_lemma(lemma, t)
    items = []
    for i, it in enumerate(body.items):
        it = {**it, "source": "user"}
        it.setdefault("key", str(it.get("sense_key") or it.get("example_key") or it.get("word")
                                 or it.get("form") or it.get("text") or i))
        it.setdefault("slot", str(it.get("sense_key") or it.get("example_key")
                                  or (it.get("word") or "").lower() or ""))
        items.append(it)
    stmt = pg_insert(m.UserOverride).values(target_language=t, native_language=n, lemma=norm,
                                            field=field, items=items, note=body.note)
    s.execute(stmt.on_conflict_do_update(constraint="uq_override",
                                         set_={"items": items, "note": body.note,
                                               "updated_at": func.now()}))
    s.flush()
    pipeline.process_word(s, t, n, lemma, [field], "reresolve")
    return jsonable_encoder(views.field_detail(s, t, n, lemma, field))


@app.delete("/words/{t}/{n}/{lemma}/fields/{field}/override", dependencies=[Auth])
def delete_override(t: str, n: str, lemma: str, field: str, s: Session = DB):
    norm = normalize_lemma(lemma, t)
    row = s.execute(select(m.UserOverride).where(
        m.UserOverride.target_language == t, m.UserOverride.native_language == n,
        m.UserOverride.lemma == norm, m.UserOverride.field == field)).scalar_one_or_none()
    if row is not None:
        s.delete(row)
        s.flush()
        adapters.configure(s)
        pipeline.process_word(s, t, n, lemma, [field], "reresolve")
    return jsonable_encoder(views.field_detail(s, t, n, lemma, field))


@app.get("/coverage/{t}/{n}", dependencies=[Auth])
def get_coverage(t: str, n: str, q: str | None = None, only: str | None = None,
                 limit: int = Query(100, le=1000), offset: int = 0, s: Session = DB):
    return views.coverage(s, t, n, q, only, limit, offset)


@app.get("/dashboard", dependencies=[Auth])
def get_dashboard(s: Session = DB):
    return jsonable_encoder(views.dashboard(s))


# ── Audio ─────────────────────────────────────────────────────────────

class DefaultAudioBody(BaseModel):
    lexeme_id: int


@app.get("/audio", dependencies=[Auth])
def list_audio(status: str | None = None, q: str | None = None, s: Session = DB):
    return jsonable_encoder(views.audio_library(s, status, q))


@app.get("/audio/{asset_id}/file")
def audio_file(asset_id: int, s: Session = DB):
    # Audio is public-licensed content; <audio> tags can't send headers.
    a = s.get(m.AudioAsset, asset_id)
    if a is None or not a.path or not (config.MEDIA / a.path).exists():
        raise HTTPException(404, "沒有這個音檔")
    return FileResponse(config.MEDIA / a.path, media_type=a.mime or "audio/mpeg")


@app.post("/audio/{asset_id}/redownload", dependencies=[Auth])
def redownload_audio(asset_id: int, s: Session = DB):
    from .audio import ensure_audio
    a = s.get(m.AudioAsset, asset_id)
    if a is None:
        raise HTTPException(404, "沒有這個音檔")
    a.status = "pending"
    s.flush()
    a = ensure_audio(s, a.language, {"url": a.source_url, "accent": [a.accent] if a.accent else []},
                     a.source)
    return {"id": a.id, "status": a.status, "error": a.error, "sha256": a.sha256}


@app.post("/audio/{asset_id}/default", dependencies=[Auth])
def default_audio(asset_id: int, body: DefaultAudioBody, s: Session = DB):
    """Make this recording the lexeme's default: saved as a user override
    of the audio field (so re-imports keep it)."""
    a, lx = s.get(m.AudioAsset, asset_id), s.get(m.Lexeme, body.lexeme_id)
    if a is None or lx is None:
        raise HTTPException(404, "找不到音檔或詞條")
    changed = []
    for fv in s.execute(select(m.FieldValue).where(
            m.FieldValue.target_language == lx.language, m.FieldValue.lemma == lx.normalized,
            m.FieldValue.field == "audio")).scalars().all():
        items = sorted(fv.items, key=lambda i: i.get("url") != a.source_url)
        stmt = pg_insert(m.UserOverride).values(target_language=lx.language,
                                                native_language=fv.native_language,
                                                lemma=lx.normalized, field="audio", items=items,
                                                note="預設發音")
        s.execute(stmt.on_conflict_do_update(constraint="uq_override",
                                             set_={"items": items, "updated_at": func.now()}))
        changed.append(fv.native_language)
    s.flush()
    for n in changed:
        pipeline.process_word(s, lx.language, n, lx.lemma, ["audio"], "reresolve")
    return {"ok": True, "directions": changed}


# ── Snapshots ─────────────────────────────────────────────────────────

class SnapshotBody(BaseModel):
    source: str
    language: str = ""


@app.get("/snapshots", dependencies=[Auth])
def list_snapshots(s: Session = DB):
    return jsonable_encoder([snapshots.snapshot_dict(r) for r in s.execute(
        select(m.SourceSnapshot).order_by(m.SourceSnapshot.id.desc())).scalars()])


@app.post("/snapshots", dependencies=[Auth], status_code=201)
def create_snapshot(body: SnapshotBody, s: Session = DB):
    return jsonable_encoder(snapshots.snapshot_dict(snapshots.request(s, body.source,
                                                                      body.language)))


@app.post("/snapshots/{snap_id}/activate", dependencies=[Auth])
def activate_snapshot(snap_id: int, s: Session = DB):
    r = jsonable_encoder(snapshots.snapshot_dict(snapshots.activate(s, snap_id)))
    adapters.configure(s)
    return r


@app.post("/snapshots/{snap_id}/verify", dependencies=[Auth])
def verify_snapshot(snap_id: int, s: Session = DB):
    return snapshots.verify(s, snap_id)


@app.get("/snapshots/compare", dependencies=[Auth])
def compare_snapshots(a: int, b: int, s: Session = DB):
    return jsonable_encoder(snapshots.compare(s, a, b))


# ── Export ────────────────────────────────────────────────────────────

class ExportBody(BaseModel):
    target_language: str
    native_language: str
    include_audio: bool = True
    fields: list[str] | None = None


def release_dict(r: m.DictionaryRelease) -> dict:
    files = []
    if r.status == "ready" and r.file_name:
        folder = config.EXPORTS / r.file_name
        files = [{"name": p.name, "bytes": p.stat().st_size}
                 for p in sorted(folder.iterdir()) if p.is_file()] if folder.exists() else []
    return jsonable_encoder({
        "id": r.id, "target_language": r.target_language, "native_language": r.native_language,
        "status": r.status, "file_name": r.file_name, "sha256": r.sha256,
        "size_bytes": r.size_bytes, "include_audio": r.include_audio, "checks": r.checks,
        "error": r.error, "created_at": r.created_at, "files": files,
        "counts": (r.manifest or {}).get("counts"),
        "completeness": (r.manifest or {}).get("completeness")})


@app.post("/exports/sqlite", dependencies=[Auth], status_code=201)
def export_sqlite(body: ExportBody, s: Session = DB,
                  idempotency_key: str | None = Header(default=None)):
    rel = exporter.export(s, body.target_language, body.native_language,
                          include_audio=body.include_audio, fields=body.fields,
                          idempotency_key=idempotency_key)
    return release_dict(rel)


@app.get("/exports", dependencies=[Auth])
def list_exports(s: Session = DB):
    return [release_dict(r) for r in s.execute(select(m.DictionaryRelease).order_by(
        m.DictionaryRelease.id.desc()).limit(50)).scalars()]


@app.post("/exports/{release_id}/install-app", dependencies=[Auth])
def install_export_in_app(release_id: int, s: Session = DB):
    """Copy this release's app pack (+ audio) into the Flutter app's assets."""
    from .app_pack import install
    r = s.get(m.DictionaryRelease, release_id)
    if r is None or r.status != "ready":
        raise HTTPException(404, "沒有這個已完成的匯出")
    try:
        return install(config.EXPORTS / r.file_name, r.target_language, r.native_language)
    except FileNotFoundError as e:
        raise HTTPException(422, str(e))


@app.get("/exports/{release_id}/files/{name}", dependencies=[Auth])
def export_file(release_id: int, name: str, s: Session = DB):
    r = s.get(m.DictionaryRelease, release_id)
    if r is None or r.status != "ready" or "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(404, "沒有這個檔案")
    path = config.EXPORTS / r.file_name / name
    if not path.is_file():
        raise HTTPException(404, "沒有這個檔案")
    return FileResponse(path, filename=name)


# ── Word lists and requests from the app ──────────────────────────────

class WordlistBody(BaseModel):
    language: str
    name: str
    words: list[str] = PField(default_factory=list)


@app.get("/wordlists", dependencies=[Auth])
def list_wordlists(language: str | None = None, s: Session = DB):
    q = select(m.Wordlist).order_by(m.Wordlist.id)
    if language:
        q = q.where(m.Wordlist.language == language)
    lists = [{"id": w.id, "language": w.language, "name": w.name, "count": len(w.words),
              "words": w.words} for w in s.execute(q).scalars()]
    # The app's 缺詞請求, kept current: words get a full entry, they leave.
    # One list per learning language (en is the target of two pairs).
    for lang in [language] if language else list(dict.fromkeys(t for t, _ in catalog.PAIRS)):
        missing = jobs.missing_words(s, lang)
        if missing:
            lists.insert(0, {"id": 0, "language": lang, "name": jobs.MISSING_LIST,
                             "count": len(missing), "words": missing, "virtual": True})
    return lists


@app.post("/wordlists", dependencies=[Auth], status_code=201)
def save_wordlist(body: WordlistBody, s: Session = DB):
    words = [w.strip() for w in body.words if w.strip()]
    stmt = pg_insert(m.Wordlist).values(language=body.language, name=body.name, words=words)
    s.execute(stmt.on_conflict_do_update(index_elements=["language", "name"],
                                         set_={"words": words}))
    return {"ok": True, "count": len(words)}


class MissingLexemeBody(BaseModel):
    target_language: str
    lemma: str
    pos: str | None = None


class MissingLocalizationBody(BaseModel):
    lexeme_id: int
    native_language: str
    field: str | None = None


@app.post("/requests/missing-lexeme", dependencies=[Auth])
def missing_lexeme(body: MissingLexemeBody, s: Session = DB):
    stmt = pg_insert(m.MissingLexemeRequest).values(
        target_language=body.target_language, lemma=normalize_lemma(body.lemma, body.target_language),
        pos=body.pos)
    s.execute(stmt.on_conflict_do_update(
        index_elements=["target_language", "lemma", "pos"],
        set_={"count": m.MissingLexemeRequest.count + 1}))
    return {"ok": True}


@app.post("/requests/missing-localization", dependencies=[Auth])
def missing_localization(body: MissingLocalizationBody, s: Session = DB):
    stmt = pg_insert(m.MissingLocalizationRequest).values(
        lexeme_id=body.lexeme_id, native_language=body.native_language, field=body.field)
    s.execute(stmt.on_conflict_do_update(
        index_elements=["lexeme_id", "native_language", "field"],
        set_={"count": m.MissingLocalizationRequest.count + 1}))
    return {"ok": True}


@app.get("/requests", dependencies=[Auth])
def list_requests(s: Session = DB):
    lex = [{"id": r.id, "target_language": r.target_language, "lemma": r.lemma, "pos": r.pos,
            "count": r.count, "status": r.status, "created_at": r.created_at}
           for r in s.execute(select(m.MissingLexemeRequest).order_by(
               m.MissingLexemeRequest.count.desc())).scalars()]
    loc = [{"id": r.id, "lexeme_id": r.lexeme_id, "native_language": r.native_language,
            "field": r.field, "count": r.count, "status": r.status, "created_at": r.created_at}
           for r in s.execute(select(m.MissingLocalizationRequest).order_by(
               m.MissingLocalizationRequest.count.desc())).scalars()]
    return jsonable_encoder({"missing_lexemes": lex, "missing_localizations": loc})


# The built admin UI (npm run build) is served at /ui/ when present.
_dist = config.HOME / "frontend" / "dist"
if _dist.exists():
    app.mount("/ui", StaticFiles(directory=_dist, html=True), name="ui")
