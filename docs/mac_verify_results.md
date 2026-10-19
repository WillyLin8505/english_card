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

## 2026-10-19 M9（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #303 | 通過 | 連續複習 40 張：不同單字 37 個，重複的只有 sun、cup、apple 各 2 次（這 3 張刻意按「忘記」，會再出現一次），沒有一直出同幾個字 | mac_verify_shots/2026-10-19/review_08_summary.png | — |

## 2026-10-19 M10（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #328 | 通過 | 設定 →「匯出到 Anki」開出「匯出到 Anki：選擇範圍」；選了之後是系統分享面板，自動化不操作 | mac_verify_shots/2026-10-19/settings_05_anki_dialog.png | — |

## 2026-10-19 M11（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #332 | 未能驗證 | 要先加入卡片集才有卡片集圖片可長按，這輪沒有安裝卡片集 | — | — |
| #307 | 通過 | 相片冊選 A1 搜 cluster：顯示「搜尋的字 cluster 在 進階（C1）」和「切到 C1」 | mac_verify_shots/2026-10-19/album_03_search_cluster_a1.png | — |

## 2026-10-19 M12（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #327 | 通過 | 存照片對話框有「要找什麼：找物品／找文字／兩者都找」；文字辨識本身需實機相機或照片 | mac_verify_shots/2026-10-19/photo_02_save_dialog.png | — |
| #326 | 通過 | 照片詳情有「自己加字」，提示寫「點標籤可改字或刪除」 | mac_verify_shots/2026-10-19/photo_04_after_save.png | — |
| #331 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |

## 2026-10-19 M13（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #333 | 通過 | 後端擷取鎖的修正，iPhone 上不需另驗（錄音播放問題另列在 M1） | — | — |

## 2026-10-19 M14（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #334 | 通過 | App 目前不開放法語，iPhone 上看不到這張卡的效果 | — | — |
| #337 | 通過 | 不需 iPhone 操作（詞庫資料／後端），App 端相關畫面正常 | — | — |

## 2026-10-19 M15（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #341 | 通過 | 連上詞庫後搜尋 ought 有詞條。附註：App 內建詞庫包沒有 ought，伺服器慢或離線時（第 6 輪 /api/lexicon 20 秒還沒回）搜不到 | mac_verify_shots/2026-10-19/cards_search_ought.png | — |

## 2026-10-19 M16（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #322 | 通過 | 設定 →「瀏覽並下載卡片集」列出「基礎 3000 字」等卡片集。附註：第 3 輪 /api/decks 曾短暫回 404，之後恢復 | mac_verify_shots/2026-10-19/decks_01_list.png | — |

## 2026-10-19 M17（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #343 | 通過 | 後端 Wikimedia 429 處理，iPhone 上不需另驗 | — | — |

## 2026-10-19 M18（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #228 | 通過 | Windows 端模擬使用者卡，iPhone 上不需另驗 | — | — |

## 2026-10-19 M19（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #348 | 通過 | 設定「卡片樣式」四種（經典／A 簡潔留白／B 圖片沉浸／C 活潑遊戲）都有 apple 小預覽 | mac_verify_shots/2026-10-19/settings_07_card_style.png | — |

## 2026-10-19 M20（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #350 | 通過 | App 目前不開放法語，iPhone 上看不到這張卡的效果 | — | — |

## 2026-10-19 M21（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #353 | 不通過 | mac_inbox.md 的 M21 標題變成問號亂碼（「????????87 ?????????????????」），看不出要驗什麼；M21 標題行也重複了兩次。請 mac_sync 寫入時用 UTF-8 | — | 低 |

## 2026-10-19 M22（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #352 | 通過 | App 目前不開放法語，iPhone 上看不到這張卡的效果 | — | — |

## 2026-10-19 M23（iPhone 模擬器）

