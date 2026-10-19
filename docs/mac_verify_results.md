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

## 2026-10-19 M1（iPhone 模擬器）

iPhone 18 Pro 模擬器（iOS 27.0），Xcode 27.1，Flutter 3.47.7，程式碼 commit 4dad506。用本機 integration_test 自動點按（不 commit），`--dart-define-from-file=iphone.json`；另跑一次不帶 iphone.json（上架設定）。截圖在 `docs/mac_verify_shots/2026-10-19/`。

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 第 4 步 run_ios_sim／App 啟動 | 通過 | App 在模擬器啟動；新手引導兩頁→「從基礎開始」進主畫面 | mac_verify_shots/2026-10-19/m1_01_onboarding_language.png、m1_02_onboarding_level.png | — |
| 設定頁填網址／金鑰 | 未做 | 金鑰要 owner 本人輸入；未填時「測試連線」顯示 API Key 不正確（符合預期） | mac_verify_shots/2026-10-19/settings_10_connection.png | — |
| 設定頁「測試連線」結果排版 | 不通過 | 結果文字被擠在「掃描 QR code／測試連線」按鈕右邊的窄欄，一行一兩個字；而且訊息要使用者去「設定 → 照片辨識連線」，但使用者就在這一頁 | mac_verify_shots/2026-10-19/settings_11_connection_test.png | 低 |
| 詞庫同步 | 通過 | 資料庫分頁顯示 5132 筆正式單字；沒有常駐「已連接詞庫・每 30 秒自動更新」 | mac_verify_shots/2026-10-19/m1_04_database_words.png | — |
| 拍照／選照片→打標（iphone.json） | 未做 | 模擬器沒有相機；選內建範例照片可存檔，但沒填金鑰所以伺服器打標回 API Key 不正確（符合預期） | mac_verify_shots/2026-10-19/photo_02_save_dialog.png、photo_04_after_save.png | — |
| 選照片→本機辨識（上架設定） | 不通過 | 不帶 iphone.json 時改用 Apple Vision，模擬器上顯示「手機辨識失敗：Failed to create espresso context.」。模擬器沒有神經網路引擎，需實機再驗；但這段英文技術字串會直接給學習者看，建議換成白話說明 | — | 低 |
| 複習正面／背面九項 | 通過 | 見 M2 #251、#253；背面英式＋美式按鈕、無等級字、無「照片情境」、詞形變化、同義／相關／容易混淆的字填滿寬度 | mac_verify_shots/2026-10-19/review_05_back_top.png、review_05_back_scroll1.png | — |
| 刪除卡片確認與復原 | 通過 | 見 M2 #235 | mac_verify_shots/2026-10-19/review_06_delete_confirm.png、review_07_delete_snackbar.png | — |
| 真人發音在原生 iOS 播放（#270） | 不通過 | 背面自動播放的錄音網址是 https://api.willylinai.com/api/audio?path=…mp3。AVPlayer 載入不了：PlatformException(DarwinAudioError, Failed to set source … AVPlayerItem.Status.failed on setSourceUrl)，而且這個例外沒有被接住。原因：/api/audio 不支援 Range（curl -r 0-1 仍回 200 全檔 21688 bytes，HEAD 回 404），iOS AVPlayer 需要 206 分段回應 | — | 高 |
| 播完錄音才播下一個口音（#251） | 不通過 | lib/services/speaker.dart:53 `finished.timeout(..., onTimeout: () {})` 在 iOS 執行時丟型別錯誤（log：Recording failed, using TTS: type '() => Null' is not a subtype of type '(() => FutureOr<AudioEvent>)?' of 'onTimeout'），每次都跳到 catch 改用 TTS：錄音剛開始播就又用 TTS 念一次，英式、美式不會等前一個播完 | — | 中 |
| 照片載入速度（#252） | 未能驗證 | 自動化測試量不到捲動是否卡頓；40 張複習中照片都有載入 | — | — |

