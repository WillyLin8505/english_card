# Cursor CLI（第三個派工對象，卡 #154）

（從 AGENTS.md 移來，卡 #158；並更新 #157／#158 的變更。）

- 看板名稱固定為 `Cursor CLI`（AI 機器人區有心跳與暫停／開始，與 Claude Code、Codex 相同機制：`POST /api/agents/hello`、`/api/agents/Cursor CLI/pause|resume`）。
- 已安裝於 `%LOCALAPPDATA%\cursor-agent`（`agent` / `cursor-agent`）。需先 `agent login` 一次（瀏覽器登入 Cursor）；`agent status` 會顯示登入狀態。
- 派工方式與其他 AI 相同：先 `POST /api/schedule/claim {"agent":"Cursor CLI","task_id":<id>}`，再
  `python lexicon/tools/launch_agent.py --card <id> --agent "Cursor CLI" --prompt lexicon/logs/agents/card<id>.prompt.txt [--model <id>]`。
  啟動器會自動加上 preamble，把完整 prompt 寫到 `lexicon/logs/agents/card<id>.cursor.prompt.md`，以 headless
  `cursor-agent -p --force --trust --output-format json` 執行（卡 #157 起改 json：結果行帶 `usage`，看板用量面板會加總）；
  log：`lexicon/logs/agents/card<id>_cursor.log`。未登入時拒絕啟動。
- 模型：`--model` > 環境變數 `CURSOR_AGENT_MODEL` > 依卡片難度（`agent_capabilities.json` 的 `models_by_difficulty`：
  簡單 grok-4.7-low、中等 -medium、困難 -high）> 自動從 `agent models` 挑 Cursor 自家模型。只用方案內「Cursor Models」額度，
  預設**不**用第三方模型（會吃另一個額度或按量計費）。
- 額度檢查：`python lexicon/tools/launch_agent.py --check-log lexicon/logs/agents/card<id>_cursor.log` 印出 `LIMIT <訊息>`（exit 1）或 `OK`（exit 0），三個 AI 的 log 都適用。
- Cursor 方案按月計，沒有 5 小時／週額度；看板只顯示 json log 加總的 tokens（估計）。
- 同一張卡永遠只派給一個 AI（Claude Code、Codex、Cursor CLI 三選一）。
- 監看：json／text 輸出都是結束才寫 log；進行中可看 `%USERPROFILE%\.cursor\projects\D-vibe-coding-english-card\agent-transcripts\<chat-id>\*.jsonl`（工具呼叫紀錄）與 node.exe 行程是否存在。
