"""控制台 (card #919): one page to see the state of everything and step in at any time.

A card and its 問題回報 are one item, so nothing shows up twice. An item's stage, who it waits for and
what the owner can do come from the same facts flow_tick uses (lexicon/docs/PIPELINE.md); stages are still
never set by hand. 「需要你」 is strict: only what blocks progress and no rule can settle.

Intervening must really arrive: a running CLI can't read card changes, so an instruction for it opens a
接續卡 that starts once the first card is collected; a card no CLI has started yet takes it in its detail.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import db, flow, issues, runs, tasks
from . import models as m

import flow_rules  # noqa: E402  (tools/ is on sys.path through runs)

TAIPEI = timezone(timedelta(hours=8))
STAGES = {"queue": "派工", "standing": "常態檢查", **flow.STAGES}
ORDER = ("queue", "dev", "windows_check", "mac_verify", "ipad_verify", "ready", "released", "done")
VERIFY = ("windows_check", "mac_verify", "ipad_verify")
CLOSED = ("released", "done", "cancelled")
SOURCES = {"owner": "你", "phone": "手機回饋", "mac": "Mac 驗證", "sim": "模擬使用者", "qc": "長期 QC", "ai": "AI／系統"}
TYPES = {"need": "需求", "bug": "問題", "decision": "決定", "standing": "常態檢查"}
WAITS = {"you": "等你", "ai": "AI 在做", "queue": "排隊等 AI", "system": "系統處理", "mac": "等 Mac／iPad",
         "release": "等發布", "paused": "已暫停", "stuck": "卡住", "none": "不用等"}
GROUPS = {"active": "要處理", "qc": "長期 QC", "closed": "已結案", "all": "全部"}
LAST_POSITION = 1_000_000.0   # tools/pick_card.py: at or past this a card goes after everything else
FOLLOW_PREFIX = "等 #"
FOLLOW_RE = re.compile(r"^等 #(\d+) 收卡")
DONE_ANSWER = "已處理好，繼續"   # a card waiting for the owner to do something, not to choose
TEST_RE = re.compile(r"\d+\s*(?:項|個)?\s*(?:passed|failed|過|敗)|全過|flutter (?:test|analyze)|npm run build", re.I)
DECIDE_RE = re.compile(r"^(?:\*\*)?需要你決定[：:]\s*")
ASK_RE = re.compile(r"(?:^|[，。；—])(請.+)")   # the part that says what to do, after the report of what was done
TASK_COLS = (m.AgentTask.id, m.AgentTask.title, m.AgentTask.status, m.AgentTask.agent, m.AgentTask.requested_by,
             m.AgentTask.progress, m.AgentTask.issue_ids, m.AgentTask.kind, m.AgentTask.stage, m.AgentTask.stage_state,
             m.AgentTask.stage_note, m.AgentTask.stage_at, m.AgentTask.created_at, m.AgentTask.updated_at,
             m.AgentTask.started_at, m.AgentTask.finished_at, m.AgentTask.difficulty)
ISSUE_COLS = (m.IssueReport.id, m.IssueReport.title, m.IssueReport.kind, m.IssueReport.status, m.IssueReport.severity,
              m.IssueReport.area, m.IssueReport.reporter, m.IssueReport.options, m.IssueReport.stage,
              m.IssueReport.stage_state, m.IssueReport.stage_note, m.IssueReport.stage_at, m.IssueReport.created_at,
              m.IssueReport.updated_at)


class ActBody(BaseModel):
    action: str
    text: str | None = None
    agent: str | None = None


def facts() -> dict:
    return flow._load(flow.FACTS)


def _source(tasks_: list, issues_: list) -> str:
    who = [i.reporter or "" for i in issues_]
    titles = [x.title or "" for x in (*tasks_, *issues_)]
    if any(w == "qc-bot" for w in who) or any(x.startswith("[qc]") for x in titles):
        return "qc"
    if any(t.requested_by == "owner" for t in tasks_) or "owner" in who or any("[owner]" in x for x in titles):
        return "owner"
    if any(w.startswith("App 使用者") for w in who) or any("[意見回饋]" in x for x in titles):
        return "phone"
    if any(w.startswith("Mac") for w in who) or any("[Mac" in x for x in titles):
        return "mac"
    if any("simulation" in w or "模擬" in w for w in who):
        return "sim"
    return "ai"


def _type(tasks_: list, issues_: list) -> str:
    if any(t.kind == "recurring" for t in tasks_):
        return "standing"
    kinds = {i.kind for i in issues_}
    return "decision" if "decision" in kinds else "bug" if "bug" in kinds else "need"


def task_stage(t, legacy: dict) -> str:
    if t.kind == "recurring":
        return "standing"
    if t.stage:
        return t.stage
    if str(t.id) in legacy:     # a card from before the pipeline that still waits for the Mac
        return legacy[str(t.id)]
    return {"queued": "queue", "done": "done", "cancelled": "cancelled"}.get(t.status, "dev")


def issue_own_stage(i) -> str:
    if i.stage:
        return i.stage
    return {"open": "queue", "needs_decision": "queue", "in_progress": "dev", "fixed": "done",
            "wont_fix": "cancelled"}.get(i.status, "queue")


def _slowest(stages: list[str]) -> str:
    live = [x for x in stages if x != "cancelled"]
    if "standing" in live:
        return "standing"
    return min(live, key=ORDER.index) if live else "cancelled"


def item_stage(cards: list, issues_: list, legacy: dict) -> str:
    """As far along as its least finished part. A card that went on to verification speaks for an old
    問題回報 still marked 處理中."""
    stages = [task_stage(t, legacy) for t in cards]
    verifying = any(x in VERIFY for x in stages)
    for i in issues_:
        own = issue_own_stage(i)
        if not cards or i.stage or (not verifying and own in ("queue", "dev")):
            stages.append(own)
    return _slowest(stages)


class Item:
    __slots__ = ("cards", "issues", "stage", "need", "runs")

    def __init__(self):
        self.cards, self.issues, self.need, self.runs, self.stage = [], [], None, {}, "queue"

    @property
    def key(self) -> str:
        return f"i{min(i.id for i in self.issues)}" if self.issues else f"t{self.cards[0].id}"

    @property
    def main_card(self):
        """The card that decides what happens next: the live one, else the newest."""
        live = [t for t in self.cards if t.status not in ("done", "cancelled", "scheduled")]
        return max(live or self.cards, key=lambda t: t.id) if self.cards else None

    @property
    def title(self) -> str:
        owner = next((t.title for t in self.cards if "[owner]" in (t.title or "")), None)
        return owner or (self.issues[0].title if self.issues else self.cards[0].title)


def merge(rows_t: list, rows_i: list) -> list[Item]:
    """問題 and its cards become one item. A standing card touches many reports over time, so it stays apart."""
    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    known = {i.id for i in rows_i}
    for t in rows_t:
        find(("t", t.id))
        if t.kind == "once":
            for iid in t.issue_ids or []:
                if iid in known:
                    parent[find(("i", iid))] = find(("t", t.id))
    groups: dict = {}
    for t in rows_t:
        groups.setdefault(find(("t", t.id)), Item()).cards.append(t)
    for i in rows_i:
        groups.setdefault(find(("i", i.id)), Item()).issues.append(i)
    return list(groups.values())


def load(s: Session, fx: dict) -> list[Item]:
    rows_t = s.execute(select(*TASK_COLS).order_by(m.AgentTask.id)).all()
    rows_i = s.execute(select(*ISSUE_COLS).order_by(m.IssueReport.id)).all()
    items = merge(rows_t, rows_i)
    for it in items:
        it.stage = item_stage(it.cards, it.issues, fx.get("legacy") or {})
        for t in it.cards:
            if t.status in tasks.WORKING:
                it.runs[t.id] = runs.card_run(t.id, t.status, t.agent, t.updated_at, t.started_at, t.progress)
        it.need = item_need(it)
    return items


def _first_line(text: str | None, limit: int = 120) -> str:
    line = next((x.strip() for x in (text or "").splitlines() if x.strip()), "")
    return DECIDE_RE.sub("", line)[:limit]


def _ask(text: str | None) -> str:
    line = _first_line(text, 400)
    found = ASK_RE.search(line)
    return (found.group(1) if found else line)[:160]


def _reply_options(card: int) -> list[str]:
    """One click: the card's own A／B／C, else the answer that lets it go on."""
    return flow_rules.decision_options(result_of(card)[1].split("\n\n")[0]) or [DONE_ANSWER]


