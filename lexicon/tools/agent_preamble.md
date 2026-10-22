# Standing rules (auto-prepended by launch_agent.py)

These rules apply to every card launched through `lexicon/tools/launch_agent.py`.
Follow them even if the card prompt below is silent on the topic.

## Foreground work and result.md
- Run **every** shell command in the **foreground**. Never background a command (`&`, `Start-Job`, detached processes, or tools that return before the work finishes).
- Split work into steps that each finish in **under 10 minutes**. Long batches must be chunked and awaited in the foreground.
- Before you end the session, always write `lexicon/logs/agents/card<ID>.result.md` (or the path the card names) with what you did, what you found, and what is left. Ending without `result.md` is a failure.

## Board / API: 5173 proxy only — no secrets
- Call the board and lexicon API **only** through `http://127.0.0.1:5173` (Vite proxy). Example: `http://127.0.0.1:5173/api/tasks`.
- **Never** call `http://127.0.0.1:8770` (or any other direct admin port) yourself.
- **Never** open, read, print, or paste secrets: `lexicon/.env`, `tagger/.api_key`, `app/tagging.local.json`, or any file that looks like credentials.
- If you get **401 Unauthorized**, switch to the `5173` proxy and continue. Do **not** stop to ask for an API key, and do **not** read `.env` to obtain one. The proxy needs no key.

## Safety and quality
- Do **not** `git commit` or `git push` unless the card and the owner explicitly say so.
- **Never** rewrite the git working tree. Do **not** run `git stash`, `git checkout -- ...` / `git restore`, `git reset`, `git clean`, or any other command that discards, overwrites, or hides uncommitted changes. Other agents have work in progress in the same tree. Only **read** git state (`git status`, `git diff`, `git log`).
- Back up files or DB rows **before** deleting or bulk-rewriting data.
- After meaningful changes, run golden / QC as the card requires; **no regression** is allowed (do not ship a change that worsens golden or QC metrics).
- Do not restart agents or services that other cards are using unless this card says so.

## Token budget (card #158)
- Don't explore the tree: read `lexicon/docs/PROJECT_MAP.md` first. `AGENTS.md` is already loaded for you — don't re-read it.
- Big files (`images.py` 2151 lines, `word_database_repository.dart` 1371, `tagging_server.py` 1544…): `rg -n` first, then read ~60 lines around the hit. Never print a whole file over 300 lines.
- Never dump `/api/schedule/board` (50 KB+ JSON); use `/api/tasks/<id>` or `python lexicon/tools/pick_card.py --agent X --all`.
- Cap every command's output (`| Select-Object -First 80` / `-Last 40`, `pytest -q`); print counts and samples, not whole datasets. Never open `*pack*.json`, big `*.jsonl` or logs in `lexicon/logs/agents/` — extract numbers with Python.
- Standing cards: reuse the earlier round's script (see PROJECT_MAP "Standing cards") instead of writing a new one; read only the last `card<ID>.result.md`.
- Screenshots only when the card needs visual judgment, at scale ≤ 0.5. Don't open images with a file-read tool.
- Keep `result.md` short: what changed, numbers, what is left (≤ 40 lines).

---
# Card prompt

- 【manager 10/20】你是派工程式開的 CLI：**不要用 task.py（hello/start/next/progress/done）**，也不要 PUT 卡片的 agent／status——那會把卡改到別的名字（例如「Claude · card385」），派工程式就收不到你的結果。進度只用 `PUT /api/tasks/<id>` 的 `progress`，結束時寫 result.md 就好。

## 暫時凍結（Mac 10/23 通知，Mac push 修正後由 Manager 移除）
Mac 正在修複習翻卡卡頓：**不要修改** `app/lib/widgets/flashcard_back.dart`、`app/lib/widgets/flashcard_session_views.dart`、`app/lib/screens/photo_detail_screen.dart`。卡片需要改這三個檔時，寫進 result.md「需要你決定：等 Mac 的翻卡修正 push 後再改」並停下。
