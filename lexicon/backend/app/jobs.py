"""Import jobs: the queue lives in PostgreSQL (no Redis / Celery).

A worker claims a job with FOR UPDATE SKIP LOCKED, then processes its
words one at a time. Each word — its data, attempts, errors and the
checkpoint — commits in one transaction, so a crash re-runs at most that
word, and re-running is harmless (everything is upserted).

States: queued → running → completed / completed_with_errors / failed;
running → pausing → paused → (resume) queued; running → cancelling →
cancelled. The worker checks the state between words.
"""

from __future__ import annotations

import csv
import io
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import catalog
from . import models as m
from . import pipeline, policies
from .adapters import http
from .text import normalize_lemma

STALE_AFTER = timedelta(minutes=5)  # a running job whose worker stopped beating
TERMINAL = {"cancelled", "completed", "completed_with_errors", "failed"}


class JobError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc)


# ── Creating ──────────────────────────────────────────────────────────

# Words the app's learners met in photos but the dictionary pack lacks
# (spec section 7: 缺詞條), offered as a word list for an import job.
MISSING_LIST = "App 缺詞請求"


def missing_words(s: Session, target: str) -> list[str]:
    """Open missing-word requests whose word still has no full entry, most
    requested first."""
    full = select(m.Lexeme.normalized).where(m.Lexeme.language == target,
                                             m.Lexeme.status == "full")
    rows = s.execute(select(m.MissingLexemeRequest.lemma).where(
        m.MissingLexemeRequest.target_language == target,
        m.MissingLexemeRequest.status == "open",
        m.MissingLexemeRequest.lemma.not_in(full)).order_by(
        m.MissingLexemeRequest.count.desc(), m.MissingLexemeRequest.id)).scalars()
    # Requests recorded before the app and tagger cleaned them: stained_glass
    # is 「stained glass」, calendrier is French (問題回報 #95).
    words = [w.replace("_", " ").strip() for w in rows]
    have = set(s.execute(full).scalars())
    # A form of a word already in the lexicon (children ← child, eaten ←
    # eat) is not a missing word; the app looks those up by their lemma.
    for fv in s.execute(select(m.FieldValue).where(
            m.FieldValue.target_language == target,
            m.FieldValue.field.in_(catalog.FORM_FIELDS),
            m.FieldValue.lemma.in_(have))).scalars():
        have |= {str(i.get("form", "")).lower() for i in fv.items or [] if i.get("form")}
    return list(dict.fromkeys(w for w in words if w and w not in have
                              and not _foreign(w, target)))


def _foreign(word: str, target: str) -> bool:
    """A word of another language: rare in the target, common elsewhere."""
    if target != "en" or " " in word:
        return False
    from wordfreq import zipf_frequency
    en = zipf_frequency(word, "en")
    return en < 2 and max(zipf_frequency(word, l) for l in ("fr", "es", "de", "it", "pt")) >= en + 2


def resolve_words(s: Session, target: str, words: list[str] | None, wordlist: str | None):
    out: list[str] = []
    if wordlist == MISSING_LIST:
        out += missing_words(s, target)
        if not out and not words:
            raise JobError("目前沒有待補的缺詞請求")
    elif wordlist:
        wl = s.execute(select(m.Wordlist).where(m.Wordlist.language == target,
                                                m.Wordlist.name == wordlist)).scalar_one_or_none()
        if wl is None:
            raise JobError(f"沒有字表 {wordlist}")
        out += wl.words
    out += words or []
    seen, clean = set(), []
    for w in out:
        w = (w or "").strip()
        k = normalize_lemma(w, target)
        if w and k not in seen and len(w) <= 64:
            seen.add(k)
            clean.append(w)
    return clean


