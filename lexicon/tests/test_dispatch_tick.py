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


# card #431: one card, one CLI
def test_prior_cli_blocks_relaunch_until_gone_or_hung():
    assert dt.prior_cli_action(False, 1000, 99999, 5400) == "free"
    assert dt.prior_cli_action(True, 1000, 1000 + 600, 5400) == "wait"
    assert dt.prior_cli_action(True, 1000, 1000 + 5401, 5400) == "kill"


def test_live_run_pid_file(tmp_path, monkeypatch):
    import launch_agent as la
    monkeypatch.setattr(la, "LOGS", tmp_path)
    assert la.live_run(7) is None  # no pid file
    la.record_run(7, "Claude Code", os.getpid())
    assert la.live_run(7)["pid"] == os.getpid()  # this process is alive
    la.record_run(7, "Claude Code", os.getpid(), at=1000.0)
    if os.name == "nt":  # process started long after the recorded launch → a reused pid
        assert la.live_run(7) is None
    la.record_run(7, "Claude Code", 999999)
    assert la.live_run(7) is None  # gone


def test_dispatch_skips_card_whose_previous_cli_runs(tmp_path, monkeypatch):
    import launch_agent as la
    monkeypatch.setattr(la, "LOGS", tmp_path)
    monkeypatch.setattr(dt, "AG_LOGS", tmp_path)
    la.record_run(329, "Claude Code", os.getpid())
    (tmp_path / "card329.result.md").write_text("x", encoding="utf-8")
    tick = dt.Tick.__new__(dt.Tick)
    tick.cfg, tick.dry, tick.events = dict(dt.DEFAULT_CFG), True, []
    assert tick.prior_busy(329) is True
    assert tick.prior_busy(330) is False
    assert tick.prior_busy(None) is False


def test_no_launch_past_max_running_clis(tmp_path, monkeypatch):
    """owner 11/04: the PC shut down with 20+ CLIs; never more than max_running_clis at once."""
    import launch_agent as la
    monkeypatch.setattr(la, "LOGS", tmp_path)
    monkeypatch.setattr(dt, "AG_LOGS", tmp_path)
    for card in (1, 2):
        la.record_run(card, "Claude CLI 1", os.getpid())
    tick = dt.Tick.__new__(dt.Tick)
    tick.cfg, tick.dry, tick.events, tick.summary = dict(dt.DEFAULT_CFG), True, [], []
    tick.cfg.update(max_running_clis=3, max_launches_per_tick=5)
    tick.launched, tick._running = 0, None
    card = {"task_id": 9, "difficulty": 2, "title": "x"}
    tick.launch("Claude CLI 3", card)
    assert tick.summary == ["(dry) Claude CLI 3→#9"]  # 2 running + this one = 3
    tick.launched = 1
    tick.launch("Claude CLI 4", card)
    assert len(tick.summary) == 1  # a fourth waits


def test_hung_board_restart_schedule():
    """owner 11/04: the API hung 12 h with its port open; restart it after 3 failed ticks, then every 15."""
    assert [n for n in range(1, 40) if dt.hang_restart_due(n)] == [3, 18, 33]


def test_restart_hung_restarts_only_what_hangs(monkeypatch):
    import watchdog as wd
    killed, started = [], []
    monkeypatch.setattr(wd, "port_up", lambda port: True)
    monkeypatch.setattr(wd, "http_ok", lambda url, timeout=15: "5173" in url)  # API hangs, UI answers
    monkeypatch.setattr(wd, "kill_matching", killed.append)
    monkeypatch.setattr(wd, "console", lambda title, cmd, cwd: started.append(title))
    assert wd.restart_hung(lambda *_: None) == ["lexicon API (8770 hung)"]
    assert started == ["lexicon API"] and "run_api" in killed[0]
    monkeypatch.setattr(wd, "http_ok", lambda url, timeout=15: True)
    assert wd.restart_hung(lambda *_: None) == []  # healthy → nothing touched


