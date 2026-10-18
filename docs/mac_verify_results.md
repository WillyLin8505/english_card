# Mac / iPhone 模擬器驗證結果

每輪一節，照 `docs/mac_verify.md` 的步驟記錄。

---

## 2026-10-18 · 第 1 輪（Claude Code，雲端 Linux container）

**驗證的版本**：`ae1d773`（main，`Snapshot for Mac verification: issue swarm, owner
decisions, app features in progress`）。本機與 `origin/main` 同步，沒有改任何 App 程式碼。

### ⚠ 重要：這一輪沒有做到 iPhone 模擬器驗證

這個 session 不是跑在 Mac 上，是跑在**雲端的 Linux container**（Ubuntu 24.04、
x86_64），不是 owner 的 Mac（`/Users/willylin/vibe_coding flash card`）。

iPhone 模擬器只能在 macOS 上跑：`app/run_ios_sim.sh` 需要 `open -a Simulator`、
`xcrun simctl`、Xcode、CocoaPods，這些在 Linux 上**不存在也無法安裝**（Xcode 只有
macOS 版）。確認過：`xcrun`、`xcodebuild`、`pod` 都找不到。

所以 `mac_verify.md` 的**步驟 4、5 完全沒有執行**，也沒有任何截圖
（`docs/mac_verify_shots/` 還是空的）。以下這些都**還沒被驗證過**，不要當成已通過：

- 首次啟動與新手引導、設定頁填網址／金鑰、QR code（卡 #280）
- 詞庫同步、拍照／選照片 → 打標（含 Cloudflare 100 秒切斷）
- 複習正面標位置、背面各項（英式＋美式發音、A2 等級字、例句間距、詞形變化、
  同義／相關／近音／拼字相近排版、構詞字塊、圖片左右滑、點字連到詳情、刪除確認與復原）
- 學習洞察 #277、備份還原 #278、原圖遺失改用同字其他圖 #279、隱私權 #268、資料來源 #269
- 照片載入速度 #252、音檔與詞庫圖片在原生 iOS 載入 #270

**要跑這一輪，必須在 owner 的 Mac 上開一個 Claude Code session。**

### 這一輪實際做到的部分

能在 Linux 上做的只有與平台無關的靜態檢查（步驟 1～3）：

1. **步驟 1 git pull**：已在 `ae1d773`，與 `origin/main` 一致。
2. **步驟 2 環境**：在 scratchpad 裝了 Flutter 3.47.7 stable（Dart 3.13.5）後跑
   `flutter doctor`。Linux 上**根本沒有 iOS 那一欄**（Flutter 只在 macOS 顯示
   Xcode toolchain），這本身就是上面那件事的佐證。另外缺 Android SDK、Chrome、
   GTK3，對本輪的 analyze／test 沒有影響。
   注意：Mac 上的 Flutter 版本可能不同，下一輪在 Mac 上要重跑一次 `flutter doctor`。
3. **步驟 3 `flutter analyze` + `flutter test`**：有跑完，結果如下。

#### `flutter analyze`：4 件（1 warning、3 info），明細見下面問題 4。

#### `flutter test`：351 passed、**4 failed**、1 skipped

4 個失敗的測試**都是 `ae1d773` 這個 commit 造成的迴歸**。在它前一個 commit
`e4638fe` 上，這 4 個測試全部通過（在 scratchpad 另外 clone 一份驗證過）。
`ae1d773` 的 commit message 自己寫了「some cards were still running at this
commit」，所以很可能是 WIP 沒收尾。

---

### 問題清單

#### 問題 1：無法在非 Mac 環境做 iPhone 模擬器驗證（流程問題，不是 App bug）

| 欄位 | 內容 |
| --- | --- |
| 日期 | 2026-10-18 |
| 步驟 | `docs/mac_verify.md` 步驟 4、5 |
| 預期 | 在 iPhone 模擬器跑 App，照學習者流程走一遍並截圖 |
| 實際 | session 在雲端 Linux container，沒有 macOS／Xcode／CocoaPods，模擬器無法啟動；步驟 4、5 全部未執行 |
| 截圖 | 無 |
| 嚴重度 | 高（這輪驗證的主要目的沒有達成） |

建議：這張卡只能派給 owner Mac 上的 session；派工時先確認 agent 跑在 macOS 上。

