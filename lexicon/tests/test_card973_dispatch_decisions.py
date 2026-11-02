"""#973: collecting and pruning decisions must not create a relaunch loop."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import dispatch_tick as dt

RESULT = """需要你決定：要不要新增沒有圖也能出的文字選擇題？
A：不用，等補圖與相關詞。
B：新增文字選擇題。
建議：A，先補資料。

原問題不處理，這項新需求需要另外決定。
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    tasks = {965: {"id": 965, "kind": "once", "status": "in_progress",
                   "agent": "Codex CLI 3", "issue_ids": [1420]}}
    issues = {1420: {"id": 1420, "status": "wont_fix", "decision": None}}
    calls = []

    def http(method, path, body=None):
        calls.append((method, path, body))
        rows = issues if path.startswith("/issues") else tasks
        if method == "GET":
            if path in ("/issues", "/tasks"):
                return {"items": list(rows.values())}
            return dict(rows[int(path.rsplit("/", 1)[1])])
        if method == "POST":
            ident = max(rows) + 1
            rows[ident] = {"id": ident, "status": "open", **body}
            return dict(rows[ident])
        assert method == "PUT"
        rows[int(path.rsplit("/", 1)[1])].update(body)
        return {}

    monkeypatch.setattr(dt, "http", http)
    monkeypatch.setattr(dt, "ROOT", tmp_path)
    monkeypatch.setattr(dt, "AG_LOGS", tmp_path)
    tick = dt.Tick.__new__(dt.Tick)
    tick.dry = False
    tick.cfg = dict(dt.DEFAULT_CFG)
    tick.now = datetime(2026, 11, 3, tzinfo=timezone.utc)
    tick.state = {"runs": {}, "failures": {}}
    tick.events, tick.summary = [], []
    monkeypatch.setattr(tick, "decision_to_mac", lambda *args: None)
    res = tmp_path / "card965.result.md"
    res.write_text(RESULT, encoding="utf-8")
    return tick, tasks, issues, calls, res


def collect(env, text=RESULT):
    tick, tasks, issues, calls, res = env
    tasks[965].update(status="in_progress", agent="Codex CLI 3")
    res.write_text(text, encoding="utf-8")
    tick.finish(965, "Codex CLI 3", dict(tasks[965]), res)
    return issues[max(issues)]


@pytest.mark.parametrize("source_status", ["fixed", "wont_fix", "open"])
def test_new_independent_decision_stays_waiting_across_ticks(env, source_status):
    tick, tasks, issues, calls, _ = env
    issues[1420]["status"] = source_status
    ask = collect(env)
    for _ in range(3):
        assert not tick.prune_decisions()
        assert not tick.answered()
    assert tasks[965]["status"] == "waiting"
    assert ask["status"] == "open"
    assert len(issues) == 2
    assert not any(b and b.get("status") == "queued" for _, _, b in calls)


def test_recollect_same_question_reuses_pending_issue_after_state_loss(env):
    tick, tasks, issues, _, _ = env
    ask = collect(env)
    tick.state.pop("asks")
    collect(env, RESULT.replace("A：", "  A："))
    assert len(issues) == 2
    assert tick.state["asks"] == {str(ask["id"]): 965}
    assert tasks[965]["status"] == "waiting"


def test_legacy_incorrectly_pruned_question_is_recovered_once(env):
    tick, tasks, issues, _, _ = env
    ask = collect(env)
    ask.update(status="wont_fix", resolution="不用你決定了：相關問題都已修好（派工程式 04:13 自動移除）")
    tick.state.pop("asks")
    collect(env)
    assert ask["status"] == "needs_decision"
    assert not tick.prune_decisions()
    assert not tick.answered()
    collect(env)
    assert len(issues) == 2
    assert tasks[965]["status"] == "waiting"


