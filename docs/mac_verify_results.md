# Mac / iPhone 模擬器驗證結果

依 `docs/mac_verify.md` 執行。嚴重度：高（擋住驗證或功能壞掉）・中（行為不對）・低（警告、外觀）。

**通道（owner，2026-10-18）**：git ＋ 問題回報 API 兩條都用（見 `docs/mac_verify.md` 第 6 步）。
Windows 的指令看 `docs/mac_inbox.md`；要 Windows 修的 bug 開 `[Mac]` 問題回報。

## 2026-10-18 第 1 輪（進行中）

環境：MacBook（Apple Silicon，macOS 26.6.2），repo commit `ae1d773`。

| # | 步驟 | 預期 | 實際 | 截圖 | 嚴重度 |
|---|------|------|------|------|--------|
| 1 | 1. git pull | 取得最新 | 已是最新（ae1d773） | — | — |
| 2 | 2. 環境 | Xcode、Flutter、CocoaPods 齊全 | 原本三樣都沒有。已用 brew 安裝 Flutter 3.47.7、CocoaPods 1.17.0；Xcode 由 owner 從 App Store 安裝中，裝好前無法開 iPhone 模擬器 | — | 高（擋住第 4、5 步） |
| 3 | 2. flutter doctor | 無問題 | Xcode 安裝不完整（只有 Command Line Tools）；Android SDK 沒裝（Mac 驗證不需要） | — | 高（Xcode）／低（Android） |
| 4 | 3. flutter analyze | 0 issues | 4 issues：`lib/screens/settings_screen.dart:7` 未使用的 import `../models/vocabulary_profile.dart`（warning）；`test/card38_redirect_scope_test.dart:28` if 未加大括號、`:57` 使用 print；`test/simulation/settings_simulation.dart:67` 不必要的字串插值（info） | — | 低 |
| 5 | 3. flutter test | 全部通過 | 351 通過、1 略過、4 失敗（見下） | — | 中 |
| 6 | 4. run_ios_sim.sh | App 在 iPhone 模擬器啟動 | 尚未執行（等 Xcode） | — | — |
| 7 | 5. 學習者流程 | — | 尚未執行（等 Xcode） | — | — |

### flutter test 失敗明細

1. `test/album_level_test.dart:148`「資料庫相片冊 the picker filters tiles and the opened picture」
   找不到文字 `入門（A1）：apple · 蘋果 · 中階（B1）：cluster · 串`（0 個，預期 1 個）。
2. `test/screens_test.dart:454`「設定 測試連線: connected」找不到 `✓ 已連線 · qwen3-vl`。
3. `test/screens_test.dart:463`「設定 測試連線: wrong key / not running」找不到 `✕ 服務正常，但 API Key 不正確`。
4. `test/screens_test.dart:468`「設定 測試連線: service not running」找不到
   `✕ 連不到 AI\n辨識服務（http://127.0.0.1:8765/tag），請確認服務已啟動`。

2–4 都在 `check()`（`screens_test.dart:446`）按下「測試連線」後找不到結果文字，可能是設定頁的連線測試文案或流程改了，測試沒跟著更新。

## 2026-10-18 重跑 analyze／test（commit cfb76db，M1 第 4 點、M2 前置）

| # | 步驟 | 預期 | 實際 | 截圖 | 嚴重度 |
|---|------|------|------|------|--------|
| 1 | flutter analyze | 0 issues | No issues found | — | — |
| 2 | flutter test | 全部通過 | 369 通過、1 略過、0 失敗（第 1 輪的 4 個失敗在 Mac 上也已消失） | — | — |
| 3 | M2 iPhone 模擬器逐卡驗證 | — | 尚未執行（Mac 還在裝 Xcode） | — | — |

## 2026-10-18 M3（commit 79070ad）

| 卡 | 結果 | 原因 | 截圖 |
|----|------|------|------|
| #291（問題回報 #294） | 通過 | Mac 上 flutter analyze：No issues found；flutter test：369 通過、1 略過、0 失敗（在 cfb76db 跑；之後到 79070ad 沒有改到 app/）。這張卡只改測試，不需要模擬器操作 | — |

## 2026-10-19 M6（commit d0bc371）— analyze／test 不通過（請 Windows 開成問題回報，Mac 還沒有 API 金鑰）

Mac 環境：Flutter 3.47.7、Dart 3.13.5。Windows 回報 analyze 無 error、372 全過，但 Mac 上：

| # | 步驟 | 預期 | 實際 | 截圖 | 嚴重度 |
|---|------|------|------|------|--------|
| 1 | flutter analyze | 無 error | 6 issues，其中 4 個 **error** 都在 `test/screens_test.dart:552`：`addTearDown(() => (sync.status, sync.hasError) = saved);`（refutable_pattern_in_irrefutable_context、constant_pattern_with_non_constant_expression）。另有 warning：`test/simulation/learner_view_simulation.dart:61` `_leakedNull` 未使用；info：`test/simulation/card226_review_audit.dart:16` 多餘的 `dart:typed_data` import | — | 中 |
| 2 | flutter test | 全部通過 | 347 通過、1 略過、1 失敗：`test/screens_test.dart` 整個檔編譯失敗（同一行 552：Not a constant expression），所以裡面的測試都沒跑。這行是 d0bc371 新增的（問題回報 #306 的測試）。Dart 的 pattern assignment 只能指派給區域變數，不能指派給 `sync.status` 這種屬性；建議改成 `addTearDown(() { sync.status = saved.$1; sync.hasError = saved.$2; });` | — | 中 |
| 3 | M6 卡 #227、#296、#228 iPhone 模擬器驗證 | — | 尚未執行（Mac 還在裝 Xcode） | — | — |

## 2026-10-19 M7（commit d9a6eb8）— analyze／test 重跑

| # | 步驟 | 預期 | 實際 | 截圖 | 嚴重度 |
|---|------|------|------|------|--------|
| 1 | flutter analyze | 無 error | 0 error、0 warning、1 info（`test/simulation/card226_review_audit.dart:16` 多餘的 `dart:typed_data` import）。M6 的 `screens_test.dart:552` 編譯錯誤已修好 | — | 低 |
| 2 | flutter test | 全部通過 | 374 通過、1 略過、0 失敗 | — | — |
| 3 | M7 卡 #297、#300、#301 iPhone 模擬器驗證 | — | 尚未執行（Mac 還在裝 Xcode） | — | — |
