"""dispatch_tick.py core logic: finish detection, cooldown, night window, lock, prompt, digest."""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import dispatch_digest as dg  # noqa: E402
import dispatch_tick as dt  # noqa: E402

TP = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=TP)


# finish detection
def test_result_newer_and_process_gone_is_finished():
    assert dt.classify_run(1000, 2000, False, None, 2100) == "finished"


def test_result_written_but_process_alive_waits_for_grace():
    assert dt.classify_run(1000, 2000, True, None, 2100, grace_s=600) == "running"
    assert dt.classify_run(1000, 2000, True, None, 2700, grace_s=600) == "finished"


def test_old_result_from_previous_round_is_ignored():
    assert dt.classify_run(5000, 1000, True, None, 6000) == "running"
    assert dt.classify_run(5000, 1000, False, None, 6000) == "failed"


def test_process_gone_with_limit_line():
    assert dt.classify_run(1000, None, False, "You've hit your usage limit", 2000) == "limit"


def test_unknown_when_process_state_unknown():
    assert dt.classify_run(1000, None, None, None, 2000) == "unknown"


# cooldown
def _rec(last_hours_ago, history=()):
    return {"kind": "recurring", "last_run_at": (NOW - timedelta(hours=last_hours_ago)).isoformat(),
            "history": list(history)}


def test_recurring_card_ran_recently_is_in_cooldown():
    assert dt.in_cooldown(_rec(3), NOW, 12)


def test_recurring_card_after_12h_is_free():
    assert not dt.in_cooldown(_rec(13), NOW, 12)


def test_owner_change_after_last_run_lifts_cooldown():
    h = [{"at": (NOW - timedelta(hours=1)).isoformat(), "by": "owner", "changes": []}]
    assert not dt.in_cooldown(_rec(3, h), NOW, 12)
    h2 = [{"at": (NOW - timedelta(hours=1)).isoformat(), "by": "Grokbot",
           "changes": [{"field": "detail", "from": "a", "to": "b"}]}]
    assert not dt.in_cooldown(_rec(3, h2), NOW, 12)
    h3 = [{"at": (NOW - timedelta(hours=1)).isoformat(), "by": "Cursor CLI",
           "changes": [{"field": "progress"}]}]
    assert dt.in_cooldown(_rec(3, h3), NOW, 12)


def test_once_card_never_in_cooldown():
    assert not dt.in_cooldown({"kind": "once", "last_run_at": NOW.isoformat()}, NOW, 12)


# night window
def test_night_card_not_started_after_last_launch():
    late = datetime(2026, 10, 18, 6, 20, tzinfo=TP)
    early = datetime(2026, 10, 18, 2, 0, tzinfo=TP)
    assert not dt.night_launch_ok(166, [166, 167], late, "06:15")
    assert dt.night_launch_ok(166, [166, 167], early, "06:15")
    assert dt.night_launch_ok(38, [166, 167], late, "06:15")


def test_order_candidates_reserved_prefer_and_taken():
    cfg = dict(dt.DEFAULT_CFG, prefer={"Claude Code": [163, 164]},
               reserved={"163": "Claude Code", "164": "Claude Code"})
    cands = [{"key": "i10", "task_id": None, "issue_id": 10},
             {"key": "t164", "task_id": 164}, {"key": "t163", "task_id": 163},
             {"key": "t38", "task_id": 38}]
    full = {38: _rec(2)}
    got = dt.order_candidates(cands, "Claude Code", cfg, NOW, set(), [], full)
    assert [c["key"] for c in got] == ["t163", "t164", "i10"]
    got_c = dt.order_candidates(cands, "Cursor CLI", cfg, NOW, {"i10"}, [], full)
    assert got_c == []


def test_rest_until_uses_future_reset_only():
    usage = {"agents": {"Codex": {"weekly": {"used_percent": 100.0,
                                             "resets_at": "2026-10-22T10:01:08+00:00"}},
                        "Claude Code": {"weekly": {"used_percent": 100.0,
                                                   "resets_at": "2026-10-18T03:00:00+00:00"}}}}
    assert dt.rest_until("Codex", usage, NOW).astimezone(TP).strftime("%m/%d %H:%M") == "10/22 18:01"
    assert dt.rest_until("Claude Code", usage, NOW) is None  # reset already passed
    assert dt.rest_until("Cursor CLI", usage, NOW) is None


# lock
def test_lock_exclusive_and_stale_takeover(tmp_path):
    lock = tmp_path / "x.lock"
    assert dt.acquire_lock(lock)
    assert not dt.acquire_lock(lock)          # our own pid is alive → busy
    dt.release_lock(lock)
    assert not lock.exists()
    lock.write_text(json.dumps({"pid": os.getpid(), "at": time.time() - 3600}))
    assert dt.acquire_lock(lock, stale_s=900)  # too old → taken over
    dt.release_lock(lock)
    lock.write_text(json.dumps({"pid": 999999999, "at": time.time()}))
    assert dt.acquire_lock(lock)               # dead pid → taken over
    dt.release_lock(lock)


