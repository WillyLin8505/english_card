"""Field-level source policies: seeding, reading, saving (one transaction,
gapped integer positions), copying to other fields, restoring defaults."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import catalog
from . import models as m

GAP = 1000


class PolicyError(ValueError):
    pass


# ── Seeding ───────────────────────────────────────────────────────────

def seed(session: Session) -> None:
    """Languages, pairs, sources, capabilities, and default policies for
    fields that have no policy row yet (existing policies are untouched)."""
    for code, lang in catalog.LANGUAGES.items():
        session.merge(m.Language(code=code, name=lang["name"], native_name=lang["native_name"]))
    session.flush()
    have_pairs = {(p.target_language, p.native_language)
                  for p in session.execute(select(m.LanguagePair)).scalars()}
    for t, n in catalog.PAIRS:
        if (t, n) not in have_pairs:
            session.add(m.LanguagePair(target_language=t, native_language=n))
    for s in catalog.SOURCES.values():
        row = session.get(m.Source, s.key) or m.Source(key=s.key)
        row.name, row.kind, row.license, row.attribution = s.name, s.kind, s.license, s.attribution
        row.url, row.note, row.implemented = s.url, s.note, s.implemented
        session.add(row)
    session.flush()
    # Steps a source no longer supports (AI once wrote English definitions
    # and word breakdowns; it now only translates into the native language).
    stale = [st for st, p in session.execute(
        select(m.SourcePolicyStep, m.SourcePolicy).join(
            m.SourcePolicy, m.SourcePolicy.id == m.SourcePolicyStep.policy_id)).all()
        if st.source in catalog.SOURCES and p.field in catalog.FIELD
        and p.target_language in catalog.LANGUAGES
        and not catalog.supports(st.source, p.target_language, p.native_language, p.field)[0]]
    if stale:
        changed = {st.policy_id for st in stale}
        session.execute(delete(m.SourcePolicyStep).where(
            m.SourcePolicyStep.id.in_([st.id for st in stale])))
        for p in session.execute(select(m.SourcePolicy).where(
                m.SourcePolicy.id.in_(changed))).scalars():
            p.version += 1
    session.execute(delete(m.SourceCapability))
    for s in catalog.SOURCES.values():
        for t, fields in s.supports.items():
            for f, natives in fields.items():
                for n in natives:
                    session.add(m.SourceCapability(source=s.key, target_language=t,
                                                   native_language=n, field=f))
    upgrade_untouched_defaults(session)
    existing = {(p.target_language, p.native_language, p.field)
                for p in session.execute(select(m.SourcePolicy)).scalars()}
    for t, n in catalog.PAIRS:
        for f in catalog.fields_for(t):
            if (t, n, f.key) not in existing:
                _write_default(session, t, n, f.key)
    session.flush()


# Earlier defaults that later gained sources. A policy still exactly at its
# first saved version with these sources was never edited, so it moves to
# the new default; anything the admin changed is left alone.
LEGACY_DEFAULTS = {"root": ["kaikki"], "prefix": ["kaikki"], "suffix": ["kaikki"]}


def upgrade_untouched_defaults(session: Session) -> None:
    for p in session.execute(select(m.SourcePolicy).where(
            m.SourcePolicy.field.in_(list(LEGACY_DEFAULTS)),
            m.SourcePolicy.version == 1)).scalars().all():
        sources = [st.source for st in steps_of(session, p)]
        new = catalog.default_policy(p.target_language, p.native_language, p.field)[0]
        if sources == LEGACY_DEFAULTS[p.field] and new != sources:
            _write_default(session, p.target_language, p.native_language, p.field, p)
    session.flush()


def _write_default(session, t, n, field_key, policy: m.SourcePolicy | None = None):
    sources, strategy, limit = catalog.default_policy(t, n, field_key)
    if policy is None:
        policy = m.SourcePolicy(target_language=t, native_language=n, field=field_key,
                                strategy=strategy, max_items=limit, version=1)
        session.add(policy)
        session.flush()
    else:
        policy.strategy, policy.max_items = strategy, limit
        policy.version += 1
        session.execute(delete(m.SourcePolicyStep).where(m.SourcePolicyStep.policy_id == policy.id))
    for i, src in enumerate(sources):
        kind = catalog.SOURCES[src].kind
        session.add(m.SourcePolicyStep(
            policy_id=policy.id, source=src, position=(i + 1) * GAP, enabled=True,
            timeout_s=120 if kind == "ai" else 20, retries=1 if kind == "ai" else 2,
            min_confidence=0.0, max_results=None, continue_on_failure=True))
    return policy


# ── Positions ─────────────────────────────────────────────────────────

def assign_positions(old: dict[str, int], order: list[str]) -> dict[str, int]:
    """New gapped positions for [order], rewriting as few rows as possible:
    the longest run of sources whose old positions are already increasing
    keeps them; the others go into the gaps (renumber only if no gap)."""
    idx = [(s, old[s]) for s in order if s in old]
    # Longest increasing subsequence of old positions, in the new order.
    best: list[list[str]] = []
    for s, p in idx:
        cand = max((seq for seq in best if old[seq[-1]] < p), key=len, default=[])
        best.append(cand + [s])
    keep = set(max(best, key=len, default=[]))
    out: dict[str, int] = {s: old[s] for s in keep}
    i = 0
    while i < len(order):
        s = order[i]
        if s in out:
            i += 1
            continue
        j = i
        while j < len(order) and order[j] not in out:
            j += 1
        lo = out[order[i - 1]] if i > 0 else 0
        hi = out[order[j]] if j < len(order) else lo + GAP * (j - i + 1)
        n = j - i
        step = (hi - lo) // (n + 1)
        if step < 1:
            return {s2: (k + 1) * GAP for k, s2 in enumerate(order)}
        for k in range(n):
            out[order[i + k]] = lo + step * (k + 1)
        i = j
    return out


# ── Reading ───────────────────────────────────────────────────────────

def _policy(session, t, n, field_key) -> m.SourcePolicy | None:
    return session.execute(select(m.SourcePolicy).where(
        m.SourcePolicy.target_language == t, m.SourcePolicy.native_language == n,
        m.SourcePolicy.field == field_key)).scalar_one_or_none()


def steps_of(session, policy: m.SourcePolicy | None) -> list[m.SourcePolicyStep]:
    if policy is None:
        return []
    return list(session.execute(select(m.SourcePolicyStep).where(
        m.SourcePolicyStep.policy_id == policy.id).order_by(m.SourcePolicyStep.position)).scalars())


def check_field(t, n, field_key):
    if t not in catalog.LANGUAGES or n not in catalog.LANGUAGES or t == n:
        raise PolicyError("目標語言與母語必須是兩種不同的已支援語言")
    f = catalog.FIELD.get(field_key)
    if f is None:
        raise PolicyError(f"沒有欄位 {field_key}")
    if f.languages is not None and t not in f.languages:
        raise PolicyError(f"「{f.label}」不適用於 {catalog.LANGUAGES[t]['zh']}")
    return f


def step_dict(st: m.SourcePolicyStep) -> dict:
    src = catalog.SOURCES[st.source]
    return {"source": st.source, "name": src.name, "kind": src.kind, "position": st.position,
            "enabled": st.enabled, "timeout_s": st.timeout_s, "retries": st.retries,
            "min_confidence": st.min_confidence, "max_results": st.max_results,
            "continue_on_failure": st.continue_on_failure, "implemented": src.implemented,
            "license": src.license}


def get(session, t, n, field_key) -> dict:
    f = check_field(t, n, field_key)
    policy = _policy(session, t, n, field_key)
    steps = steps_of(session, policy)
    used = {s.source for s in steps}
    available, unsupported = [], []
    for key, src in catalog.SOURCES.items():
        if key in used:
            continue
        ok, reason = catalog.supports(key, t, n, field_key)
        entry = {"source": key, "name": src.name, "kind": src.kind, "license": src.license,
                 "implemented": src.implemented, "note": src.note}
        if ok:
            available.append(entry)
        else:
            unsupported.append({**entry, "reason": reason})
    enabled = [s for s in steps if s.enabled]
    return {
        "target_language": t, "native_language": n, "field": field_key, "label": f.label,
        "block": f.block, "scope": f.scope, "description": f.description,
        "strategy": policy.strategy if policy else None,
        "max_items": policy.max_items if policy else None,
        "version": policy.version if policy else 0,
        "steps": [step_dict(s) for s in steps],
        "available": available, "unsupported": unsupported,
        "status": "unset" if not enabled else (
            "attention" if any(not catalog.SOURCES[s.source].implemented for s in enabled)
            else "ok"),
        "first_source": enabled[0].source if enabled else None,
        "backups": max(0, len(enabled) - 1),
        "last_test": policy.last_test if policy else None,
        "default": dict(zip(("sources", "strategy", "max_items"),
                            catalog.default_policy(t, n, field_key))),
    }


def overview(session, t, n) -> dict:
    """Every block with its field rows and block-level counts."""
    if t not in catalog.LANGUAGES or n not in catalog.LANGUAGES or t == n:
        raise PolicyError("目標語言與母語必須是兩種不同的已支援語言")
    policies = {p.field: p for p in session.execute(select(m.SourcePolicy).where(
        m.SourcePolicy.target_language == t, m.SourcePolicy.native_language == n)).scalars()}
    steps: dict[int, list] = {}
    if policies:
        for st in session.execute(select(m.SourcePolicyStep).where(
                m.SourcePolicyStep.policy_id.in_([p.id for p in policies.values()]))
                .order_by(m.SourcePolicyStep.position)).scalars():
            steps.setdefault(st.policy_id, []).append(st)
    blocks = []
    for bkey, blabel in catalog.BLOCKS:
        rows = []
        for f in catalog.fields_for(t):
            if f.block != bkey:
                continue
            p = policies.get(f.key)
            sts = steps.get(p.id, []) if p else []
            enabled = [s for s in sts if s.enabled]
            test = (p.last_test or {}) if p else {}
            status = "unset" if not enabled else (
                "attention" if any(not catalog.SOURCES[s.source].implemented for s in enabled)
                else "error" if test.get("errors") else "ok")
            rows.append({
                "field": f.key, "label": f.label, "scope": f.scope, "status": status,
                "strategy": p.strategy if p else None, "max_items": p.max_items if p else None,
                "first_source": enabled[0].source if enabled else None,
                "first_source_name": catalog.SOURCES[enabled[0].source].name if enabled else None,
                "backups": max(0, len(enabled) - 1),
                "sources": [s.source for s in enabled], "version": p.version if p else 0,
                "last_test": {k: test.get(k) for k in ("word", "at", "adopted", "errors",
                                                       "status")} if test else None,
            })
        if rows:
            blocks.append({
                "block": bkey, "label": blabel, "fields": rows,
                "counts": {"total": len(rows),
                           "configured": sum(r["status"] in ("ok", "error") for r in rows),
                           "unset": sum(r["status"] == "unset" for r in rows),
                           "attention": sum(r["status"] == "attention" for r in rows),
                           "errors": sum(r["status"] == "error" for r in rows)},
            })
    return {"target_language": t, "native_language": n, "blocks": blocks,
            "strategies": catalog.STRATEGIES}


# ── Saving ────────────────────────────────────────────────────────────

def validate_body(t, n, field_key, body: dict) -> list[dict]:
    check_field(t, n, field_key)
    strategy = body.get("strategy")
    if strategy not in catalog.STRATEGIES:
        raise PolicyError(f"策略必須是 {', '.join(catalog.STRATEGIES)}")
    seen, out = set(), []
    for st in body.get("steps", []):
        src = st.get("source")
        if src not in catalog.SOURCES:
            raise PolicyError(f"沒有來源 {src}")
        if src in seen:
            raise PolicyError(f"來源 {src} 重複")
        seen.add(src)
        ok, reason = catalog.supports(src, t, n, field_key)
        if not ok:
            raise PolicyError(f"{catalog.SOURCES[src].name}：{reason}")
        timeout = float(st.get("timeout_s", 20))
        retries = int(st.get("retries", 2))
        conf = float(st.get("min_confidence", 0))
        mr = st.get("max_results")
        if not (1 <= timeout <= 600) or not (0 <= retries <= 10) or not (0 <= conf <= 1):
            raise PolicyError("逾時 1–600 秒、重試 0–10 次、可信度 0–1")
        if mr is not None and not (1 <= int(mr) <= 200):
            raise PolicyError("最大結果數 1–200")
        out.append({"source": src, "enabled": bool(st.get("enabled", True)),
                    "timeout_s": timeout, "retries": retries, "min_confidence": conf,
                    "max_results": int(mr) if mr is not None else None,
                    "continue_on_failure": bool(st.get("continue_on_failure", True))})
    mi = body.get("max_items")
    if mi is not None and not (1 <= int(mi) <= 200):
        raise PolicyError("欄位上限 1–200")
    return out


def put(session, t, n, field_key, body: dict, expected_version: int | None = None) -> dict:
    """Save one field's policy in one transaction. Only this field changes."""
    steps = validate_body(t, n, field_key, body)
    policy = session.execute(select(m.SourcePolicy).where(
        m.SourcePolicy.target_language == t, m.SourcePolicy.native_language == n,
        m.SourcePolicy.field == field_key).with_for_update()).scalar_one_or_none()
    if policy is None:
        policy = m.SourcePolicy(target_language=t, native_language=n, field=field_key,
                                strategy=body["strategy"], version=0)
        session.add(policy)
        session.flush()
    if expected_version is not None and policy.version != expected_version:
        raise PolicyError(f"這個欄位已被其他人更新（版本 {policy.version}），請重新載入")
    current = {s.source: s for s in steps_of(session, policy)}
    new_pos = assign_positions({k: v.position for k, v in current.items()},
                               [s["source"] for s in steps])
    for gone in set(current) - {s["source"] for s in steps}:
        session.delete(current[gone])
    for st in steps:
        row = current.get(st["source"])
        if row is None:
            row = m.SourcePolicyStep(policy_id=policy.id, source=st["source"])
            session.add(row)
        row.position = new_pos[st["source"]]
        for k in ("enabled", "timeout_s", "retries", "min_confidence", "max_results",
                  "continue_on_failure"):
            setattr(row, k, st[k])
    policy.strategy = body["strategy"]
    policy.max_items = int(body["max_items"]) if body.get("max_items") is not None else None
    policy.version += 1
    session.flush()
    return get(session, t, n, field_key)


