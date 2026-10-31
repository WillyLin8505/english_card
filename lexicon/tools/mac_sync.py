"""Hand finished app cards to the Mac for iPhone verification (owner, 2026-10-18).

Every card that changed the Flutter app must be verified on the owner's Mac (iPhone
simulator, and a real iPhone) before it counts. The Mac only sees what is on GitHub, so:

 1. Collect cards finished since the last sync (dispatch_events.jsonl `finished`) whose
    result.md touches the app (app/…, flutter, iOS).
 2. Take a private copy of app/ and put every file still being edited back to HEAD (card #917,
    merge_candidate.py): a card in progress blocks nobody and is never pushed.
 3. `flutter analyze` (errors only) and `flutter test` on that copy. A failure takes the changes
    that caused it out of the copy, those cards keep waiting and 問題回報 "[Windows] flutter test 失敗"
    is opened/updated so the issue swarm fixes them; the other cards go on.
 4. Commit exactly the bytes that passed, merge origin/main, push.
 5. Add an item M<n> to docs/mac_inbox.md (commit, cards, what to check on the iPhone) and
    push it; mark those issues "待 Mac 驗證" in their resolution.

    python lexicon/tools/mac_sync.py            # one sync (run by dispatch_tick, own lock)
    python lexicon/tools/mac_sync.py --dry-run  # list what would be handed over
    python lexicon/tools/mac_sync.py --check-only  # run the checks; commit and push nothing
State: lexicon/state/mac_sync.json · log: lexicon/logs/mac_sync.log
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import flow_rules
import heavy_lock
import merge_candidate as mc
from flutter_check_workspace import check_workspace

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
STATE = ROOT / "lexicon" / "state" / "mac_sync.json"
LOCK = ROOT / "lexicon" / "state" / "mac_sync.lock"
EVENTS = ROOT / "lexicon" / "state" / "dispatch_events.jsonl"
LOG = ROOT / "lexicon" / "logs" / "mac_sync.log"
INBOX = ROOT / "docs" / "mac_inbox.md"
AG_LOGS = ROOT / "lexicon" / "logs" / "agents"
API = "http://127.0.0.1:5173/api"
TAIPEI = timezone(timedelta(hours=8))
FAIL_TITLE = "[Windows] flutter test 失敗：修好才會推給 Mac 驗證"
FLUTTER = "flutter.bat" if os.name == "nt" else "flutter"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
SESSIONS = Path.home() / ".claude" / "projects" / re.sub(r"[:\\/_]", "-", str(ROOT))
QUIET_S = 10 * 60               # a file touched this recently may be mid-edit, whoever did it
INTERACTIVE_S = 60 * 60         # an interactive session has no card that says when it is finished
SESSION_HOURS = 48
ANALYZE_TIMEOUT_S = 540
TEST_TIMEOUT_S = 25 * 60        # 540 s ended every run under load 10/31 11:41–16:07, without a word
SLOT_WAIT_S = 20 * 60
TEST_GAP_S = 10 * 60            # CLIs wait for the same heavy slot
MAX_TEST_ROUNDS = 2
MAX_ANALYZE_ROUNDS = 12
QUARANTINE_S = 2 * 60 * 60      # the cause may be fixed in another file: try again after this


def log(msg: str):
    line = f"{datetime.now(TAIPEI):%Y-%m-%d %H:%M:%S} {msg}"
    print(line)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def http(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def sh(*args, cwd=None, timeout=1800, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=cwd or ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=NO_WINDOW, env=env)


def flutter(*args, cwd, timeout) -> tuple[int, str]:
    """(exit code, output); 124 = timed out. flutter.bat's children keep the pipes open after a
    plain kill, so output goes to a file and the whole process tree is ended."""
    LOCK.touch()    # a run outlives one lock age; the next tick must not start a second one
    with tempfile.TemporaryFile() as out:
        p = subprocess.Popen([FLUTTER, *args], cwd=cwd, stdout=out, stderr=subprocess.STDOUT,
                             creationflags=NO_WINDOW)
        try:
            code = p.wait(timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True,
                               creationflags=NO_WINDOW)
            p.kill()
            p.wait()
            code = 124
        out.seek(0)
        return code, out.read().decode("utf-8", "replace").strip()


GIT_BUSY_FILES = ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "rebase-merge", "rebase-apply")
MARKER_RE = re.compile(r"^\+(<<<<<<< |>>>>>>> )", re.M)


def git_dir() -> Path:
    return ROOT / ".git"


def git_busy() -> str:
    """Name of an unfinished merge/rebase/cherry-pick in progress (someone is resolving it), else ''."""
    for n in GIT_BUSY_FILES:
        if (git_dir() / n).exists():
            return n
    return ""


def conflict_marker_files(paths: list[str] | None = None) -> list[str]:
    """Files whose working-tree diff adds git conflict markers (10/30 #949: 25cd7b82 pushed some)."""
    bad = []
    cmd = ["git", "diff", "HEAD", "-U0", "--no-color"]
    for i in range(0, len(paths or [None]), 100):   # Windows limits a command line to 32 KB
        cur = ""
        for line in sh(*cmd, *(["--", *paths[i:i + 100]] if paths else [])).stdout.splitlines():
            if line.startswith("+++ b/"):
                cur = line[6:]
            elif MARKER_RE.match(line) and cur and cur not in bad:
                bad.append(cur)
    # untracked files are not in `git diff HEAD`
    for line in sh("git", "ls-files", "-o", "--exclude-standard").stdout.splitlines():
        if paths and line.strip() not in paths:
            continue
        f = ROOT / line.strip()
        try:
            if f.is_file() and f.stat().st_size < 2_000_000 and re.search(
                    r"^<<<<<<< ", f.read_text(encoding="utf-8", errors="ignore"), re.M):
                bad.append(line.strip())
        except OSError:
            pass
    return bad


def warn(text: str):
    """Visible on the board: a ⚠ event (dispatch_digest) and a line on #13."""
    log("WARN " + text)
    try:
        with EVENTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "type": "blocker", "agent": "mac_sync", "outcome": text[:300]},
                               ensure_ascii=False) + "\n")
        http("PUT", "/tasks/13", {"by": "Grokbot",
                                  "progress": f"{datetime.now(TAIPEI):%H:%M} mac_sync：{text}"[:500]})
    except Exception as e:  # board down: the log line above still exists
        log(f"warn: board not updated ({e})")


