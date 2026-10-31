"""card #917: one failure or one unfinished card must not stop the other finished App cards.
Flutter is faked; git is real, in a throwaway repo with a bare `origin`."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import mac_sync  # noqa: E402
import merge_candidate as mc  # noqa: E402


def _git(cwd, *a):
    r = subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip()


def _session(folder, name, card, edits, root_name="repo"):
    lines = [json.dumps({"type": "user", "message": {"content": f"preamble\n# 卡 #{card}：x" if card else "hi"}}, separators=(",", ":"))]
    for path, at in edits:
        lines.append(json.dumps({"type": "assistant", "timestamp": at, "message": {"content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": f"D:\\x\\{root_name}\\{path}".replace("/", "\\")}}]}}))
    (folder / f"{name}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    origin, root = tmp_path / "o.git", tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "remote", "add", "origin", str(origin))
    for name in ("a", "b", "c"):
        f = root / "app" / "lib" / f"{name}.dart"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"// {name} v1\n", encoding="utf-8")
    (root / "app" / "test").mkdir()
    (root / "app" / "test" / "a_test.dart").write_text("import 'package:app/a.dart';\n", encoding="utf-8")
    (root / "app" / "pubspec.yaml").write_text("name: app\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "mac_inbox.md").write_text("# inbox\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    _git(root, "push", "-q", "origin", "main")

    state = root / "lexicon" / "state"
    state.mkdir(parents=True)
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (root / ".git" / "info" / "exclude").write_text("lexicon/\n", encoding="utf-8")
    for name, value in (("ROOT", root), ("APP", root / "app"), ("STATE", state / "mac_sync.json"), ("LOCK", state / "l"),
                        ("EVENTS", state / "e.jsonl"), ("LOG", state / "m.log"), ("INBOX", root / "docs" / "mac_inbox.md"),
                        ("SESSIONS", sessions), ("QUIET_S", 0), ("TEST_GAP_S", 0)):
        monkeypatch.setattr(mac_sync, name, value)
    monkeypatch.setattr(mac_sync.flow_rules, "result_text", lambda c: "")
    monkeypatch.setattr(mac_sync, "open_cards", lambda: {})
    monkeypatch.setattr(mac_sync.heavy_lock, "slot", lambda timeout_s=0: True)     # never wait for a real job
    monkeypatch.setattr(mac_sync.heavy_lock, "release", lambda: None)
    monkeypatch.setattr(mac_sync, "mark_issues", lambda *a: None)
    monkeypatch.setattr(mac_sync, "sh", _no_web_build(mac_sync.sh))
    reports = []
    monkeypatch.setattr(mac_sync, "report_failure", lambda text, cards: reports.append((text, cards)))
    monkeypatch.setattr(mac_sync, "warn", lambda text: reports.append((text, None)))
    return root, sessions, reports


def _no_web_build(real):
    def sh(*args, **kw):
        if args and args[0] == mac_sync.FLUTTER:
            return subprocess.CompletedProcess(args, 0, "", "")
        return real(*args, **kw)
    return sh


class FakeFlutter:
    """`rules(cwd, args)` → (code, output); everything passes by default. Records what it saw."""

    def __init__(self, monkeypatch, rule=None):
        self.calls, self.seen, self.rule = [], [], rule or (lambda app, args: (0, "All tests passed!"))
        monkeypatch.setattr(mac_sync, "flutter", self)

    def __call__(self, *args, cwd, timeout):
        self.calls.append(args)
        self.seen.append((Path(cwd) / "lib" / "a.dart").read_text(encoding="utf-8")
                         if (Path(cwd) / "lib" / "a.dart").is_file() else None)
        return self.rule(Path(cwd), args)


def _cards(*ids):
    return [{"card": str(i), "t": f"2026-10-31T1{n}:00:00+08:00", "title": f"t{i}", "outcome": "ok"}
            for n, i in enumerate(ids)]


def _shown(root, path, ref="origin/main"):
    return _git(root, "show", f"{ref}:{path}")


def test_unfinished_card_stays_out_and_the_finished_one_goes(repo, monkeypatch):
    root, sessions, _ = repo
    (root / "app/lib/a.dart").write_text("// a done\n", encoding="utf-8")
    (root / "app/lib/b.dart").write_text("half done(\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/lib/a.dart", "2026-10-31T10:00:00Z")])
    _session(sessions, "s2", 2, [("app/lib/b.dart", "2026-10-31T10:00:00Z")])
    monkeypatch.setattr(mac_sync, "open_cards", lambda: {2: {"status": "in_progress", "agent": "Claude CLI 1"}})
    FakeFlutter(monkeypatch)
    state = {}
    assert mac_sync.sync_app(_cards(1), state) == 0
    assert _shown(root, "app/lib/a.dart") == "// a done"
    assert _shown(root, "app/lib/b.dart") == "// b v1"     # the half-done file was never pushed
    assert (root / "app/lib/b.dart").read_text(encoding="utf-8") == "half done(\n"  # and is still there
    assert "app/lib/b.dart" in _git(root, "status", "--porcelain")
    assert "app/lib/a.dart" not in _git(root, "status", "--porcelain")
    assert "- 卡 #1：" in _shown(root, "docs/mac_inbox.md")
    assert state["since"] == _cards(1)[0]["t"]


def test_the_bytes_that_passed_are_what_gets_committed(repo, monkeypatch):
    root, sessions, _ = repo
    (root / "app/lib/a.dart").write_text("// checked\n", encoding="utf-8")

    def edit_during_the_check(app, args):
        (root / "app/lib/a.dart").write_text("// changed after the check\n", encoding="utf-8")
        return 0, "ok"
    FakeFlutter(monkeypatch, edit_during_the_check)
    assert mac_sync.sync_app(_cards(1), {}) == 0
    assert _shown(root, "app/lib/a.dart") == "// checked"
    assert "changed after" in (root / "app/lib/a.dart").read_text(encoding="utf-8")


def test_snapshot_commit_leaves_a_crlf_tree_clean(repo, monkeypatch):
    """This PC runs core.autocrlf=true: the commit must not make every pushed file look changed."""
    root, sessions, _ = repo
    _git(root, "config", "core.autocrlf", "true")
    data = bytes([47, 47, 32, 97, 13, 10, 47, 47, 32, 98, 13, 10])     # "// a", "// b" with CRLF
    (root / "app/lib/new.dart").write_bytes(data)
    _session(sessions, "s1", 1, [("app/lib/new.dart", "2026-10-31T10:00:00Z")])
    FakeFlutter(monkeypatch)
    assert mac_sync.sync_app(_cards(1), {}) == 0
    assert (root / "app/lib/new.dart").read_bytes() == data
    shown = subprocess.run(["git", "cat-file", "blob", "origin/main:app/lib/new.dart"], cwd=root, capture_output=True).stdout
    assert 13 not in shown
    assert _git(root, "status", "--porcelain", "--", "app/") == ""


def test_compile_error_blocks_only_that_card(repo, monkeypatch):
    root, sessions, reports = repo
    (root / "app/lib/a.dart").write_text("// a ok\n", encoding="utf-8")
    (root / "app/lib/b.dart").write_text("broken(\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/lib/a.dart", "2026-10-31T10:00:00Z")])
    _session(sessions, "s2", 2, [("app/lib/b.dart", "2026-10-31T10:00:00Z")])

    def rule(app, args):
        if args[0] == "analyze" and "broken" in (app / "lib" / "b.dart").read_text(encoding="utf-8"):
            return 1, "  error - Expected x - lib\\b.dart:1:1 - expected_token\n1 issue"
        return 0, "ok"
    FakeFlutter(monkeypatch, rule)
    state = {}
    assert mac_sync.sync_app(_cards(1, 2), state) == 0
    assert _shown(root, "app/lib/a.dart") == "// a ok"
    assert _shown(root, "app/lib/b.dart") == "// b v1"
    assert "- 卡 #2：" not in _shown(root, "docs/mac_inbox.md")
    assert state["handed"] == {"1": _cards(1, 2)[0]["t"]}
    # card 2 stays waiting and card 1 doesn't come back
    assert state["waiting"]["2"]


def test_failing_test_finds_the_card_that_broke_it(repo, monkeypatch):
    root, sessions, _ = repo
    (root / "app/lib/a.dart").write_text("// a bad\n", encoding="utf-8")
    (root / "app/test/a_test.dart").write_text("import 'package:app/a.dart';\nimport 'package:app/b.dart';\n", encoding="utf-8")
    (root / "app/lib/c.dart").write_text("// c ok\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/lib/a.dart", "2026-10-31T10:00:00Z")])
    _session(sessions, "s3", 3, [("app/lib/c.dart", "2026-10-31T10:00:00Z")])

    def rule(app, args):
        if args[0] == "test" and "bad" in (app / "lib" / "a.dart").read_text(encoding="utf-8"):
            return 1, "00:01 +0 -1: test/a_test.dart: works [E]\n  boom"
        return 0, "ok"
    FakeFlutter(monkeypatch, rule)
    state = {}
    assert mac_sync.sync_app(_cards(1, 3), state) == 0
    assert _shown(root, "app/lib/a.dart") == "// a v1"
    assert _shown(root, "app/lib/c.dart") == "// c ok"
    assert list(state["waiting"]) == ["1"]
    assert "app/lib/a.dart" in state["quarantine"]


def test_blocked_file_is_reported_once(repo, monkeypatch):
    root, sessions, reports = repo
    (root / "app/lib/a.dart").write_text("// a bad\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/lib/a.dart", "2026-10-31T10:00:00Z")])

    def rule(app, args):
        if args[0] == "analyze" and "bad" in (app / "lib" / "a.dart").read_text(encoding="utf-8"):
            return 1, "  error - nope - lib\\a.dart:1:1 - nope"
        return 0, "ok"
    fake = FakeFlutter(monkeypatch, rule)
    state = {}
    assert mac_sync.sync_app(_cards(1), state) == 1
    assert len(reports) == 1 and "app/lib/a.dart" in reports[0][0]
    assert _shown(root, "app/lib/a.dart") == "// a v1"
    n = len(fake.calls)
    assert mac_sync.sync_app(_cards(1), state) == 0     # nothing changed: no flutter, no new CLI
    assert len(fake.calls) == n and len(reports) == 1


def test_failure_that_head_also_has_blocks_nobody_and_is_reported(repo, monkeypatch):
    root, sessions, reports = repo
    (root / "app/lib/a.dart").write_text("// a new\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/lib/a.dart", "2026-10-31T10:00:00Z")])

    def rule(app, args):
        if args[0] == "test":
            return 1, "00:01 +0 -1: test/a_test.dart: old failure [E]\n  boom"
        return 0, "ok"
    FakeFlutter(monkeypatch, rule)
    assert mac_sync.sync_app(_cards(1), {}) == 0
    assert _shown(root, "app/lib/a.dart") == "// a new"
    assert "HEAD 上就失敗" in _shown(root, "docs/mac_inbox.md")


def test_timeout_is_no_verdict_and_nobody_is_blamed(repo, monkeypatch):
    root, sessions, reports = repo
    (root / "app/lib/a.dart").write_text("// a\n", encoding="utf-8")
    FakeFlutter(monkeypatch, lambda app, args: (124, "") if args[0] == "test" else (0, "ok"))
    state = {}
    assert mac_sync.sync_app(_cards(1), state) == 2
    assert len(reports) == 1 and reports[0][1] is None and "沒跑完" in reports[0][0]    # a visible warning
    assert not state.get("last_sig") and not state.get("quarantine")
    assert _shown(root, "app/lib/a.dart") == "// a v1"


def test_flaky_test_needs_to_pass_alone_and_is_written_down(repo, monkeypatch):
    root, sessions, _ = repo
    (root / "app/lib/a.dart").write_text("// a\n", encoding="utf-8")

    def rule(app, args):
        if args[0] == "test" and len(args) == 2:
            return 1, "00:01 +0 -1: test/a_test.dart: x [E]"
        return 0, "ok"
    FakeFlutter(monkeypatch, rule)
    assert mac_sync.sync_app(_cards(1), {}) == 0
    assert "單獨重跑通過" in _shown(root, "docs/mac_inbox.md")


def test_half_a_card_is_not_pushed_unless_the_file_is_shared(repo, monkeypatch):
    root, sessions, _ = repo
    for n in ("a", "b", "c"):
        (root / f"app/lib/{n}.dart").write_text(f"// {n} new\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/lib/a.dart", "2026-10-31T10:00:00Z"), ("app/lib/b.dart", "2026-10-31T10:00:00Z")])
    _session(sessions, "s2", 2, [("app/lib/c.dart", "2026-10-31T10:00:00Z")])
    _session(sessions, "s9", 9, [("app/lib/b.dart", "2026-10-31T10:00:00Z")])     # still running
    monkeypatch.setattr(mac_sync, "open_cards", lambda: {9: {"status": "in_progress", "agent": "Claude CLI 1"}})
    FakeFlutter(monkeypatch)
    state = {}
    assert mac_sync.sync_app(_cards(1, 2), state) == 0
    assert _shown(root, "app/lib/a.dart") == "// a v1"     # card 1 has to wait for b.dart
    assert _shown(root, "app/lib/c.dart") == "// c new"
    assert list(state["waiting"]) == ["1"]


def test_merge_failure_keeps_every_card_waiting(repo, monkeypatch):
    root, sessions, _ = repo
    (root / "app/lib/a.dart").write_text("// a\n", encoding="utf-8")
    FakeFlutter(monkeypatch)
    _git(root, "remote", "set-url", "origin", str(root.parent / "gone.git"))
    state = {}
    assert mac_sync.sync_app(_cards(1), state) == 2
    assert not state.get("handed") and not state.get("since")


def test_check_only_changes_nothing(repo, monkeypatch):
    root, sessions, _ = repo
    (root / "app/lib/a.dart").write_text("// a\n", encoding="utf-8")
    FakeFlutter(monkeypatch)
    head = _git(root, "rev-parse", "HEAD")
    assert mac_sync.sync_app(_cards(1), {}, check_only=True) == 0
    assert _git(root, "rev-parse", "HEAD") == head and not mac_sync.STATE.exists()


def test_check_only_reports_and_saves_nothing(repo, monkeypatch):
    root, sessions, reports = repo
    (root / "app/lib/a.dart").write_text("// a bad\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/lib/a.dart", "2026-10-31T10:00:00Z")])
    FakeFlutter(monkeypatch, lambda app, args: (1, "  error - nope - lib\\a.dart:1:1 - nope") if args[0] == "analyze"
                and "bad" in (app / "lib" / "a.dart").read_text(encoding="utf-8") else (0, "ok"))
    state = {}
    assert mac_sync.sync_app(_cards(1), state, check_only=True) == 1
    assert not reports and state == {} and not mac_sync.STATE.exists()


def test_a_blamed_card_gets_its_fix_card_even_when_the_others_are_pushed(repo, monkeypatch):
    root, sessions, reports = repo
    (root / "app/lib/a.dart").write_text("// a ok\n", encoding="utf-8")
    (root / "app/lib/b.dart").write_text("broken(\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/lib/a.dart", "2026-10-31T10:00:00Z")])
    _session(sessions, "s2", 2, [("app/lib/b.dart", "2026-10-31T10:00:00Z")])
    FakeFlutter(monkeypatch, lambda app, args: (1, "  error - x - lib\\b.dart:1:1 - x") if args[0] == "analyze"
                and "broken" in (app / "lib" / "b.dart").read_text(encoding="utf-8") else (0, "ok"))
    state = {}
    assert mac_sync.sync_app(_cards(1, 2), state) == 0
    assert len(reports) == 1 and "app/lib/b.dart" in reports[0][0]
    assert [c["card"] for c in reports[0][1]] == ["2"]      # the issue names that card, not the batch
    assert state["blocked"] == [2]


def test_failure_head_also_has_opens_a_fix_card(repo, monkeypatch):
    root, sessions, reports = repo
    (root / "app/lib/a.dart").write_text("// a new\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/lib/a.dart", "2026-10-31T10:00:00Z")])
    FakeFlutter(monkeypatch, lambda app, args: (1, "00:01 +0 -1: test/a_test.dart: old failure [E]") if args[0] == "test" else (0, "ok"))
    state = {}
    assert mac_sync.sync_app(_cards(1), state) == 0
    assert len(reports) == 1 and "HEAD 上就失敗" in reports[0][0] and not state["blocked"]


def test_analyze_error_outside_the_batch_opens_a_fix_card(repo, monkeypatch):
    root, sessions, reports = repo
    (root / "app/lib/a.dart").write_text("// a new\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/lib/a.dart", "2026-10-31T10:00:00Z")])
    FakeFlutter(monkeypatch, lambda app, args: (1, "  error - x - lib\\c.dart:1:1 - x") if args[0] == "analyze" else (0, "ok"))
    state = {}
    assert mac_sync.sync_app(_cards(1), state) == 2
    assert any(cards and "app/lib/c.dart" in text for text, cards in reports)
    assert _shown(root, "app/lib/a.dart") == "// a v1"


def test_a_pubspec_change_can_be_the_cause_of_a_failing_test(repo, monkeypatch):
    root, sessions, _ = repo
    (root / "app/pubspec.yaml").write_text("name: app\n# bad\n", encoding="utf-8")
    (root / "app/lib/c.dart").write_text("// c ok\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/pubspec.yaml", "2026-10-31T10:00:00Z")])
    _session(sessions, "s3", 3, [("app/lib/c.dart", "2026-10-31T10:00:00Z")])

    def rule(app, args):
        if args[0] == "test" and "bad" in (app / "pubspec.yaml").read_text(encoding="utf-8"):
            return 1, "00:01 +0 -1: test/a_test.dart: works [E]\n  boom"
        return 0, "ok"
    FakeFlutter(monkeypatch, rule)
    state = {}
    assert mac_sync.sync_app(_cards(1, 3), state) == 0
    assert "bad" not in _shown(root, "app/pubspec.yaml") and list(state["waiting"]) == ["1"]


def test_cooling_down_touches_nothing(repo, monkeypatch):
    root, sessions, _ = repo
    (root / "app/lib/a.dart").write_text("// a\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/lib/a.dart", "2026-10-31T10:00:00Z")])
    monkeypatch.setattr(mac_sync, "TEST_GAP_S", 600)
    fake = FakeFlutter(monkeypatch)
    state = {"tested_at": time.time()}
    assert mac_sync.sync_app(_cards(1), state) == 2
    assert not fake.calls


def test_second_round_after_a_blame_runs_inside_the_cool_down(repo, monkeypatch):
    root, sessions, reports = repo
    (root / "app/lib/a.dart").write_text("// a bad\n", encoding="utf-8")
    (root / "app/lib/c.dart").write_text("// c ok\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/lib/a.dart", "2026-10-31T10:00:00Z")])
    _session(sessions, "s3", 3, [("app/lib/c.dart", "2026-10-31T10:00:00Z")])
    monkeypatch.setattr(mac_sync, "TEST_GAP_S", 600)
    FakeFlutter(monkeypatch, lambda app, args: (1, "00:01 +0 -1: test/a_test.dart: w [E]") if args[0] == "test"
                and "bad" in (app / "lib" / "a.dart").read_text(encoding="utf-8") else (0, "ok"))
    assert mac_sync.sync_app(_cards(1, 3), {}) == 0
    assert _shown(root, "app/lib/c.dart") == "// c ok" and len(reports) == 1


def test_head_moving_in_app_under_the_check_stops_the_push(repo, monkeypatch):
    root, sessions, _ = repo
    (root / "app/lib/a.dart").write_text("// a\n", encoding="utf-8")
    _session(sessions, "s1", 1, [("app/lib/a.dart", "2026-10-31T10:00:00Z")])

    def rule(app, args):
        if args[0] == "test":     # someone else commits another app file meanwhile
            (root / "app/lib/c.dart").write_text("// c other\n", encoding="utf-8")
            _git(root, "add", "app/lib/c.dart")
            _git(root, "commit", "-qm", "other")
        return 0, "ok"
    FakeFlutter(monkeypatch, rule)
    assert mac_sync.sync_app(_cards(1), {}) == 2
    assert _shown(root, "app/lib/a.dart") == "// a v1"


def test_file_no_log_explains_waits_for_the_clis_running_when_it_was_written(tmp_path):
    import os
    f = tmp_path / "a.dart"
    f.write_text("x", encoding="utf-8")
    now = time.time()
    ago = lambda s: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - s))  # noqa: E731
    os.utime(f, (now - 5000, now - 5000))
    running = {5: {"status": "in_progress", "agent": "Claude CLI 1", "started_at": ago(6000)}}
    later = {5: {"status": "in_progress", "agent": "Claude CLI 1", "started_at": ago(100)}}
    assert "a.dart" in mc.held_files(["a.dart"], tmp_path, [], running, now, 600, 3600)
    assert "a.dart" not in mc.held_files(["a.dart"], tmp_path, [], later, now, 600, 3600)       # that CLI came later
    assert "a.dart" not in mc.held_files(["a.dart"], tmp_path, [], running, now, 600, 3600, {"a.dart"})    # a result names it
    assert "a.dart" not in mc.held_files(["a.dart"], tmp_path, [], {}, now, 600, 3600)


def test_slot_timeout_leaves_no_fake_lock(tmp_path, monkeypatch):
    import heavy_lock
    monkeypatch.setattr(heavy_lock, "LOCK", tmp_path / "h.lock")
    monkeypatch.delenv(heavy_lock.ENV, raising=False)
    monkeypatch.setattr(heavy_lock, "_try", lambda fh: False)
    assert heavy_lock.slot(0) is False
    assert heavy_lock._FH is None and heavy_lock.slot(0) is False


def test_conflict_marker_scan_takes_long_path_lists(repo):
    root, _, _ = repo
    (root / "app/lib/a.dart").write_text("// x\n<<<<<<< HEAD\n", encoding="utf-8")
    paths = [f"app/lib/none{i}.dart" for i in range(250)] + ["app/lib/a.dart"]
    assert mac_sync.conflict_marker_files(paths) == ["app/lib/a.dart"]


def test_a_later_round_of_a_handed_card_comes_back(repo):
    root, _, _ = repo
    lines = [{"t": "2026-10-31T10:00:00+08:00", "type": "finished", "card": "7", "action": "done", "summary": "app/lib/a.dart"},
             {"t": "2026-10-31T11:00:00+08:00", "type": "finished", "card": "8", "action": "done", "summary": "app/lib/a.dart"}]
    mac_sync.EVENTS.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    assert [c["card"] for c in mac_sync.app_cards(None, {"7": lines[0]["t"]})] == ["8"]
    lines.append({**lines[0], "t": "2026-10-31T12:00:00+08:00"})
    mac_sync.EVENTS.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    assert sorted(c["card"] for c in mac_sync.app_cards(None, {"7": lines[0]["t"]})) == ["7", "8"]


def test_held_files_rules(tmp_path):
    for name in ("a", "b", "c", "d"):
        (tmp_path / f"{name}.dart").write_text("x", encoding="utf-8")
    now = time.time()
    ago = lambda s: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - s))  # noqa: E731
    sessions = [mc.Session(5, [("a.dart", now)]), mc.Session(6, [("b.dart", now)]),
                mc.Session(None, [("c.dart", now - 100), ("d.dart", now - 7200)])]
    tasks = {5: {"status": "queued", "agent": "Claude CLI 1"},                 # a CLI stopped mid-way counts too
             77: {"status": "in_progress", "agent": "Claude · Manager", "started_at": ago(9999)}}
    import os
    for name in ("a", "b", "c", "d"):
        os.utime(tmp_path / f"{name}.dart", (now - 5000, now - 5000))
    held = mc.held_files(["a.dart", "b.dart", "c.dart", "d.dart"], tmp_path, sessions, tasks, now, 600, 3600)
    assert set(held) == {"a.dart", "c.dart"}
    tasks[88] = {"status": "in_progress", "agent": "Codex", "started_at": ago(6000)}   # no session log
    held = mc.held_files(["a.dart", "b.dart", "c.dart", "d.dart"], tmp_path, sessions, tasks, now, 600, 3600)
    assert set(held) == {"a.dart", "b.dart", "c.dart", "d.dart"}
    os.utime(tmp_path / "b.dart", (now - 60, now - 60))
    assert "b.dart" in mc.held_files(["b.dart"], tmp_path, [], {}, now, 600, 3600)


def test_parsers():
    out = ("   info - x - lib\\a.dart:1:1 - y\n"
           "  error - The getter 'cards' isn't defined - test\\card912_cloud_sync_test.dart:223:19 - undefined_getter\n"
           "  error - no - lib\\services\\b.dart:1:1 - z\n")
    assert mc.analyze_errors(out) == ["app/test/card912_cloud_sync_test.dart", "app/lib/services/b.dart"]
    assert mc.analyze_errors("   error • no • lib\\c.dart:1:1 • z\n") == ["app/lib/c.dart"]    # Windows Terminal
    out = ("00:01 +1: test/ok_test.dart: fine\n"
           "00:02 +1 -1: test/simulation/x_test.dart: name [E]\n"
           "00:03 +1 -2: C:/tmp/app/test/y_test.dart: other [E]\n"
           "00:03 +1 -3: loading test\\z_test.dart [E]\n")
    assert mc.failed_tests(out) == ["app/test/simulation/x_test.dart", "app/test/y_test.dart", "app/test/z_test.dart"]


def test_narrow():
    culprit = {"m"}
    runs = []

    def passes(group):
        runs.append(group)
        return culprit <= group
    assert mc.narrow(passes, set("abcdmnop")) == culprit
    assert len(runs) <= 6
    assert mc.narrow(lambda g: False, {"a", "b"}) == set()     # removing them doesn't help: not their fault
    assert mc.narrow(lambda g: True, set()) == set()
    both = {"a", "z"}                                          # needs two files: the whole group stays out
    assert mc.narrow(lambda g: both <= g or len(g) == 8, set("abcdwxyz")) == set("abcdwxyz")
