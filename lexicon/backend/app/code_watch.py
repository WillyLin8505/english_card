"""API restarts itself when backend code changes on disk (#335, like workers #285).

run_api.bat starts uvicorn again on exit code 3. Without the loop (plain
uvicorn) the API only reports `codeStale` in /health and keeps running."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
ROOT = CODE_DIR.parents[2]
EXIT_CODE = 3
CHECK_S = 15
LOADED_AT = time.time()


def changed_file(loaded_at: float = LOADED_AT) -> str | None:
    """A code file edited after the API loaded, else None. A file dated in the
    future does not count, or the API would restart forever."""
    wall = time.time()
    for path in CODE_DIR.rglob("*.py"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if loaded_at < mtime <= wall:
            return str(path.relative_to(ROOT))
    return None


def status() -> dict:
    changed = changed_file()
    return {"loadedAt": int(LOADED_AT), "codeStale": changed is not None, "staleFile": changed}


def start() -> None:
    """Only under run_api.bat (LEXICON_API_AUTORESTART=1), where exit 3 is handled."""
    if os.environ.get("LEXICON_API_AUTORESTART") != "1":
        return

    def loop():
        while True:
            time.sleep(CHECK_S)
            if changed_file():
                os._exit(EXIT_CODE)

    threading.Thread(target=loop, daemon=True, name="code-watch").start()