@pytest.mark.parametrize("status,decision", [("fixed", "A"), ("wont_fix", None), ("open", "B")])
def test_already_handled_question_blocks_relaunch_instead_of_reasking(env, status, decision):
    tick, tasks, issues, _, _ = env
    ask = collect(env)
    ask.update(status=status, decision=decision)
    collect(env)
    assert tasks[965]["status"] == "blocked"
    assert str(ask["id"]) in tasks[965]["progress"]
    assert len(issues) == 2
    assert not tick.answered()


def test_answer_is_dispatched_once_then_repeated_question_stops(env):
    tick, tasks, issues, _, _ = env
    ask = collect(env)
    ask["decision"] = "B"
    assert tick.answered()
    assert tasks[965]["status"] == "queued"
    assert "B" in tasks[965]["detail"]
    collect(env)
    assert tasks[965]["status"] == "blocked"
    assert len(issues) == 2
    assert not tick.answered()


def test_changed_option_is_a_new_question_even_if_old_question_closed(env):
    tick, tasks, issues, _, _ = env
    ask = collect(env)
    ask.update(status="fixed", decision="A")
    collect(env, RESULT.replace("B：新增文字選擇題。", "B：只新增聽力題。"))
    assert tasks[965]["status"] == "waiting"
    assert len(issues) == 3
    assert not tick.answered()
    assert tasks[965]["status"] == "waiting"


def test_same_question_on_another_card_is_not_a_duplicate(env):
    tick, tasks, issues, _, _ = env
    ask = collect(env)
    ask["title"] = ask["title"].replace("#965", "#966")
    ask["status"] = "fixed"
    collect(env)
    assert len(issues) == 3
    assert tasks[965]["status"] == "waiting"


@pytest.mark.parametrize("card_status", ["done", "cancelled"])
def test_completed_card_still_prunes_obsolete_question(env, card_status):
    tick, tasks, issues, _, _ = env
    ask = collect(env)
    tasks[965]["status"] = card_status
    assert tick.prune_decisions()
    assert ask["status"] == "wont_fix"
    assert tasks[965]["status"] == card_status
    assert not tick.answered()


def test_no_decision_result_finishes_without_new_ask(env):
    tick, tasks, issues, _, _ = env
    collect(env, "全部完成：已確認原問題不處理。\n需要你決定：無。")
    assert tasks[965]["status"] == "done"
    assert len(issues) == 1


def test_empty_old_question_is_pruned_then_result_can_finish(env):
    tick, tasks, issues, _, _ = env
    ask = collect(env)
    ask["title"] = "[待決定] 卡 #965：無。"
    assert tick.prune_decisions()
    assert tasks[965]["status"] == "queued"
    collect(env, "全部完成：需要你決定：無。")
    assert tasks[965]["status"] == "done"
    assert len(issues) == 2


def test_issue_lookup_failure_preserves_result_and_blocks_without_post(env, monkeypatch):
    tick, tasks, issues, _, res = env
    original = dt.http
    def http(method, path, body=None):
        if method == "GET" and path == "/issues":
            raise OSError("offline")
        return original(method, path, body)
    monkeypatch.setattr(dt, "http", http)
    collect(env)
    assert tasks[965]["status"] == "blocked"
    assert len(issues) == 1
    assert res.exists()


def test_dry_run_does_not_create_or_modify_decisions(env):
    tick, tasks, issues, calls, _ = env
    tick.dry = True
    collect(env)
    assert len(issues) == 1
    assert tasks[965]["status"] == "in_progress"
    assert all(method == "GET" for method, _, _ in calls)


def test_answered_duplicate_takes_precedence_over_old_unanswered_copy(env):
    tick, tasks, issues, _, _ = env
    ask = collect(env)
    issues[1500] = {**ask, "id": 1500, "decision": "B", "status": "fixed"}
    collect(env)
    assert tasks[965]["status"] == "blocked"
    assert "1500" in tasks[965]["progress"]
    assert len(issues) == 3


def test_english_word_boundaries_do_not_merge_distinct_decisions():
    assert dt.decision_key({"detail": "Allow now here"}) != dt.decision_key({"detail": "Allow nowhere"})
