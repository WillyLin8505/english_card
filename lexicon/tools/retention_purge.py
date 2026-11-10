"""Make the privacy policy's retention numbers true (card #1010, owner 11/10 option A).

- Server access logs (uvicorn's api.log: time-less lines with IP and URL): the live file is
  copied to api.log.<yyyymmdd> and emptied once it is a day old; dated copies, api.log.1 and
  the per-run api-*.log files are deleted after 30 days.
- Anonymous statistics (app_events): rows older than 24 months are deleted.
Run daily by dispatch_tick; by hand: python lexicon/tools/retention_purge.py [--dry-run]."""
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
LOGS = HOME / "logs"
LOG_DAYS = 30
ROTATE_AFTER_H = 24


def _is_access_log(p: Path) -> bool:
    n = p.name
    return n.startswith("api") and (".log" in n or n.endswith((".err", ".out")))


def _last_rotation(logs: Path, live: Path) -> float:
    try:
        return float((logs / ".api_log_rotated").read_text())
    except (OSError, ValueError):
        return live.stat().st_ctime   # first run: the file's creation time


def purge_logs(logs: Path = LOGS, now: float | None = None, dry: bool = False) -> dict:
    now = now or time.time()
    out = {"rotated": 0, "deleted": 0}
    live = logs / "api.log"
    if live.exists() and live.stat().st_size and now - _last_rotation(logs, live) > ROTATE_AFTER_H * 3600:
        out["rotated"] = 1
        if not dry:
            copy = logs / f"api.log.{datetime.fromtimestamp(now):%Y%m%d%H%M}"
            shutil.copyfile(live, copy)
            try:
                with open(live, "r+b") as f:   # the server holds it in append mode
                    f.truncate(0)
                (logs / ".api_log_rotated").write_text(str(now))
            except OSError:
                copy.unlink(missing_ok=True)   # still in use: try again next run
                out["rotated"] = 0
    for p in logs.iterdir():
        if p == live or not p.is_file() or not _is_access_log(p):
            continue
        if now - p.stat().st_mtime > LOG_DAYS * 86400:
            out["deleted"] += 1
            if not dry:
                p.unlink(missing_ok=True)
    return out


def purge_events(dry: bool = False) -> int:
    sys.path.insert(0, str(HOME / "backend"))
    from app import app_events, db
    with db.SessionLocal() as s:
        n = app_events.purge_old(s)
        if dry:
            s.rollback()
        else:
            s.commit()
        return n


def main(argv=None) -> int:
    dry = "--dry-run" in (argv or sys.argv[1:])
    print("logs:", purge_logs(dry=dry))
    print("app_events deleted:", purge_events(dry=dry))
    return 0


if __name__ == "__main__":
    sys.exit(main())