def item_need(it: Item) -> dict | None:
    """Why this item can only go on with the owner, with the one thing to do."""
    decision = next((i for i in it.issues if flow.is_decision(i)), None)
    if decision:
        return {"kind": "decision", "issue": decision.id, "ask": "請你決定：" + decision.title[:80],
                "options": decision.options or [], "since": decision.updated_at}
    for t in it.cards:
        need = flow.task_need(t)
        if need == "reply":
            return {"kind": "reply", "task": t.id, "ask": _ask(t.progress) or f"這張卡在等你回覆：{t.title[:60]}",
                    "options": _reply_options(t.id), "since": t.updated_at}
        if need == "account":
            return {"kind": "account", "task": t.id, "ask": "需要帳號／付款／憑證：" + _first_line(t.progress, 90),
                    "options": [], "since": t.updated_at}
        if need == "manual":
            return {"kind": "manual", "task": t.id, "ask": "請在 iPad 上手動確認：" + _first_line(t.stage_note, 90),
                    "options": ["已確認沒問題"], "since": t.stage_at}
    return None


def _waits(it: Item) -> str:
    if it.need:
        return "you"
    states = {r["state"] for r in it.runs.values()}
    if "paused" in states:
        return "paused"
    if it.stage == "queue":
        return "queue"
    if it.stage == "dev":
        if states & {"running", "session"}:
            return "ai"
        if "collecting" in states:
            return "system"
        if any(t.status == "queued" or FOLLOW_RE.match(t.progress or "") for t in it.cards):
            return "queue"
        return "stuck"  # open, and nothing is working on it or queued for it
    if it.stage == "windows_check":
        return "system"
    if it.stage in ("mac_verify", "ipad_verify"):
        return "mac"
    return "release" if it.stage == "ready" else "none"


