"""Card difficulty, agent capabilities and pick_card (card #156)."""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import card_difficulty as cd  # noqa: E402
import launch_agent  # noqa: E402
import pick_card  # noqa: E402

CAPS = {
    "agents": {
        "Claude Code": {"match": ["Claude"], "max_difficulty": 4, "prefer_min_difficulty": 3},
        "Codex": {"match": ["Codex"], "max_difficulty": 3, "reasoning_effort_by_difficulty": {"1": "low", "3": "high"}},
        "Cursor CLI": {"match": ["Cursor"], "max_difficulty": 3,
                       "models_by_difficulty": {"1": "grok-4.7-low", "3": "grok-4.7-high"}},
        "Qwen": {"match": ["Qwen"], "max_difficulty": 0, "dispatchable": False},
    },
    "skip_tasks": [27], "skip_issues": [202],
}


def test_grade_levels_and_reason():
    lvl, why = cd.grade({"title": "常態：掃描缺圖片的字", "kind": "recurring", "card": "task"})
    assert lvl <= 2 and "常態" in why
    lvl, why = cd.grade({"title": "問題回報 #200 群組：打標 502/超時根因、#197、#198、#199", "card": "task"})
    assert lvl == 4 and "根因" in why
    lvl, _ = cd.grade({"title": "修正設定頁的文案", "card": "task"})
    assert lvl == 1
    lvl, _ = cd.grade({"title": "[qc] photo.fewer_than_3_tags：照片標籤少於 3 個", "card": "issue", "area": "data"})
    assert lvl >= 3
    for c in ({"title": ""}, {"title": "x" * 500, "detail": "y" * 5000}):
        assert 1 <= cd.grade(c)[0] <= 4


def test_profiles_and_eligibility():
    assert cd.agent_profile(CAPS, "Codex 桌面版")[0] == "Codex"
    assert cd.agent_profile(CAPS, "Claude · card12 simulation")[0] == "Claude Code"
    assert cd.agent_profile(CAPS, "Someone")[1] is None
    cursor = CAPS["agents"]["Cursor CLI"]
    assert cd.eligible(3, cursor) and not cd.eligible(4, cursor)
    assert not cd.eligible(1, CAPS["agents"]["Qwen"])
    assert cd.model_for(cursor, 1) == "grok-4.7-low" and cd.model_for(cursor, 2) is None
    assert cd.effort_for(CAPS["agents"]["Codex"], 3) == "high"


def test_real_capability_file_is_valid():
    caps = cd.load_capabilities()
    for name in ("Claude Code", "Codex", "Cursor CLI", "Qwen"):
        assert name in caps["agents"]
    assert caps["agents"]["Claude Code"]["max_difficulty"] == 4
    assert set(caps["levels"]) == {"1", "2", "3", "4"}


def _board():
    return {
        "bots": [{"agent": "Cursor CLI", "assigned": [], "paused": False},
                 {"agent": "Codex", "assigned": [{"id": 50, "title": "交給 Codex 的卡", "kind": "once",
                                                  "status": "queued", "agent": "Codex", "difficulty": 2}]}],
        "deck": [
            {"card": "task", "id": 3, "title": "掃描缺圖片的字", "kind": "recurring", "status": "scheduled", "difficulty": 2},
            {"card": "task", "id": 27, "title": "被跳過的卡", "kind": "once", "status": "queued", "difficulty": 2},
            {"card": "task", "id": 40, "title": "使用者的需求", "kind": "once", "status": "queued", "difficulty": 4},
            {"card": "task", "id": 41, "title": "另一個需求", "kind": "once", "status": "queued", "difficulty": 2},
            {"card": "issue", "issue_id": 202, "title": "skip", "kind": "bug", "severity": "high", "difficulty": 1},
            {"card": "issue", "issue_id": 210, "title": "低", "kind": "bug", "severity": "low", "difficulty": 3},
            {"card": "issue", "issue_id": 211, "title": "高", "kind": "bug", "severity": "high", "difficulty": 1},
            {"card": "issue", "issue_id": 212, "title": "決定", "kind": "decision", "severity": "high", "difficulty": 1},
        ],
    }


