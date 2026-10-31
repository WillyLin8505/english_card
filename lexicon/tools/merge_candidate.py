"""Card #917: which changes mac_sync may check and push while other CLIs still edit the shared tree.

The tree holds finished and half-done work side by side. mac_sync checks a private copy where every
file still being edited is put back to HEAD, so a card in progress blocks nobody and is never pushed.

Who edits what comes from the Claude session logs (exact, also for sessions still running). Codex and
Cursor keep no such log here: for them a changed file newer than the card's start counts as theirs.
No I/O beyond git status and reading files; the steps are in mac_sync.sync_app.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath

MAX_BYTES = 50 * 1024 * 1024    # GitHub refuses big files; every later push would fail too (10/22)
OPEN_STATUS = ("in_progress", "queued", "blocked", "waiting")
FIRST_USER_LINES = 40
EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")
CARD_RE = re.compile(r"# 卡 #(\d+)[：:]")
ANALYZE_ERROR_RE = re.compile(r"^\s*error - .* - (\S+?):\d+:\d+ - \S+\s*$", re.M)
FAILED_TEST_RE = re.compile(r"(?:^|[\s/\\])(test[/\\]\S*?_test\.dart)\b.*\[E\]\s*$", re.M)
IMPORT_RE = re.compile(r"""^\s*(?:import|export|part)\s+['"]([^'"]+)['"]""", re.M)


@dataclass
class Session:
    card: int | None                                # None: an interactive session, not a dispatched card
    edits: list[tuple[str, float]] = field(default_factory=list)    # (repo path, when)


def changed_paths(root: Path) -> list[str]:
    """Changed files under app/ (added, edited, deleted), skipping those too big to ever commit."""
    r = subprocess.run(["git", "status", "--porcelain", "-uall", "-z", "--", "app/"], cwd=root,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=0x08000000 if __import__("os").name == "nt" else 0)
    out, parts = [], r.stdout.split("\0")
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        paths = [entry[3:]]
        if entry[0] in "RC":        # -z lists a rename's old path as the next entry
            paths.append(parts[i])
            i += 1
        for p in paths:
            f = root / p
            if not (f.is_file() and f.stat().st_size > MAX_BYTES):
                out.append(p)
    return sorted(set(out))


def _when(text: str | None) -> float:
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _repo_path(path: str, root: Path) -> str | None:
    m = re.search(re.escape(root.name) + "/(.+)", path.replace("\\", "/"), re.I)
    return m.group(1) if m else None


def _user_text(line: str) -> str:
    try:
        msg = json.loads(line).get("message") or {}
    except ValueError:
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in content or [] if isinstance(b, dict))


def read_session(path: Path, root: Path) -> Session:
    s, read_lines, first_user = Session(None), 0, False
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            read_lines += 1
            if not first_user and read_lines <= FIRST_USER_LINES and '"type":"user"' in line:
                first_user = True
                m = CARD_RE.search(_user_text(line))    # only the prompt: later text quotes other cards
                s.card = int(m.group(1)) if m else None
            if '"file_path"' not in line or not any(f'"{t}"' in line for t in EDIT_TOOLS):
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            content = (d.get("message") or {}).get("content")
            for b in content if isinstance(content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in EDIT_TOOLS:
                    p = _repo_path((b.get("input") or {}).get("file_path") or "", root)
                    if p:
                        s.edits.append((p, _when(d.get("timestamp"))))
    return s


def read_sessions(folder: Path, root: Path, newer_than: float) -> list[Session]:
    out = []
    for p in folder.glob("*.jsonl"):
        try:
            if p.stat().st_mtime >= newer_than:
                out.append(read_session(p, root))
        except OSError:
            continue
    return out


def held_files(changed: list[str], root: Path, sessions: list[Session], tasks: dict[int, dict], now: float,
               quiet_s: float, interactive_s: float) -> dict[str, str]:
    """Changed file → why it is not ready. `tasks` holds only unfinished cards."""
    held: dict[str, str] = {}
    wanted = set(changed)
    has_log = {s.card for s in sessions if s.card is not None}
    for s in sessions:
        for p, at in s.edits:
            if p not in wanted or p in held:
                continue
            if s.card in tasks:
                held[p] = f"卡 #{s.card} 還沒做完"
            elif s.card is None and now - at < interactive_s:
                held[p] = "互動工作階段剛改過"
    for cid, t in tasks.items():
        if t.get("status") != "in_progress" or cid in has_log or (t.get("agent") or "").startswith("Claude"):
            continue
        start = _when(t.get("started_at"))
        for p in changed:
            f = root / p
            if p not in held and f.is_file() and f.stat().st_mtime >= start:
                held[p] = f"{t.get('agent')} 卡 #{cid} 開工後改過"
    for p in changed:
        f = root / p
        if p not in held and f.is_file() and now - f.stat().st_mtime < quiet_s:
            held[p] = "剛改過"
    return held


def card_files(card: int, result_text: str, sessions: list[Session], changed: list[str]) -> set[str]:
    """Changed files this card touched: its session's edits plus what its result.md names."""
    text = (result_text or "").replace("\\", "/")
    named = {p for p in changed if p in text or p.split("/", 1)[-1] in text or p.rsplit("/", 1)[-1] in text}
    edited = {p for s in sessions if s.card == card for p, _ in s.edits}
    return named | (edited & set(changed))