def create(s: Session, body: dict, idempotency_key: str | None = None) -> m.ImportJob:
    if idempotency_key:
        found = s.execute(select(m.ImportJob).where(
            m.ImportJob.idempotency_key == idempotency_key)).scalar_one_or_none()
        if found is not None:
            return found
    t, n = body.get("target_language"), body.get("native_language")
    if not t or not n:
        raise JobError("target_language 和 native_language 都是必填")
    if t not in catalog.LANGUAGES or n not in catalog.LANGUAGES or t == n:
        raise JobError("目標語言與母語必須是兩種不同的已支援語言")
    mode = body.get("mode", "fill_missing")
    if mode not in pipeline.MODES:
        raise JobError(f"模式必須是 {', '.join(pipeline.MODES)}")
    words = resolve_words(s, t, body.get("words"), body.get("wordlist"))
    if not words:
        raise JobError("沒有要處理的單字")
    available = {f.key for f in catalog.fields_for(t)}
    fields = body.get("fields") or sorted(available)
    bad = [f for f in fields if f not in available]
    if bad:
        raise JobError(f"這個語言沒有欄位：{', '.join(bad)}")
    sources = body.get("sources") or None
    if sources and any(x not in catalog.SOURCES for x in sources):
        raise JobError("有不存在的來源")
    job = m.ImportJob(target_language=t, native_language=n, mode=mode, words=words,
                      fields=fields, sources=sources, total=len(words), status="queued",
                      counts={}, note=body.get("note", ""), retry_of=body.get("retry_of"),
                      idempotency_key=idempotency_key)
    s.add(job)
    s.flush()
    log(s, job.id, f"建立工作：{catalog.LANGUAGES[t]['zh']}→{catalog.LANGUAGES[n]['zh']}，"
                   f"{len(words)} 個單字、{len(fields)} 個欄位、模式 {pipeline.MODES[mode]}")
    return job


def create_shards(s: Session, body: dict, idempotency_key: str | None = None
                  ) -> list[m.ImportJob]:
    """Create independent word shards so several workers can run concurrently."""
    if idempotency_key:
        existing = list(s.execute(select(m.ImportJob).where(
            (m.ImportJob.idempotency_key == idempotency_key)
            | m.ImportJob.idempotency_key.like(f"{idempotency_key}:%")
        ).order_by(m.ImportJob.id)).scalars())
        if existing:
            return existing
    target = body.get("target_language")
    words = resolve_words(s, target, body.get("words"), body.get("wordlist"))
    parallelism = max(1, min(int(body.get("parallelism") or 1), 8, len(words)))
    if parallelism == 1:
        return [create(s, {**body, "words": words, "wordlist": None}, idempotency_key)]
    chunks = [words[i::parallelism] for i in range(parallelism)]
    base_note = (body.get("note") or "").strip()
    out = []
    for index, chunk in enumerate(chunks, 1):
        note = f"平行批次 {index}/{parallelism}"
        if base_note:
            note = f"{base_note} · {note}"
        shard_key = idempotency_key if index == 1 else (
            f"{idempotency_key}:{index}" if idempotency_key else None)
        out.append(create(s, {**body, "words": chunk, "wordlist": None, "note": note},
                          shard_key))
    for job in out:
        log(s, job.id, f"同批平行工作：{', '.join('#' + str(x.id) for x in out)}")
    return out


def log(s: Session, job_id: int, message: str, level: str = "info"):
    s.add(m.JobLog(job_id=job_id, message=message, level=level))


# ── Control ───────────────────────────────────────────────────────────

def control(s: Session, job_id: int, action: str) -> m.ImportJob:
    """pause / resume / cancel — idempotent: repeating an action is a no-op."""
    job = s.execute(select(m.ImportJob).where(m.ImportJob.id == job_id).with_for_update()
                    ).scalar_one_or_none()
    if job is None:
        raise KeyError(job_id)
    st = job.status
    if action == "pause":
        if st in ("queued",):
            job.status = "paused"
        elif st == "running":
            job.status = "pausing"
        elif st not in ("pausing", "paused"):
            raise JobError(f"狀態 {st} 不能暫停")
    elif action == "resume":
        if st in ("paused", "pausing"):
            job.status = "queued" if st == "paused" else "running"
        elif st not in ("queued", "running"):
            raise JobError(f"狀態 {st} 不能繼續")
    elif action == "cancel":
        if st in ("queued", "paused"):
            job.status, job.finished_at = "cancelled", now()
        elif st in ("running", "pausing"):
            job.status = "cancelling"
        elif st not in ("cancelling", "cancelled"):
            raise JobError(f"狀態 {st} 不能取消")
    else:
        raise JobError(f"未知動作 {action}")
    if job.status != st:
        log(s, job.id, {"pause": "要求暫停", "resume": "繼續", "cancel": "要求取消"}[action]
            + f"（{st} → {job.status}）")
    s.flush()
    return job


