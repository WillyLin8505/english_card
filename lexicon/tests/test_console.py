"""控制台 (card #919): one list, a strict 需要你, real interventions, and only live processes count as working."""
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import dispatch_tick as dt  # noqa: E402
import flow_rules as fr  # noqa: E402
import flow_tick  # noqa: E402
import launch_agent as la  # noqa: E402
import pick_card  # noqa: E402
import proc_identity as pi  # noqa: E402
import resource_guard as rg  # noqa: E402

H = {"X-API-Key": "test-key"}


@pytest.fixture
def child():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    yield p
    p.kill()
    p.wait()


@pytest.fixture
def client(session, monkeypatch, tmp_path):
    from app import config, console, flow, runs
    from app.main import app
    monkeypatch.setattr(config, "API_KEY", "test-key")
    monkeypatch.setattr(flow, "start_ids", lambda: {"task": 1, "issue": 1})
    monkeypatch.setattr(flow, "_load", lambda p: {})
    monkeypatch.setattr(console, "facts", lambda: {})
    monkeypatch.setattr(runs, "AGENT_LOGS", tmp_path)
    monkeypatch.setattr(runs, "SESSIONS", tmp_path / "no-sessions")
    monkeypatch.setattr(runs, "_sessions_cache", (0.0, []))
    with TestClient(app) as c:
        yield c


