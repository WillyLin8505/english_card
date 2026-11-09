# Notes for AI agents working in this repository

Start with `lexicon/docs/PROJECT_MAP.md` (where things are, file sizes, how to read big files)
instead of exploring the tree. Details that only some cards need live in `lexicon/docs/agents/`.

All features, problems and feedback follow one flow (owner, 2026-10-31): `lexicon/docs/PIPELINE.md`.
Stages are worked out by `lexicon/tools/flow_tick.py` (run by dispatch_tick); never set them by hand. Overview:
http://127.0.0.1:5173/ui/#/console. A card's `done` only means the CLI finished: a new App 問題回報 stays 處理中 until
the iPad passed. Mac rows need the card number first, plus 結果 and 裝置 columns.

## 排程看板: report what you work on, pull cards when idle

The owner runs several AIs (Claude Code, Codex, Cursor CLI) and watches them on the 排程 board
(控制台 http://127.0.0.1:5173/ui/#/console, replaces #/schedule, #/flow, #/issues): the owner's
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
- One card, one CLI (card #431): `launch_agent.py` records each CLI in `lexicon/logs/agents/card<id>.pid.json` (pid + creation time; every liveness check goes through `proc_identity.py` because Windows reuses pids)
  and refuses to launch a card whose previous CLI still runs; the tick skips such cards, waits
  `finish_grace_alive_minutes` (45) before collecting a card whose CLI is still alive, and ends a CLI quiet for
  `lingering_kill_minutes` (90).
- serve_app reload (card #522, owner A): serve_app loads `lexicon/backend/app`, `lexicon/quality`, `serve_app.py`,
  `lexicon_transport.py` only at start-up; the tick restarts it when that code changed, has been quiet 15 min, the CLIs
  running at the change are done (≤ 6 h) and no `busy_tasks` card (simulation) runs (`serve_app_reload` in dispatch_config.json;
  check by hand: `python lexicon/tools/serve_app_stale.py`).
- Night simulation (owner, 2026-11-03: the PC is free at night): inside `night_simulation.window` (01:00–07:00) the
  user-simulation cards (#12, #224–#228, #496) rerun every `cooldown_hours` (1 h) instead of 12 h; what they find becomes
  問題回報 and the swarm opens cards. The Mac does the same on the iPad (docs/mac_inbox.md M611).
- `priority_tasks` in dispatch_config.json (owner 11/04 「法文優先」, now #833): those cards take the next free CLI
  before every issue; take a card out when it is done.
- Hung services (owner, 2026-11-04: the API hung 12 h with its port open and nothing ran): after
  `api_hang_restart_after` (3) failed board reads in a row, then every 15 more, the tick runs `watchdog.restart_hung`:
  the API (8770 `/health`) or admin UI (5173) whose port is open but doesn't answer within 15 s is stopped and started again.
- Qwen GPU guard (owner 11/05 「好，卸載它」): photo_tidy_up's Ollama keeps qwen3-vl in the shared 8 GB GPU forever and
  stalled our llama-server 23:11–04:46. Each tick checks `:8790/health`: 2 failures in a row → unload any Ollama model idle
  ≥ 5 min (it reloads on demand); 4 → restart only our llama-server (start_llm.py's child, never Ollama's runner).
  `qwen_gpu_guard: false` in dispatch_config.json turns it off. The same check restarts the tagger (`:8765` open but
  `/health` failing 2 ticks, owner 11/05) via `start_tagger.bat`, and the hourly watchdog starts a missing tagger even
  while llama-server runs (start_llm.py then starts no second one).
- Dry run: `python lexicon/tools/dispatch_tick.py --dry-run`. Tests: `lexicon/tests/test_dispatch_tick.py`.

## AI 資源上限 (owner, 2026-10-31: PC powered off under load; 11-02: CPU and GPU 80 %, Qwen and gap-fill cards run all day)

`lexicon/tools/ai_watch.py` (kept running by dispatch_tick) holds the whole PC to 80 % CPU and 80 % GPU: AI caps add up to
76 % (half for the shared Job Object, half split among the dispatched CLIs' own jobs, at least 2 % each), all scaled down
every 10 s while the PC is at 72 %; a busy GPU runs the model servers in bursts (0.4 s on, 0.6 s suspended), ≥ 85 °C
suspends them 20 s. **11/05 (the PC powered off again after 8 min at GPU 100 % while the log said gpu-bursts):** the
bursts run in their own process (`ai_watch.py --pace`, heartbeat `lexicon/state/ai_watch_pace.beat`; the watcher restarts
it), because as a thread they lost the GIL to the process sweeps; GPU ≥ 90 % for 3 samples while bursting → 20 s rest and
the log names the GPU users; resource_guard holds new CLIs while the GPU is over 80 %.
**Later 11/05: all three power-offs were bug check 0x116 VIDEO_TDR_FAILURE (NVIDIA driver 2025-08 timing out; nvlddmkm
errors since 10/22), each while llama-server was being suspended. `GPU_SUSPEND = False`: model servers are never suspended
any more (no bursts, no rests). Don't turn it back on; limit GPU load by sending Qwen less work instead.** 11/06 (owner 「GPU 百分百」): the tagger
paces background calls itself (`TAGGER_GPU_DUTY`, default 0.6: after a T-second call no background call starts for
T·(1-d)/d s; App photo calls never wait) — measured 54 % average instead of ~95 %.
**11/06 08:30, 4th 0x116 on the new driver 621.14: the cause is GPU memory, not load.** llama-server held 7.4 GB of the
8 GB card plus 2 GB spilled into shared RAM (its vision buffer sized for the model's largest image), and photo_tidy_up's
Ollama had loaded qwen3-vl 5 min earlier. Now `--image-max-tokens 1024` (5.4 GB, photos ≤ 768 px ≈ 576 tokens) and
photo_tidy_up's laptop_ai sends `num_gpu: 0` (its models on the CPU, owner's choice). Check per-process GPU memory with
`Get-Counter '\GPU Process Memory(*)\Dedicated Usage','\GPU Process Memory(*)\Shared Usage'`; keep ≥ 1.5 GB free. Interactive Claude sessions and what they run are never capped. No new CLIs while CPU is over 80 %.
**11/04 (the PC shut down twice with 20+ CLIs): at most `max_running_clis` CLIs at once (2 while testing) and
`max_launches_per_tick` 1, whatever the swarm slots allow; raise one step at a time after watching ai_watch.log.**
**11/09 owner 「所有的問題都開卡做，卡片沒有上限」 (those power-offs turned out to be the GPU 0x116, fixed above): `max_running_clis`
and `issue_swarm.max_parallel` are 40 (no practical cap), `max_launches_per_tick` 2 so load builds up gradually; the limit is
resource_guard (memory / CPU / GPU over 80 % → no new CLIs) plus ai_watch's CPU caps. Don't lower the count again unless those fail.**
The limits are set through Process Governor (`procgov`, winget LowLevelDesign.ProcessGovernor; ai_watch `PgJob`).
Never `procgov --install`: its service would clash with Process Lasso's core service, also named ProcessGovernor. Limits of nested jobs only add up and a job keeps its limit after its handle closes, so a
restarted watcher skips processes already handled (lexicon/state/ai_watch_handled.json). A process over its memory limit gets out-of-memory errors:
split the work, don't work around it. Log: `lexicon/logs/ai_watch.log` (one line every 10 s).

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