def test_ui_kill_pattern_spares_other_projects():
    import re
    import watchdog as wd
    import inspect
    pat = re.search(r'kill_matching\(r"([^"]*5173[^"]*)"\)', inspect.getsource(wd.restart_hung)).group(1)
    ours = r'"node" "D:\vibe_coding\english_card\lexicon\frontend\node_modules\.bin\..\vite\bin\vite.js" --host 127.0.0.1 --port 5173 --strictPort'
    other = r'"node" "D:\vibe_coding\photo_tidy_up\dashboard\frontend\node_modules\.bin\..\vite\bin\vite.js" --host 0.0.0.0 --port 5180 --strictPort'
    other_npm = r'npm-cli.js --prefix dashboard/frontend run dev'
    assert re.search(pat, ours) and not re.search(pat, other) and not re.search(pat, other_npm)


def test_priority_task_goes_first_in_swarm(monkeypatch):
    """owner 11/04 「法文優先」: a priority_tasks card takes the next CLI before owner issues."""
    import pick_card
    owner_issue = {"key": "i1", "issue_id": 1, "task_id": None, "difficulty": 3, "title": "[owner] x"}
    french = {"key": "t833", "issue_id": None, "task_id": 833, "difficulty": 3, "title": "[owner] 補齊法文詞條"}
    monkeypatch.setattr(pick_card, "candidates", lambda *a, **k: [owner_issue, french])
    monkeypatch.setattr(dt, "http", lambda *a, **k: {"items": []})
    tick = dt.Tick.__new__(dt.Tick)
    tick.cfg = dict(dt.DEFAULT_CFG, priority_tasks=[833],
                    issue_swarm={"enabled": True, "max_parallel": 3, "codex_parallel": 0})
    tick.dry, tick.events, tick.summary, tick.caps, tick.now = True, [], [], {}, NOW
    tick.state, tick.night_tasks = {"runs": {}}, []
    tick.limited = lambda agent: False
    tick.prior_busy = lambda tid: False
    launched = []
    tick.launch = lambda agent, c: launched.append(c["key"])
    tick.swarm({"bots": [], "deck": [], "recurring": []})
    assert launched[0] == "t833"


def test_free_gpu_for_qwen_steps(monkeypatch):
    """owner 11/05: unload photo_tidy_up's idle Ollama model at 2 failed checks, restart llama at 4."""
    import watchdog as wd
    unloaded, restarts = [], []
    monkeypatch.setattr(wd, "ollama_resident", lambda: ["qwen3-vl:4b-instruct-q4_K_M"])
    monkeypatch.setattr(wd, "ollama_unload", unloaded.append)
    monkeypatch.setattr(wd, "restart_llama_server", lambda: restarts.append(1))
    monkeypatch.setattr(wd, "port_up", lambda port: True)
    quiet = lambda *_: None  # noqa: E731
    monkeypatch.setattr(wd, "ollama_idle_minutes", lambda: 1.0)  # photo_tidy_up busy right now
    assert wd.free_gpu_for_qwen(2, quiet) == [] and unloaded == []
    monkeypatch.setattr(wd, "ollama_idle_minutes", lambda: 30.0)
    assert wd.free_gpu_for_qwen(1, quiet) == []
    assert wd.free_gpu_for_qwen(2, quiet) and unloaded == ["qwen3-vl:4b-instruct-q4_K_M"]
    assert wd.free_gpu_for_qwen(3, quiet) == [] and restarts == []
    assert wd.free_gpu_for_qwen(4, quiet) == ["restarted llama-server"] and restarts == [1]


def test_ollama_idle_minutes_reads_last_post(tmp_path):
    import watchdog as wd
    from datetime import datetime, timedelta
    at = (datetime.now() - timedelta(minutes=12)).strftime("%Y/%m/%d - %H:%M:%S")
    log = tmp_path / "server.log"
    log.write_text(f'[GIN] {at} | 200 | 1.2s | 127.0.0.1 | POST     "/api/chat"\n'
                   '[GIN] 2099/01/01 - 00:00:00 | 200 | 1ms | 127.0.0.1 | GET      "/api/tags"\n', encoding="utf-8")
    assert 11.5 < wd.ollama_idle_minutes(log) < 12.5
    assert wd.ollama_idle_minutes(tmp_path / "none.log") == float("inf")


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