def unsafe_to_commit(paths: list[str] | None = None) -> str:
    busy = git_busy()
    if busy:
        return f"git 正在合併／重放中（{busy}），不提交、不推"
    bad = conflict_marker_files(paths)
    if bad:
        return "工作區有衝突標記，不提交、不推：" + ", ".join(bad[:5])
    return ""


def push_origin(what: str) -> bool:
    """git push; a failure (e.g. non-fast-forward) must be seen on the board, never skipped quietly."""
    p = sh("git", "push", "origin", "main")
    if p.returncode != 0:
        warn(f"{what} push 失敗（可能非 fast-forward）：{(p.stderr or p.stdout).strip()[-200:]}")
    return p.returncode == 0


def issue_areas(card: int) -> list[str]:
    try:
        return [http("GET", f"/issues/{i}").get("area") for i in http("GET", f"/tasks/{card}").get("issue_ids") or []]
    except Exception:  # noqa: BLE001 — board down: an App card; the Mac checks once too often rather than never
        return []


def app_cards(since: str | None, handed: dict | None = None, again: set[int] | None = None) -> list[dict]:
    """Finished one-off cards since `since` whose result touches the app, minus those already
    handed over (`handed`: card → event time; a later round of the same card comes back)."""
    out, seen, handed = [], {}, handed or {}
    if not EVENTS.exists():
        return out
    for line in EVENTS.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "finished" or e.get("action") not in ("done", "scheduled"):
            continue
        if since and e["t"] <= since:
            continue
        if e["t"] <= handed.get(str(e["card"]), "") and e["card"] not in (again or ()):
            continue
        res = ROOT / (e.get("result") or "")
        text = res.read_text(encoding="utf-8", errors="replace") if res.is_file() else e.get("summary", "")
        if e["card"] in seen:
            out[seen[e["card"]]] = e
            continue
        if not flow_rules.is_app(text, None if flow_rules.STRONG_RE.search(text) else issue_areas(e["card"])):
            continue
        seen[e["card"]] = len(out)
        out.append(e)
    return out


@dataclass
class Scan:
    changed: list[str]
    held: dict[str, str]
    owned: dict[int, set[str]]      # waiting card → changed files it touched


class CheckStopped(Exception):
    """The checks themselves couldn't finish: no verdict, no card blamed."""


def open_cards() -> dict[int, dict]:
    """Unfinished cards. Raises when the board is down: nothing can be called finished then."""
    tasks: dict[int, dict] = {}
    for status in mc.OPEN_STATUS:
        items = http("GET", f"/tasks?status={status}")
        for t in items if isinstance(items, list) else items.get("items", []):
            if t.get("status") == status:
                tasks[t["id"]] = {k: t.get(k) for k in ("status", "agent", "started_at")}
    return tasks


def result_of(card: dict) -> str:
    """A repeat card's result is renamed card<id>.rN.result.md; the event knows which."""
    f = ROOT / (card.get("result") or "-")
    return f.read_text(encoding="utf-8", errors="replace") if f.is_file() else flow_rules.result_text(int(card["card"]))


def scan_tree(cards: list[dict]) -> Scan:
    changed = mc.changed_paths(ROOT)
    sessions = mc.read_sessions(SESSIONS, ROOT, mc.age_cutoff(SESSION_HOURS))
    owned = {int(c["card"]): mc.card_files(int(c["card"]), result_of(c), sessions, changed) for c in cards}
    known = {p for files in owned.values() for p in files}
    held = mc.held_files(changed, ROOT, sessions, open_cards(), time.time(), QUIET_S, INTERACTIVE_S, known)
    return Scan(changed, held, owned)


def tree_sig(scan: Scan, cards: list[dict]) -> str:
    """Same value = same inputs as the last run, so that run's verdict still stands."""
    bits = [sh("git", "rev-parse", "HEAD:app").stdout.strip(), sorted(scan.held), sorted(str(c["card"]) for c in cards)]
    for p in scan.changed:
        f = ROOT / p
        bits.append((p, f.stat().st_mtime_ns if f.is_file() else 0))
    return hashlib.sha1(repr(bits).encode("utf-8", "replace")).hexdigest()


class Candidate:
    """The private copy under check. `out` = file taken out (back to HEAD) → why."""

    def __init__(self, app: Path, scan: Scan, quarantine: dict):
        self.app, self.checkout, self.scan = app, app.parent, scan
        self.out: dict[str, str] = dict(scan.held)
        self.blamed: dict[str, str] = {}    # taken out because a check failed, not merely unfinished
        self.known_failures: list[str] = []
        self.bytes: dict[str, bytes | None] = {}
        for p in scan.changed:
            mine = self.checkout / p
            if p not in scan.held and not mine.exists() and (ROOT / p).is_file():
                mine.parent.mkdir(parents=True, exist_ok=True)     # app/ios, app/android…: not check inputs
                shutil.copy2(ROOT / p, mine)
            self.bytes[p] = mine.read_bytes() if mine.is_file() else None
        for p, q in quarantine.items():
            if p in self.bytes and p not in self.out and time.time() - q["at"] < QUARANTINE_S \
                    and q["sha"] == self.sha(p):
                self.out[p] = "上次檢查擋下，內容還沒改"
                self.blamed[p] = q.get("why") or self.out[p]
        for p in self.out:
            self.head(p)

    def sha(self, path: str) -> str:
        return hashlib.sha1(self.bytes.get(path) or b"").hexdigest()

    @property
    def included(self) -> set[str]:
        return set(self.scan.changed) - set(self.out)

    def head(self, path: str):
        f = self.checkout / path
        data = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True, creationflags=NO_WINDOW)
        if data.returncode == 0:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data.stdout)
        else:
            f.unlink(missing_ok=True)

    def mine(self, path: str):
        f = self.checkout / path
        if self.bytes.get(path) is None:
            f.unlink(missing_ok=True)
        else:
            f.write_bytes(self.bytes[path])

    def take_out(self, files: set[str], why: str, blamed: bool = False):
        for p in files:
            self.out[p] = why
            if blamed:
                self.blamed[p] = why
            self.head(p)

    def settle(self) -> bool:
        """A card missing a file doesn't go at all: nothing half-done reaches the Mac."""
        extra = mc.only_theirs(self.scan.owned, set(self.out)) - set(self.out)
        self.take_out(extra, "同一張卡還有檔案沒好")
        return bool(extra)

    def unready(self, card: dict) -> bool:
        return bool(self.scan.owned[int(card["card"])] & set(self.out))

    def fingerprint(self) -> str:
        bits = [sh("git", "rev-parse", "HEAD:app").stdout.strip()] + [(p, self.sha(p)) for p in sorted(self.included)]
        return hashlib.sha1(repr(bits).encode("utf-8", "replace")).hexdigest()