def _task(client, title="改東西", **kw):
    r = client.post("/tasks", headers=H, json={"title": title, "kind": "once", "requested_by": "owner", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _issue(client, title="有問題", **kw):
    r = client.post("/issues", headers=H, json={"title": title, "kind": "bug", "status": "open", "severity": "medium",
                                                "area": "app", **kw})
    assert r.status_code in (200, 201), r.text
    return r.json()


def _pid_file(tmp_path, card, pid, **kw):
    (tmp_path / f"card{card}.pid.json").write_text(json.dumps({"pid": pid, "agent": "Claude CLI 1", **kw}), encoding="utf-8")


def _items(client, **q):
    return client.get("/console/items", headers=H, params={"group": "all", **q}).json()["items"]


def _one(client, key):
    r = client.get(f"/console/items/{key}", headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def _act(client, key, action, **kw):
    r = client.post(f"/console/items/{key}/act", headers=H, json={"action": action, **kw})
    assert r.status_code == 200, r.text
    return r.json()["message"]


# ── Is it the CLI we launched? ───────────────────────────────────────

def test_same_process_by_creation_time(child):
    started = pi.process_started(child.pid)
    assert started and pi.same_process(child.pid, started)
    assert not pi.same_process(child.pid, started - 100)  # same pid, another program


def test_reused_pid_of_an_old_record_is_not_alive(child):
    long_ago = time.time() - 3600
    assert not pi.run_alive({"pid": child.pid, "at": long_ago})  # started after that launch: reused
    assert pi.run_alive({"pid": child.pid, "at": time.time()})


def test_pid_without_any_record_of_the_launch_proves_nothing(child):
    assert not pi.run_alive({"pid": child.pid})


def test_ended_process_is_not_alive(child):
    started = pi.process_started(child.pid)
    child.kill()
    child.wait()
    assert pi.process_started(child.pid) is None
    assert not pi.same_process(child.pid, started)


def test_kill_tree_refuses_a_reused_pid(child):
    assert pi.kill_tree({"pid": child.pid, "started": pi.process_started(child.pid) - 100}) is False
    assert child.poll() is None
    assert pi.kill_tree({"pid": child.pid, "started": pi.process_started(child.pid)}) is True


def test_launch_agent_records_creation_time_and_sees_reuse(child, tmp_path, monkeypatch):
    monkeypatch.setattr(la, "LOGS", tmp_path)
    la.record_run(7, "Claude CLI 1", child.pid)
    info = json.loads((tmp_path / "card7.pid.json").read_text(encoding="utf-8"))
    assert info["started"] == pytest.approx(pi.process_started(child.pid))
    assert la.live_run(7)["pid"] == child.pid
    info["started"] -= 500
    (tmp_path / "card7.pid.json").write_text(json.dumps(info), encoding="utf-8")
    assert la.live_run(7) is None


def test_dispatch_tick_and_resource_guard_share_the_check(child, tmp_path, monkeypatch):
    monkeypatch.setattr(la, "LOGS", tmp_path)
    monkeypatch.setattr(rg, "LOGS", tmp_path)
    tick = dt.Tick.__new__(dt.Tick)
    run = {"pid": child.pid, "launched_at": time.time()}
    la.record_run(8, "Claude CLI 1", child.pid)
    assert tick.cli_up(8, run) is True
    assert rg.cli_roots() == {child.pid: 8}
    _pid_file(tmp_path, 8, child.pid, at=time.time() - 3600)
    assert tick.cli_up(8, run) is False  # the pid file says this pid was launched long before the process started
    assert rg.cli_roots() == {}


def test_dispatch_tick_old_run_without_pid_file_tolerates_a_slow_launch(child, tmp_path, monkeypatch):
    monkeypatch.setattr(la, "LOGS", tmp_path)
    tick = dt.Tick.__new__(dt.Tick)
    assert tick.cli_up(9, {"pid": child.pid, "launched_at": time.time() - 120}) is True
    assert tick.cli_up(9, {"pid": child.pid, "launched_at": time.time() - 3600}) is False


# ── What the AI is really doing ──────────────────────────────────────

def _run(card, status="in_progress", agent="Claude CLI 1", ago=0, progress=None):
    from app import runs
    now = datetime.now(timezone.utc)
    return runs.card_run(card, status, agent, now - timedelta(minutes=ago), now - timedelta(hours=1), progress)


def test_card_run_states(child, tmp_path, monkeypatch):
    from app import runs
    monkeypatch.setattr(runs, "AGENT_LOGS", tmp_path)
    monkeypatch.setattr(runs, "SESSIONS", tmp_path / "x")
    monkeypatch.setattr(runs, "_sessions_cache", (0.0, []))
    started = pi.process_started(child.pid)
    _pid_file(tmp_path, 1, child.pid, at=started, started=started)
    assert _run(1, ago=500)["state"] == "running"  # quiet for hours, alive: not 「可能已停止」
    _pid_file(tmp_path, 2, child.pid, at=started - 3600)  # reused pid
    assert _run(2)["state"] == "idle"
    assert _run(3)["state"] == "idle"
    assert _run(4, agent="Claude · Manager")["state"] == "session"
    assert _run(4, agent="Claude · Manager", ago=60 * 24 * 4)["state"] == "idle"  # #721: the old Manager card
    assert _run(5, status="waiting")["state"] == "waiting"
    _pid_file(tmp_path, 6, child.pid, at=started, started=started)
    (tmp_path / "card6.result.md").write_text("做完了", encoding="utf-8")
    assert _run(6)["state"] == "collecting"


def test_board_counts_only_processes_as_working(client, tmp_path, child):
    started = pi.process_started(child.pid)
    live = _task(client, "活的", status="in_progress", agent="Claude CLI 1")
    dead = _task(client, "舊卡", status="in_progress", agent="Claude · Manager")
    _pid_file(tmp_path, live["id"], child.pid, at=started, started=started)
    from sqlalchemy import update

    from app import models as m
    from app import db
    with db.SessionLocal() as s:
        s.execute(update(m.AgentTask).where(m.AgentTask.id.in_([live["id"], dead["id"]]))
                  .values(updated_at=datetime.now(timezone.utc) - timedelta(days=4)))
        s.commit()
    bots = {b["agent"]: b for b in client.get("/schedule/board", headers=H).json()["bots"]}
    assert bots["Claude CLI 1"]["state"] == "working"
    assert bots["Claude CLI 1"]["doing"][0]["stale"] is False
    assert bots["Claude · Manager"]["state"] == "stale"


def test_overview_splits_working_waiting_and_old(client, tmp_path, child):
    started = pi.process_started(child.pid)
    a = _task(client, "跑", status="in_progress", agent="Claude CLI 1")
    b = _task(client, "寫完", status="in_progress", agent="Claude CLI 2")
    c = _task(client, "等人", status="waiting", agent="Claude CLI 3")
    d = _task(client, "舊", status="in_progress", agent="Grok")
    _pid_file(tmp_path, a["id"], child.pid, at=started, started=started)
    (tmp_path / f"card{b['id']}.result.md").write_text("結果", encoding="utf-8")
    _pid_file(tmp_path, b["id"], 1, at=time.time() - 60)
    r = client.get("/console/overview", headers=H).json()["runs"]
    assert (r["counts"]["working"], r["counts"]["collecting"], r["counts"]["waiting"]) == (1, 1, 1)
    assert [x["card"] for x in r["working"]] == [a["id"]]
    assert r["working"][0]["pid"] == child.pid and r["working"][0]["started_at"]
    assert d["id"] in [x["card"] for x in r["idle"]]
    assert c["id"] in [x["card"] for x in r["waiting"]]


def test_same_agent_on_two_cards_is_visible(client, tmp_path, child):
    started = pi.process_started(child.pid)
    a = _task(client, "一", status="in_progress", agent="Claude Code")
    b = _task(client, "二", status="in_progress", agent="Claude Code")
    _pid_file(tmp_path, a["id"], child.pid, at=started, started=started)
    r = client.get("/console/overview", headers=H).json()["runs"]
    assert r["working"][0]["also"] == [b["id"]]


def test_interactive_sessions_are_listed_apart(client, tmp_path, monkeypatch, child):
    from app import config, runs
    d = tmp_path / "sessions"
    d.mkdir()
    started = pi.process_started(child.pid)
    fields = {"cwd": str(config.HOME.parent), "startedAt": started * 1000, "procStart": int((started + 11644473600) * 1e7),
              "name": "card manager", "status": "idle"}
    (d / "1.json").write_text(json.dumps({"pid": child.pid, "entrypoint": "claude-desktop", **fields}), encoding="utf-8")
    (d / "2.json").write_text(json.dumps({"pid": child.pid, "entrypoint": "sdk-cli", **fields}), encoding="utf-8")
    (d / "3.json").write_text(json.dumps({"pid": 999999, "entrypoint": "claude-desktop", **fields}), encoding="utf-8")
    monkeypatch.setattr(runs, "SESSIONS", d)
    r = client.get("/console/overview", headers=H).json()["runs"]
    assert [x["name"] for x in r["sessions"]] == ["card manager"]
    assert r["counts"]["working"] == 0


# ── One row per item ─────────────────────────────────────────────────

def test_issue_and_its_card_are_one_row(client):
    i = _issue(client, "相機壞了")
    t = _task(client, f"問題回報 #{i['id']}：相機壞了", issue_ids=[i["id"]])
    rows = [r for r in _items(client) if i["id"] in r["issues"]]
    assert len(rows) == 1 and rows[0]["cards"] == [t["id"]] and rows[0]["key"] == f"i{i['id']}"
    assert _one(client, f"t{t['id']}")["key"] == f"i{i['id']}"  # the card's address finds the same item


def test_standing_card_stays_apart_from_its_reports(client):
    i = _issue(client, "舊問題")
    t = client.post("/tasks", headers=H, json={"title": "每天看", "kind": "recurring", "interval_minutes": 60,
                                               "requested_by": "owner", "issue_ids": [i["id"]]}).json()
    rows = _items(client)
    assert [r["type"] for r in rows if t["id"] in r["cards"]] == ["standing"]
    assert [r["cards"] for r in rows if i["id"] in r["issues"]] == [[]]
    assert client.get("/console/items", headers=H, params={"group": "qc"}).json()["total"] == 1


def test_qc_metrics_are_kept_out_of_what_needs_handling(client):
    q = _issue(client, "[qc] sense.native_empty：義項沒有中文", reporter="qc-bot", status="in_progress", area="data")
    real = _issue(client, "真的壞了")
    active = client.get("/console/items", headers=H, params={"group": "active"}).json()["items"]
    qc = client.get("/console/items", headers=H, params={"group": "qc"}).json()["items"]
    assert [r["key"] for r in active] == [f"i{real['id']}"]
    assert [r["key"] for r in qc] == [f"i{q['id']}"] and qc[0]["source_label"] == "長期 QC"


def test_filters_and_search(client):
    phone = _issue(client, "[意見回饋] 字太小", reporter="App 使用者")
    _issue(client, "別的")
    assert [r["key"] for r in _items(client, source="phone")] == [f"i{phone['id']}"]
    assert [r["key"] for r in _items(client, q=f"#{phone['id']}")] == [f"i{phone['id']}"]
    assert [r["key"] for r in _items(client, q="字太小")] == [f"i{phone['id']}"]
    assert _items(client, wait="you") == []
    assert _items(client, stage="ready") == []


# ── 完成 only at the last gate ───────────────────────────────────────

def test_finished_cli_on_app_card_says_waiting_for_verification(client):
    t = _task(client, "改畫面", status="done")
    client.post("/flow/stages", headers=H, json={"items": [{"type": "task", "id": t["id"], "stage": "windows_check"}]})
    r = _items(client)[0]
    assert (r["status_text"], r["wait_label"], r["group"]) == ("等驗證", "系統處理", "active")


def test_card_older_than_the_pipeline_shows_what_it_still_waits_for(client, monkeypatch):
    from app import console
    t = _task(client, "舊 App 卡", status="done")
    assert _items(client)[0]["status_text"] == "完成"
    monkeypatch.setattr(console, "facts", lambda: {"legacy": {str(t["id"]): "windows_check"}})
    assert _items(client)[0]["status_text"] == "等驗證"
    assert client.get("/console/overview", headers=H).json()["counts"]["windows_check"] == 1


def test_timeline_of_an_app_card_quotes_its_evidence(client, tmp_path, monkeypatch):
    from app import console
    t = _task(client, "改畫面", status="done", agent="Claude CLI 1")
    (tmp_path / f"card{t['id']}.result.md").write_text("改好了\nflutter test 1834 過\n", encoding="utf-8")
    client.post("/flow/stages", headers=H, json={"items": [{"type": "task", "id": t["id"], "stage": "ipad_verify"}]})
    monkeypatch.setattr(console, "facts", lambda: {
        "handed": {str(t["id"]): ["M540", "abcdef123456"]},
        "verdicts": {str(t["id"]): {"sim": {"verdict": "pass", "text": "| M540 | 通過 |"}}}})
    steps = {x["key"]: x for x in _one(client, f"t{t['id']}")["timeline"]}
    assert [k for k in steps] == ["source", "dispatch", "dev", "windows_check", "mac_verify", "ipad_verify", "ready"]
    assert steps["dev"]["state"] == "done" and any("1834" in x for x in steps["dev"]["evidence"])
    assert any("M540" in x for x in steps["windows_check"]["evidence"])
    assert steps["mac_verify"]["state"] == "done" and "通過" in steps["mac_verify"]["evidence"][0]
    assert steps["ipad_verify"]["state"] == "current" and steps["ready"]["state"] == "todo"


def test_timeline_skips_the_mac_for_a_card_outside_the_app(client):
    t = _task(client, "後台", status="done")
    client.post("/flow/stages", headers=H, json={"items": [{"type": "task", "id": t["id"], "stage": "done"}]})
    steps = {x["key"]: x for x in _one(client, f"t{t['id']}")["timeline"]}
    assert steps["mac_verify"]["state"] == "skipped" and steps["ready"]["state"] == "done"


# ── 需要你 ───────────────────────────────────────────────────────────

def test_waiting_card_reaches_needs_you_even_if_its_report_says_in_progress(client):
    # 卡 #386 / 問題回報 #380: the report looked 處理中 while the card waited for the owner's key
    i = _issue(client, "Openverse 金鑰", status="in_progress")
    t = _task(client, "Openverse", status="waiting", issue_ids=[i["id"]], progress="需要你決定：要不要申請金鑰\nA：要")
    needs = client.get("/console/overview", headers=H).json()["needs_you"]
    assert [(n["key"], n["kind"]) for n in needs] == [(f"i{i['id']}", "reply")]
    assert needs[0]["ask"] == "要不要申請金鑰"
    assert _items(client, wait="you")[0]["cards"] == [t["id"]]


def test_needs_you_is_strict(client):
    _task(client, "卡住但不用你", status="blocked", progress="第 5 輪未完成")
    _task(client, "排隊")
    _issue(client, "一般問題")
    assert client.get("/console/overview", headers=H).json()["needs_you"] == []


def test_account_step_and_decision_are_needs_you(client):
    _task(client, "上架", status="blocked", progress="要先完成 Apple 帳號付款")
    d = _issue(client, "選哪個", kind="decision", status="needs_decision", options=["A：要", "B：不要"])
    needs = client.get("/console/overview", headers=H).json()["needs_you"]
    assert {n["kind"] for n in needs} == {"account", "decision"}
    decision = next(n for n in needs if n["kind"] == "decision")
    assert decision["options"] == ["A：要", "B：不要"]
    assert _act(client, f"i{d['id']}", "answer", text="A：要")
    assert client.get("/console/overview", headers=H).json()["needs_you"][0]["kind"] == "account"


def test_answering_a_waiting_card_sends_it_back_with_the_answer(client):
    t = _task(client, "等回覆", status="waiting", agent="Claude CLI 1", progress="要哪個？")
    _act(client, f"t{t['id']}", "answer", text="用第二個")
    full = client.get(f"/tasks/{t['id']}", headers=H).json()
    assert full["status"] == "queued" and full["agent"] is None and "用第二個" in full["detail"]


def test_manual_confirmation_counts_as_ipad_pass():
    row = fr.Row([5], "note", "ipad", "| 相機 |", "k1")
    item = {"id": 5, "status": "done", "issue_ids": [], "stage": "ipad_verify", "stage_state": "note", "stage_note": "| 相機 |"}
    args = ({"tasks": [item], "issues": []}, [row], {5: ("M1", "abc")}, set(), {}, False)
    assert flow_tick.plan(*args, text_of=lambda c: "app/lib", confirmed={})[0] == []
    changes, _ = flow_tick.plan(*args, text_of=lambda c: "app/lib", confirmed={"5": "2026-10-31"})
    assert changes[0]["stage"] == "ready"


# ── Stepping in ──────────────────────────────────────────────────────

def test_instruction_for_a_running_cli_opens_a_follow_up_that_starts_after_collection(client, tmp_path, child):
    started = pi.process_started(child.pid)
    i = _issue(client, "問題", status="in_progress")
    t = _task(client, "跑著", status="in_progress", agent="Claude CLI 1", issue_ids=[i["id"]])
    _pid_file(tmp_path, t["id"], child.pid, at=started, started=started)
    msg = _act(client, f"i{i['id']}", "instruct", text="順便把標題改短")
    assert "接續卡" in msg
    item = _one(client, f"i{i['id']}")
    f_id = max(item["cards"])
    follow = client.get(f"/tasks/{f_id}", headers=H).json()
    assert follow["status"] == "blocked" and "順便把標題改短" in follow["detail"] and follow["issue_ids"] == [i["id"]]
    assert "收卡後派工" in item["instructions"][0]["where"]
    assert client.post("/console/followups", headers=H).json()["released"] == 0  # still running
    assert client.get(f"/tasks/{t['id']}", headers=H).json()["detail"] in (None, "")  # the CLI would not see it
    client.put(f"/tasks/{t['id']}", headers=H, json={"status": "done"})
    assert client.post("/console/followups", headers=H).json()["released"] == 1
    assert client.get(f"/tasks/{f_id}", headers=H).json()["status"] == "queued"


def test_instruction_for_a_queued_card_goes_into_what_the_cli_reads(client):
    t = _task(client, "排隊中", detail="原本的說明")
    msg = _act(client, f"t{t['id']}", "instruct", text="多加一項")
    assert "下一個 CLI" in msg
    assert "多加一項" in client.get(f"/tasks/{t['id']}", headers=H).json()["detail"]
    assert "下一個 CLI" in _one(client, f"t{t['id']}")["instructions"][0]["where"]


def test_instruction_for_a_finished_card_queues_a_follow_up(client):
    t = _task(client, "做完了", status="done")
    assert "接續卡" in _act(client, f"t{t['id']}", "instruct", text="再加一個")
    rows = client.get("/tasks", headers=H, params={"status": "queued"}).json()
    rows = rows if isinstance(rows, list) else rows["items"]
    assert any(x["title"].startswith(f"[owner] 接續 #{t['id']}") for x in rows)


def test_instruction_on_a_report_without_a_card(client):
    i = _issue(client, "沒人接", detail="原文")
    assert "問題回報" in _act(client, f"i{i['id']}", "instruct", text="補充")
    assert "補充" in client.get(f"/issues/{i['id']}", headers=H).json()["detail"]


def test_pause_keeps_a_report_from_the_swarm_and_resume_requeues(client):
    i = _issue(client, "先別動")
    _act(client, f"i{i['id']}", "pause")
    item = _one(client, f"i{i['id']}")
    t = client.get(f"/tasks/{item['main_card']}", headers=H).json()
    assert t["status"] == "blocked" and item["wait"] == "paused" and item["actions"][0] == "resume"
    assert client.get("/console/overview", headers=H).json()["needs_you"] == []  # a pause is the owner's own doing
    deck = client.get("/schedule/board", headers=H).json()["deck"]
    assert not [c for c in deck if c.get("issue_id") == i["id"]]
    _act(client, f"i{i['id']}", "resume")
    assert client.get(f"/tasks/{t['id']}", headers=H).json()["status"] == "queued"


def test_pause_ends_the_running_cli(client, tmp_path, child):
    started = pi.process_started(child.pid)
    t = _task(client, "跑著", status="in_progress", agent="Claude CLI 1")
    _pid_file(tmp_path, t["id"], child.pid, at=started, started=started)
    assert "結束" in _act(client, f"t{t['id']}", "pause")
    child.wait(timeout=10)
    assert client.get(f"/tasks/{t['id']}", headers=H).json()["agent"] is None


def test_priority_changes_what_gets_picked(client):
    a = _task(client, "先來")
    b = _task(client, "後來")
    _act(client, f"t{b['id']}", "top")
    pos = {t: client.get(f"/tasks/{t}", headers=H).json()["position"] for t in (a["id"], b["id"])}
    assert pos[b["id"]] < pos[a["id"]] and pos[b["id"]] < 0
    _act(client, f"t{b['id']}", "bottom")
    assert client.get(f"/tasks/{b['id']}", headers=H).json()["position"] >= pick_card.LAST_POSITION


def test_pick_card_honours_the_priority():
    caps = {"agents": {"Claude CLI": {"match": ["Claude CLI"], "max_difficulty": 4}}}
    cards = [{"card": "task", "id": 1, "status": "queued", "kind": "once", "title": "一般", "difficulty": 4, "position": 0},
             {"card": "task", "id": 2, "status": "queued", "kind": "once", "title": "提前", "difficulty": 1, "position": -1},
             {"card": "task", "id": 3, "status": "queued", "kind": "once", "title": "排後", "difficulty": 4, "position": 2e6}]
    got = pick_card.candidates({"deck": cards, "bots": []}, "Claude CLI 1", caps, state={})
    assert [c["task_id"] for c in got] == [2, 1, 3]


def test_cancel_closes_card_and_report(client):
    i = _issue(client, "不做了")
    t = _task(client, "卡", issue_ids=[i["id"]])
    _act(client, f"i{i['id']}", "cancel")
    assert client.get(f"/tasks/{t['id']}", headers=H).json()["status"] == "cancelled"
    assert client.get(f"/issues/{i['id']}", headers=H).json()["status"] == "wont_fix"
    assert _one(client, f"i{i['id']}")["group"] == "closed"


def test_redo_reopens_a_finished_card_with_the_reason(client):
    i = _issue(client, "修過了", status="fixed")
    t = _task(client, "卡", status="done", issue_ids=[i["id"]])
    _act(client, f"i{i['id']}", "redo", text="還是壞的")
    full = client.get(f"/tasks/{t['id']}", headers=H).json()
    assert full["status"] == "queued" and "還是壞的" in full["detail"]
    assert client.get(f"/issues/{i['id']}", headers=H).json()["status"] == "in_progress"


def test_action_that_does_not_fit_is_refused(client):
    t = _task(client, "排隊")
    r = client.post(f"/console/items/t{t['id']}/act", headers=H, json={"action": "resume"})
    assert r.status_code == 409
    r = client.post(f"/console/items/t{t['id']}/act", headers=H, json={"action": "instruct", "text": " "})
    assert r.status_code == 422


def test_unknown_item_is_a_404(client):
    assert client.get("/console/items/x1", headers=H).status_code == 404
    assert client.get("/console/items/t999999", headers=H).status_code == 404


def test_ask_says_what_to_do_not_what_was_done(client):
    i = _issue(client, "金鑰", status="in_progress")
    _task(client, "金鑰卡", status="waiting", issue_ids=[i["id"]],
          progress="需要你決定：程式已完成（測試全過），但金鑰還沒設——請到網站註冊，寫進設定才會生效。")
    assert client.get("/console/overview", headers=H).json()["needs_you"][0]["ask"] == "請到網站註冊，寫進設定才會生效。"


def test_report_nobody_works_on_is_stuck_not_queued(client):
    i = _issue(client, "沒人管", status="in_progress")
    r = _items(client, q=f"#{i['id']}")[0]
    assert (r["wait"], r["status_text"]) == ("stuck", "卡住")
    assert client.get("/console/overview", headers=H).json()["stuck"][0]["key"] == f"i{i['id']}"


def test_actions_fit_the_stage(client):
    t = _task(client, "等驗證", status="done")
    client.post("/flow/stages", headers=H, json={"items": [{"type": "task", "id": t["id"], "stage": "windows_check"}]})
    assert set(_one(client, f"t{t['id']}")["actions"]) == {"instruct", "redo", "cancel"}
    closed = _issue(client, "結案", status="fixed")
    assert _one(client, f"i{closed['id']}")["actions"] == ["redo"]
    r = client.post("/tasks", headers=H, json={"title": "常態", "kind": "recurring", "interval_minutes": 60}).json()
    assert _one(client, f"t{r['id']}")["actions"] == ["pause", "instruct"]