def _status_text(it: Item, wait: str) -> str:
    """Finished is said only at the last gate: a CLI being done means 等驗證."""
    states = {r["state"] for r in it.runs.values()}
    if wait in ("you", "paused", "stuck"):
        return WAITS[wait]
    if it.stage == "dev":
        return "等收卡" if "collecting" in states else "開發中" if wait == "ai" else "排隊中"
    if it.stage in VERIFY:
        return "等驗證"
    return {"queue": "排隊中", "standing": "定期執行", "ready": "可發布", "released": "已發布", "done": "完成",
            "cancelled": "已取消"}[it.stage]


def _source_group(it: Item, source: str, type_: str) -> str:
    if it.stage in CLOSED:
        return "closed"
    return "qc" if source == "qc" or type_ == "standing" else "active"


def _since(it: Item):
    times = [x for t in it.cards for x in (t.stage_at, t.finished_at, t.updated_at) if x]
    times += [x for i in it.issues for x in (i.stage_at, i.updated_at) if x]
    return max(times) if times else None


def row(it: Item) -> dict:
    source, type_ = _source(it.cards, it.issues), _type(it.cards, it.issues)
    wait = _waits(it)
    state = next((x.stage_state for x in (*it.cards, *it.issues) if x.stage_state), None)
    sev = next((i.severity for sev in ("high", "medium", "low") for i in it.issues if i.severity == sev), None)
    return {"key": it.key, "title": it.title, "type": type_, "type_label": TYPES[type_], "source": source,
            "source_label": SOURCES[source], "stage": it.stage, "stage_label": STAGES[it.stage], "state": state,
            "wait": wait, "wait_label": WAITS[wait], "status_text": _status_text(it, wait),
            "group": _source_group(it, source, type_), "severity": sev,
            "cards": [t.id for t in it.cards], "issues": [i.id for i in it.issues],
            "agent": it.main_card.agent if it.main_card else None, "since": _since(it),
            "created_at": min(x.created_at for x in (*it.cards, *it.issues))}


def _sort_key(r: dict):
    return (r["wait"] != "you", -(r["since"].timestamp() if r["since"] else 0))


def _match(r: dict, it: Item, q: str) -> bool:
    q = q.strip().lower().lstrip("#")
    if q.isdigit() and int(q) in (*r["cards"], *r["issues"]):
        return True
    return any(q in (x.title or "").lower() for x in (*it.cards, *it.issues))


def list_items(s: Session, group: str = "active", source: str | None = None, type_: str | None = None,
               stage: str | None = None, wait: str | None = None, q: str | None = None,
               limit: int = 200, offset: int = 0) -> dict:
    items = load(s, facts())
    pairs = [(row(it), it) for it in items]
    wanted = [r for r, it in pairs
              if (group == "all" or r["group"] == group) and (not source or r["source"] == source)
              and (not type_ or r["type"] == type_) and (not stage or r["stage"] == stage)
              and (not wait or r["wait"] == wait) and (not q or _match(r, it, q))]
    wanted.sort(key=_sort_key)
    return {"items": wanted[offset:offset + limit], "total": len(wanted), "groups": group_counts(pairs), "meta": meta()}


def group_counts(pairs: list) -> dict:
    return {k: sum(k == "all" or r["group"] == k for r, _ in pairs) for k in GROUPS}


def meta() -> dict:
    return {"sources": SOURCES, "types": TYPES, "stages": STAGES, "waits": WAITS, "group_labels": GROUPS}


