# Notes for AI agents working in this repository

Start with `lexicon/docs/PROJECT_MAP.md` (where things are, file sizes, how to read big files)
instead of exploring the tree. Details that only some cards need live in `lexicon/docs/agents/`.

## 排程看板: report what you work on, pull cards when idle

The owner runs several AIs (Claude Code, Codex, Cursor CLI) and watches them on the 排程 board
(http://127.0.0.1:5173/ui/#/schedule): AIs on the left, task cards on the right — the owner's
requests, open 問題回報 (bugs / unbuilt requirements), and standing cards (recurring checks).

Use `python lexicon/tools/task.py` (local tools only; dispatched agents use the 5173 proxy, see the
preamble). Your name: `Claude · <session title>` for a Claude Code session, `Codex 桌面版` for the
Codex app — the same name every time.

- **Start of a session**: `task.py hello --agent "<name>"`.
- **New request from the owner in chat** → `task.py start "<one line, Traditional Chinese>" --agent "<name>"`.
- **Idle / 「去拉卡」** → `task.py next --agent "<name>"` (`--pile once|recurring`). A 問題回報 card links
  the issue; update it on the 問題回報 page as you fix it.
- **Milestones** (≤ every 30 min, else 「可能已停止」): `task.py progress <n> "<one line>" --agent "<name>"`.
- **Waiting for the owner** → `task.py waiting <n> "<question>"`; **stuck** → `task.py blocked <n> "<why>"`.
- **Finished** → `task.py done <n> "<result with numbers>" --agent "<name>" [--issues 169,171]`
  (a standing card then waits for its next run).

Standing cards describe a check, not a fix: report what you found (問題回報 for anything that needs the
owner), fix only what the card allows, and ask before calling the AI model at scale or rewriting data.
If the API isn't running, carry on without it; don't start servers only for this.

## Rule: nothing starts before it is on the board (owner, 2026-10-15)

Every piece of work — Claude Code, Codex, Cursor CLI **and the Grokbot dispatcher** — must first be a
card in `in_progress` with your agent name. Work without a card is invisible and not allowed.

- Grokbot's own work: `POST /api/tasks {"title":"…","kind":"once","agent":"Grokbot","status":"in_progress","by":"Grokbot","requested_by":"owner"}`;
  finish with `PUT /api/tasks/<id> {"status":"done","progress":"…","by":"Grokbot","agent":"Grokbot"}`.
- Dispatching: claim first (`POST /api/schedule/claim {"agent":"Codex","task_id":<id>}`), then launch only via
  `python lexicon/tools/launch_agent.py --card <id> --agent <name> --prompt <file>` (refuses unless the card is
  in_progress and held by that agent). Never put one card on two AIs.

## Dispatching by difficulty (card #156)

Every card has a difficulty: **1 簡單 · 2 中等 · 3 困難 · 4 極難** (badge on the board, editable there or
`PUT /api/schedule/difficulty {task_id|issue_id, difficulty, reason}`). What each AI may take is in
`lexicon/tools/agent_capabilities.json` (Claude Code ≤ 4, prefers 3–4 · Codex ≤ 3 · Cursor CLI ≤ 3 ·
Qwen/Grokbot take no cards), shown in the board's AI 機器人 panel with each AI's 5-hour / weekly usage.

- Pick a card: `python lexicon/tools/pick_card.py --agent "<name>" [--all] [--claim]` — eligible difficulty,
  owner's requests → 問題回報 by severity → due standing cards; skips cards another AI holds, blocked cards
  and the skip lists in the capabilities file. Exit 3 = nothing fits, 4 = paused.
- New cards: `python lexicon/tools/grade_cards.py` grades ungraded cards (heuristic + one-line reason);
  `--set t89=3:理由` overrides. A grade set on the board is kept.
- **Night-only cards** (owner, 2026-10-17): Qwen-heavy cards listed in `night_only_tasks` (now #166, #167)
  are dispatched only 01:00–07:00 Asia/Taipei (`night_window`). `pick_card.py` skips them outside the window;
  before launching a card by id, run `pick_card.py --agent X --check-task <id>` (exit 6 = not now).
- `launch_agent.py` picks the model by difficulty when `--model` is not given (Cursor grok-4.7-low/medium/high,
  Codex reasoning effort low/medium/high) — cheap models for easy cards.

## Dispatcher = `dispatch_tick.py` (owner, 2026-10-18: cut Grokbot tokens to ≤ 1/5)

All routine dispatching runs **without an LLM**: Windows Task Scheduler task `EnglishCard_DispatchTick`
runs `pythonw lexicon/tools/dispatch_tick.py` every 2 min (owner 10/19: a new card gets its CLI at once) (lock file, log `lexicon/logs/dispatch_tick.log`).
Each tick: Grokbot paused → nothing; collects finished cards (result.md → done / next run / queued,
repeat cards' result renamed `card<id>.rN.result.md`); LIMIT → card queued, AI rested until its reset
(`lexicon/state/dispatch_state.json`); unblocks `unblock_after` cards; grades ungraded cards; picks and
launches a card for each idle AI (pick_card rules + `lexicon/tools/dispatch_config.json`: reserved/prefer,
12 h cooldown for standing cards, no night card after 06:15) with the prompt built from
`lexicon/tools/dispatch_prompt_template.md`; heartbeats; one line on #13. No per-run log cards.
- Grokbot reads only `python lexicon/tools/dispatch_digest.py` (unread notable events, ≤ 15 lines) and acts
  on ❓/⚠/✖ lines; it does not re-run heartbeats, quota checks or pick_card by hand.
- Pause: board Grokbot ⏸, or `schtasks /change /tn EnglishCard_DispatchTick /disable` (`/enable` to resume).
- **Issue swarm** (owner, 2026-10-18): every new 問題回報 card (and every decision the owner has answered) gets its
  own new Claude CLI (`Claude CLI 1..N`, `issue_swarm.max_parallel` in dispatch_config.json, Claude Code's quota);
  a finished card marks its issues fixed. Agents read the issue's `decision` field and follow it.
- Dry run: `python lexicon/tools/dispatch_tick.py --dry-run`. Tests: `lexicon/tests/test_dispatch_tick.py`.

## Standing preamble (auto-attached on every launch)

`launch_agent.py` always prepends `lexicon/tools/agent_preamble.md` (foreground work in steps < 10 min,
always write result.md, 5173 proxy only, no secrets, no commit/push, no git stash/checkout --/restore/reset/clean,
back up before deleting data, golden + QC no regression, token budget). Edit that one file to change the
standing rules for every dispatch. Older docs that mention `:8770` with a key from `.env` are for local
tools that already hold the key, not for dispatched agents.

## 暫停／開始機器人（看板按鈕）
- 每個機器人有「⏸ 暫停／▶ 開始」：`POST /api/agents/{name}/pause|resume`；狀態在 `GET /api/schedule/board` 的 `.bots[].paused`（`lexicon/state/paused_agents.json`）。
- 暫停中：手上的卡可以做完，但 `/api/schedule/claim` 回 423、`launch_agent.py` 拒絕啟動。沒有「立即停止」。
- **Grokbot 暫停 = 派工整輪不派任何工作。** 派工前先讀 board `.bots`：Grokbot `paused` 就結束；其他機器人 `paused` 就跳過。
- Qwen（本機模型）同一個暫停檔，細節：`lexicon/docs/agents/qwen_pause.md`。

## Card-specific notes
- 模擬使用者（常態卡 #12）易用性評估：`lexicon/docs/agents/simulation_usability.md`（每輪必讀）。
- Cursor CLI 派工細節（安裝、模型、log、監看）：`lexicon/docs/agents/cursor_cli.md`。
- Tagger restarts (card #70): only via `tagger/start_tagger.bat` (also starts llama-server; never a second one).
  Defaults live in `tagger/tagger_config.py`; never set `TAGGER_BACKEND=ollama` unless the user asks.