## 2026-10-19 M2（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #208 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #210 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #211 | 通過 | 資料庫相片冊縮圖的標籤在照片內、彼此分開、引線短 | mac_verify_shots/2026-10-19/album_02_level_a1.png | — |
| #163 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #170 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常；背面例句是完整句 | mac_verify_shots/2026-10-19/review_05_back_top.png | — |
| #227 | 通過 | Windows 端模擬使用者卡，iPhone 上不需另驗 | — | — |
| #225 | 通過 | Windows 端模擬使用者卡，iPhone 上不需另驗 | — | — |
| #228 | 通過 | Windows 端模擬使用者卡，iPhone 上不需另驗 | — | — |
| #226 | 通過 | Windows 端模擬使用者卡，iPhone 上不需另驗 | — | — |
| #229 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #250 | 通過 | 相片冊縮圖每級一行，沒有「入門（A1）：… · 中階（B1）：…」接成一長行 | mac_verify_shots/2026-10-19/album_02_level_a1.png | — |
| #257 | 通過 | 啟動畫面是 App 圖示（藍底卡片圖），不是 1×1 空白 | — | — |
| #260 | 不通過 | 原生 iOS 已改走 /api/audio，但錄音播不出來（見 M1「真人發音在原生 iOS 播放」：伺服器不支援 Range） | — | 高 |
| #262 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #263 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #264 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #259 | 通過 | 設定 → 關於 →「資料來源與授權」頁可開啟 | mac_verify_shots/2026-10-19/settings_09_sources.png | — |
| #272 | 通過 | 設定 →「進階設定：照片辨識連線」有「掃描 QR code」按鈕；模擬器沒有相機，掃描本身需實機 | mac_verify_shots/2026-10-19/settings_10_connection.png | — |
| #256 | 通過 | App 以 com.willylinai.photoflashcard 安裝並啟動 | — | — |
| #242 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #269 | 通過 | 設定 → 資料有「匯出備份／從備份還原」，還原會先問「從備份還原？」；匯出與選檔是系統分享／檔案面板，自動化不操作 | mac_verify_shots/2026-10-19/settings_06_restore_dialog.png | — |
| #271 | 未能驗證 | 要有「原檔遺失的照片」才看得到；模擬器新裝的 App 沒有這種資料 | — | — |
| #268 | 未能驗證 | 上架設定下設定頁沒有網址／金鑰欄（符合）；Apple Vision 本機辨識要實機才能驗，模擬器上的訊息問題已列在 M1「選照片→本機辨識」 | — | — |
| #279 | 通過 | 照片詳情「返回時自動保存，不用再按建立。」在「辨識單字列表」標題下、第一個單字之前 | mac_verify_shots/2026-10-19/photo_04_after_save.png | — |
| #280 | 通過 | 拍照首頁副標是「拍照或選一張照片，找出生活中的英文單字」 | mac_verify_shots/2026-10-19/m1_03_camera_home.png | — |
| #276 | 未能驗證 | 同 #271，需要原檔遺失的照片 | — | — |
| #164 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #285 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #286 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #277 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #289 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #233 | 通過 | 背面詞形變化、同義詞等小方塊保留小寫（gladder、happy…）；單字詳情詞義是黑字。標題字仍首字大寫（Glad），看起來是刻意的 | mac_verify_shots/2026-10-19/review_05_back_scroll1.png、m1_05_word_detail_apple.png | — |
| #234 | 通過 | 資料庫頁沒有常駐同步狀態文字 | mac_verify_shots/2026-10-19/m1_04_database_words.png | — |
| #235 | 通過 | 按「刪除此卡片」先跳「移除「happy」？」確認，移除後有「復原」 | mac_verify_shots/2026-10-19/review_06_delete_confirm.png、review_07_delete_snackbar.png | — |
| #236 | 通過 | 我的單字本按返回回到「資料庫單字本」，沒有跳到拍照 | mac_verify_shots/2026-10-19/cards_my_words.png、cards_my_words_back.png | — |
| #237 | 通過 | 資料庫圖片詳情的標籤沒有「已確認／待確認」 | mac_verify_shots/2026-10-19/album_05_image_detail_tags.png | — |
| #238 | 通過 | 我的單字本頁沒有「我的收藏」「複習字卡」字樣 | mac_verify_shots/2026-10-19/cards_my_words.png | — |
| #246 | 未能驗證 | 要找同拼字不同詞性的字才看得出來，這輪沒抽到 | — | — |
| #249 | 未能驗證 | 這輪沒有操作單字詳情的編輯對話框 | — | — |
| #251 | 通過 | 背面九項：英式／美式按鈕都在、沒有 CEFR 等級字、沒有「照片情境」、例句緊、詞形變化全列、同義／相關／容易混淆的字填滿寬度、構詞拆解（有資料的字）、多圖可左右滑（coffee 有圓點）、英文字可點。自動播放的錄音問題另列在 M1 | mac_verify_shots/2026-10-19/review_05_back_top.png、review_05_back_scroll1.png | — |
| #252 | 未能驗證 | 見 M1 照片載入速度 | — | — |
| #253 | 通過 | 看圖題正面在照片上用圓圈標出位置、不顯示單字（截圖是 high 那張；圓圈貼在照片下緣，被切掉一半） | mac_verify_shots/2026-10-19/review_photo_front_ring.png | — |