def retry_failures(s: Session, job_id: int, idempotency_key: str | None = None) -> m.ImportJob:
    job = s.get(m.ImportJob, job_id)
    if job is None:
        raise KeyError(job_id)
    rows = s.execute(select(m.ImportAttempt.lemma, m.ImportAttempt.field).where(
        m.ImportAttempt.job_id == job_id, m.ImportAttempt.status == "failed")).all()
    errs = s.execute(select(m.ImportError_.lemma, m.ImportError_.field).where(
        m.ImportError_.job_id == job_id, m.ImportError_.resolved.is_(False))).all()
    pairs = {(r.lemma, r.field) for r in rows + errs}
    if not pairs:
        raise JobError("這個工作沒有失敗項目")
    words = sorted({lem for lem, _ in pairs})
    fields = sorted({f for _, f in pairs if f in catalog.FIELD}) or job.fields
    return create(s, {"target_language": job.target_language,
                      "native_language": job.native_language, "mode": "fill_missing",
                      "words": words, "fields": fields, "sources": job.sources,
                      "retry_of": job.id, "note": f"重試工作 #{job.id} 的失敗項目"},
                  idempotency_key)


# ── Worker side ───────────────────────────────────────────────────────

def claim(s: Session, worker_id: str) -> m.ImportJob | None:
    """Lock and take the oldest runnable job; other workers skip it."""
    job = s.execute(
        select(m.ImportJob).where(
            (m.ImportJob.status == "queued")
            | (m.ImportJob.status.in_(("running", "pausing", "cancelling"))
               & ((m.ImportJob.heartbeat_at.is_(None))
                  | (m.ImportJob.heartbeat_at < now() - STALE_AFTER))))
        .order_by(m.ImportJob.created_at).limit(1).with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if job is None:
        return None
    if job.status == "queued":
        job.status = "running"
    job.worker_id, job.heartbeat_at = worker_id, now()
    job.started_at = job.started_at or now()
    log(s, job.id, f"Worker {worker_id} 從第 {job.checkpoint + 1} 個單字開始")
    s.flush()
    return job


class JobRecorder(pipeline.Recorder):
    def __init__(self, s: Session, job: m.ImportJob):
        self.s, self.job = s, job
        self.steps: dict[tuple[str, str], dict] = {}

    def attempt(self, lemma, field_key, source, status, ms, count, error=None, kind=None,
                attempts=1, record_id=None):
        stmt = pg_insert(m.ImportAttempt).values(
            job_id=self.job.id, lemma=lemma, field=field_key, source=source, status=status,
            attempts=attempts, count=count, ms=ms, error=error)
        self.s.execute(stmt.on_conflict_do_update(
            index_elements=["job_id", "lemma", "field", "source"],
            set_={"status": status, "count": count, "ms": ms, "error": error,
                  "attempts": m.ImportAttempt.attempts + attempts,
                  "updated_at": func.now()}))
        st = self.steps.setdefault((field_key, source), {"succeeded": 0, "missing": 0, "failed": 0,
                                                          "skipped": 0, "retried": 0, "ms": 0})
        st[status if status in st else "skipped"] += 1
        st["ms"] += ms
        if attempts > 1:
            st["retried"] += 1
        if status == "failed" and kind not in ("not_implemented", "unsupported"):
            self.s.add(m.ImportError_(
                job_id=self.job.id, lemma=lemma, field=field_key, source=source,
                error_type=kind or "error", message=error or "", attempts=attempts,
                next_retry_at=pipeline.next_retry(attempts), source_record_id=record_id))

    def flush_steps(self, run_policies):
        for (field_key, source), st in self.steps.items():
            pos = next((x.position for x in run_policies.get(field_key, (None, []))[1]
                        if x.source == source), 0)
            stmt = pg_insert(m.ImportJobStep).values(
                job_id=self.job.id, field=field_key, source=source, position=pos,
                succeeded=st["succeeded"], missing=st["missing"], failed=st["failed"],
                skipped=st["skipped"], retried=st["retried"], ms_total=st["ms"])
            T = m.ImportJobStep
            self.s.execute(stmt.on_conflict_do_update(
                index_elements=["job_id", "field", "source"],
                set_={"succeeded": T.succeeded + st["succeeded"],
                      "missing": T.missing + st["missing"], "failed": T.failed + st["failed"],
                      "skipped": T.skipped + st["skipped"], "retried": T.retried + st["retried"],
                      "ms_total": T.ms_total + st["ms"]}))
        self.steps.clear()


def flush_usage(s: Session):
    day = now().strftime("%Y-%m-%d")
    for source, u in http.take_usage().items():
        stmt = pg_insert(m.ApiUsage).values(source=source, day=day, requests=u.requests,
                                            errors=u.errors, cache_hits=u.cache_hits,
                                            ms_total=u.ms_total)
        A = m.ApiUsage
        s.execute(stmt.on_conflict_do_update(
            index_elements=["source", "day"],
            set_={"requests": A.requests + u.requests, "errors": A.errors + u.errors,
                  "cache_hits": A.cache_hits + u.cache_hits, "ms_total": A.ms_total + u.ms_total}))


def run(session_factory, job_id: int, worker_id: str, stop=lambda: False,
        on_word=None, max_words: int | None = None) -> str:
    """Process a claimed job from its checkpoint. Returns the final state
    for this run (paused / cancelled / completed … or 'released')."""
    from .adapters import configure
    with session_factory() as s:
        configure(s)
        job = s.get(m.ImportJob, job_id)
        t, n = job.target_language, job.native_language
        run_policies = policies.load_for_run(s, t, n)
        s.expunge_all()
    processed = 0
    while True:
        with session_factory() as s:
            job = s.execute(select(m.ImportJob).where(m.ImportJob.id == job_id)
                            .with_for_update()).scalar_one()
            if job.worker_id != worker_id:
                return "released"  # another worker took over (we looked dead)
            if job.status == "pausing":
                job.status = "paused"
                log(s, job.id, f"已暫停於第 {job.checkpoint} / {job.total} 個單字")
                s.commit()
                return "paused"
            if job.status == "cancelling":
                job.status, job.finished_at = "cancelled", now()
                log(s, job.id, f"已取消（完成 {job.checkpoint} / {job.total}）")
                s.commit()
                return "cancelled"
            if job.status != "running":
                return job.status
            if stop():
                job.worker_id = None
                job.heartbeat_at = None
                log(s, job.id, "Worker 停止；工作留在佇列，下次從檢查點繼續")
                s.commit()
                return "released"
            if job.checkpoint >= job.total:
                counts = job.counts or {}
                failed_words = counts.get("words_failed", 0)
                # Any failed source step counts, even if a later source
                # filled the field (the admin should see and retry it).
                step_errors = s.execute(select(func.count()).select_from(m.ImportError_).where(
                    m.ImportError_.job_id == job.id,
                    m.ImportError_.resolved.is_(False))).scalar()
                errors = counts.get("fields_failed", 0) + failed_words + step_errors
                job.status = ("failed" if failed_words and failed_words >= job.total
                              else "completed_with_errors" if errors else "completed")
                job.finished_at = now()
                log(s, job.id, f"完成：{job.status}")
                s.commit()
                return job.status
            word = job.words[job.checkpoint]
            s.commit()
        # One word, one transaction (data + attempts + checkpoint).
        started = time.time()
        with session_factory() as s:
            job = s.get(m.ImportJob, job_id)
            rec = JobRecorder(s, job)
            counts = dict(job.counts or {})
            try:
                reports = pipeline.process_word(
                    s, t, n, word, job.fields, job.mode, sources=job.sources, recorder=rec,
                    run_policies=run_policies)
                for r in reports:
                    k = f"fields_{r.status}"
                    counts[k] = counts.get(k, 0) + 1
                counts["words_done"] = counts.get("words_done", 0) + 1
                rec.flush_steps(run_policies)
                flush_usage(s)
            except Exception as e:  # noqa: BLE001 — record, roll back this word, move on
                s.rollback()
                job = s.get(m.ImportJob, job_id)
                counts = dict(job.counts or {})
                counts["words_failed"] = counts.get("words_failed", 0) + 1
                s.add(m.ImportError_(job_id=job_id, lemma=normalize_lemma(word, t), field="*",
                                     source="*", error_type="exception",
                                     message=f"{type(e).__name__}: {e}"[:2000]))
                log(s, job_id, f"「{word}」處理失敗：{type(e).__name__}: {e}", "error")
            job.checkpoint += 1
            job.counts = counts
            job.heartbeat_at = now()
            processed += 1
            yielded = bool(max_words and processed >= max_words and job.checkpoint < job.total)
            if yielded:
                # Give another worker a chance to take this shard. A short slice
                # also lets the same worker alternate text and deferred images.
                job.status = "queued"
                job.worker_id = None
                job.heartbeat_at = None
            s.commit()
        if on_word:
            on_word(word, time.time() - started)
        if yielded:
            return "yielded"


def heartbeat(session_factory, job_id: int, worker_id: str):
    with session_factory() as s:
        s.execute(update(m.ImportJob).where(m.ImportJob.id == job_id,
                                            m.ImportJob.worker_id == worker_id)
                  .values(heartbeat_at=now()))
        s.commit()


# ── Reading ───────────────────────────────────────────────────────────

def job_dict(job: m.ImportJob, detail: bool = False) -> dict:
    c = job.counts or {}
    words = job.words or []
    d = {"id": job.id, "target_language": job.target_language,
         "native_language": job.native_language, "mode": job.mode,
         "mode_label": pipeline.MODES.get(job.mode, job.mode), "status": job.status,
         "total": job.total, "checkpoint": job.checkpoint,
         "progress": round(job.checkpoint / job.total, 4) if job.total else 0,
         "counts": c, "fields": len(job.fields), "sources": job.sources,
         "worker_id": job.worker_id, "retry_of": job.retry_of, "note": job.note,
         "created_at": job.created_at, "started_at": job.started_at,
         "finished_at": job.finished_at, "heartbeat_at": job.heartbeat_at,
         "succeeded": sum(c.get(f"fields_{st}", 0) for st in catalog.DONE),
         "partial": c.get("fields_partial", 0), "missing": c.get("fields_missing", 0),
         "failed": c.get("fields_failed", 0) + c.get("words_failed", 0),
         "skipped": c.get("fields_skipped", 0), "unset": c.get("fields_unset", 0),
         # Keep queue payloads small while still showing which words a job handles.
         "word_preview": words[:8], "word_preview_remaining": max(0, len(words) - 8),
         "current_word": words[job.checkpoint] if job.checkpoint < len(words) else None}
    if detail:
        d["words"] = words
        d["field_list"] = job.fields
    return d


def detail(s: Session, job_id: int) -> dict:
    job = s.get(m.ImportJob, job_id)
    if job is None:
        raise KeyError(job_id)
    d = job_dict(job, detail=True)
    d["steps"] = [{"field": r.field, "label": catalog.FIELD[r.field].label if r.field in
                   catalog.FIELD else r.field, "source": r.source, "position": r.position,
                   "succeeded": r.succeeded, "missing": r.missing, "failed": r.failed,
                   "skipped": r.skipped, "retried": r.retried,
                   "avg_ms": int(r.ms_total / max(1, r.succeeded + r.missing + r.failed))}
                  for r in s.execute(select(m.ImportJobStep).where(
                      m.ImportJobStep.job_id == job_id).order_by(
                      m.ImportJobStep.field, m.ImportJobStep.position)).scalars()]
    d["errors_by_type"] = [{"error_type": r[0], "source": r[1], "count": r[2]} for r in s.execute(
        select(m.ImportError_.error_type, m.ImportError_.source, func.count()).where(
            m.ImportError_.job_id == job_id).group_by(m.ImportError_.error_type,
                                                      m.ImportError_.source)).all()]
    d["errors"] = [{"id": e.id, "lemma": e.lemma, "field": e.field, "source": e.source,
                    "error_type": e.error_type, "message": e.message, "attempts": e.attempts,
                    "next_retry_at": e.next_retry_at, "created_at": e.created_at}
                   for e in s.execute(select(m.ImportError_).where(
                       m.ImportError_.job_id == job_id).order_by(m.ImportError_.id.desc())
                       .limit(200)).scalars()]
    d["logs"] = [{"id": g.id, "level": g.level, "message": g.message, "at": g.created_at}
                 for g in s.execute(select(m.JobLog).where(m.JobLog.job_id == job_id)
                                    .order_by(m.JobLog.id.desc()).limit(100)).scalars()]
    return d


def errors_csv(s: Session, job_id: int) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "lemma", "field", "field_label", "source", "error_type", "message",
                "attempts", "next_retry_at", "source_record_id", "created_at"])
    for e in s.execute(select(m.ImportError_).where(m.ImportError_.job_id == job_id)
                       .order_by(m.ImportError_.id)).scalars():
        w.writerow([e.id, e.lemma, e.field, catalog.FIELD[e.field].label if e.field in catalog.FIELD
                    else "", e.source, e.error_type, e.message, e.attempts, e.next_retry_at,
                    e.source_record_id or "", e.created_at])
    return "﻿" + buf.getvalue()  # BOM so Excel opens it as UTF-8