iPhone 18 Pro 模擬器（iOS 27.0），新安裝；跑兩次：帶 iphone.json（開發）與不帶（上架設定，選「找文字」）。

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| analyze／test（commit 9530f99） | 通過 | flutter analyze 0 error、0 warning；flutter test 441 通過、2 略過 | — | — |
| #360 | 通過 | 不需 iPhone 操作（後端／資料） | — | — |
| #320 | 通過 | 對同一字每次都按「忘記」，20 張內 coffee 出現 3 次、butter knife 出現 3 次，沒有超過 3 次 | mac_verify_shots/2026-10-19/m23_320_again_cap.png | — |
| #309 預設樣式 B | 通過 | 新安裝後複習背面是 B 圖片沉浸（單字疊在照片上） | mac_verify_shots/2026-10-19/m23_308_counter_bright.png | — |
| #309 B 樣式沒有照片的字 | 不通過 | B 圖片沉浸遇到沒有照片的字（out），標題字「Out」是白字放在淺色背景上，幾乎看不見；音標 /ˈäʊt/ 也被切掉一半。沒有照片時標題字要改深色或給深色底 | mac_verify_shots/2026-10-19/m23_309_style_b_no_photo.png | 中 |
| #367 | 通過 | App 目前不開放法語，iPhone 上看不到這張卡的效果 | — | — |
| #373 | 通過 | 與 #371 重複已標 wontfix；/api/audio 的 Range 問題要看 #371，這輪 iPhone 上背面錄音仍走伺服器網址 | — | — |
| #375 | 通過 | 「測試連線」結果「✕ API Key 不正確」改在按鈕列下方整行顯示，沒有「（設定 → 照片辨識連線）」 | mac_verify_shots/2026-10-19/m23_375_connection_result.png | — |
| #339 | 通過 | App 目前不開放法語，iPhone 上看不到這張卡的效果 | — | — |
| #377 | 通過 | 上架設定在模擬器選照片：畫面沒有 espresso 等英文技術字串（這次顯示「這張照片沒有新的單字」） | mac_verify_shots/2026-10-19/m23_377_store_photo.png | — |
| #379 | 通過 | 選「找文字」存照片後畫面沒有英文平台錯誤字串 | mac_verify_shots/2026-10-19/m23_377_store_photo.png | — |
| speaker.dart onTimeout（上一輪 M1 #251） | 通過 | 在 iPhone 模擬器用真的 DeviceSpeaker 播內建錄音：say() 回傳 true、約 1 秒播完，沒有再改用 TTS | — | — |
| #308 超過 12 張照片的計數 | 通過 | bright 有 46 張照片，背面顯示「第 23 / 46 張 · 左右滑動換照片」 | mac_verify_shots/2026-10-19/m23_308_counter_bright.png | — |
| 詞庫：out 的同義詞 | 不通過 | out（副詞，出）背面同義詞列出 knocked out、forbidden、prohibited、taboo，是別的義項（禁忌、被擊倒）的同義詞，跟卡片的「出」不符 | mac_verify_shots/2026-10-19/m23_309_style_b_no_photo.png | 低 |
| 詞庫：bright 的主要義項 | 不通過 | bright 卡片背面中文意思是動詞「照亮」（Often followed by up: to cast light on…），A1 學習者要的是形容詞「明亮的」 | mac_verify_shots/2026-10-19/m23_308_counter_bright.png | 低 |

## 2026-10-19 M24（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| analyze／test（commit fb73166） | 通過 | flutter analyze 0 error、0 warning；flutter test 441 通過、2 略過 | — | — |
| #362 | 通過 | 不需 iPhone 操作（後端／資料） | — | — |