# ── Timeline ─────────────────────────────────────────────────────────

def _stage_at(history: list | None, label: str) -> tuple[str | None, str | None]:
    for h in history or []:
        for c in h.get("changes") or []:
            if c.get("field") == "stage" and c.get("to") == label:
                return h.get("at"), h.get("by")
    return None, None


def result_of(card: int) -> tuple[str | None, str]:
    """Newest result file of a card: path for the owner, its text."""
    base = runs.AGENT_LOGS
    found = sorted(base.glob(f"card{card}.r*.result.md"), key=lambda p: p.stat().st_mtime)
    plain = base / f"card{card}.result.md"
    path = plain if plain.exists() else (found[-1] if found else None)
    if not path:
        return None, ""
    return f"lexicon/logs/agents/{path.name}", path.read_text(encoding="utf-8", errors="replace")


def result_summary(text: str) -> list[str]:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    tests = [x[:160] for x in lines[1:] if TEST_RE.search(x)][:3]
    return [*lines[:1], *tests]


def _step(key: str, label: str, state: str, at=None, by=None, evidence=None) -> dict:
    return {"key": key, "label": label, "state": state, "at": at, "by": by, "evidence": evidence or []}


def timeline(it: Item, t, fx: dict) -> list[dict]:
    """source → 派工 → 開發 → Windows 檢查 → Mac → iPad → 可發布. state: done · current · todo · skipped · failed."""
    source = SOURCES[_source(it.cards, it.issues)]
    first = min(x.created_at for x in (*it.cards, *it.issues))
    steps = [_step("source", "來源", "done", first, source, [it.title[:120]])]
    stage = task_stage(t, fx.get("legacy") or {}) if t else it.stage
    if not t:
        steps.append(_step("dispatch", "派工", "current"))
        steps += [_step(k, v, "todo") for k, v in (("dev", "開發"), ("windows_check", "Windows 檢查"),
                                                   ("mac_verify", "Mac"), ("ipad_verify", "iPad"), ("ready", "可發布"))]
        return steps
    steps.append(_step("dispatch", "派工", "done" if t.started_at else "current", t.started_at, t.agent,
                       [f"卡 #{t.id}"] + ([f"難度 {tasks.DIFFICULTY.get(t.difficulty, t.difficulty)}"] if t.difficulty else [])))
    path, text = result_of(t.id) if t.status != "queued" else (None, "")
    done_dev = t.status == "done"
    run = it.runs.get(t.id) or {}
    dev_notes = result_summary(text) if text else ([t.progress[:160]] if t.progress else [])
    if path:
        dev_notes.append(f"結果：{path}")
    steps.append(_step("dev", "開發", "done" if done_dev else "todo" if not t.started_at else "current",
                       t.finished_at, t.agent, dev_notes))
    if run.get("state") == "collecting":
        steps[-1]["state"] = "current"
        steps[-1]["evidence"].insert(0, "CLI 寫完結果，等派工程式收卡")
    if done_dev and stage == "done":
        for k, v in (("windows_check", "Windows 檢查"), ("mac_verify", "Mac"), ("ipad_verify", "iPad")):
            steps.append(_step(k, v, "skipped", evidence=["不需要：這張卡沒有改到 App"]))
        steps.append(_step("ready", "可發布", "done", t.finished_at, "系統", ["卡片完成，不需 Mac 驗證"]))
        return steps
    handed = (fx.get("handed") or {}).get(str(t.id))
    verdicts = (fx.get("verdicts") or {}).get(str(t.id)) or {}
    pos = ORDER.index(stage) if stage in ORDER else 0
    bad = t.stage_state in ("failed", "note")

    def gate(key: str, label: str, device: str | None, notes: list[str], when: str | None = None) -> dict:
        at, by = _stage_at(t.history, flow.STAGES[ORDER[ORDER.index(key) + 1]])
        state = "done" if pos > ORDER.index(key) else "current" if pos == ORDER.index(key) and done_dev else "todo"
        if state == "current" and bad:
            state = "failed" if t.stage_state == "failed" else "current"
        v = verdicts.get(device) if device else None
        if v:
            day = f"{v['date'][5:].replace('-', '/')} " if v.get("date") else ""
            notes = [*notes, f"{day}{ {'pass': '通過', 'fail': '不通過', 'note': '注意'}.get(v['verdict'], v['verdict']) }：{v['text']}"]
        elif device == "sim" and state == "done" and verdicts.get("ipad"):
            notes = [*notes, "Mac 沒有單獨一列，以 iPad 那列為準"]
        if state == "current" and t.stage_note:
            notes = [*notes, t.stage_note[:200]]
        return _step(key, label, state, at or when, by or ("Mac" if device else "mac_sync" if state == "done" else None), notes)

    steps.append(gate("windows_check", "Windows 檢查", None, [f"已推給 Mac：{handed[0]}（commit {handed[1][:8]}）"] if handed else [],
                      handed[2] if handed and len(handed) > 2 else None))
    steps.append(gate("mac_verify", "Mac", "sim", []))
    steps.append(gate("ipad_verify", "iPad", "ipad", []))
    at, by = _stage_at(t.history, flow.STAGES["ready"])
    steps.append(_step("ready", "可發布", "done" if pos >= ORDER.index("ready") else "todo", at, by))
    return steps


def instructions(s: Session, tasks_: list, issues_: list) -> list[dict]:
    """補充指示 and where each one has got to: it is visible whether it arrived."""
    out = []
    for row_ in (*tasks_, *issues_):
        for h in row_.history or []:
            delivery = h.get("delivery")
            if not delivery:
                continue
            out.append({"at": h.get("at"), "text": h.get("text"), "kind": delivery.get("kind"),
                        "where": delivery_status(s, delivery, h.get("at"), row_)})
    return sorted(out, key=lambda x: x["at"] or "", reverse=True)


def delivery_status(s: Session, d: dict, at: str | None, row_) -> str:
    if d.get("kind") == "followup":
        f = s.get(m.AgentTask, d["card"])
        if not f:
            return f"接續卡 #{d['card']} 已被刪除"
        if FOLLOW_RE.match(f.progress or ""):
            return f"已開接續卡 #{f.id}，等 #{d.get('after')} 收卡後派工"
        word = {"queued": "排隊等 AI", "in_progress": f"{f.agent or 'AI'} 已開工，有讀到", "done": "已做完",
                "cancelled": "已取消", "blocked": "卡住", "waiting": "等你回覆"}.get(f.status, f.status)
        return f"接續卡 #{f.id}：{word}"
    if d.get("kind") == "issue":
        return "已寫進問題回報，接手的 CLI 會讀到"
    if isinstance(row_, m.AgentTask) and row_.started_at and at and row_.started_at.isoformat() > at:
        return f"{row_.agent or 'AI'} 開工時已讀到"
    return "已寫進卡片說明，下一個 CLI 開工時會讀到"


def detail(s: Session, key: str) -> dict:
    fx = facts()
    it = find(load(s, fx), key)
    r = row(it)
    full_t = [s.get(m.AgentTask, t.id) for t in it.cards]
    full_i = [s.get(m.IssueReport, i.id) for i in it.issues]
    main = it.main_card
    main_full = next((t for t in full_t if main and t.id == main.id), None)
    log = [{"at": h.get("at"), "by": h.get("by"), "what": f"{'卡' if isinstance(x, m.AgentTask) else '問題'} #{x.id}",
            "note": h.get("note"), "changes": h.get("changes") or []} for x in (*full_t, *full_i) for h in x.history or []]
    log.sort(key=lambda h: h["at"] or "", reverse=True)
    return {**r, "need": it.need, "timeline": timeline(it, main_full, fx), "main_card": main.id if main else None,
            "actions": allowed_actions(it), "run": it.runs.get(main.id) if main else None,
            "cards_full": [{"id": t.id, "title": t.title, "detail": t.detail, "status": t.status,
                            "status_label": tasks.STATUSES.get(t.status, t.status), "agent": t.agent, "progress": t.progress,
                            "difficulty": t.difficulty, "stage": task_stage(t, fx.get("legacy") or {})} for t in full_t],
            "issues_full": [issues.issue_dict(i) for i in full_i],
            "instructions": instructions(s, full_t, full_i), "log": log[:60]}


def find(items: list[Item], key: str) -> Item:
    if not re.fullmatch(r"[ti]\d+", key):
        raise HTTPException(404, "找不到這個項目")
    kind, num = key[0], int(key[1:])
    for it in items:
        if num in [x.id for x in (it.cards if kind == "t" else it.issues)]:
            return it
    raise HTTPException(404, "找不到這個項目")


# ── Stepping in ──────────────────────────────────────────────────────

