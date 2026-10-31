"""Launch Claude Code / Codex / Cursor CLI on a board card — refuses unless the card is on the 排程 board.

    python lexicon/tools/launch_agent.py --card 33 --agent "Claude Code" --prompt lexicon/logs/agents/card33.prompt.txt
    python lexicon/tools/launch_agent.py --card 33 --agent Codex --prompt ...
    python lexicon/tools/launch_agent.py --card 33 --agent "Cursor CLI" --prompt ... [--model composer-2.5]
    python lexicon/tools/launch_agent.py --check-log lexicon/logs/agents/card33_cursor.log   # usage-limit check

Rule (owner, 2026-10-15): every piece of work must appear on the board first.
The card must exist, be kind=once or recurring, status in_progress and its agent
must equal --agent (claim it first: POST /api/schedule/claim {agent, task_id}).
Logs: lexicon/logs/agents/card<id>_<claude|codex|cursor>.log

Every prompt is prefixed with lexicon/tools/agent_preamble.md (foreground work,
result.md, 5173 proxy only, no secrets, no commit/push, backup + no QC regression).

Cursor CLI (card #154): headless `cursor-agent -p --force --trust`. The full prompt
(preamble + card) is written to lexicon/logs/agents/card<id>.cursor.prompt.md and the
agent is told to read it (cmd/powershell argv cannot carry newlines). Model: --model,
else env CURSOR_AGENT_MODEL, else the first of CURSOR_MODEL_PREFS that
`cursor-agent models` lists (Cursor's own models first — they use the plan's
"Cursor Models" pool, not the paid third-party pool).

Difficulty → model (card #158): without --model, the card's difficulty (board,
else lexicon/state/card_difficulty.json, else the heuristic) picks the model /
reasoning effort from lexicon/tools/agent_capabilities.json — e.g. Cursor
grok-4.7-low for 簡單 cards, -high for 困難; Codex model_reasoning_effort
low/medium/high. Cursor runs with --output-format json so its token usage lands
in the log (read by the board's usage panel, card #157).
"""
import argparse, json, os, re, subprocess, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proc_identity  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "lexicon" / "logs" / "agents"
API = "http://127.0.0.1:5173/api"
PREAMBLE = Path(__file__).resolve().parent / "agent_preamble.md"
DIFF_STATE = ROOT / "lexicon" / "state" / "card_difficulty.json"
CLAUDE = r"C:\Users\USER\AppData\Roaming\npm\claude.cmd"
CODEX = r"C:\Users\USER\AppData\Roaming\npm\codex.cmd"
CURSOR_PS1 = str(Path(os.environ.get("LOCALAPPDATA", r"C:\Users\USER\AppData\Local"))
                 / "cursor-agent" / "cursor-agent.ps1")
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
# Cursor-owned models first (plan's "Cursor Models" pool); never a third-party model by default.
# Real ids seen 2026-10-17 (`agent models`): grok-4.7-{low,medium,high,xhigh}[-fast], composer-2.5[-fast],
# cursor-grok-4.6-*, cursor-grok-4.5-*. composer-2.5 via CLI is billed as -fast (known CLI bug), so grok first.
CURSOR_MODEL_PREFS = ["grok-4.7-high", "grok-4.7-medium", "grok-4.7", "cursor-grok-4.6-high", "composer-2.5", "auto"]

# Usage-limit / quota messages seen from Claude Code, Codex and Cursor CLI.
LIMIT_PATTERNS = [
    r"usage limit", r"hit your (usage |session )?limit", r"session limit", r"limit reached", r"weekly limit",
    r"out of (usage|credits|requests)", r"spend(ing)? limit", r"you've reached your",
    r"you have reached your", r"upgrade to (pro|ultra|a higher)",
]
_LIMIT_RE = re.compile("|".join(LIMIT_PATTERNS), re.I)


def get(path):
    with urllib.request.urlopen(API + path, timeout=60) as r:
        return json.loads(r.read())


