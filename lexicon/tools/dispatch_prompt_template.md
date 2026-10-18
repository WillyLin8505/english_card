# 卡 #{id}：{title}

{kind_line}｜難度 {difficulty}｜相關問題回報：{issue_ids}

先讀 `GET http://127.0.0.1:5173/api/tasks/{id}`（只讀這張卡，不要讀整個看板），再讀每個相關問題回報 `GET http://127.0.0.1:5173/api/issues/<id>`：`decision` 欄位有值就是 owner 已經決定，照它做，不要再問。{prev_result_line}

## 卡片內容
{detail}

## 做法與規則
- 照 preamble 的 token 預算：先 `lexicon/docs/PROJECT_MAP.md`，大檔先 `rg -n` 再讀附近 ~60 行，輸出一律截短。
- 從根因修，範圍是整個詞庫：同一類問題其他字也會發生，先全庫量出受影響數量，再系統性修正；不要只修卡上舉例的字。新發現的根因問題開問題回報，不要自己擴大範圍。
- 改資料前先備份（檔名用 `card{id}_*`，不要覆蓋別張卡的備份）；golden（300 詞＋50 照片）與 `python lexicon/tools/qc.py check --live` 前後比對，任何指標退步就還原。
- 不要 commit/push；不要 git stash/reset/checkout --/restore/clean；不要讀 secrets（lexicon/.env、tagger/.api_key、app/tagging.local.json）。
- 不要暫停、重啟或搶用 Qwen／tags worker，除非卡片明寫。
- 【owner 10/18：Qwen 暫停期間由 Claude 代做】需要 AI 翻譯、AI 例句等原本呼叫 Qwen 的工作，由你自己直接產生並寫回資料（照原流程的欄位與來源標記，標成 AI 翻譯／AI 例句；中文一律台灣用語），不要呼叫 Qwen、不要取消它的暫停。量大就分批（每批 ≤ 200 筆，先備份、批後跑 golden/QC），一輪做不完就在 result.md 寫進度與下一輪從哪裡續；全部做完時 result.md 第一行寫「全部完成：…」。
{night_line}
- 里程碑用 `PUT http://127.0.0.1:5173/api/tasks/{id}` 的 `progress` 寫一行（≤ 每 30 分鐘一次）。狀態不用自己改，派工程式會依 result.md 收卡；需要使用者決定的事，在 result.md 第一行寫「需要你決定：…」。

## 結束前
寫 `lexicon/logs/agents/card{id}.result.md`（≤ 40 行）：第一行一句話結論（含關鍵數字），接著前後數字表、改了哪些程式與資料、備份與還原指令、golden/QC 結果、剩下什麼。