def analyze(c: Candidate) -> tuple[bool, str]:
    """Take out what doesn't compile until the rest does. Needing a card that isn't finished is
    nobody's failure, so only real errors are blamed."""
    for _ in range(MAX_ANALYZE_ROUNDS):
        code, output = flutter("analyze", "--no-fatal-infos", "--no-fatal-warnings", cwd=c.app, timeout=ANALYZE_TIMEOUT_S)
        if code == 0:
            if c.settle():
                continue
            return True, ""
        errors = mc.analyze_errors(output)
        if code == 124 or not errors:
            return False, f"flutter analyze 沒跑完（{code}）\n" + output[-2000:]
        moved = False
        for f in errors:
            reach = mc.import_closure(c.checkout, f)
            suspects = {f} if f in c.included else reach & c.included
            if not suspects:
                continue
            if reach & set(c.scan.held):
                c.take_out(suspects, "依賴還沒做完的卡")
            else:
                c.take_out(suspects, f"analyze error：{f}", blamed=True)
            moved = True
        if not moved:
            c.known_failures += errors
            return False, "flutter analyze 的錯誤不在這批改動裡\n" + output[-2000:]
    return False, "flutter analyze 拆了太多輪還是有錯"


def run_tests(c: Candidate, files: list[str] | None = None) -> tuple[int, str]:
    args = ["test", "--reporter=expanded", *[f.split("/", 1)[1] for f in files or []]]
    return flutter(*args, cwd=c.app, timeout=TEST_TIMEOUT_S)


def test_passes_without(c: Candidate, failed: list[str], group: set[str]) -> bool:
    for p in group:
        c.head(p)
    try:
        return run_tests(c, failed)[0] == 0
    finally:
        for p in group:
            c.mine(p)


def test_round(c: Candidate) -> tuple[bool, str]:
    """(passed, line). False: something was taken out, check what is left."""
    code, output = run_tests(c)
    if code == 0:
        return True, output.splitlines()[-1] if output else "flutter test passed"
    failed = mc.failed_tests(output)
    if code == 124 or not failed:
        raise CheckStopped(f"flutter test 沒跑完（{code}）\n" + output[-2000:])
    code2, again = run_tests(c, failed)
    still = [] if code2 == 0 else mc.failed_tests(again)
    if code2 != 0 and not still:
        raise CheckStopped("flutter test 重跑沒跑完\n" + again[-2000:])
    flaky = sorted(set(failed) - set(still))
    if flaky:
        log("failed in the full run, passed alone: " + ", ".join(flaky[:8]))
    moved = False
    for t in still:
        suspects = c.included & (mc.import_closure(c.checkout, t) | {p for p in c.included if not p.endswith(".dart")})
        cause = mc.narrow(lambda g: test_passes_without(c, [t], g), suspects)
        if not cause:
            c.known_failures.append(t)
            continue
        c.take_out(cause, f"flutter test 失敗：{t}", blamed=True)
        moved = True
    if moved:
        return False, ""
    return True, f"flutter test 全過（{len(flaky)} 檔在全部一起跑時失敗、單獨重跑通過）" if flaky else "flutter test 全過"