def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def load_preamble() -> str:
    """Standing rules prepended to every launched prompt."""
    if not PREAMBLE.is_file():
        raise FileNotFoundError(f"missing agent preamble: {PREAMBLE}")
    text = PREAMBLE.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"agent preamble is empty: {PREAMBLE}")
    return text if text.endswith("\n") else text + "\n"


def build_prompt(prompt_path: Path, preamble: str | None = None) -> str:
    """Return preamble + card prompt body (preamble always first)."""
    body = Path(prompt_path).read_text(encoding="utf-8")
    head = load_preamble() if preamble is None else preamble
    if not head.endswith("\n"):
        head += "\n"
    return head + body


def pid_file(card: int) -> Path:
    return LOGS / f"card{card}.pid.json"


def live_run(card: int) -> dict | None:
    """The CLI last launched on this card if it is still running (card #431: never two CLIs on one
    card). A reused pid is another program (proc_identity, card #919)."""
    info = proc_identity.read_run(pid_file(card))
    return info if proc_identity.run_alive(info) else None


def record_run(card: int, agent: str, pid: int, at: float | None = None):
    import time
    LOGS.mkdir(parents=True, exist_ok=True)
    # an older launch time (dispatch_tick re-recording a run) must not vouch for whatever has this pid now
    started = proc_identity.process_started(pid) if at is None or proc_identity.same_process(pid, None, at) else None
    pid_file(card).write_text(json.dumps({"pid": int(pid), "agent": agent, "at": at or time.time(),
                                          "started": started}), encoding="utf-8")


def agent_kind(agent: str) -> str:
    """'codex' | 'cursor' | 'claude' from the board agent name."""
    a = agent.strip().lower()
    if a.startswith("codex"):
        return "codex"
    if a.startswith("cursor"):
        return "cursor"
    return "claude"


def parse_model_ids(models_output: str) -> list[str]:
    """Model ids from `cursor-agent models` ("<id> - <Name>" entries; robust to glued lines)."""
    ids = []
    for m in re.finditer(r"(?<![\w.\-])([a-z][a-z0-9]*(?:[.\-][a-z0-9]+)*) - ", models_output):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    if ids:
        return ids
    for line in models_output.splitlines():
        line = line.strip().lstrip("*-•> ").strip()
        if not line:
            continue
        tok = re.split(r"\s+", line)[0].rstrip(":,")
        if re.fullmatch(r"[a-z][a-z0-9]*(?:[.\-][a-z0-9]+)*", tok) and tok not in ids:
            ids.append(tok)
    return ids


def pick_cursor_model(models_output: str, prefs=None) -> str | None:
    """First preferred Cursor-owned model the account lists; else newest non-fast grok/composer."""
    ids = parse_model_ids(models_output)
    for p in prefs or CURSOR_MODEL_PREFS:
        if p in ids:
            return p
    for fam in ("grok", "composer"):
        cands = [i for i in ids if (i.startswith(fam) or i.startswith("cursor-" + fam)) and "fast" not in i]
        if cands:
            return sorted(cands, key=lambda s: [int(x) if x.isdigit() else 0
                                                 for x in re.findall(r"\d+", s)], reverse=True)[0]
    return None


def detect_limit(text: str) -> str | None:
    """Return the line that reports a usage/quota limit (last 60 lines only), else None."""
    for line in text.splitlines()[-60:]:
        if _LIMIT_RE.search(line):
            return line.strip()[:300]
    return None


def cursor_pointer(card: int, prompt_file: Path) -> str:
    """One-line argv prompt telling Cursor to read the full prompt file (no newlines)."""
    rel = prompt_file.relative_to(ROOT).as_posix() if prompt_file.is_relative_to(ROOT) else str(prompt_file)
    return (f"You are working on board card #{card}. Read the file {rel} in full first and carry out "
            f"every instruction in it exactly; it holds the standing rules and the card task. "
            f"Finish by writing lexicon/logs/agents/card{card}.result.md.")


