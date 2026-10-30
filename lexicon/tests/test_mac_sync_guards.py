"""card #837 / issue #949: mac_sync must not commit/push mid-merge or with conflict markers,
and a failed push must raise a visible warning."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import mac_sync  # noqa: E402


def _git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.dart").write_text("ok\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "x")
    monkeypatch.setattr(mac_sync, "ROOT", tmp_path)


def test_clean_tree_is_safe(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    (tmp_path / "a.dart").write_text("changed\n")
    assert mac_sync.unsafe_to_commit() == ""


def test_merge_head_blocks(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    (tmp_path / ".git" / "MERGE_HEAD").write_text("deadbeef\n")
    assert "MERGE_HEAD" in mac_sync.unsafe_to_commit()


def test_conflict_markers_block(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    (tmp_path / "a.dart").write_text("<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> origin/main\n")
    (tmp_path / "new.dart").write_text("<<<<<<< HEAD\nz\n")
    msg = mac_sync.unsafe_to_commit()
    assert "a.dart" in msg and "new.dart" in msg


def test_push_failure_warns(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)  # no remote -> push fails
    seen = []
    monkeypatch.setattr(mac_sync, "warn", seen.append)
    assert mac_sync.push_origin("app") is False
    assert seen and "push 失敗" in seen[0]