def allowed_actions(it: Item) -> list[str]:
    t = it.main_card
    paused = bool(t) and runs.is_paused(t.progress)
    if t and t.kind == "recurring":
        return ["resume", "instruct"] if paused else ["pause", "instruct"]
    if paused:
        return ["resume", "instruct", "cancel"]
    closed = it.stage in CLOSED
    out = [] if closed and not t else ["instruct"]      # a closed report has nothing left to read an instruction
    if it.stage in ("queue", "dev"):                    # further on nothing is waiting to be picked up
        out += ["pause", "top", "bottom"]
        if not t or (t.status == "queued" and not t.agent):
            out.append("assign")
    if t or closed:
        out.append("redo")
    if not closed:
        out.append("cancel")
    if it.need:
        out.append("answer")
    return out


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clock() -> str:
    return datetime.now(TAIPEI).strftime("%m/%d %H:%M")


def _note_delivery(row_, text: str, delivery: dict):
    row_.history = [*(row_.history or []), {
        "at": _now().isoformat(), "by": "owner", "note": f"補充指示：{text[:200]}", "text": text, "delivery": delivery,
        "changes": [{"field": "instruction", "from": None, "to": text[:200]}]}]


def ensure_card(s: Session, it: Item) -> m.AgentTask:
    """An action on a 問題回報 nobody took yet needs a card to hold it (the swarm then skips the report)."""
    live = it.main_card
    if live and live.status not in ("done", "cancelled"):
        return s.get(m.AgentTask, live.id)
    i = s.get(m.IssueReport, it.issues[0].id)
    t = tasks.card_for_issue(i)
    t.issue_ids = [x.id for x in it.issues]
    s.add(t)
    tasks._apply(t, {"status": "queued"}, "控制台：由問題回報建立", "owner")
    s.flush()
    return t


def _follow_up(s: Session, parent, text: str, after: int | None) -> m.AgentTask:
    title = f"[owner] 接續 #{parent.id}：{text.splitlines()[0][:60]}"
    body = (f"owner 在卡 #{parent.id}「{parent.title}」的補充指示：\n{text}\n\n"
            f"先讀 lexicon/logs/agents/card{parent.id}.result.md，沿用它的結果，不要重做。")
    f = m.AgentTask(title=title[:300], detail=body, issue_ids=list(parent.issue_ids or []), requested_by="owner",
                    kind="once", history=[], difficulty=parent.difficulty, difficulty_reason=parent.difficulty_reason,
                    position=0)
    s.add(f)
    data = {"status": "blocked", "progress": f"{FOLLOW_PREFIX}{after} 收卡後自動派工"} if after else {"status": "queued"}
    tasks._apply(f, data, f"控制台：接續卡 #{parent.id}", "owner")
    s.flush()
    return f


def instruct(s: Session, it: Item, text: str) -> str:
    t = it.main_card
    if not t:
        i = s.get(m.IssueReport, it.issues[0].id)
        i.detail = f"{i.detail or ''}\n\n【owner {_clock()} 補充指示】{text}".strip()
        _note_delivery(i, text, {"kind": "issue"})
        return "已寫進問題回報，接手的 CLI 會讀到"
    full = s.get(m.AgentTask, t.id)
    run = it.runs.get(t.id) or {}
    if run.get("alive") or run.get("state") == "collecting":
        f = _follow_up(s, full, text, t.id)
        _note_delivery(full, text, {"kind": "followup", "card": f.id, "after": t.id})
        return f"CLI 執行中讀不到修改，已開接續卡 #{f.id}，#{t.id} 收卡後自動派工"
    if t.status in ("done", "cancelled"):
        f = _follow_up(s, full, text, None)
        _note_delivery(full, text, {"kind": "followup", "card": f.id, "after": t.id})
        return f"卡 #{t.id} 已結束，已開接續卡 #{f.id} 排隊"
    full.detail = f"{full.detail or ''}\n\n【owner {_clock()} 補充指示】{text}".strip()
    full.updated_at = _now()
    _note_delivery(full, text, {"kind": "detail"})
    return "已寫進卡片說明，下一個 CLI 開工時會讀到"


def _pause(s: Session, it: Item) -> str:
    t = ensure_card(s, it)
    killed = runs.stop_cli(t.id)
    tasks._apply(t, {"status": "blocked", "agent": None, "progress": f"{runs.PAUSED_PREFIX} {_clock()}"}, "控制台：暫停", "owner")
    return f"#{t.id} 已暫停" + ("，並結束正在跑的 CLI（已做的修改留在工作目錄）" if killed else "")


def _resume(s: Session, it: Item) -> str:
    t = s.get(m.AgentTask, it.main_card.id)
    if not runs.is_paused(t.progress):
        raise HTTPException(409, "這個項目沒有暫停")
    tasks._apply(t, {"status": "scheduled" if t.kind == "recurring" else "queued", "progress": None}, "控制台：繼續", "owner")
    return f"#{t.id} 已排回待辦"


