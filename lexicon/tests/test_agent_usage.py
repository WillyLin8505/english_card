"""The AI panel's 5-hour / weekly usage collectors (card #157) on fixture files."""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import agent_usage as au  # noqa: E402

NOW = datetime(2026, 10, 17, 6, 0, tzinfo=timezone.utc)   # 14:00 Asia/Taipei


def _touch(p: Path):
    t = time.time()
    os.utime(p, (t, t))


def test_codex_reads_rate_limits(tmp_path):
    d = tmp_path / ".codex" / "sessions" / "2026" / "10" / "17"
    d.mkdir(parents=True)
    reset5 = int((NOW + timedelta(hours=2)).timestamp())
    resetw = int((NOW + timedelta(days=5)).timestamp())
    lines = [
        {"timestamp": "2026-10-17T05:00:00Z", "payload": {"type": "token_count", "rate_limits": {
            "limit_id": "premium", "primary": None, "secondary": None}}},
        {"timestamp": "2026-10-17T05:30:00Z", "payload": {"type": "token_count", "rate_limits": {
            "limit_id": "codex", "plan_type": "plus",
            "primary": {"used_percent": 40.0, "window_minutes": 300, "resets_at": reset5},
            "secondary": {"used_percent": 100.0, "window_minutes": 10080, "resets_at": resetw}}}},
    ]
    f = d / "rollout-2026-10-17T05-00-00-x.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    _touch(f)
    u = au.codex_usage(NOW, home=tmp_path)
    assert u["five_hour"]["used_percent"] == 40.0 and u["five_hour"]["exact"]
    assert u["weekly"]["used_percent"] == 100.0 and u["plan"] == "plus"
    later = au.codex_usage(NOW + timedelta(hours=3), home=tmp_path)
    assert later["five_hour"]["used_percent"] == 0.0 and "重置" in later["five_hour"]["note"]


def test_codex_missing_is_unknown(tmp_path):
    u = au.codex_usage(NOW, home=tmp_path)
    assert u["five_hour"]["used_percent"] is None and u["weekly"]["used_percent"] is None


def test_claude_limit_message_and_tokens(tmp_path):
    d = tmp_path / ".claude" / "projects" / "p"
    d.mkdir(parents=True)
    rows = [
        {"type": "assistant", "timestamp": "2026-10-17T04:10:00Z",
         "message": {"usage": {"input_tokens": 10, "cache_creation_input_tokens": 90, "output_tokens": 50,
                               "cache_read_input_tokens": 9999}}},
        {"type": "assistant", "timestamp": "2026-10-16T16:30:00Z",
         "message": {"content": [{"type": "text", "text": "You've hit your weekly limit · resets Oct 19, 7pm (Asia/Taipei)"}],
                     "usage": {"input_tokens": 0, "output_tokens": 0}}},
    ]
    f = d / "s.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    _touch(f)
    u = au.claude_usage(NOW, home=tmp_path)
    assert u["weekly"]["used_percent"] == 100.0
    assert u["weekly"]["resets_at"].startswith("2026-10-19T11:00")      # 19:00 Taipei
    assert u["five_hour"]["used_percent"] is None and u["five_hour"]["tokens"] == 150


def test_parse_limit_variants():
    at = datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc)                 # 09:00 Taipei
    w, r = au.parse_limit("You've hit your session limit · resets 3pm (Asia/Taipei)", at)
    assert w == "five_hour" and r == datetime(2026, 10, 17, 7, 0, tzinfo=timezone.utc)
    w, r = au.parse_limit("5-hour limit reached ∙ resets 2:30am (Asia/Taipei)", at)
    assert r == datetime(2026, 10, 17, 18, 30, tzinfo=timezone.utc)       # next day 02:30 Taipei
    assert au.parse_limit("no limit here", at) is None


def test_cursor_tokens_from_json_logs(tmp_path):
    log = tmp_path / "card38_cursor.log"
    log.write_text('{"type":"result","result":"done","usage":{"inputTokens":1000,"outputTokens":20,'
                   '"cacheReadTokens":5000,"cacheWriteTokens":30}}\n', encoding="utf-8")
    _touch(log)
    u = au.cursor_usage(datetime.now(timezone.utc), logs=tmp_path)
    assert u["five_hour"]["tokens"] == 1050 and u["five_hour"]["used_percent"] is None
    assert "按月" in u["weekly"]["note"]


def test_cursor_text_logs_are_unknown_not_zero(tmp_path):
    log = tmp_path / "card5_cursor.log"
    log.write_text("done, result written\n", encoding="utf-8")
    _touch(log)
    u = au.cursor_usage(datetime.now(timezone.utc), logs=tmp_path)
    assert u["five_hour"]["tokens"] is None