def commit_snapshot(c: Candidate, paths: list[str], msg: str) -> bool:
    """Commit the bytes that passed, not whatever the tree holds by now."""
    index = c.checkout / ".candidate_index"
    env = {**os.environ, "GIT_INDEX_FILE": str(index)}
    base = ["git", "--git-dir", str(git_dir()), "--work-tree", str(c.checkout)]
    sh(*base, "read-tree", "HEAD", env=env, cwd=c.checkout)
    for i in range(0, len(paths), 100):
        r = sh(*base, "add", "-A", "--", *paths[i:i + 100], env=env, cwd=c.checkout)
        if r.returncode != 0:
            log(f"add failed: {r.stderr[-300:]}")
            return False
    if sh(*base, "diff", "--cached", "--quiet", env=env, cwd=c.checkout).returncode == 0:
        return True
    r = sh(*base, "commit", "-q", "-m", msg, env=env, cwd=c.checkout)
    if r.returncode != 0:
        log(f"commit failed: {r.stderr[-300:]}")
        return False
    for i in range(0, len(paths), 100):     # the real index follows; the working tree isn't touched
        sh("git", "reset", "-q", "--", *paths[i:i + 100])
    return True


def quarantine_of(c: Candidate, state: dict) -> dict:
    kept = {p: q for p, q in (state.get("quarantine") or {}).items() if p in c.blamed and p in c.bytes}
    for p, why in c.blamed.items():
        kept.setdefault(p, {"sha": c.sha(p), "at": time.time(), "why": why})
    return kept


def report_blamed(c: Candidate, cards: list[dict], state: dict):
    if not c.blamed and not c.known_failures:
        return
    sig = hashlib.sha1(repr((sorted(c.blamed), sorted(c.known_failures))).encode("utf-8", "replace")).hexdigest()
    if sig == state.get("reported"):    # one failure, one CLI: not a new one every two minutes
        return
    lines = [f"{p}：{why}" for p, why in sorted(c.blamed.items())][:15]
    if c.known_failures:
        lines.append("HEAD 上就失敗，不是這批改動造成：" + "、".join(c.known_failures[:10]))
    report_failure("\n".join(lines), [x for x in cards if c.scan.owned[int(x["card"])] & set(c.blamed)] or cards)
    state["reported"] = sig


def note_waiting(state: dict, cards: list[dict], why: dict[str, str], blamed: dict[str, str], owned: dict):
    """What flow_tick shows per card: why it waits, and which cards are blocked by their own failure."""
    state["waiting"] = {str(x["card"]): sorted({why[p] for p in owned[int(x["card"])] if p in why})[:3]
                        for x in cards if owned[int(x["card"])] & set(why)}
    state["blocked"] = sorted(int(x["card"]) for x in cards if owned[int(x["card"])] & set(blamed))


def save_state(state: dict):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def sync_app(cards: list[dict], state: dict, check_only: bool = False) -> int:
    scan = scan_tree(cards)
    sig = tree_sig(scan, cards)
    if sig == state.get("last_sig") and not check_only:
        return 0
    ready = [c for c in cards if not scan.owned[int(c["card"])] & set(scan.held)]
    log(f"{len(cards)} app card(s) to hand over: {', '.join('#' + str(c['card']) for c in cards)}"
        f"; {len(scan.held)} of {len(scan.changed)} changed files still being edited, {len(ready)} card(s) ready")
    if not ready and not check_only:
        note_waiting(state, cards, scan.held, {}, scan.owned)
        state["last_sig"] = sig
        save_state(state)
        return 0
    if time.time() - (state.get("tested_at") or 0) < TEST_GAP_S and not check_only:
        return 2    # the CLIs need the heavy slot too; a later tick tries again
    with check_workspace(ROOT) as app:
        head = sh("git", "rev-parse", "HEAD").stdout.strip()
        c = Candidate(app, scan_tree(cards), state.get("quarantine") or {})     # an edit during the copy counts
        started = time.time()
        rc = check_and_push(c, cards, state, head, check_only)
        log(f"check took {int(time.time() - started)} s, exit {rc}, left out: {len(c.out)} file(s), "
            f"{len(c.blamed)} blamed, {len(c.scan.held)} still being edited")
        if check_only:
            log(f"would take out: {sorted(c.blamed)[:8]}; known failures {c.known_failures[:8]}")
            return rc
        state["quarantine"] = quarantine_of(c, state)
        note_waiting(state, cards, c.out, c.blamed, c.scan.owned)
        report_blamed(c, cards, state)      # also on a push: the others went on, these still need a fix
        state["last_sig"] = sig if rc == 1 else None
        save_state(state)
        return rc


