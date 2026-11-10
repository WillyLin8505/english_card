"""Access-log retention (card #1010): 30 days, daily rotation of the live api.log."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import retention_purge as rp  # noqa: E402


def test_purge_logs(tmp_path):
    now = time.time()
    old = tmp_path / "api.log.1"
    old.write_text("x")
    os.utime(old, (now - 31 * 86400,) * 2)
    new = tmp_path / "api.log.20261101"
    new.write_text("x")
    other = tmp_path / "ai_watch.log"
    other.write_text("x")
    os.utime(other, (now - 90 * 86400,) * 2)
    live = tmp_path / "api.log"
    live.write_text("GET /health")
    (tmp_path / ".api_log_rotated").write_text(str(now - 2 * 86400))
    r = rp.purge_logs(tmp_path, now)
    assert r == {"rotated": 1, "deleted": 1}
    assert not old.exists() and new.exists() and other.exists()
    assert live.read_text() == "" and len(list(tmp_path.glob("api.log.2026*"))) == 2
    assert rp.purge_logs(tmp_path, now)["rotated"] == 0
