# Mac / iPhone 模擬器驗證結果

照 `docs/mac_verify.md` 做的驗證紀錄。每一輪往下追加。

---

## 2026-10-18 · 第 1 輪（雲端 Linux session，非 Mac）

執行者：Claude Code（cloud session，分支 `claude/serene-mccarthy-8dysdu`）
Repo commit：`ae1d773`（與 `origin/main` 同一個 commit，已是最新）
工具版本：Flutter 3.47.7 stable · Dart 3.13.5（repo 沒有釘版本，Mac 上 `brew install --cask flutter` 也會拿到同一個 stable）

### 這一輪的範圍（重要）

這個 session 跑在**雲端 Linux 容器（Ubuntu 24.04）**，不是 Mac。
`docs/mac_verify.md` 的步驟 4、5（`./run_ios_sim.sh`、iPhone 模擬器實機走查與截圖）**無法執行**，
因為 `run_ios_sim.sh` 需要 macOS 專屬的 `open -a Simulator` 與 `xcrun simctl`，
而 `flutter doctor` 在 Linux 上連 Xcode / iOS 這一段都不會出現。

所以：
- **已完成**：步驟 1（取最新 code）、步驟 2（`flutter doctor`）、步驟 3（`flutter analyze` + `flutter test`）。
- **未完成**：步驟 4、5 全部 — 新手引導、設定頁、詞庫同步、拍照打標、複習正反面、學習洞察（#277）、
  備份還原（#278）、原圖遺失（#279）、隱私權（#268）、資料來源（#269）、照片載入速度（#252）、
  原生 iOS 音檔與圖片（#270），**一項都沒有在 iPhone 上驗證過**。
- **沒有截圖**（`docs/mac_verify_shots/` 這一輪是空的）。

下面 1–5 是這一輪真的驗到的東西。**步驟 5 的清單還是要在 Mac 上跑一次**，這一輪不能當成替代。

看板 127.0.0.1:5173 與 8770 從這個容器連不到（預期如此，看板只在 Windows 上），所以這一輪沒有進板。

---

### 問題 1：`設定` → `測試連線` 三個測試都失敗（按鈕被擠出測試畫面）

| 項目 | 內容 |
|---|---|
| 步驟 | `cd app && flutter test test/screens_test.dart` |
| 預期 | `設定 測試連線: connected` / `wrong key / not running` / `service not running` 三個測試通過 |
| 實際 | 三個都失敗 |
| 嚴重度 | **中** |
| 截圖 | 無（無法跑模擬器） |

`screens_test.dart` 用 `size: const Size(402, 1600)` 開設定頁，展開「進階設定：照片辨識連線」後，
`測試連線` 這顆按鈕算出來的位置是 `Offset(290.2, 1614.0)`，已經掉在測試畫面 `Size(402.0, 1600.0)` 外面 14px：

```
Warning: A call to tap() with finder "Found 1 widget with text "測試連線"" derived an
Offset (Offset(290.2, 1614.0)) that would not hit test on the specified widget.
Indeed, Offset(290.2, 1614.0) is outside the bounds of the root of the render tree, Size(402.0, 1600.0).
```

`tap()` 因此沒點到任何東西，接著 `expect(find.text(expected), findsOneWidget)`
在 `screens_test.dart:446` 找不到 `✓ 已連線 · qwen3-vl` / `✕ 服務正常，但 API Key 不正確` /
`✕ 連不到 AI 辨識服務（http://127.0.0.1:8765/tag），請確認服務已啟動` 而失敗。

測試**已經有**呼叫 `await tester.ensureVisible(find.text('測試連線'))`（`screens_test.dart:443`），
但捲動沒有生效（位置仍是 1614）。兩種可能，**需要 Mac / Windows 端確認是哪一種**：

- **只是測試壞了**：`ensureVisible` 後少一次 `pumpAndSettle()`，捲動動畫還沒跑完就 `tap()`。
  真機上設定頁可以捲動，使用者不會遇到。
- **是 App 的問題**：設定頁最近長高了（`settings_screen.dart` 在 `ae1d773` 這個 snapshot 有改），
  把按鈕推出可視範圍。若那一段其實不在 `Scrollable` 裡，真機上在小螢幕 iPhone（SE 之類）就會點不到。

後者會直接打到 `mac_verify.md` 步驟 4「打標金鑰由 owner 在 App 的設定輸入」這條路，
所以 **Mac 那一輪請優先在 iPhone SE 尺寸的模擬器上，確認設定頁真的捲得到「測試連線」**。