def check_and_push(c: Candidate, cards: list[dict], state: dict, head: str, check_only: bool) -> int:
    """0 = pushed or nothing to do · 1 = no push, the verdict stands · 2 = no verdict, try again."""
    line = ""
    try:
        for _ in range(MAX_TEST_ROUNDS):
            LOCK.touch()
            ok, why = analyze(c)
            if not ok:
                raise CheckStopped(why)
            if all(c.unready(x) for x in cards):
                log("no card can go yet: " + "; ".join(f"{p}: {w}" for p, w in list(c.out.items())[:5]))
                return 1
            mark = c.fingerprint()
            if mark == state.get("passed"):
                line = state.get("passed_line") or "flutter test 全過"
                break
            if mark == state.get("failed"):
                return 1
            if not heavy_lock.slot(SLOT_WAIT_S):
                log("heavy slot busy → next tick")
                return 2
            LOCK.touch()
            try:
                passed, line = test_round(c)
            finally:
                heavy_lock.release()
                state["tested_at"] = time.time()
            if passed:
                state["passed"], state["passed_line"] = mark, line
                break
            state["failed"] = mark
        else:
            log("checks failed → taken out: " + ", ".join(sorted(c.blamed)[:8]))
            return 1
    except CheckStopped as e:
        warn("檢查沒跑完：" + str(e)[:200].replace("\n", " "))
        return 2
    landing = [x for x in cards if not c.unready(x)]
    log(f"checks passed: {len(landing)} card(s) go, {len(cards) - len(landing)} wait; {line}")
    if c.known_failures:
        line += f"；另有 {len(c.known_failures)} 檔在 HEAD 上就失敗（已開問題回報，不是這批造成）"
    return 0 if check_only else push_cards(c, landing, cards, state, head, line)


def push_cards(c: Candidate, landing: list[dict], cards: list[dict], state: dict, head: str, line: str) -> int:
    paths = sorted(c.included)
    why = unsafe_to_commit(paths)
    if why:
        warn(why)
        return 2
    moved = sh("git", "diff", "--name-only", head, "HEAD", "--", "app/").stdout.split()     # not what was checked
    if moved:
        log("HEAD moved under the check: " + ", ".join(moved[:5]))
        return 2
    msg = ("Sync for Mac verification: cards " + ", ".join(f"#{x['card']}" for x in landing)
           + "\n\nCommitted by lexicon/tools/mac_sync.py after flutter analyze + flutter test passed.")
    if paths and not commit_snapshot(c, paths, msg):
        return 2
    sh("git", "fetch", "-q", "origin")
    r = sh("git", "merge", "-q", "--no-edit", "origin/main")
    if r.returncode != 0:
        log(f"merge with origin/main failed: {r.stdout[-300:]} {r.stderr[-300:]}")
        sh("git", "merge", "--abort")
        return 2
    commit = sh("git", "rev-parse", "--short", "HEAD").stdout.strip()
    no = next_item_no()
    with INBOX.open("a", encoding="utf-8", newline="\n") as f:
        f.write(inbox_item(no, commit, landing, line))
    sh("git", "commit", "-q", "-m", f"Mac inbox M{no}: verify cards on iPhone", "--", "docs/mac_inbox.md")
    if not push_origin("app"):
        return 2
    mark_issues(landing, no, commit)
    # the web app served by serve_app.py (127.0.0.1:8123 / api.willylinai.com) is a build:
    # rebuild it so the owner sees the same code the Mac verifies (owner 10/19)
    defines = ["--dart-define-from-file=posthog.local.json"] if (APP / "posthog.local.json").exists() else []
    b = sh(FLUTTER, "build", "web", "--release", *defines, cwd=APP, timeout=1500)
    log("web build " + ("OK" if b.returncode == 0 else f"failed: {(b.stdout + b.stderr)[-300:]}"))
    handed = state.setdefault("handed", {})
    for x in landing:
        if x["t"]:
            handed[str(x["card"])] = x["t"]
    if len(landing) == len(cards):      # nobody left behind: the plain time mark is enough again
        state["since"] = max([x["t"] for x in cards if x["t"]] or [state.get("since") or ""])
        state["handed"] = {}
    state["last"] = {"at": datetime.now(TAIPEI).isoformat(timespec="seconds"), "item": f"M{no}",
                     "commit": commit, "cards": [x["card"] for x in landing]}
    save_state(state)
    log(f"pushed {commit}; inbox M{no} with {len(landing)} card(s)")
    return 0