def restore_default(session, t, n, field_key) -> dict:
    check_field(t, n, field_key)
    _write_default(session, t, n, field_key, _policy(session, t, n, field_key))
    session.flush()
    return get(session, t, n, field_key)


def copy_to(session, t, n, from_field: str, to_fields: list[str], confirm: bool) -> dict:
    """「複製此順位到⋯」: only the fields the user picked, only after
    confirmation. Sources a target field doesn't support are dropped and
    reported."""
    src = get(session, t, n, from_field)
    plan = []
    for f in to_fields:
        if f == from_field:
            continue
        check_field(t, n, f)
        keep, dropped = [], []
        for st in src["steps"]:
            ok, reason = catalog.supports(st["source"], t, n, f)
            (keep if ok else dropped).append(st if ok else {"source": st["source"],
                                                            "reason": reason})
        plan.append({"field": f, "label": catalog.FIELD[f].label, "steps": keep,
                     "dropped": dropped})
    if not confirm:
        return {"confirmed": False, "plan": plan}
    for p in plan:
        put(session, t, n, p["field"], {"strategy": src["strategy"], "max_items": src["max_items"],
                                        "steps": p["steps"]})
    return {"confirmed": True, "plan": plan}


def load_for_run(session, t, n) -> dict[str, tuple[m.SourcePolicy, list[m.SourcePolicyStep]]]:
    policies = session.execute(select(m.SourcePolicy).where(
        m.SourcePolicy.target_language == t, m.SourcePolicy.native_language == n)).scalars().all()
    out = {p.field: (p, []) for p in policies}
    ids = {p.id: p.field for p in policies}
    if ids:
        for st in session.execute(select(m.SourcePolicyStep).where(
                m.SourcePolicyStep.policy_id.in_(list(ids))).order_by(
                m.SourcePolicyStep.position)).scalars():
            out[ids[st.policy_id]][1].append(st)
    return out