---

### 問題 2：`album_level_test` —「資料庫相片冊」縮圖說明文字對不上

| 項目 | 內容 |
|---|---|
| 步驟 | `cd app && flutter test test/album_level_test.dart` |
| 預期 | `資料庫相片冊 the picker filters tiles and the opened picture` 通過 |
| 實際 | 失敗於 `album_level_test.dart:148` |
| 嚴重度 | **低**（看起來是測試沒跟上實作） |
| 截圖 | 無 |

```
Expected: exactly one matching candidate
  Actual: _TextWidgetFinder:<Found 0 widgets with text "入門（A1）：apple · 蘋果 · 中階（B1）：cluster · 串": []>
```

測試期望**一個** Text 同時包含 A1 與 B1 兩組，中間用 ` · ` 接起來。
但現在 `lib/widgets/database_tag_sections.dart` 在 compact 模式下是**每個等級各自一個 Text**
（`_compactTagLabels()` 回傳 `'$head：${words.join('、')}'`，在 build 的 `if (widget.compact)` 分支逐組 `out.add(Text(...))`），
所以不會有任何一個 widget 同時帶兩組字。

同一個測試後面那句 `find.text('中階（B1）：cluster · 串')`（篩成 B1 之後）格式是對得上的 —
失敗只發生在「沒篩等級、兩組並存」的第一個 expect。

從學習者角度看，一個等級一行其實不算壞，所以**比較可能是測試的期望字串過期**，
而不是 UI 退步。但這要 Mac 上實際看一眼縮圖說明才能確定，這一輪沒看到畫面。

---

### 問題 3：`flutter analyze` 有一個 warning

| 項目 | 內容 |
|---|---|
| 步驟 | `cd app && flutter analyze` |
| 預期 | 沒有 warning |
| 實際 | `lib/screens/settings_screen.dart:7:8` · `unused_import`：`'../models/vocabulary_profile.dart'` 沒用到 |
| 嚴重度 | **低** |

（刪掉這行 import 就好，但照 `mac_verify.md` 的規則這一輪不動 App 程式碼。）

---

### 問題 4：`flutter analyze` 三個 info（都在測試／模擬輔助檔）

| 檔案 | 規則 |
|---|---|
| `test/card38_redirect_scope_test.dart:28:57` | `curly_braces_in_flow_control_structures` |
| `test/card38_redirect_scope_test.dart:57:5` | `avoid_print` |
| `test/simulation/settings_simulation.dart:67:25` | `unnecessary_string_interpolations` |

嚴重度 **低**。

---

### 問題 5：`mac_verify.md` 這張卡被派給了非 Mac 的 agent

| 項目 | 內容 |
|---|---|
| 預期 | 這張卡只派給 Mac 上的 session |
| 實際 | 被雲端 Linux session 接走，步驟 4、5（也就是這張卡的重點）做不到 |
| 嚴重度 | **資訊**（流程問題，不是 App 問題） |

建議在 `lexicon/tools/agent_capabilities.json` 或 dispatch 設定裡，把這張卡限定給 Mac 的 agent，
或在 `mac_verify.md` 開頭加一句「非 macOS 環境請直接回報不適用」，省掉一輪空轉。

---

### 順手確認（沒問題，記錄備查）

- **後端 tunnel 是通的**（2026-10-18 從雲端測）：
  - `GET https://api.willylinai.com/api/lexicon` → **401**，符合 `e4638fe` 加的 public-host 金鑰防護。
  - `GET https://api.willylinai.com/tag` → **404**，正常：`tagger/tagging_server.py` 只在 `do_POST` 處理 `/tag`。
  - 兩個都在 ~1.2 秒內回應。沒有讀或送任何金鑰。
- **測試整體**：`flutter test` → **351 passed · 1 skipped · 4 failed**（失敗的 4 個就是問題 1、2）。
  跳過的那個是 `card38_redirect_scope_test.dart`，條件是 `../lexicon/logs/agents/card123.resume.pack.json` 不存在，屬預期。
- **`flutter pub get` 乾淨**：沒有改到 `pubspec.lock`（28 個套件有新版但受 constraint 限制，與這一輪無關）。
- **`flutter doctor`**：Flutter 本身 ✓、Network resources ✓；Android SDK / Chrome / Linux GTK ✗ —
  都是這個 Linux 容器沒裝，與 iOS 驗證無關。