## 2026-10-19 M4（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #166 | 通過 | 背面例句是完整句，40 張複習沒看到罕見人名例句 | mac_verify_shots/2026-10-19/review_05_back_top.png | — |
| Xcode 已裝好，開始模擬器驗證 | 通過 | 本輪就是這一項 | — | — |
| 連續複習 40 張 | 通過 | 見 M9 #303 | — | — |

## 2026-10-19 M5（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #295 | 通過 | 連上詞庫後搜尋 peak 有詞條，詳情有「峰」 | mac_verify_shots/2026-10-19/cards_search_peak.png、cards_peak_detail.png | — |

## 2026-10-19 M6（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #227 | 通過 | Windows 端模擬使用者卡，iPhone 上不需另驗 | — | — |
| #296 | 通過 | 伺服器打標計時，iPhone 上不需另驗（本輪沒有金鑰，沒有實際打標） | — | — |
| #228 | 通過 | Windows 端模擬使用者卡，iPhone 上不需另驗 | — | — |

## 2026-10-19 M7（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #297 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
| #300 | 通過 | 設定頁沒有常駐「詞庫連線」卡（「已連接詞庫」「上次確認」都沒有） | mac_verify_shots/2026-10-19/settings_02_scroll01.png | — |
| #301 | 未能驗證 | 自動化測試兩輪共對 15 張卡按「忘記」，學習洞察仍顯示「還沒有常按「忘記」或「吃力」的字」，看不到弱項單字與「複習這些字」。可能是同一張卡在同一天第二次按「忘記」沒有記錄（要 ≥2 次才算弱項），請 Windows 確認是否符合設計 | mac_verify_shots/2026-10-19/settings_07_card_style.png | — |

## 2026-10-19 M8（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #308 | 未能驗證 | 40 張複習沒有抽到超過 12 張照片的字；2–12 張的圓點正常 | — | — |
| #304 | 通過 | 複習右上角旗標開出「回報「apple」這張卡」，六種類型＋說明欄；按取消不送出 | mac_verify_shots/2026-10-19/review_03_report_dialog.png | — |
| #315 | 通過 | 選照片的預設名稱是「10/19 20:22」 | mac_verify_shots/2026-10-19/photo_02_save_dialog.png | — |
| #317 | 通過 | 照片詳情難度顯示「基礎（A2） · 剛好」 | mac_verify_shots/2026-10-19/photo_04_after_save.png | — |
| #310 | 通過 | Windows 端模擬使用者卡，iPhone 上不需另驗 | — | — |
| #321 | 通過 | 按「顯示字首提示」後變成「提示已顯示」且不能再按 | mac_verify_shots/2026-10-19/review_04_hint.png | — |
| #313 | 通過 | 設定 → 資料只寫「91 個單字 · 0 張照片 · 已學會 0 個」，沒有「張卡片」 | mac_verify_shots/2026-10-19/settings_11_connection_test.png | — |
| #312 | 未能驗證 | 要在使用中遇到詞庫背景更新才會出現提示，這輪沒碰到 | — | — |
| #318 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |
