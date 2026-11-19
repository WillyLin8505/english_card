"""One launch gate shared by English and French Piper (card #1227)."""
from contextlib import contextmanager
from pathlib import Path

from heavy_lock import _try


@contextmanager
def slot():
    path = Path(__file__).resolve().parents[1] / "state" / "piper.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as fh:
        yield _try(fh)  # OS releases the lock on close, including crashes.


def english_running():
    import psutil
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower() not in ("python.exe", "pythonw.exe", "python", "python3"):
                continue
            if any(Path(a).name == "card879_piper_worker.py" for a in p.info["cmdline"] or []):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False