def test_pick_order_skip_and_cap():
    got = pick_card.candidates(_board(), "Cursor CLI", CAPS, state={})
    keys = [g["key"] for g in got]
    assert keys == ["t41", "i211", "i210", "t3"]          # t40 too hard, t27/i202 skipped, decision excluded
    claude = [g["key"] for g in pick_card.candidates(_board(), "Claude · x", CAPS, state={})]
    assert claude[0] == "t40"                              # hard request first for Claude
    codex = [g["key"] for g in pick_card.candidates(_board(), "Codex", CAPS, state={})]
    assert codex[0] == "t50"                               # the card handed to it comes first
    assert pick_card.candidates(_board(), "Qwen", CAPS, state={}) == []


def test_pick_falls_back_to_state_then_heuristic():
    b = {"bots": [], "deck": [{"card": "task", "id": 9, "title": "架構重構＋根因＋遷移", "kind": "once", "status": "queued"}]}
    assert pick_card.candidates(b, "Cursor CLI", CAPS, state={}) == []          # heuristic says 4
    got = pick_card.candidates(b, "Cursor CLI", CAPS, state={"t9": {"difficulty": 2, "reason": "手動"}})
    assert got[0]["source"] == "graded" and got[0]["difficulty"] == 2


def test_launch_agent_tunes_model_by_difficulty(monkeypatch):
    monkeypatch.setattr(cd, "load_capabilities", lambda path=None: CAPS)
    assert launch_agent.tuned_for("Cursor CLI", 1) == ("grok-4.7-low", None)
    assert launch_agent.tuned_for("Codex", 3) == (None, "high")
    assert launch_agent.card_level({"id": 1, "difficulty": 3}) == 3
    cmd = launch_agent.cursor_cmd(5, launch_agent.LOGS / "card5.cursor.prompt.md", "grok-4.7-low")
    assert cmd[cmd.index("--output-format") + 1] == "json"


def test_preamble_and_docs_carry_the_token_budget():
    pre = launch_agent.PREAMBLE.read_text(encoding="utf-8")
    for needle in ("Token budget", "PROJECT_MAP.md", "/api/schedule/board", "rg -n"):
        assert needle in pre, needle
    root = TOOLS.parents[1]
    assert (root / "lexicon" / "docs" / "PROJECT_MAP.md").is_file()
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "pick_card.py" in agents and "agent_capabilities.json" in agents
    for doc in ("qwen_pause.md", "simulation_usability.md", "cursor_cli.md"):
        assert (root / "lexicon" / "docs" / "agents" / doc).is_file()


def test_night_only_cards_wait_for_the_night_window():
    from datetime import datetime
    caps = {**CAPS, "night_only_tasks": [41], "night_window": {"start": "01:00", "end": "07:00"}}
    day = datetime(2026, 10, 17, 14, 0, tzinfo=pick_card.TAIPEI)
    night = datetime(2026, 10, 18, 2, 30, tzinfo=pick_card.TAIPEI)
    assert "t41" not in [g["key"] for g in pick_card.candidates(_board(), "Cursor CLI", caps, state={}, now=day)]
    assert "t41" in [g["key"] for g in pick_card.candidates(_board(), "Cursor CLI", caps, state={}, now=night)]
    assert pick_card.night_blocked(caps, 41, day) and not pick_card.night_blocked(caps, 41, night)
    assert not pick_card.night_blocked(caps, 3, day)                 # ordinary cards any time
    wrap = {"night_window": {"start": "23:00", "end": "06:00"}}
    assert pick_card.is_night(wrap, datetime(2026, 10, 17, 23, 30, tzinfo=pick_card.TAIPEI))
    assert not pick_card.is_night(wrap, datetime(2026, 10, 17, 12, 0, tzinfo=pick_card.TAIPEI))
    real = cd.load_capabilities()
    assert {166, 167} <= set(real["night_only_tasks"])