def card_level(task: dict) -> int | None:
    """The card's difficulty: board value, else grade_cards.py's mirror, else the heuristic."""
    if task.get("difficulty"):
        return int(task["difficulty"])
    try:
        got = json.loads(DIFF_STATE.read_text(encoding="utf-8")).get(f"t{task.get('id')}")
        if got:
            return int(got["difficulty"])
    except (OSError, ValueError):
        pass
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from card_difficulty import grade
        return grade(task)[0]
    except Exception:  # noqa: BLE001
        return None


def tuned_for(agent: str, level: int | None) -> tuple[str | None, str | None]:
    """(model, reasoning effort) for this agent at this difficulty, from agent_capabilities.json."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from card_difficulty import agent_profile, effort_for, load_capabilities, model_for
        _, prof = agent_profile(load_capabilities(), agent)
        return model_for(prof, level), effort_for(prof, level)
    except Exception:  # noqa: BLE001
        return None, None


def cursor_cmd(card: int, prompt_file: Path, model: str | None) -> list[str]:
    cmd = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", CURSOR_PS1,
           "-p", "--force", "--trust", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    return cmd + [cursor_pointer(card, prompt_file)]


def _cursor_run(*args, timeout=60) -> str:
    r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", CURSOR_PS1, *args],
                       cwd=ROOT, capture_output=True, timeout=timeout, creationflags=0x08000000)
    return (r.stdout + r.stderr).decode("utf-8", "replace")


def check_log(path: str) -> int:
    p = Path(path)
    if not p.is_file():
        print(f"NO_LOG {p}")
        return 2
    hit = detect_limit(p.read_text(encoding="utf-8", errors="replace"))
    print(f"LIMIT {hit}" if hit else "OK")
    return 1 if hit else 0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", type=int)
    ap.add_argument("--agent")
    ap.add_argument("--prompt")
    ap.add_argument("--model", help="Cursor CLI only: model id (default: CURSOR_AGENT_MODEL / auto-pick)")
    ap.add_argument("--check-log", help="print LIMIT <line> if the log shows a usage limit, else OK")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.check_log:
        sys.exit(check_log(a.check_log))
    if a.card is None or not a.agent or not a.prompt:
        ap.error("--card, --agent and --prompt are required")
    try:
        bots = get("/schedule/board").get("bots", [])
    except Exception as e:  # noqa: BLE001
        sys.exit(f"拒絕啟動：讀不到看板（{e}），無法確認 {a.agent} 是否暫停。")
    if any(b.get("agent") == a.agent and b.get("paused") for b in bots):
        sys.exit(f"拒絕啟動：{a.agent} 在看板上是「暫停」。請先「開始」（POST /api/agents/{a.agent}/resume）。")
    try:
        t = get(f"/tasks/{a.card}")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"拒絕啟動：看板上找不到卡 #{a.card}（{e}）。先在看板建立／認領卡片。")
    if t.get("status") != "in_progress" or t.get("agent") != a.agent:
        sys.exit(f"拒絕啟動：卡 #{a.card} 狀態={t.get('status')} 負責={t.get('agent')}，"
                 f"必須是 in_progress 且由 {a.agent} 認領（POST /api/schedule/claim）。")
    prev = live_run(a.card)
    if prev:
        sys.exit(f"拒絕啟動：卡 #{a.card} 上一個 CLI 還在跑（pid {prev.get('pid')}，{prev.get('agent')}）；"
                 f"等它結束再派，不要讓兩個 CLI 同做一張卡。")
    prompt = Path(a.prompt)
    if not prompt.is_file():
        sys.exit(f"找不到 prompt 檔：{prompt}")
    try:
        text = build_prompt(prompt)
    except (FileNotFoundError, ValueError) as e:
        sys.exit(f"拒絕啟動：{e}")
    kind = agent_kind(a.agent)
    log = LOGS / f"card{a.card}_{kind}.log"
    model = None
    level = card_level(t)
    tuned_model, effort = tuned_for(a.agent, level)
    if kind == "claude" and level == 4:
        # owner 10/23 (token savings): an auto-graded 極難 card runs on Opus; Fable only for
        # the cards listed in agent_capabilities.json fable_cards
        try:
            from card_difficulty import load_capabilities
            fable = int(a.card) in set(load_capabilities().get("fable_cards", []))
        except Exception:  # noqa: BLE001
            fable = False
        if not fable:
            tuned_model = "claude-opus-5-5"
    if kind == "codex":
        cmd = [CODEX, "exec", "-s", "danger-full-access"]
        if effort:
            cmd += ["-c", f"model_reasoning_effort={effort}"]
        if a.model or tuned_model:
            cmd += ["-m", a.model or tuned_model]
        cmd.append("-")
    elif kind == "claude":
        cmd = [CLAUDE, "-p", "--permission-mode", "acceptEdits"]
        if a.model or tuned_model:
            cmd += ["--model", a.model or tuned_model]
        cmd += ["--allowedTools", "Bash Read Edit Write Grep Glob"]
    else:
        if not Path(CURSOR_PS1).is_file():
            sys.exit(f"拒絕啟動：找不到 Cursor CLI（{CURSOR_PS1}）。安裝：irm 'https://cursor.com/install?win32=true' | iex")
        if not os.environ.get("CURSOR_API_KEY"):
            st = _cursor_run("status")
            if "not logged in" in st.lower() or "authentication required" in st.lower():
                sys.exit("拒絕啟動：Cursor CLI 尚未登入。請在終端機執行 `agent login`（會開瀏覽器登入 Cursor）。")
        model = a.model or os.environ.get("CURSOR_AGENT_MODEL") or tuned_model
        if not model:
            try:
                model = pick_cursor_model(_cursor_run("models"))
            except Exception:  # noqa: BLE001
                model = None
        prompt_file = LOGS / f"card{a.card}.cursor.prompt.md"
        cmd = cursor_cmd(a.card, prompt_file, model)
    print(f"卡 #{a.card}「{t['title']}」→ {a.agent}，log: {log}")
    print(f"preamble: {PREAMBLE.name} ({len(load_preamble())} chars) + prompt ({prompt.stat().st_size} bytes)")
    print(f"difficulty: {level or '?'} → model {a.model or tuned_model or model or 'default'}"
          + (f", reasoning effort {effort}" if effort and kind == "codex" else ""))
    if kind == "cursor":
        print(f"cursor model: {model or '(CLI default)'}; prompt file: {prompt_file}")
    if a.dry_run:
        return
    LOGS.mkdir(parents=True, exist_ok=True)
    try:
        post("/agents/hello", {"agent": a.agent, "note": f"launch_agent 卡 #{a.card}"})
    except Exception:  # noqa: BLE001
        pass
    out = open(log, "w", encoding="utf-8")
    if kind == "cursor":
        prompt_file.write_text(text, encoding="utf-8")
        p = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                             stdout=out, stderr=subprocess.STDOUT,
                             creationflags=0x00000200 | 0x08000000)
    else:
        p = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.PIPE,
                             stdout=out, stderr=subprocess.STDOUT,
                             creationflags=0x00000200 | 0x08000000)
        # prompt always via stdin: --allowedTools is variadic and cmd.exe cuts argv at newlines
        p.stdin.write(text.encode("utf-8")); p.stdin.close()
    record_run(a.card, a.agent, p.pid)
    try:  # card #731: memory cap + BelowNormal for the CLI's whole process tree
        import job_limits
        print("job limit:", job_limits.assign(p.pid, float(os.environ.get("CLI_JOB_MEM_GB", "6"))))
    except Exception:  # noqa: BLE001
        pass
    print(f"pid={p.pid}")


if __name__ == "__main__":
    main()
