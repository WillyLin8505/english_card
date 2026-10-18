# 模擬使用者（常態卡 #12）易用性評估

（從 AGENTS.md 移來，卡 #158；內容不變。另見 `lexicon/docs/SIMULATION_USABILITY_RUBRIC.md`。）

除了抓漏與錯誤，每一輪必須以**學習者**視角評估畫面是否方便、必要、一目了然：
- 方便（少步驟、少點擊）、必要（資訊對學習有幫助）、一目了然（掃一眼就懂）
- 雜訊／無意義資訊（來源、授權、編號、頻率、內部 id 等不應出現在卡片背面）
- 清晰度與文案是否像給人看的，而不是給除錯用的

每輪至少提出 1–3 個具體 UX 改善建議；沒有重複的就開問題回報（reporter=claude-simulation），不要只回報測試失敗。
截圖請用 scale ≤ 0.5，能用文字／DOM 判斷的就不要截圖（每張截圖約數千 tokens）。

## 學習者實際看到的畫面（10/18 起）

`run_round.py` 會跑 `learner_view`：B1 學習者把 60 個字加進收藏，逐張看複習正面、背面（捲到底）與單字詳情頁，每個畫面的文字依閱讀順序存在 `app/build/rounds/<N>/learner_view.json`。每輪至少挑 3 個字完整讀過（正面→背面→詳情），並統計每區數量（例句、近義詞、相關詞），以學習者的眼光判斷：主要意思一眼看得到嗎？例句適合嗎？中文對嗎？再搭配 1–2 張實機截圖看版面。

## PostHog（10/18 起）

`run_round.py` 會把每個模擬的 App 埋點事件（`app/build/rounds/<N>/<name>.events.jsonl`）上傳到 PostHog，
每個模擬是一個模擬學習者（distinct_id `sim-r<N>-<name>`，屬性 `simulated=true`、`sim_round`、`sim_name`），
時間間隔保留、整體平移到現在。看真實使用者時要篩掉 `simulated=true`。不想上傳加 `--no-posthog`。
每輪結果請附上本地 events.jsonl 的統計（事件數、card_reviewed 的 rating 分布、平均作答毫秒），跟上一輪比較。
事件清單見 `app/README.md`「使用者行為分析」。