def report_failure(text: str, cards: list[dict]):
    items = http("GET", "/issues").get("items", [])
    # owner 10/23 (token savings): one issue for every test failure — reopen the latest one,
    # even after it was fixed, instead of opening a new issue (and a new CLI) each time
    open_ = sorted((i for i in items if i.get("title") == FAIL_TITLE), key=lambda i: i["id"], reverse=True)
    detail = (f"mac_sync {datetime.now(TAIPEI):%m/%d %H:%M}：等著推給 Mac 的卡 "
              f"{'、'.join('#' + str(c['card']) for c in cards)}，但 Windows 上檢查沒過，所以沒有 push。\n{text}\n"
              "修到 flutter analyze 無 error、flutter test 全過；不要為了過而刪測試。")
    if open_:
        # reopen so the issue swarm dispatches it again (an in_progress issue whose card is
        # already done would otherwise never be picked up)
        http("PUT", f"/issues/{open_[0]['id']}", {"detail": detail, "status": "open", "by": "mac_sync"})
    else:
        http("POST", "/issues", {"kind": "bug", "severity": "high", "area": "app", "title": FAIL_TITLE,
                                 "detail": detail, "reporter": "mac_sync"})


def next_item_no() -> int:
    text = INBOX.read_text(encoding="utf-8") if INBOX.exists() else ""
    return max([int(n) for n in re.findall(r"^## M(\d+)", text, re.M)] or [0]) + 1


def clean_outcome(text: str) -> str:
    """A result written through a non-UTF-8 shell is all '?' (10/24 #676, Codex): say so
    instead of passing the noise to the Mac."""
    body = (text or "").split("（dispatch_tick")[0]  # the tick's own note is real Chinese
    if body.count("?") >= 12 and not re.search(r"[一-鿿]", body):
        return "（結果檔編碼損壞，看不出內容；請看該卡的 log）"
    return text


def clean_title(c: dict) -> str:
    """Titles that reached the board through a non-UTF-8 shell arrive as '????' (card #376):
    show the result's first sentence instead of unreadable text."""
    t = (c.get("title") or "").strip()
    if len(re.findall(r"[?�]", t)) < 3:
        return t
    out = (c.get("outcome") or "").replace("全部完成：", "").strip()
    return f"問題回報（標題亂碼）：{out[:50]}"


def inbox_item(no: int, commit: str, cards: list[dict], test_line: str) -> str:
    rows = []
    for c in cards:
        rows.append(f"- 卡 #{c['card']}：{clean_title(c)[:70]}\n  結果：{clean_outcome(c.get('outcome') or '')[:160]}")
    return (f"\n## M{no}（{datetime.now(TAIPEI):%Y-%m-%d %H:%M}）狀態：待做\n"
            f"commit `{commit}`（Windows：flutter analyze 無 error、{test_line}）。`git pull` 後在 iPhone 模擬器"
            "逐張驗證下面的卡（owner 10/28：用 owner 的 iPad 驗證，模擬器只做快速檢查；不用 owner 的 iPhone）：照卡上的結果實際操作一次、截圖，"
            "結果寫進 docs/mac_verify_results.md（每張卡一列：通過／不通過／注意＋原因；第一欄寫卡號 #N，"
            "表格加「裝置」欄寫 iPad 或 模擬器，階段依這些欄位自動前進）。"
            "不通過的開 `[Mac]` 問題回報，標題寫卡號。\n" + "\n".join(rows) + "\n")


def mark_issues(cards: list[dict], no: int, commit: str):
    for c in cards:
        try:
            t = http("GET", f"/tasks/{c['card']}")
        except Exception:  # noqa: BLE001
            continue
        for iid in t.get("issue_ids") or []:
            i = http("GET", f"/issues/{iid}")
            note = f"（待 Mac 驗證：docs/mac_inbox.md M{no}，commit {commit}）"
            if note not in (i.get("resolution") or ""):
                http("PUT", f"/issues/{iid}", {"resolution": ((i.get("resolution") or "") + note)[:1500],
                                               "by": "mac_sync"})