# result files / prompt / digest
def test_round_paths(tmp_path):
    assert dt.next_round_path(38, tmp_path).name == "card38.r1.result.md"
    (tmp_path / "card38.r1.result.md").write_text("a")
    (tmp_path / "card38.r3.result.md").write_text("b")
    (tmp_path / "card38.pre-cursor.result.md").write_text("c")
    assert dt.next_round_path(38, tmp_path).name == "card38.r4.result.md"
    assert dt.latest_round_path(38, tmp_path).name == "card38.r3.result.md"


def test_outcome_line_prefers_numbers():
    text = "# 卡 #38 結果\n\n**完成**：檢查相似詞\n| 項目 | 前 | 後 |\n|---|---|---|\n| 未持有 | 3 | 0 |\n"
    out = dt.outcome_line(text)
    assert out.startswith("完成：檢查相似詞") and "0" in out


def test_render_prompt_night_and_prev(tmp_path):
    tpl = (dt.TOOLS / "dispatch_prompt_template.md").read_text(encoding="utf-8")
    task = {"id": 166, "title": "例句", "detail": "做事", "kind": "once", "difficulty": 3, "issue_ids": [185]}
    prev = dt.ROOT / "lexicon" / "logs" / "agents" / "card166.r3.result.md"
    p = dt.render_prompt(task, dt.DEFAULT_CFG, [166], tpl, prev)
    assert "卡 #166：例句" in p and "06:45" in p and "card166.r3.result.md" in p and "#185" in p
    assert "{" not in p.replace("{n", "")  # every placeholder filled
    p2 = dt.render_prompt(dict(task, id=38), dt.DEFAULT_CFG, [166], tpl, None)
    assert "夜間卡" not in p2


def test_digest_reads_from_offset_and_caps(tmp_path, monkeypatch):
    ev = tmp_path / "e.jsonl"
    rows = [{"t": "2026-10-18T10:00:00+08:00", "type": "finished", "card": i, "agent": "Cursor CLI",
             "title": "t", "action": "done", "outcome": f"r{i}"} for i in range(20)]
    ev.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(dg, "EVENTS", ev)
    got, end = dg.read_new(0)
    assert len(got) == 20 and end == ev.stat().st_size
    got2, _ = dg.read_new(end)
    assert got2 == []
    assert dg.read_new(end + 999)[0][0]["card"] == 0   # file shrank → restart
    assert "#3" in dg.fmt(rows[3]) and len(dg.fmt(rows[3])) <= 150


def test_probe_due_hourly():
    assert dt.probe_due(None, 1000.0, 60)
    assert not dt.probe_due(1000.0, 1000.0 + 59 * 60, 60)
    assert dt.probe_due(1000.0, 1000.0 + 60 * 60, 60)


def test_probe_verdict():
    assert dt.probe_verdict(0, "OK\n")
    assert not dt.probe_verdict(1, "OK")
    assert not dt.probe_verdict(0, "something else")


def test_stale_panel_limit_cleared_by_probe(monkeypatch):
    tk = dt.Tick.__new__(dt.Tick)
    tk.now = datetime.now(timezone.utc)
    tk.cfg = dict(dt.DEFAULT_CFG, probe_cmd={"Claude Code": ["x"]})
    tk.events, tk.dry = [], True
    until = (tk.now + timedelta(hours=20)).isoformat()
    tk.state = {"limits": {"Claude Code": until, "Codex": until}, "limit_src": {"Codex": "log"}}
    calls = []
    monkeypatch.setattr(dt, "run_probe", lambda cmd: calls.append(cmd) or True)
    assert tk.limited("Claude Code") is False          # usage-sourced + probe OK -> cleared
    assert "Claude Code" not in tk.state["limits"]
    assert tk.limited("Codex") is True                 # log-sourced limit is trusted, no probe
    tk.state["limits"]["Claude Code"] = until
    tk.state["limit_src"]["Claude Code"] = "usage"
    monkeypatch.setattr(dt, "run_probe", lambda cmd: calls.append(cmd) or False)
    assert tk.limited("Claude Code") is False          # cached OK within the hour, no new probe
    assert len(calls) == 1


def test_issue_swarm_slots_share_claude_quota():
    import dispatch_tick as d
    assert d.is_swarm("Claude CLI 3") and not d.is_swarm("Claude Code") and not d.is_swarm("Claude CLI x")
    assert d.quota_agent("Claude CLI 7") == "Claude Code" and d.quota_agent("Codex") == "Codex"
    assert d.free_slot({"Claude CLI 1", "Claude CLI 2"}, 3) == "Claude CLI 3"
    assert d.free_slot({"Claude CLI 1"}, 1) is None


def test_all_done_marker_ends_a_multi_round_card():
    import dispatch_tick as d
    assert d.ALL_DONE_RE.search("全部完成：5,552 槽補完")
    assert not d.ALL_DONE_RE.search("第 2 輪：補了 800 槽，還剩 4,752")