def test_simulations_run_back_to_back_at_night_only():
    cfg = {"night_simulation": {"enabled": True, "window": "01:00-07:00", "tasks": [224], "cooldown_hours": 1}}
    night = datetime(2026, 11, 3, 2, 0, tzinfo=TP)
    day = datetime(2026, 11, 3, 14, 0, tzinfo=TP)
    assert dt.cooldown_hours(224, cfg, night, 12) == 1
    assert dt.cooldown_hours(224, cfg, day, 12) == 12
    assert dt.cooldown_hours(38, cfg, night, 12) == 12
    assert dt.cooldown_hours(224, {}, night, 12) == 12
    ran = {"kind": "recurring", "last_run_at": (night - timedelta(hours=2)).isoformat()}
    assert not dt.in_cooldown(ran, night, dt.cooldown_hours(224, cfg, night, 12))


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


def test_not_done_result_is_queued_again():
    import dispatch_tick as d
    for text in ("本夜尚未補到字：stub 仍剩 7,612", "未完成：第一批 100 字已補完",
                 "卡 #809 部分完成：縮圖格子改要 480", "本輪未完成：已補 269／7,949"):
        assert d.NOT_DONE_RE.search(text), text
    for text in ("全部完成：8,973 句", "已修好（程式已在 repo）：不會再完成前就關卡",
                 "結論：已改成保留自己的卡；未完成的部分無"):
        assert not d.NOT_DONE_RE.search(text), text


def test_multi_round_card_hands_mac_part_only_when_all_done(tmp_path, monkeypatch):
    import datetime
    monkeypatch.setattr(dt, "ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    inbox = tmp_path / "docs" / "mac_inbox.md"
    inbox.write_text("## M1\n", encoding="utf-8")
    tick = dt.Tick.__new__(dt.Tick)
    tick.dry, tick.now, tick.cfg = False, datetime.datetime(2026, 10, 31), {"multi_round_tasks": [738]}
    tick.hand_to_mac(738, {}, "第 3 輪：補了 100，還剩 900\n需要 Mac：查 maison")
    assert "M2" not in inbox.read_text(encoding="utf-8")
    tick.hand_to_mac(738, {}, "全部完成：fr→zh-TW\n需要 Mac：查 maison")
    tick.hand_to_mac(845, {}, "已修好\n需要 Mac：截圖")
    assert "## M2" in inbox.read_text(encoding="utf-8") and "## M3" in inbox.read_text(encoding="utf-8")


def test_tag_fallback_starts_run_only_when_enabled(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(dt.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    monkeypatch.setattr(dt, "TOOLS", tmp_path)
    tick = dt.Tick.__new__(dt.Tick)
    tick.dry = False
    (tmp_path / "tag_fallback_config.json").write_text('{"enabled": false}', encoding="utf-8")
    tick.tag_fallback()
    assert calls == []
    (tmp_path / "tag_fallback_config.json").write_text('{"enabled": true}', encoding="utf-8")
    tick.tag_fallback()
    assert len(calls) == 1 and calls[0][-2:] == [str(tmp_path / "tag_fallback.py"), "run"]
    tick.dry = True
    tick.tag_fallback()
    assert len(calls) == 1


def test_serve_app_reload_waits_until_change_settles():
    # card #522 / decision #553 = A
    cfg = {"quiet_minutes": 15, "max_wait_hours": 6}
    now = 100_000.0
    act = dt.serve_app_reload_action
    assert act(None, [], [], now, now, cfg)[0] == "ok"
    assert act(now - 60, [], [], now - 60, now, cfg)[0] == "wait"            # still being edited
    assert act(now - 3600, [], [12], now - 3600, now, cfg)[0] == "wait"      # simulation uses 8123
    assert act(now - 3600, [501], [], now - 3600, now, cfg)[0] == "wait"     # editing CLI still runs
    assert act(now - 3600, [501], [], now - 7 * 3600, now, cfg)[0] == "restart"  # waited max_wait_hours
    assert act(now - 3600, [], [], now - 3600, now, cfg)[0] == "restart"


def test_serve_app_stale_revision_matches_serve_app():
    import serve_app_stale as sas
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import serve_app
    assert serve_app.snapshot_directory().name == sas.revision()
