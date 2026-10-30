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

## 分工（owner 10/23 #626）與暫時凍結
owner 在哪台下的指令就在哪台做（owner 10/28）：owner 在 Windows 交代的需求（卡片／問題回報標 [owner]、沒有 [給 Mac]），App 程式（app/lib）也由 Windows 卡自己改，改完跑 flutter analyze 與 flutter test，Mac 只在模擬器驗證；不要寫「需要 Mac：改畫面」。
一律由 Windows 修（owner 10/30：「現在一律只要發現新的問題，就直接在 Windows 這邊派卡修理」）：App 使用者回報、Mac 退回的問題、[意見回饋]、[卡片回報] 的 App 畫面也由 Windows 卡自己改 app/lib，改完跑 flutter analyze 與 flutter test；「需要 Mac：…」只寫要 Mac 在 iPad／iPhone 量測或驗證的項目，不要把修改交給 Mac。做不完寫「第 N 輪：…還剩…」，不要寫成完成。
常態卡（每輪重跑）（manager 10/28）：「需要 Mac：…」「剩餘：…」只寫本輪截圖／JSON 真的看到的新問題；不要從上一輪 result.md 照抄，已修好、已驗過的舊項目不要再列。
Mac 預設用 owner 的 iPad（A16，有辨識金鑰）驗證，模擬器只做快速檢查（owner 10/28）；tagger 的修正（補字、等級、辨識）仍由 Windows 卡自己經 5173 打 tagger 量測、把數字寫進 result.md，Mac 用 iPad 抽驗。

## 要 owner 決定的問題（owner 10/23、10/26）
result.md 第一段「需要你決定：…」要白話、一眼看懂，**最多 300 字**：
- 第一行：一句話說要決定什麼（不要用程式名詞）。
- 接著**最多 3 個選項**，每個一行，開頭寫 `A：`、`B：`、`C：`，每個選項一句話。
- 最後一行：`建議：B，因為…`（一定要有）。
問題回報頁會把 A／B／C 變成可以點的按鈕，另有「其他」欄讓 owner 自己寫。細節放空一行之後的段落。開 [待決定] 問題回報時也一樣。

## 寫檔一律 UTF-8（10/24：Codex 的 result.md 中文全變成 ???）
result.md、progress 和所有中文檔案，都用 Python 寫：`open(path, 'w', encoding='utf-8')`。PowerShell 的 `Set-Content`／`Out-File`／`echo >`／`>` 預設不是 UTF-8，中文會變成 ?，不要用。寫完用 Python 讀回第一行確認看得到中文。

## Heavy jobs one at a time (card #731)
- Memory-heavy commands (`flutter test`, full exports / pack builds, `card*_measure` / whole-library scans) must run as
  `python lexicon/tools/heavy_lock.py run -- <command>` (waits for its turn; `qc.py check --live` already does). Each CLI is capped at 6 GB
  and BelowNormal; above 90 % memory for 2 min the guard ends your biggest child process ("資源不足，稍後重跑") — rerun it later.
