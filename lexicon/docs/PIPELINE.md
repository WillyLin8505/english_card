# 統一流程（owner, 2026-10-31）

新功能、問題、手機回饋、模擬發現、Mac 發現都走同一條流程。目標是 owner 介入越少越好：
進度由系統回報，不靠 owner 追問，也不靠 AI 之間傳話。

## 階段

| # | 階段 | 誰負責 | 通過條件 | 不通過 |
|---|---|---|---|---|
| 1 | 收件 | 系統 | 任何來源都成為一張卡或問題回報，標來源 | — |
| 2 | 派工 | dispatch_tick | 分級後自動派給 CLI | 需要產品決定 → 待決定 |
| 3 | 開發 | CLI | result.md 寫出結果與測試 | 排回待辦 |
| 4 | Windows 檢查 | mac_sync | flutter analyze、flutter test 全過後推送 | 自動開修復卡 |
| 5 | Mac 驗證 | Mac | 模擬器逐項通過，寫進 mac_verify_results | 自動開 Windows 卡，回到 2 |
| 6 | iPad 驗證 | Mac | 實機逐項通過；相機由 owner 手動確認 | 同上 |
| 7 | 可發布 | 系統 | 該版本的卡全部通過，沒有高嚴重度問題 | — |
| 8 | 發布 | TestFlight 系統；App Store owner | 跑發布清單；TestFlight 自動發，App Store 由 owner 按一下 | 停止放量 |
| 9 | 上線觀察 | 系統 | 當機、留存、回饋進入第 1 階段 | — |

## 規則

- 卡的 `done` 只代表 CLI 做完。App 卡要過第 6 階段，問題才算處理完。
- 一張卡只由流程決定狀態，不用人工判斷或口頭回報。
- 「注意」和「不通過」一樣要進系統，不能只留在訊息裡。
- 手機回饋必須能追到卡號、階段、結果。
- AI 之間靠 docs/mac_inbox.md 和 docs/mac_verify_results.md，不靠對話傳話。

## Owner 只介入這些事

1. 產品決定（問題回報的待決定）。
2. 帳號、付款、條款、憑證、登入。
3. 相機等 Mac 工具驗不到的手動確認。
4. 正式發布到 App Store：owner 按一下（owner 10/31 決定，問題回報 #1174）。TestFlight 由系統自動發，但要等 Apple 開發者帳號下來後另開卡實作，現在不做。

其餘事情不應該需要 owner 查看。需要時由每日摘要列出，不在對話裡零散通知。

## 自動化怎麼運作（卡 #916）

`lexicon/tools/flow_tick.py` 每次 dispatch_tick 跑一次，不用 LLM。從卡片狀態與 origin/main 的
`docs/mac_inbox.md`、`docs/mac_verify_results.md`、`docs/releases.md` 算出階段，存進卡與問題回報的
`stage`；沒有人工更新階段的流程。卡 #919、問題回報 #1175 起才追蹤（`dispatch_config.json` 的
`flow`），更早的資料欄位維持空值。

| 欄位值 | 階段 | 什麼時候進來 |
|---|---|---|
| `dev` | 開發 | 卡還沒做完 |
| `windows_check` | Windows 檢查 | App 卡 done，mac_sync 還沒推 |
| `mac_verify` | Mac 驗證 | M 項（有 commit 的 `- 卡 #N`）已在 origin/main |
| `ipad_verify` | iPad 驗證 | 模擬器那列通過 |
| `ready` | 可發布 | iPad 那列通過 |
| `released` | 已發布 | commit 包含在 `docs/releases.md` 的某一版 |
| `done` | 完成（不需驗證） | 非 App 卡做完，不經過 Mac |
| `cancelled` | 取消 | 卡取消或問題不處理 |

- 不通過或注意：停在該階段，`stage_state` 為 `failed`／`note`；不通過的列由 mac_results_to_issues 開問題，
  那個問題走完流程後原卡自動往下。
- App 判定：`flow_rules.is_app`，result.md 提到 `app/lib` 等路徑、`.dart`、`flutter test`、「需要 Mac：」，
  或有畫面相關字眼且問題範圍是 App。mac_sync 用同一規則。
- 問題回報：跟著最慢的那張卡。新問題的 App 卡做完時維持「處理中」，過 iPad 才變「已修正」。

後台「流程總覽」（`#/flow`，`GET /api/flow/overview`）：需要你、能不能發布與原因、每階段張數、卡住最久、
手機回饋對到卡號與階段。每日摘要在 09:00 後由 flow_tick 產生，只列「需要你」的事，存
`lexicon/logs/daily_digest/<日期>.md` 並顯示在總覽頁；沒事就不產生。

有摘要的那天寄 Gmail 給 owner 自己（owner 10/31，問題回報 #1175，`tools/gmail_send.py`）：`lexicon/.env` 的
`LEXICON_GMAIL_ADDRESS`、`LEXICON_GMAIL_APP_PASSWORD` 由 owner 自己填，AI 不索取、不讀、不印。沒填就略過，
總覽頁顯示「尚未設定 Gmail」，不報錯也不擋 flow_tick；當天稍晚才填，下一輪仍會補寄當天摘要。寄失敗每 30 分鐘
重試，一天最多 3 次，原因顯示在總覽頁。

## 目前還沒自動化的部分

由卡片補上，完成後刪掉這段：檢查失敗時不擋住全部卡（#917）。

（#918 已做：Mac 回報格式在 docs/mac_verify.md「報告格式」；`注意` 列由 mac_results_to_issues 開 `[Mac 注意]` 低嚴重度待辦，不用卡號也行；通過列由 flow_tick 推進階段；同一項未結案不重複開；Mac 定時讀 inbox 見 mac_inbox M541。）