def analyze_errors(output: str) -> list[str]:
    """Files (repo paths) with an analyzer `error`, as flutter prints them relative to app/."""
    seen = []
    for f in ANALYZE_ERROR_RE.findall(output or ""):
        p = "app/" + f.replace("\\", "/")
        if p not in seen:
            seen.append(p)
    return seen


def failed_tests(output: str) -> list[str]:
    seen = []
    for f in FAILED_TEST_RE.findall(output or ""):
        p = "app/" + f.replace("\\", "/")
        if p not in seen:
            seen.append(p)
    return seen


def _imports(checkout: Path, path: str, package: str) -> list[str]:
    f = checkout / path
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for uri in IMPORT_RE.findall(text):
        if uri.startswith(f"package:{package}/"):
            out.append("app/lib/" + uri.split("/", 1)[1])
        elif not re.match(r"[a-z]+:", uri):
            parts: list[str] = []
            for bit in (PurePosixPath(path).parent / uri).parts:
                if bit == ".." and parts:
                    parts.pop()
                elif bit != ".":
                    parts.append(bit)
            out.append("/".join(parts))
    return out


def import_closure(checkout: Path, path: str) -> set[str]:
    """`path` and every file of the app it reaches through imports, read in the checked copy."""
    m = re.search(r"(?m)^name:\s*(\S+)", (checkout / "app" / "pubspec.yaml").read_text(encoding="utf-8", errors="replace")
                  if (checkout / "app" / "pubspec.yaml").is_file() else "")
    package = m.group(1) if m else "app"
    seen, todo = set(), [path]
    while todo:
        p = todo.pop()
        if p not in seen:
            seen.add(p)
            todo += _imports(checkout, p, package)
    return seen


def narrow(passes, suspects: set[str], tries: int = 6) -> set[str]:
    """Smallest group of suspects whose removal makes the failing tests pass; empty = removing them
    all doesn't help, so these changes didn't cause it. `passes(group)` runs with `group` put back."""
    if not suspects or not passes(suspects):
        return set()
    best = set(suspects)
    while len(best) > 1 and tries:
        tries -= 1
        half = set(sorted(best)[:len(best) // 2])
        best = half if passes(half) else best - half
    return best if len(best) == len(suspects) or passes(best) else set(suspects)


def unready_cards(owned: dict[int, set[str]], excluded: set[str]) -> set[int]:
    return {c for c, files in owned.items() if files & excluded}


def only_theirs(owned: dict[int, set[str]], excluded: set[str]) -> set[str]:
    """Files only cards that can't go yet touched: half a card must not reach the Mac on its own.
    A file shared with a card that can go stays, or one blocked card would hold all the others."""
    waiting = unready_cards(owned, excluded)
    mine = {p for c in waiting for p in owned[c]}
    others = {p for c, files in owned.items() if c not in waiting for p in files}
    return mine - others


def age_cutoff(hours: float) -> float:
    return time.time() - hours * 3600