#### 問題 2：設定頁變高，`測試連線` 按鈕被推出測試視窗，3 個測試失敗

| 欄位 | 內容 |
| --- | --- |
| 日期 | 2026-10-18 |
| 步驟 | `cd app && flutter test test/screens_test.dart` |
| 預期 | `設定 測試連線: connected` / `wrong key / not running` / `service not running` 三個測試通過 |
| 實際 | 三個都失敗，`find.text('✓ 已連線 · qwen3-vl')` 等狀態文字找不到（0 widgets） |
| 截圖 | 無（widget test） |
| 嚴重度 | 中 |

根本原因已查到：測試用 402×1600 的畫面，而 `ae1d773` 在設定頁加了「學習洞察」
整個區塊（複習次數／CEFR 等級變化／弱項單字）與「掃描 QR code」按鈕，把
`測試連線` 按鈕推到 **y=1614**，超出 1600 的測試畫面。Flutter 的 `tap()` 只印
warning 不會讓測試失敗：

```
Warning: A call to tap() with finder "Found 1 widget with text "測試連線""
derived an Offset (Offset(290.2, 1614.0)) that would not hit test on the
specified widget. Indeed, Offset(290.2, 1614.0) is outside the bounds of the
root of the render tree, Size(402.0, 1600.0).
```

所以 `_testConnection()` 從來沒被呼叫（按鈕還顯示「測試連線」而不是「測試中…」，
狀態文字 `_check` 還是 null），最後的 `expect` 才失敗。
`test/screens_test.dart` 的 `check()` 裡雖然有 `ensureVisible`，但在這個尺寸下沒有
把按鈕捲進畫面。

影響：**「測試連線」這個功能現在等於沒有測試在守**。按鈕本身在真機上應該還是能按
（真機畫面可捲動），但這點要等 Mac 那輪才能確認。

#### 問題 3：資料庫相片冊的程度說明文字被拆成兩個 Text，測試失敗

| 欄位 | 內容 |
| --- | --- |
| 日期 | 2026-10-18 |
| 步驟 | `cd app && flutter test test/album_level_test.dart` |
| 預期 | `資料庫相片冊 the picker filters tiles and the opened picture` 通過 |
| 實際 | 失敗：找不到 `入門（A1）：apple · 蘋果 · 中階（B1）：cluster · 串`（0 widgets） |
| 截圖 | 無（widget test） |
| 嚴重度 | 低（看起來只是測試沒跟上 UI 改動） |

查到的實際畫面：同一張圖的說明被拆成**兩個獨立的 Text**
`入門（A1）：apple · 蘋果` 與 `中階（B1）：cluster · 串`，測試還在找合併成一行的
舊字串。`ae1d773` 動到 `app/lib/widgets/database_tag_sections.dart`（-8 行），
但沒有同步更新這個測試。

另外確認過 `進階（C1）：cluster · 串` 是對的，那是測試資料裡第 2 張圖
(`id: 10`) 自己帶 `'cefr': 'C1'`，不是程度過濾的 bug。

#### 問題 4：`flutter analyze` 一個 warning 與三個 info

| 欄位 | 內容 |
| --- | --- |
| 日期 | 2026-10-18 |
| 步驟 | `cd app && flutter analyze` |
| 預期 | 沒有 warning |
| 實際 | 1 warning + 3 info（見下） |
| 截圖 | 無 |
| 嚴重度 | 低 |

```
warning • Unused import: '../models/vocabulary_profile.dart'
        • lib/screens/settings_screen.dart:7:8 • unused_import
   info • Statements in an if should be enclosed in a block
        • test/card38_redirect_scope_test.dart:28:57 • curly_braces_in_flow_control_structures
   info • Don't invoke 'print' in production code
        • test/card38_redirect_scope_test.dart:57:5 • avoid_print
   info • Unnecessary use of string interpolation
        • test/simulation/settings_simulation.dart:67:25 • unnecessary_string_interpolations
```

那個 unused import 同樣來自 `ae1d773` 對 `settings_screen.dart` 的改動（+115 行）。

---

### 下一輪要注意

- 這份報告**不能取代** Mac 上的模擬器驗證；步驟 4、5 還是全新的。
- 上 Mac 之前先把問題 2、3 的測試迴歸修掉，否則 `flutter test` 一直是紅的，
  模擬器那輪會分不清是新問題還是舊的。
