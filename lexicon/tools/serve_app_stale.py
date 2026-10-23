"""Is the running serve_app (8123) older than its code? (card #522 / issue #547)

serve_app hashes its code + quality rules into the snapshot directory name once
at start-up (serve_app.snapshot_directory()); later edits only reach the app pack
after a restart. This lists the source files changed since the process started.

Run: python lexicon/tools/serve_app_stale.py [--json]
Exit 0 = up to date, 1 = stale (restart needed), 2 = serve_app not running.
Read-only: it never restarts anything. dispatch_tick.serve_app_reload() uses status()
to restart serve_app once the change has settled (owner decision #553 = A).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sources() -> list[Path]:
    # Same list as serve_app.snapshot_directory().
    files = [ROOT / 'serve_app.py', ROOT / 'lexicon_transport.py']
    files += sorted((ROOT / 'lexicon' / 'backend' / 'app').rglob('*.py'))
    files += sorted((ROOT / 'lexicon' / 'quality').rglob('*.json'))
    return files


def revision() -> str:
    """serve_app.snapshot_directory()'s name for the code on disk now."""
    digest = hashlib.sha256()
    for source in sources():
        digest.update(source.relative_to(ROOT).as_posix().encode())
        digest.update(source.read_bytes())
    return digest.hexdigest()[:20]


def running() -> list[dict]:
    script = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
              "Where-Object CommandLine -match 'serve_app\\.py' | "
              "Where-Object CommandLine -notmatch 'warm-only' | "
              "ForEach-Object { [pscustomobject]@{pid=$_.ProcessId; "
              "started=$_.CreationDate.ToUniversalTime().ToString('o')} } | ConvertTo-Json -Compress")
    out = subprocess.run(['powershell', '-NoProfile', '-Command', script],
                         capture_output=True, text=True, timeout=60,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip()
    if not out:
        return []
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


def status(procs: list[dict] | None = None) -> dict:
    """{'running', 'pids', 'started' (aware datetime), 'changed': [(mtime, file)] newest first}."""
    procs = running() if procs is None else procs
    if not procs:
        return {'running': False, 'pids': [], 'started': None, 'changed': []}
    started = min(dt.datetime.fromisoformat(p['started']) for p in procs)
    changed = []
    for path in sources():
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
        if mtime > started:
            changed.append((mtime, path.relative_to(ROOT).as_posix()))
    changed.sort(reverse=True)
    return {'running': True, 'pids': [p['pid'] for p in procs], 'started': started, 'changed': changed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    st = status()
    if not st['running']:
        print(json.dumps({'running': False}) if args.json else 'serve_app is not running')
        return 2
    changed = st['changed']
    result = {'running': True, 'pids': st['pids'],
              'started': st['started'].astimezone().isoformat(timespec='seconds'),
              'stale': bool(changed), 'revision': revision(),
              'changed': [{'file': f, 'modified': m.astimezone().isoformat(timespec='seconds')}
                          for m, f in changed]}
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"serve_app pid {result['pids']} started {result['started']}: "
              + (f"STALE, {len(changed)} file(s) changed since" if changed else 'up to date')
              + f" (code revision {result['revision']})")
        for item in result['changed'][:20]:
            print(f"  {item['modified']}  {item['file']}")
    return 1 if changed else 0


if __name__ == '__main__':
    sys.exit(main())
