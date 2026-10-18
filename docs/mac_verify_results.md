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

## 2026-10-18 雲端 Linux session（非 Mac，commit `ffa3aea` 合併後重跑）

執行者：Claude Code 雲端 session（Ubuntu 24.04 容器，**沒有 macOS／Xcode**），Flutter 3.47.7 · Dart 3.13.5。
這個 session 接到「照 `docs/mac_verify.md` 做一輪 iPhone 模擬器驗證」，但環境跑不了 iOS 模擬器
（`run_ios_sim.sh` 需要 `open -a Simulator` 與 `xcrun simctl`），所以**步驟 4、5 一項都沒做到**。
以下只有在 Linux 上做得到的部分，以及一個 Mac 端還沒碰到的新問題。

| # | 步驟 | 預期 | 實際 | 嚴重度 |
|---|------|------|------|--------|
| 1 | flutter analyze | 0 issues | No issues found（與 Mac 端一致） | — |
| 2 | flutter test | 全部通過 | **369 通過、1 略過、0 失敗**（與 Mac 端一致） | — |
| 3 | flutter build web | 編譯成功 | **編不過**，見下 | 中 |
| 4 | 4./5. iPhone 模擬器 | — | 未執行（這台沒有 macOS） | — |

### 問題：`flutter build web` 編不過 — `run_web.bat` 這條開發路線是壞的

```
lib/services/photo_intake.dart:45:13:
Error: The integer literal 0xcbf29ce484222325 can't be represented exactly in JavaScript.
lib/services/photo_intake.dart:47:39:
Error: The integer literal 0xFFFFFFFFFFFFFFFF can't be represented exactly in JavaScript.
```

`hashBytes()` 的 64-bit FNV-1a 常數在 dart2js 下無法表示（JS 的 number 是 double）。
在 `ffa3aea` 上仍然如此。**原生 iOS／Android 不受影響**（Dart native 有真正的 64-bit int），
只有 web 編不過，所以 repo 裡的 `app/run_web.bat` 現在跑不起來。

修的方向（這個 session 沒有改 App 程式碼）：改 32-bit FNV-1a、改用 `BigInt`，
或把 `hashBytes` 拆成 web／native 兩個實作。注意換演算法會改變既有照片指紋，
要顧 `findDuplicate()` 對舊資料的相容性。

### 補充

- 第 1 輪（`ae1d773`）在這台看到的 4 個測試失敗（`screens_test` 測試連線 ×3、`album_level_test` ×1）
  與 1 個 analyze warning，**在 `ffa3aea` 上都已經修掉**，與 Mac 端「369 通過、0 失敗」的紀錄一致。
  這幾項不需要再追。
- 後端 tunnel 通：`/api/lexicon` → 401（金鑰防護正常）、`/health` → 401、`/tag` → 404（只收 POST，正常）。
  沒有讀或送任何金鑰。
- 因為看不到模擬器，另外用 **Flutter web + Chromium 390×844** 抓了 UI 截圖放在 `docs/mac_verify_shots/`
  （檔名有 `web`，是在暫時改掉上述 hash 常數後編出來的，該暫改已還原、沒有進 commit）。
  **這不能取代步驟 5**：無頭瀏覽器沒有相機、相片庫、QR 掃描、TTS、音檔，詞庫也被 CORS 擋住，
  所以拍照→打標整條流程與 #252 / #270 / #277 / #278 / #279 / #268 / #269 都還沒驗到。
  截圖中「測試連線」顯示「連不到 AI 辨識服務」是瀏覽器 CORS，不是 App 的問題。
- 流程建議：這張卡被派給了非 Mac 的 agent，重點步驟做不到；建議在 dispatch 設定裡限定只派給 Mac。