## 2026-10-20 M25（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| analyze／test（commit 3fd8a4f） | 通過 | flutter analyze 0 error、0 warning；flutter test 442 通過、2 略過 | — | — |
| #380 | 通過 | 從 Mac 經公開網址抓 /api/lexicon 兩次都回 200，用時 34 秒、31 秒（沒有被 Cloudflare 切斷）；重啟後第一次的情況要在 Windows 重啟才量得到 | — | — |
| iPhone 首次同步詞庫的下載量 | 不通過 | /api/lexicon 一次回 237,872,038 bytes（約 238 MB），iPhone 用行動網路第一次同步就要下載這麼多；建議分片、壓縮（gzip）或只送差異 | — | 低 |
| #382 | 通過 | 後端圖片來源順序調整，iPhone 上不需另驗 | — | — |
| #309 B 樣式沒有照片的字（上一輪 M23 不通過） | 通過 | 新安裝（預設 B 圖片沉浸）複習沒有照片的 sunshine、drop、butter knife：標題字改成深色（亮度 0.01），清楚可讀，音標完整 | mac_verify_shots/2026-10-19/m25_309_no_photo_sunshine.png、m25_309_no_photo_butter_knife.png | — |
| 詞庫：sunshine 的主要義項 | 不通過 | sunshine（A1）卡片背面中文意思是形容詞「公開開放」（Open to and permitting public access…，陽光法案的意思），學習者要的是名詞「陽光」；例句卻是「You're my sunshine.」，義項和例句對不上 | mac_verify_shots/2026-10-19/m25_309_no_photo_sunshine.png | 低 |

## 2026-10-20 M26（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #370 | 通過 | App 目前不開放法語，iPhone 上看不到這張卡的效果；這次沒有改到 app/ | — | — |
| #388 | 通過 | #383 是 Mac 的通過列被自動誤開成問題回報（那列的說明用到會被當成缺陷的字）。之後通過列的說明會避開那些字 | — | — |

## 2026-10-20 M27（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #389 | 通過 | M23 #375 那列本來就是通過（測試連線結果已在按鈕下方整行顯示），因為說明裡引用了結果訊息的符號被自動誤開成問題回報 #382。這次沒有改到 app/ | mac_verify_shots/2026-10-19/m23_375_connection_result.png | — |

## 2026-10-20 M28（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| analyze／test（commit 751d1c5） | 通過 | flutter analyze 0 error、0 warning；flutter test 443 通過、2 略過 | — | — |
| #392 | 通過 | 從 Mac 帶 Accept-Encoding: gzip 抓 /api/lexicon：回 content-encoding gzip、有 ETag，實際傳輸 34,096,632 bytes（約 34 MB，15 秒）。App 用 http.Client（iOS 上會自動要 gzip），所以 M25 那列的 238 MB 是未壓縮大小，是 Mac 量法的問題 | — | — |

## 2026-10-20 M29（iPhone 模擬器）

iPhone 18 Pro 模擬器新安裝、帶 iphone.json，等伺服器詞庫同步進 App 後讀每個詞性的 CEFR 與中文意思。

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #381 moment、train、top | 通過 | 新安裝、同步伺服器詞庫後：train 名詞變成「火車、列車」（不再是「拖裾」），moment 名詞是「刻；瞬間」，top 名詞「頂」、形容詞「最高的」（B1） | mac_verify_shots/2026-10-19/m29_381_moment_detail.png | — |
| #381 冷門詞性被標成 A1 | 不通過 | 同步後的詞庫仍把冷門詞性標成 A1，這些就會變成 A1 字卡：bright 動詞 A1「照亮」、sunshine 形容詞 A1「公開開放」、out 名詞 A1「出路；脫身之計；（棒球）出局」、out 動詞 A1「驅逐；趕出…」、out 感嘆詞 A1「滾」。入門學習者看到「滾」很不妥。建議冷門詞性的 CEFR 不要沿用主詞性的 A1 | — | 中 |
| #381 其他觀察 | 不通過 | top 動詞（A2）中文是「蓋、加以頂」，讀起來不通順；out 介系詞（A2）沒有中文意思 | — | 低 |