def _move(s: Session, it: Item, top: bool) -> str:
    t = ensure_card(s, it)
    if t.status not in ("queued", "blocked"):
        raise HTTPException(409, "這張卡已經開工，順序不能再改；要改方向請用補充指示")
    others = [x or 0 for x in s.execute(select(m.AgentTask.position).where(m.AgentTask.status == "queued")).scalars()]
    t.position = min([0.0, *others]) - 1 if top else max([LAST_POSITION, *others]) + 1
    t.updated_at = _now()
    t.history = [*(t.history or []), {"at": _now().isoformat(), "by": "owner", "changes": [],
                                      "note": "控制台：提到最前" if top else "控制台：排到最後"}]
    return f"#{t.id} 已{'提到最前' if top else '排到最後'}"


def _cancel(s: Session, it: Item) -> str:
    killed = False
    for x in it.cards:
        if x.kind == "once" and x.status not in ("done", "cancelled"):
            killed = runs.stop_cli(x.id) or killed
            tasks._apply(s.get(m.AgentTask, x.id), {"status": "cancelled", "agent": None}, "控制台：取消", "owner")
    for i in it.issues:
        if i.status not in issues.CLOSED:
            issues._apply(s.get(m.IssueReport, i.id), {"status": "wont_fix"}, "控制台：取消", "owner")
    return f"{it.key[1:]} 已取消" + ("，並結束正在跑的 CLI" if killed else "")


def _redo(s: Session, it: Item, text: str | None) -> str:
    if not it.cards:
        for i in it.issues:
            issues._apply(s.get(m.IssueReport, i.id), {"status": "open"}, "控制台：退回重做", "owner")
        return "已退回，排回待辦"
    t = s.get(m.AgentTask, it.main_card.id)
    killed = runs.stop_cli(t.id)
    t.detail = f"{t.detail or ''}\n\n【owner {_clock()} 退回重做】{text or '上一輪不算數，請重新檢查再做。'}".strip()
    tasks._apply(t, {"status": "queued", "agent": None, "progress": None}, f"控制台：退回重做。{text or ''}", "owner")
    for i in it.issues:
        if i.status in issues.CLOSED:
            issues._apply(s.get(m.IssueReport, i.id), {"status": "in_progress"}, f"控制台：卡 #{t.id} 退回重做", "owner")
    return f"#{t.id} 已退回重做" + ("，並結束正在跑的 CLI" if killed else "")


def _answer(s: Session, it: Item, text: str) -> str:
    need = it.need
    if not need:
        raise HTTPException(409, "這個項目沒有在等你")
    if need["kind"] == "decision":
        i = s.get(m.IssueReport, need["issue"])
        issues._apply(i, {"decision": text, "status": issues._status_after_decision(text)}, None, "owner")
        return f"#{i.id} 已記下你的決定"
    t = s.get(m.AgentTask, need["task"])
    if need["kind"] == "manual":
        path = flow.STATE / "owner_confirmed.json"
        done = flow._load(path)
        done[str(t.id)] = _now().isoformat()
        path.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
        t.history = [*(t.history or []), {"at": _now().isoformat(), "by": "owner", "changes": [], "note": f"控制台：手動確認。{text}"}]
        return f"#{t.id} 已記下確認，下一輪流程會往前走"
    t.detail = f"{t.detail or ''}\n\n【owner {_clock()} 回覆】{text}".strip()
    tasks._apply(t, {"status": "queued", "agent": None, "progress": None}, f"控制台：回覆。{text[:200]}", "owner")
    return f"#{t.id} 已收到回覆，排回待辦"


def act(s: Session, key: str, body: ActBody) -> dict:
    it = find(load(s, facts()), key)
    text = (body.text or "").strip()
    a = body.action
    if a not in allowed_actions(it):
        raise HTTPException(409, "這個項目現在不能這樣操作")
    if a in ("instruct", "answer") and not text:
        raise HTTPException(422, "請先寫內容")
    if a == "instruct":
        msg = instruct(s, it, text)
    elif a == "answer":
        msg = _answer(s, it, text)
    elif a == "pause":
        msg = _pause(s, it)
    elif a == "resume":
        msg = _resume(s, it)
    elif a in ("top", "bottom"):
        msg = _move(s, it, a == "top")
    elif a == "cancel":
        msg = _cancel(s, it)
    elif a == "redo":
        msg = _redo(s, it, text)
    elif a == "assign":
        if not body.agent:
            raise HTTPException(422, "要指定 AI")
        t = ensure_card(s, it)
        tasks.assign(s, body.agent, t.id, None)
        msg = f"#{t.id} 已交給 {body.agent}"
    else:
        raise HTTPException(422, f"不認得的操作：{a}")
    s.flush()
    return {"message": msg}