def leftover_cards(state: dict) -> list[dict]:
    """Card #927: app/ files a handed-over card left behind (held as 「還在改」 at that run). Once no card is
    open and every changed file is quiet, the owning cards go round again, not waiting for the next card."""
    changed = [p for p in mc.changed_paths(ROOT) if p.startswith("app/")]
    if not changed or not state.get("handed"):
        return []
    try:
        if open_cards():
            return []
    except Exception:  # noqa: BLE001 — board down: wait
        return []
    cards = app_cards(None, state.get("handed"), {int(c) for c in state["handed"]})
    last = {}
    for c in cards:
        last[c["card"]] = c
    cards = list(last.values())
    scan = scan_tree(cards)
    owners = [c for c in cards if scan.owned[int(c["card"])] & set(scan.changed)]
    if scan.held or not owners:
        return []
    return owners


def push_non_app() -> int:
    """owner 10/23 「修改完就push」: changes outside app/ (lexicon, server, tools, docs) need no
    flutter checks — commit and push them as they come. app/ still waits for its checks above."""
    changed = [line[3:].strip().strip('"') for line in sh("git", "status", "--porcelain").stdout.splitlines()]
    paths = [p for p in changed if p and not p.startswith(("app/", "lexicon/tmp/"))
             and not ((ROOT / p).is_file() and (ROOT / p).stat().st_size > 50 * 1024 * 1024)]
    if not paths:
        log("no finished app cards since last sync; nothing else to push")
        return 0
    why = unsafe_to_commit()
    if why:
        warn(why)
        return 1
    LOCK.write_text(str(os.getpid()))
    try:
        sh("git", "add", "-A", "--", *paths)
        if sh("git", "diff", "--cached", "--quiet").returncode == 0:
            return 0
        r = sh("git", "commit", "-q", "-m", "Windows: lexicon / server / tools changes (mac_sync, no app/ code)")
        if r.returncode != 0:
            log(f"commit failed: {r.stderr[-300:]}")
            return 1
        sh("git", "fetch", "-q", "origin")
        if sh("git", "merge", "-q", "--no-edit", "origin/main").returncode != 0:
            log("merge with origin/main failed (non-app push)")
            sh("git", "merge", "--abort")
            return 1
        ok = push_origin("non-app")
        if ok:
            log(f"pushed {len(paths)} non-app path(s)")
        return 0 if ok else 1
    finally:
        LOCK.unlink(missing_ok=True)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--also", default="", help="extra card ids (e.g. cards launched by hand), comma-separated")
    a = ap.parse_args(argv)
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 60 * 60:
        log("another mac_sync is running → skip")
        return 0
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    cards = app_cards(state.get("since"), state.get("handed"))
    for cid in [int(x) for x in a.also.split(",") if x.strip()]:
        if all(c["card"] != cid for c in cards):
            t = http("GET", f"/tasks/{cid}")
            cards.append({"card": cid, "t": "", "title": t.get("title"), "outcome": (t.get("progress") or "")[:200]})
    if not cards:
        cards = leftover_cards(state)
        if cards:
            log(f"leftover app changes of handed-over card(s) {', '.join('#' + str(c['card']) for c in cards)}")
    if not cards:
        return 0 if a.dry_run else push_non_app()
    if a.dry_run:
        log(f"{len(cards)} app card(s) to hand over: {', '.join('#' + str(c['card']) for c in cards)}")
        scan = scan_tree(cards)
        ready = [str(c["card"]) for c in cards if not scan.owned[int(c["card"])] & set(scan.held)]
        log(f"{len(scan.changed)} changed, {len(scan.held)} still being edited; ready now: {', '.join(ready)}")
        return 0
    LOCK.write_text(str(os.getpid()))
    try:
        rc = sync_app(cards, state, a.check_only)
    finally:
        LOCK.unlink(missing_ok=True)
        heavy_lock.release()
    if not a.check_only:
        # the Mac's inbox and screenshots don't wait for app tests (10/26: #726–#729 shots stuck)
        push_non_app()
    return rc


if __name__ == "__main__":
    sys.exit(main())