## 2026-10-20 M-ASK1（iPhone 模擬器重驗 #385、#387）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 詞庫版本 | 通過 | iPhone 18 Pro 模擬器新安裝、帶 iphone.json；內建包 e62d1540… 同步成伺服器版 b09db387…（最後同步成功 2026-10-20 06:53），資料庫顯示 9188 筆正式單字 | — | — |
| #385 bright 詞性 | 通過 | 從資料庫搜 bright 列出兩列：第一列「亮、明、明亮／形容詞 · 入門（A1）」，第二列「照亮／動詞 · 罕見用法」。學習者照順序點第一列就是形容詞。Mac 之前看到動詞卡，是因為自動化測試直接照詞庫目錄順序加字（M23），這次又點了最後一列，選到的是罕見用法那一列；不是 App 的問題，#385 可以關 | mac_verify_shots/2026-10-19/ask1_bright_search.png、ask1_bright_detail.png | — |
| #387 sunshine 詞性 | 通過 | 搜 sunshine 第一列「陽光／名詞 · 入門（A1）」，第二列「公開開放／形容詞 · 罕見用法」。原因同上，是 Mac 測試挑到罕見用法那列，#387 可以關 | mac_verify_shots/2026-10-19/ask1_sunshine_search.png | — |
| 更正 M29「冷門詞性被標成 A1」那列 | 通過 | 那列也是同一個測試挑字的原因造成：詞庫目錄裡這些詞性的 cefr 欄位仍是 A1，但資料庫畫面已標成「罕見用法」並排在後面，學習者照正常流程不會先拿到。除非拍照辨識或卡片集等其他流程會用罕見用法的詞位建卡，否則那張問題回報也可以關 | — | — |

## 2026-10-20 M-ASK2（重現「選照片辨識閃退」）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 模擬器重現：相簿選 6 張照片去辨識 | 未重現 | iPhone 18 Pro 模擬器（iOS 27.0），commit bb73d03，新安裝。相簿加入 6 張測試照：4032×3024／3024×4032 的 JPEG 與 HEIC、8064×6048（48MP）的 JPEG 與 HEIC。從 App「選擇照片」的最近照片（19 張，第一次讀 14 秒）依序選這 6 張→存到相片冊→辨識；上架設定（本機 Apple Vision）與 iphone.json（伺服器）各跑一輪，12 次都沒有閃退、沒有 Flutter 例外，系統 log 沒有 jetsam。注意：模擬器上 Apple Vision 一開始就放棄（CSU: Failed to create espresso context），所以 VNClassifyImageRequest 真正分析大圖那一段只有實機才會跑到 | mac_verify_shots/2026-10-19/ask2_picker_library.png、ask2_result_48mp.png | — |
| 可能的閃退原因：詞庫快取太大 | 不通過 | App 沙盒裡 Documents/dictionary_cache_v1.hive 有 261,298,439 bytes（約 261 MB）。10/19 Mac 第一次跑 integration test 時就在讀這個 Hive 檔時 Out of Memory（BinaryReaderImpl.readString ← FrameIoHelper.framesFromFile）。實機記憶體上限比模擬器低，啟動或同步時把整個詞庫讀進記憶體，再加上辨識一張大照片，很可能被系統因記憶體不足砍掉（看起來就是閃退）。建議詞庫改成分批讀或用檔案索引，不要整包載入 | — | 高 |
| 可能的閃退原因：相簿原圖沒有縮小 | 不通過 | lib/screens/photo_picker_screen.dart:49 最近照片用 entity.originBytes，拿到的是原始檔（HEIC 或 48MP 原圖，解碼後可達 190 MB 以上）直接存檔、顯示、送 Apple Vision；「從相簿選擇」那條路有 maxWidth: 2048，最近照片這條沒有。建議用 entity.thumbnailDataWithSize 或先縮到長邊 2048 再處理 | — | 中 |
| 最近照片第一次讀取很慢 | 不通過 | 相簿只有 19 張，第一次打開「選擇照片」要 14 秒才讀完最近照片（之後 1 秒）；期間只看到「正在讀取最近照片…」 | — | 低 |
| 請 owner 提供實機 log | 未做 | 需要實機才知道真正原因。請把 iPhone 接到 Mac 跑 `flutter run -d <iPhone>`（我這邊可以收 log），或在 iPhone「設定 → 隱私權與安全性 → 分析與改進 → 分析資料」找 Runner-*.ips 或 JetsamEvent-*.ips 傳過來 | — | — |