def release_followups(s: Session) -> int:
    """接續卡 start when the card they follow has been collected (run by flow_tick every tick)."""
    n = 0
    for t in s.execute(select(m.AgentTask).where(m.AgentTask.status == "blocked",
                                                 m.AgentTask.progress.like(f"{FOLLOW_PREFIX}%"))).scalars():
        got = FOLLOW_RE.match(t.progress or "")
        parent = s.get(m.AgentTask, int(got.group(1))) if got else None
        if got and (parent is None or parent.status not in ("in_progress",)):
            tasks._apply(t, {"status": "queued", "progress": None}, f"#{got.group(1)} 已收卡，開始接續", "控制台")
            n += 1
    s.flush()
    return n


# ── 現況 ─────────────────────────────────────────────────────────────

def needs_list(items: list[Item], release: dict, fx: dict, now: datetime, rows_t: list) -> list[dict]:
    out = [{"key": it.key, "title": it.title, **it.need} for it in items if it.need]
    out.sort(key=lambda x: x["since"] or now)
    if release["can_release"]:
        out.append({"key": None, "kind": "release", "title": f"版本 {release['version']} 可以發布", "options": [],
                    "ask": f"{release['ready']} 張卡都過了 iPad 驗證，到 App Store Connect 按發布", "since": None})
    silent = flow.mac_silent(rows_t, fx, now)
    if silent:
        out.append({"key": None, "kind": "mac", "title": "Mac 沒有回報", "options": [], "since": None,
                    "ask": f"Mac 超過 {flow.MAC_QUIET_HOURS // 24} 天沒有寫驗證結果，{silent} 張卡在等：請確認 Mac 有開著"})
    return out


def stuck_list(pairs: list[tuple[dict, Item]], now: datetime) -> list[dict]:
    rows_ = [r for r, _ in pairs if r["group"] == "active" and r["wait"] in ("stuck", "system", "mac", "queue") and r["since"]]
    out = [{"key": r["key"], "title": r["title"], "stage_label": r["stage_label"], "wait_label": r["wait_label"],
            "state": r["state"], "hours": int((now - r["since"]).total_seconds() // 3600)} for r in rows_]
    return sorted(out, key=lambda x: -x["hours"])[:8]


def overview(s: Session) -> dict:
    now = _now()
    fx = facts()
    o = flow.overview(s)
    items = load(s, fx)
    pairs = [(row(it), it) for it in items]
    rows_t = s.execute(select(*TASK_COLS).where(m.AgentTask.kind == "once", m.AgentTask.stage.is_not(None))).all()
    counts = {k: sum(r["stage"] == k for r, _ in pairs if r["group"] != "qc") for k in STAGES}
    hand = [{"card": t.id, "title": t.title, "agent": t.agent, "status": t.status, **it.runs[t.id]}
            for it in items for t in it.cards if t.id in it.runs]
    cards_verify = sum(1 for it in items for t in it.cards if task_stage(t, fx.get("legacy") or {}) in VERIFY)
    return {"needs_you": needs_list(items, o["release"], fx, now, rows_t), "release": o["release"], "counts": counts,
            "stages": STAGES, "main_stages": [k for k in ORDER if k not in ("released", "done")] + ["released", "done"],
            "stuck": stuck_list(pairs, now), "runs": runs.overview(hand), "cards_verifying": cards_verify,
            "legacy_waiting": len(fx.get("legacy") or {}), "digest": o["digest"],
            "flow_at": o["updated_at"], "now": now, "groups": group_counts(pairs)}


def register(app, auth):
    DB = Depends(db.get_session)

    @app.get("/console/overview", dependencies=[auth])
    def console_overview(s: Session = DB):
        return overview(s)

    @app.get("/console/items", dependencies=[auth])
    def console_items(group: str = "active", source: str | None = None, type: str | None = None,  # noqa: A002
                      stage: str | None = None, wait: str | None = None, q: str | None = None,
                      limit: int = 200, offset: int = 0, s: Session = DB):
        return list_items(s, group, source, type, stage, wait, q, min(limit, 500), offset)

    @app.get("/console/items/{key}", dependencies=[auth])
    def console_item(key: str, s: Session = DB):
        return detail(s, key)

    @app.post("/console/items/{key}/act", dependencies=[auth])
    def console_act(key: str, body: ActBody, s: Session = DB):
        return act(s, key, body)

    @app.post("/console/followups", dependencies=[auth])
    def console_followups(s: Session = DB):
        return {"released": release_followups(s)}