def estimate(s: Session, body: dict) -> dict:
    """Before starting: expected completeness, requests and storage, for
    target-language data and native-language data separately."""
    t, n = body.get("target_language"), body.get("native_language")
    if not t or not n:
        raise JobError("target_language 和 native_language 都是必填")
    words = resolve_words(s, t, body.get("words"), body.get("wordlist"))
    available = {f.key for f in catalog.fields_for(t)}
    fields = [f for f in (body.get("fields") or sorted(available)) if f in available]
    mode = body.get("mode", "fill_missing")
    lemmas = [normalize_lemma(w, t) for w in words]
    run_policies = policies.load_for_run(s, t, n)
    have = {(r.lemma, r.field): r.status for r in s.execute(select(
        m.FieldValue.lemma, m.FieldValue.field, m.FieldValue.status).where(
        m.FieldValue.target_language == t, m.FieldValue.native_language == n,
        m.FieldValue.lemma.in_(lemmas))).all()} if lemmas else {}
    # Historic success rate per field + source, from earlier lookups.
    rates = {(r.field, r.source): (r.ok, r.total) for r in s.execute(text("""
        SELECT field, source, count(*) FILTER (WHERE status = 'succeeded') AS ok,
               count(*) AS total FROM source_lookups WHERE target_language = :t
        GROUP BY field, source"""), {"t": t}).all()}
    out = {}
    for scope in ("target", "native"):
        fs = [f for f in fields if catalog.FIELD[f].scope == scope]
        done = sum(1 for lem in lemmas for f in fs if have.get((lem, f)) in catalog.SETTLED)
        todo = len(lemmas) * len(fs) - (done if mode == "fill_missing" else 0)
        requests = 0
        expected = 0.0
        for f in fs:
            pol, steps = run_policies.get(f, (None, []))
            steps = [st for st in steps if st.enabled and catalog.SOURCES[st.source].implemented]
            p_missing = 1.0
            for st in steps:
                ok, total = rates.get((f, st.source), (0, 0))
                p = ok / total if total >= 5 else 0.6
                if catalog.SOURCES[st.source].kind in ("api", "dump", "ai"):
                    requests += 1 * len(lemmas)
                p_missing *= 1 - p
            expected += 1 - p_missing if steps else 0
        out[scope] = {
            "fields": len(fs), "cells": len(lemmas) * len(fs), "already_complete": done,
            "to_process": max(0, todo),
            "current_completeness": round(done / max(1, len(lemmas) * len(fs)), 3),
            "expected_completeness": round(expected / max(1, len(fs)), 3),
            "requests_upper_bound": requests,
            "storage_bytes": int(max(0, todo) * (1800 if scope == "target" else 300)),
        }
    # Media separately (spec: 文字、音檔、圖片各自的請求數與儲存量).
    audio = "audio" in fields
    out["audio"] = {"files": len(lemmas) if audio else 0,
                    "requests_upper_bound": 2 * len(lemmas) if audio else 0,
                    "storage_bytes": len(lemmas) * 60_000 if audio else 0}
    pics = "sense_image" in fields
    pol = run_policies.get("sense_image", (None, []))[0]
    per_sense = (pol.max_items if pol and pol.max_items else 3) if pics else 0
    images = len(lemmas) * 2 * per_sense  # the first two senses of a noun
    out["images"] = {"files": images,
                     # concept match (2) + search (2) per sense; licence check + download a picture
                     "requests_upper_bound": len(lemmas) * 2 * 4 + images * 2,
                     # original (~250 KB) + app thumbnail (~30 KB); AI labels ~7 s a picture
                     "storage_bytes": images * 280_000, "ai_label_seconds": images * 7}
    return {"words": len(words), "fields": len(fields), "mode": mode, **out,
            "note": "請求數是上限：有快取、策略提早停止（第一個有效來源、已達上限）時會更少。"}
