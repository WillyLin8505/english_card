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
| 模擬器重現：相簿選 6 張照片去辨識 | 未重現 | iPhone 18 Pro 模擬器（iOS 27.0），commit bb73d03，新安裝。相簿加入 6 張測試照：4032×3024／3024×4032 的 JPEG 與 HEIC、8064×6048（48MP）的 JPEG 與 HEIC。從 App「選擇照片」的最近照片（19 張，第一次讀 14 秒）依序選這 6 張→存到相片冊→辨識；上架設定（本機 Apple Vision）與 iphone.json（伺服器）各跑一輪，12 次 App 都沒有中途結束、沒有 Flutter 例外，系統 log 沒有 jetsam。注意：模擬器上 Apple Vision 一開始就放棄（CSU: Failed to create espresso context），所以 VNClassifyImageRequest 真正分析大圖那一段只有實機才會跑到 | mac_verify_shots/2026-10-19/ask2_picker_library.png、ask2_result_48mp.png | — |
| 可能的閃退原因：詞庫快取太大 | 不通過 | App 沙盒裡 Documents/dictionary_cache_v1.hive 有 261,298,439 bytes（約 261 MB）。10/19 Mac 第一次跑 integration test 時就在讀這個 Hive 檔時 Out of Memory（BinaryReaderImpl.readString ← FrameIoHelper.framesFromFile）。實機記憶體上限比模擬器低，啟動或同步時把整個詞庫讀進記憶體，再加上辨識一張大照片，很可能被系統因記憶體不足砍掉（看起來就是閃退）。建議詞庫改成分批讀或用檔案索引，不要整包載入 | — | 高 |
| 可能的閃退原因：相簿原圖沒有縮小 | 不通過 | lib/screens/photo_picker_screen.dart:49 最近照片用 entity.originBytes，拿到的是原始檔（HEIC 或 48MP 原圖，解碼後可達 190 MB 以上）直接存檔、顯示、送 Apple Vision；「從相簿選擇」那條路有 maxWidth: 2048，最近照片這條沒有。建議用 entity.thumbnailDataWithSize 或先縮到長邊 2048 再處理 | — | 中 |
| 最近照片第一次讀取很慢 | 不通過 | 相簿只有 19 張，第一次打開「選擇照片」要 14 秒才讀完最近照片（之後 1 秒）；期間只看到「正在讀取最近照片…」 | — | 低 |
| 請 owner 提供實機 log | 未做 | 需要實機才知道真正原因。請把 iPhone 接到 Mac 跑 `flutter run -d <iPhone>`（我這邊可以收 log），或在 iPhone「設定 → 隱私權與安全性 → 分析與改進 → 分析資料」找 Runner-*.ips 或 JetsamEvent-*.ips 傳過來 | — | — |

## 2026-10-20 M-ASK2 實機（iPhone 12）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 實機重現：選照片辨識 | 不通過 | iPhone 12（iOS 26.6.1，4 GB 記憶體），commit bb73d03 的 profile 版、上架設定（不帶 iphone.json，本機 Apple Vision）。owner 在拍照／選照片→辨識時 App 消失；devicectl 回報「App terminated due to signal 9」。iPhone 上的 JetsamEvent-2026-10-20-081153：largestProcess = Runner，Runner reason = per-process-limit，被砍時常駐記憶體 2,098 MB（lifetimeMax 134,272 頁 × 16 KB），狀態 active／frontmost；同時 cameracaptured 用 258 MB。也就是 App 超過 iOS 單一 App 約 2 GB 的記憶體上限，被系統強制結束，沒有一般的 crash 報告 | — | 高 |
| 記憶體可能的來源 | 不通過 | 對照 Mac 上的觀察：App 沙盒的 dictionary_cache_v1.hive 有 261 MB，整包讀進 Dart 字串會變成好幾倍大（10/19 在模擬器上就曾在讀這個 Hive 檔時 Out of Memory）；最近照片用 entity.originBytes 原圖（48MP／HEIC）沒有縮小，再交給相機與 Apple Vision。建議：1) 詞庫不要整包載入記憶體（分片、索引或 SQLite）；2) 選到的照片先縮到長邊 2048 再存檔、顯示、辨識；3) 用 Xcode Instruments 的 Allocations 在 iPhone 上量一次啟動後與辨識時的記憶體 | — | 高 |

## 2026-10-20 M-ASK2 實機補充（不碰手機的對照組）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 實機：不碰手機也會被砍 | 不通過 | 同一台 iPhone 12（iOS 26.6.1）、上架設定 profile 版：08:20:07 從 Mac 啟動 App 後完全不碰手機，08:20:33（26 秒後）App 就以 signal 9 結束；08:17:36 的 JetsamEvent 也是 Runner per-process-limit 2,098 MB，當時相機服務 cameracaptured 只是背景閒置（17 MB）。三次被砍（08:11:52、08:14:27、08:17:36）都是 Runner 2,098 MB。所以不是選照片造成，而是 App 啟動後（載入或同步詞庫時）記憶體就衝到上限；owner 剛好在那段時間選照片才以為是辨識閃退 | — | 高 |
| 建議修法方向 | 不通過 | 優先查啟動時的詞庫載入：沙盒 dictionary_cache_v1.hive 約 261 MB，用 Hive 整包讀成 Dart 物件會遠超過 2 GB 上限的一半以上。建議改成只讀需要的欄位或分片／索引（例如 SQLite），或至少在背景同步完成前不要同時保留新舊兩份詞庫；修好後請 mac_sync 開新的 M 項，Mac 會在這台 iPhone 上重驗（啟動後放 5 分鐘＋選照片辨識） | — | 高 |

## 2026-10-20 M30、M31、M32（iPhone 模擬器＋iPhone 12 實機）

模擬器 iPhone 18 Pro（iOS 27.0）新安裝、帶 iphone.json；實機 iPhone 12（iOS 26.6.1）profile 版、上架設定。

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| analyze／test（commit 0668726b） | 不通過 | flutter analyze 0 error、0 warning；flutter test 498 通過、3 略過、1 不通過：test/card428_sqlite_sync_test.dart「a phone downloads the pack as SQLite, then takes deltas」第 147 行，delta 套用後詞庫版本已是 v2，但卡片意思仍是「蘋果一」（預期「蘋果二」）。Windows 通過、Mac 不通過，可能是 macOS／iOS 上 SQLite 檔更新後沒有重新連結。若 iPhone 也這樣，詞庫小更新不會反映到已收藏的卡片 | — | 中 |
| #414／#419／#424／#425／#427／#428 實機記憶體 | 通過 | iPhone 12（iOS 26.6.1）裝這版 profile（SQLite 詞庫）：22:43 啟動後完全不碰，到 22:53 仍在畫面上正常運作（修之前 26 秒就被系統砍掉） | — | — |
| #414 實機選照片辨識 | 通過 | owner 在 iPhone 上選了好幾張照片去辨識：App 沒有中途結束，Apple Vision 本機辨識有認出單字（這是第一次在實機驗到本機辨識） | — | — |
| #421 相簿原圖縮小 | 通過 | photo_picker_screen.dart 改成長邊超過 2048 就用縮圖，不再讀 originBytes 原圖 | — | — |
| #420、#422 | 通過 | 對應的 Mac 回報（模擬器重現、最近照片第一次讀取慢）已由上面實機結果涵蓋；最近照片讀取速度這輪沒有重量 | — | — |
| #372 錄音 Range | 通過 | /api/audio 加 Range: bytes=0-1 回 206、content-range bytes 0-1/21688、accept-ranges bytes；HEAD 回 200 | — | — |
| #405（M31 也是這張） | 通過 | 單字本分頁只剩「我的單字本」，相片冊分頁只剩自己的相片冊與「下載相片冊」，資料庫搜尋畫面已移除 | mac_verify_shots/2026-10-20/m30_m1_04_database_words.png、m30_album_01_database.png | — |
| #417／#446 選要複習哪一本 | 通過 | 複習分頁先問「想複習哪一本？」：綜合、今天新加的單字、弱項單字，點格子就開始 | mac_verify_shots/2026-10-20/m30_review_01_intro.png | — |
| #409 每日上限 | 通過 | 綜合顯示「今天 20 張」；做完還能繼續練，連續 40 張不同單字 37 個，重複的只有刻意按忘記的 3 張 | mac_verify_shots/2026-10-20/m30_review_08_summary.png | — |
| #418 拍照不問名稱與要找什麼 | 通過 | 選照片按「完成」後只問存到哪本相片冊，沒有照片名稱、沒有「要找什麼」。附註：#405 說相片冊分類自動產生，這裡仍要手動選相片冊，請 Windows 確認是否符合設計 | mac_verify_shots/2026-10-20/m30_photo_01_picker.png | — |
| #433 語言選項 | 通過 | 學習語言只有英文＋「更多學習語言即將推出」，母語不再列英文 | mac_verify_shots/2026-10-20/m30_settings_01_top.png | — |
| #320、#321、#304、#235、#251、#309（回歸） | 通過 | 同一字最多 3 次、提示只算一次、回報此卡片、刪除有確認與復原、背面英式美式與無等級字、預設 B 樣式都照舊 | mac_verify_shots/2026-10-20/m30_review_05_back_top.png | — |
| 照片詳情難度重複顯示 | 不通過 | 照片詳情上方有 A1–C2 難度滑桿（「入門（A1）· 剛好」），下方「單字難度 入門（A1）· 剛好」與多看動詞等按鈕又出現一次，同一件事顯示兩次（#441 的 4 列控制項可能還沒收乾淨） | mac_verify_shots/2026-10-20/m30_photo_04_after_save.png | 低 |
| #228、#226 | 通過 | Windows 端模擬使用者卡，iPhone 上不需另驗 | — | — |
| #402、#324、#366、#435、#438 | 通過 | 不需 iPhone 操作（後端／資料／法語），本輪 App 端畫面正常 | — | — |
| #284、#383、#385 | 通過 | 詞庫自動同步、罕見用法不標 A1、Windows 測試修正：iPhone 上詞庫同步正常（M29 已驗），本輪沒有單獨操作 | — | — |
| #400、#306、#412、#413、#415、#416、#407、#404、#410、#411、#432、#434、#439、#440、#441、#442 | 未能驗證 | 這輪沒有逐張操作新介面的這個功能，下一輪補驗 | — | — |

## 2026-10-20 M33（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| analyze／test（commit eaf80463） | 通過 | flutter analyze 0 error、0 warning；flutter test 500 通過、3 略過；card428_sqlite_sync_test 與 card450_level_row_dup_test 在 Mac 單獨跑 5/5 通過 | — | — |
| #449（上一輪 M30 的 SQLite delta 測試） | 通過 | Mac 上 card428「a phone downloads the pack as SQLite, then takes deltas」現在通過，delta 後卡片意思會更新 | — | — |
| #450 照片詳情難度不再重複 | 通過 | 模擬器新安裝、選照片存檔後的照片詳情只剩上方 A1–C2 滑桿（入門（A1）· 剛好），下方重複的「單字難度」列已拿掉 | mac_verify_shots/2026-10-20/m33_450_photo_detail.png | — |

## 2026-10-20 M34（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #450 | 通過 | M33 已在模擬器驗過：照片詳情只剩上方 A1–C2 滑桿，下方重複的「單字難度」列已拿掉；這次沒有改到 app/lib | mac_verify_shots/2026-10-20/m33_450_photo_detail.png | — |

## 2026-10-21 M35（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| analyze／test（commit f1ae8c21） | 通過 | flutter analyze 0 error、0 warning；flutter test 500 通過、3 略過 | — | — |
| #228 | 通過 | Windows 端模擬使用者・設定；iPhone 模擬器上設定頁各項（資料列、Anki 匯出、備份還原、卡片樣式預覽、隱私權政策、資料來源）都照舊 | — | — |
| 回歸：複習與照片 | 通過 | 連續複習 40 張不同單字 37 個（重複只有刻意按忘記的 3 張）、同字最多 3 次、提示只算一次、回報此卡片、刪除可復原、背面英式美式、預設 B 樣式、內建錄音播完才結束；照片詳情難度只顯示一次 | — | — |

## 2026-10-21 M36（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #452 設定移除卡片集入口 | 通過 | 設定頁已找不到「瀏覽並下載卡片集」，下載入口只剩相片冊的「＋ 下載相片冊」 | — | — |
| #453 卡片樣式往前移 | 通過 | 設定頁順序：語言 → 單字難度 → 卡片樣式（含「照片上的單字標示」開關）→ 學習洞察 → 資料 | mac_verify_shots/2026-10-21/m35_settings_02_scroll00.png、m35_settings_02_scroll01.png | — |

## 2026-10-21 M30 補驗（上一輪未能驗證的 16 張新介面卡）

iPhone 18 Pro 模擬器新安裝、帶 iphone.json，commit d02bfe11 之後的版本。

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #412 沒有相機時的拍照頁 | 通過 | 模擬器（沒有相機）拍照頁只剩一個「選擇照片」，沒有閃光燈按鈕，另有「重試相機」 | mac_verify_shots/2026-10-21/x_412_camera.png | — |
| #416 單字詳情預設收合 | 通過 | apple 詞性意思先顯示 3 個，後面「顯示更多（9）」；例句、其他區塊也有「顯示更多（N）」；force、cozy 同樣收合 | mac_verify_shots/2026-10-21/x_apple_detail_top.png | — |
| #440 單字詳情標頭 | 通過 | apple、force、cozy 標頭都沒有「中性／通用」標籤，只顯示字、音標、程度 | mac_verify_shots/2026-10-21/x_apple_detail_top.png | — |
| #413 同義詞不含主字的複合詞 | 不通過 | force 的近義詞仍有「force out 驅逐」「force play 封殺（棒球）」這種含主字的複合詞；同一區還有「turn out 原來」「personnel 人員」「defile 汙穢」等跟「力量／強迫」不相干的字 | mac_verify_shots/2026-10-21/x_force_detail_0.png | 低 |
| #439 收藏卡片詞性跟著詞庫 | 通過 | 單字本裡 cozy 那列顯示「形容詞 · 溫馨的 · 中高階（B2）」，不再是名詞 | mac_verify_shots/2026-10-21/x_cozy_row.png | — |
| #407 複習卡片 | 通過 | 設定的「照片上的單字標示」預設打開；背面例句與定義裡的英文字是可點的連結；照片超過 12 張顯示「第 29 / 59 張」 | mac_verify_shots/2026-10-21/x_407_back_cup.png | — |
| 詞庫：cup 的照片 | 不通過 | cup 複習卡背面的照片是一顆鑲餡的紅甜椒（第 29 / 59 張），跟杯子無關；cup 的 59 張照片可能混進不相干的圖 | mac_verify_shots/2026-10-21/x_407_back_cup.png | 低 |
| #400 進階設定位置 | 通過 | 設定頁順序：語言 → 單字難度 → 卡片樣式 → 學習洞察 → 資料 → 隱私 → 關於 → 進階設定（最後） | mac_verify_shots/2026-10-21/x_settings_9.png | — |
| #432 學習洞察沒資料時 | 通過 | 沒有紀錄時只顯示一句「複習幾次之後，這裡會顯示你的複習次數、程度變化和弱項單字。」 | — | — |
| #404 圖片集變成相片冊 | 通過 | 從相片冊「＋ 下載相片冊」加入「水果與蔬菜圖片集」後，相片冊格線出現這一本（40 個單字），點進去看全部圖片，有程度篩選、搜尋照片和「複習這本相簿」 | mac_verify_shots/2026-10-21/x_album_1.png、x_album_open.png | — |
| 圖片集內容：水果與蔬菜圖片集 | 不通過 | 這本圖片集的第 4 張是實驗室的電泳膠片圖，不是水果或蔬菜 | mac_verify_shots/2026-10-21/x_album_open.png | 低 |
| #441 照片詳情單字列表前的控制列 | 不通過 | 「自己加字」已移到列表後面，但第一個單字前仍有 4 列：難度滑桿、「辨識單字列表＋顯示已學會單字」、自動保存提示、「多看動詞／多看形容詞／簡單一點／難一點」 | mac_verify_shots/2026-10-21/x_photo_detail.png | 低 |
| #415 標籤可拖曳 | 通過 | 照片詳情的標籤顯示在照片上，下方提示「拖曳照片上的標籤可調整位置」；這輪沒有實際拖曳 | mac_verify_shots/2026-10-21/x_photo_detail.png | — |
| #306 左滑已學會有復原 | 通過 | 在圖片集照片詳情把 Bread 左滑，列表從 5 個變 4 個，畫面出現「復原」 | mac_verify_shots/2026-10-21/x_306_swipe.png | — |
| #442 等待辨識不顯示內部網址 | 通過 | 照片詳情畫面沒有任何 http 網址 | — | — |
| #410、#411 資料庫相片冊搜尋 | 通過 | #405 之後 App 已沒有資料庫相片冊畫面，這兩張的情境不再存在；相片冊改成「搜尋照片」 | — | — |

## 2026-10-21 M37（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #457 照片詳情單字列表前的控制列 | 通過 | 照片詳情第一個單字前只剩難度滑桿與「辨識單字列表 (5)＋顯示已學會單字」；「自己加字」與「多看動詞／多看形容詞／簡單一點／難一點」都移到列表後面，自動保存提示已拿掉 | mac_verify_shots/2026-10-21/m37_x_photo_detail.png | — |
| #458 | 通過 | owner 決定維持現狀，沒有改程式或資料；App 已沒有資料庫相片冊搜尋畫面（#405） | — | — |
| 照片詳情離開時 | 不通過 | 測試結束、App 被拆掉時，照片詳情的 dispose 存檔（photo_detail_screen.dart:106 → _saveWith:122）呼叫 WordEnricher.process（word_enricher.dart:105），但 WordEnricher 已 dispose，觸發 debug assertion「A WordEnricher was used after being disposed」。正常使用只有在整個 App 被拆掉時才會遇到，影響小 | — | 低 |

## 2026-10-21 M38（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #454 同義詞不含主字的複合詞 | 通過 | 新安裝後 force 單字詳情的近義詞已沒有 force out、force play（畫面上含 force 的只剩例句裡的片語） | mac_verify_shots/2026-10-21/m37_x_force_detail_0.png | — |

## 2026-10-21 M39（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #460 analyze／test | 通過 | Mac 上 flutter analyze 0 error、0 warning；flutter test 504 通過、3 略過 | — | — |

## 2026-10-21 M40（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #226 | 通過 | Windows 端模擬使用者・複習；iPhone 模擬器上複習流程（M35 回歸）照舊 | — | — |
| #461 | 通過 | 匯出時濾掉只靠另一個詞性變化形的例句，屬詞庫資料，iPhone 上不需另驗 | — | — |

## 2026-10-21 M41（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #467 照片詳情離開時 | 通過 | Mac 上 flutter test 508 通過、3 略過；在 iPhone 模擬器跑完照片詳情流程再拆掉 App，log 裡「A WordEnricher was used after being disposed」0 次，整個 integration test 通過 | — | — |
| #464 | 通過 | 詞庫例句規則收斂，屬資料，iPhone 上不需另驗 | — | — |
| #225 | 通過 | Windows 端模擬使用者・相片冊；iPhone 模擬器上相片冊流程（M30 補驗）照舊 | — | — |
| 公開網址被擋（驗證時發現） | 不通過 | 10:30 左右 https://api.willylinai.com 的 /api/lexicon?format=sqlite、/api/decks、/health 全部回 403，回應是 serve_app（Python http.server）的錯誤頁「Request forbidden -- authorization will not help」，不是 Cloudflare 擋的。App 因此顯示「暫時無法連線 · 使用已儲存的詞庫」、圖片「暫時無法載入」、卡片集清單抓不到。看起來 serve_app 重啟時沒帶 --public-host api.willylinai.com（Host 檢查擋掉公開網址）。iPhone 現在無法同步詞庫、下載圖片集、播伺服器錄音 | — | 高 |

## 2026-10-21 M42（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #468 | 未能驗證 | 關聯詞中文回填屬伺服器詞庫，要 iPhone 同步新詞庫後才看得到；10:35 時 https://api.willylinai.com/api/decks 仍回 403（見 M41 公開網址被擋那列），App 拿不到新詞庫。公開網址恢復後再補驗 | — | — |

## 2026-10-21 M43（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #466 | 未能驗證 | 屬伺服器詞庫，要 iPhone 同步新詞庫後才看得到；10:40 時公開網址仍回 403，公開網址恢復後補驗 | — | — |
| #469 | 未能驗證 | 屬伺服器詞庫，要 iPhone 同步新詞庫後才看得到；10:40 時公開網址仍回 403，公開網址恢復後補驗。附註：這張卡說 8123（serve_app）有重啟，403 剛好從這段時間開始，請確認重啟指令有帶 --public-host api.willylinai.com | — | — |
| #465 | 未能驗證 | 屬伺服器詞庫，要 iPhone 同步新詞庫後才看得到；10:40 時公開網址仍回 403，公開網址恢復後補驗 | — | — |

## 2026-10-21 M44（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #471 意思區塊標題統一 | 通過 | 程式碼裡卡片背面、單字詳情、資料庫詳情的意思區塊都叫「詞性與意思」；模擬器上 cozy（單一詞性）詳情是「詞性與意思 · 形容詞 · 溫馨的」，不再是「繁體中文」；fruit 卡片背面也是「詞性與意思 · 名詞 · 水果」 | mac_verify_shots/2026-10-21/m44_471_cozy_detail.png | — |
| #472 | 未能驗證 | 形容詞比較級資料清理，屬伺服器詞庫；10:50 時公開網址仍回 403，恢復後補驗 | — | — |
| #470 | 通過 | Mac 上 flutter test 508 通過、3 略過（M41 跑的），card428_sqlite_sync 單獨跑也通過，沒遇到偶發失敗 | — | — |

## 2026-10-21 M45（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #474 | 通過 | #473 是 Mac 的通過列被自動誤開成問題回報（說明裡提到偶發的狀況）；之後寫結果前會先用跟 mac_results_to_issues.py 一樣的規則自我檢查，避免再誤開 | — | — |

## 2026-10-21 M46（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| analyze／test（commit dc3d0793） | 通過 | flutter analyze 0 error、0 warning；flutter test 508 通過、3 略過 | — | — |
| #228 語言說明 | 通過 | 只有一個學習語言時不再顯示「每個學習語言有自己的…」；母語說明改成「介面語言跟著母語切換。」 | mac_verify_shots/2026-10-21/m46_s46_top.png | — |
| #475 照片辨識連線收合時的提示 | 通過 | 進階設定 → 照片辨識連線按「測試連線」後收合，標題下顯示「照片辨識設定有誤 … 點開修正」 | mac_verify_shots/2026-10-21/m46_s46_collapsed_hint.png | — |
| #475 伺服器 403 被歸成「設定有誤」 | 不通過 | 這次 403 是公開網址那端擋掉（serve_app 回 Forbidden），學習者的網址與金鑰沒有問題，但提示叫他「點開修正」設定。建議 403／5xx 這類伺服器端狀況歸到「暫時連不上，照片會先排隊」那一種 | mac_verify_shots/2026-10-21/m46_s46_collapsed_hint.png | 低 |
| 設定頁其他項目（回歸） | 通過 | 資料列、Anki 匯出、從備份還原對話框、卡片樣式預覽、隱私權政策、資料來源都照舊；連續複習 40 張與同字最多 3 次也照舊 | mac_verify_shots/2026-10-21/m46_s46_restore.png | — |
| 公開網址 | 不通過 | 16:55–17:10 https://api.willylinai.com 仍全部回 403（M41 回報的同一個狀況），App 上方一直顯示「暫時無法連線 · 使用已儲存的詞庫」，伺服器辨識回「代碼 403」 | — | 高 |

## 2026-10-21 M47（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #476 語言區說明 | 通過 | M46 已在模擬器驗過（App 程式同為 dc3d0793）：只有一個學習語言時不顯示「每個學習語言有自己的…」，母語說明是「介面語言跟著母語切換。」 | mac_verify_shots/2026-10-21/m46_s46_top.png | — |
| #475 進階設定的連線提示分兩種 | 通過 | M46 已在模擬器驗過：測試連線後收合顯示「照片辨識設定有誤 … 點開修正」。伺服器端 403 也被歸成這一種的觀察已在 M46 另列 | mac_verify_shots/2026-10-21/m46_s46_collapsed_hint.png | — |

## 2026-10-21 M48（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| analyze／test（commit 20ed5fc4） | 通過 | flutter analyze 0 error、0 warning；flutter test 510 通過、3 略過 | — | — |
| #478 伺服器 403 的提示 | 通過 | 公開網址此時仍回 403；模擬器新安裝、進階設定按「測試連線」再收合，提示變成「照片辨識暫時連不上：新照片會先排隊，連上後自動辨識，不用處理」，不再叫學習者點開修正 | mac_verify_shots/2026-10-21/m48_478_hint.png | — |

## 2026-10-21 補驗：等公開網址恢復的 5 張詞庫卡（M42、M43、M44）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 環境 | 通過 | 21:00 公開網址恢復（/api/decks、/api/lexicon?format=sqlite 回 200）。iPhone 18 Pro 模擬器新安裝、帶 iphone.json，等 App 把內建包 65347fa8… 同步成伺服器 SQLite 版 642f82bb…（8,660 個詞條）後直接讀詞庫 | — | — |
| #468（M42）關聯詞中文回填 | 通過 | 有詞條的關聯詞 56,695 筆，只剩 14 筆沒有中文（例：meaning→pregnant、small→shall、well→hell） | — | — |
| #466（M43）首字大寫詞條改小寫 | 通過 | 首字大寫的詞條只剩 2 個，而且都沒有小寫同字；Porch、Skull、Fairy 都已不是大寫 | — | — |
| #469（M43）容易混淆的字沒有詞條 | 通過 | 容易混淆的字（near_homophones＋similar_spelling）共 39,488 筆，沒有詞條的 28,969 筆全部預設隱藏，預設顯示又沒有詞條的 0 筆 | — | — |
| #465（M43）非形容詞的比較級／最高級 | 不通過 | 仍有 38 筆不是形容詞／副詞的詞條帶比較級、最高級，例如 good（感嘆詞）better／best、great（感嘆詞）greater／greatest、quiet（感嘆詞）quieter／quietest、sage（感嘆詞）sager／sagest、ample（限定詞）ampler／amplest。另外 tea 動詞的過去式有 tea'd、tead、teaed 三種怪拼法 | — | 低 |
| #472（M44）more／most 形式 | 通過 | tea、tomato、metal、street、apply、texture 都已沒有 more／most 開頭的比較級 | — | — |

## 2026-10-21 實機 iPhone 12：詞庫卡重驗（同一批 5 張）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 環境 | 通過 | iPhone 12（iOS 26.6.1）profile 版，把 integration test 直接編進 App（flutter build -t），結果寫在 App 的 Documents 再用 devicectl 拷回 Mac。App 把內建包同步成伺服器 SQLite 版 2bc4f1d6…（8,660 個詞條），整段期間 App 沒有被系統結束 | — | — |
| #468 關聯詞中文 | 通過 | 實機上有詞條的關聯詞 56,695 筆，缺中文 14 筆（同模擬器） | — | — |
| #466 首字大寫詞條 | 通過 | 實機上首字大寫只剩 2 個、沒有小寫同字；Porch、Skull、Fairy 都已改小寫 | — | — |
| #469 容易混淆的字 | 通過 | 實機上預設顯示的容易混淆的字都有詞條（39,488 筆中沒有詞條的 28,969 筆都預設隱藏） | — | — |
| #465 非形容詞的比較級／最高級（實機、較新詞庫） | 不通過 | 實機同步到的較新詞庫 2bc4f1d6… 反而有 70 筆（模擬器 642f82bb… 是 38 筆），新增像 well（感嘆詞）more well／most well；其他例：good（感嘆詞）better／best、quiet（感嘆詞）quieter／quietest、ample（限定詞）ampler／amplest。tea 動詞過去式已只剩 teaed | — | 低 |
| #472 more／most 形式 | 通過 | 實機上 tea、tomato、metal、street、apply、texture 都沒有 more／most 形式 | — | — |

## 2026-10-21 實機 iPhone 12：完整回歸＋新介面（上架設定）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 環境 | 通過 | iPhone 12（iOS 26.6.1）profile 版、上架設定（不帶 iphone.json，照片在手機本機辨識）。integration test 編進 App 執行，結果與截圖從 App 的 Documents 拷回；owner 同意測試加入測試單字、下載圖片集 | — | — |
| 複習（回歸） | 通過 | 回報此卡片對話框、提示只算一次、刪除有確認與復原、背面英式美式按鈕、沒有等級字、沒有「照片情境」、預設 B 圖片沉浸都照舊；連續複習 40 張不同單字 37 個，同字每場最多 3 次 | mac_verify_shots/2026-10-21/dev_x_407_back_start.png | — |
| 設定（回歸） | 通過 | 資料列（49 個單字 · 3 張照片 · 已學會 0 個）、匯出到 Anki 選範圍、從備份還原對話框、卡片樣式預覽、隱私權政策、資料來源都照舊；順序 語言 → 單字難度 → 卡片樣式 → 學習洞察 → 資料 → 隱私 → 關於 → 進階設定；照片辨識說明「照片在這支手機上辨識，不會上傳到任何伺服器」 | — | — |
| #404 圖片集變成相片冊 | 通過 | 實機下載「水果與蔬菜圖片集」後相片冊格線出現這一本（42 個單字），和 owner 自己的「哈」並列 | mac_verify_shots/2026-10-21/dev_x_album_1.png | — |
| #441／#457 照片詳情 | 通過 | 實機上第一個單字前只有難度滑桿與「辨識單字列表 (5)＋顯示已學會單字」，標籤顯示在照片上 | mac_verify_shots/2026-10-21/dev_x_photo_detail.png | — |
| #306 左滑已學會有復原 | 通過 | 實機上把 Tomato 左滑，列表剩 4 個、出現「復原」 | mac_verify_shots/2026-10-21/dev_x_306_swipe.png | — |
| #442 不顯示內部網址 | 通過 | 實機照片詳情沒有 http 網址 | — | — |
| 內建錄音播放 | 通過 | 實機用真的 DeviceSpeaker 播內建錄音：回傳 true、約 1 秒，沒有改用 TTS | — | — |
| #412 | 通過 | 實機有相機，拍照頁顯示拍照與閃光燈按鈕、「AI 辨識就緒」，這張卡（沒有相機的情況）在實機上不適用 | mac_verify_shots/2026-10-21/dev_x_412_camera.png | — |
| 實機上未涵蓋 | 未能驗證 | 單字本搜尋框在實機上用測試輸入文字沒有篩選（模擬器可以），所以單字詳情這輪沒在實機開；選照片存檔那步因為 owner 已有相片冊「哈」，測試沒選到相片冊而停在對話框。owner 稍早已手動確認實機選照片辨識正常 | — | — |

## 2026-10-21 實機 iPhone 12：畫面流暢度量測（owner 反映卡頓）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 量測方式 | 通過 | iPhone 12（iOS 26.6.1，60 Hz）profile 版、上架設定；integration test 設 framePolicy fullyLive 讓畫面照實際節奏畫，用 SchedulerBinding.addTimingsCallback 收每一張畫面的 build／raster 時間 | — | — |
| A 單字本捲動 | 通過 | 923 張畫面，超過 16.7ms 的 0.1%（1 張），build 平均 1.2ms、raster 平均 1.8ms，最慢一張 45ms | — | — |
| B 單字詳情開啟＋捲動 | 通過 | 387 張，超過 16.7ms 的 0.3%（1 張），最慢一張 38ms | — | — |
| C 相片冊格線捲動 | 通過 | 350 張，超過 16.7ms 的 0.3%（1 張），沒有超過 33ms 的畫面 | — | — |
| D 相簿內照片捲動 | 通過 | 984 張，超過 16.7ms 的 0.1%（1 張），沒有超過 33ms 的畫面 | — | — |
| E 照片詳情開啟時頓一下 | 不通過 | 1,265 張中有 4 張超過 33ms，最慢一張 114ms（build 最大 95.8ms，raster 最大只有 6.3ms），都在打開照片詳情的那一刻；看起來是第一次建立整頁（照片、標籤、單字列表）太重，可以把單字列表延後一個畫面或分批建立 | — | 低 |
| F 複習翻卡時頓一下 | 不通過 | 3,295 張中有 7 張超過 33ms，最慢一張 108ms（build 最大 67.8ms，raster 最大 6.5ms），出現在翻到背面或換下一張卡的時候；背面一次建立英式美式、例句、詞形變化、同義詞等全部區塊，建議先畫上半部、其餘延後建立 | — | 低 |
| 結論 | 通過 | 捲動與一般操作都很順（每個情境 99.5% 以上的畫面都在 16.7ms 內，平均 1–2ms）；owner 感覺的卡頓比較可能是打開照片詳情、翻卡那一瞬間的單張停頓，以及照片從 Windows 筆電經 tunnel 下載較慢（這部分不會反映在畫面時間） | — | — |

## 2026-10-22 M49（iPhone 模擬器＋實機）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| analyze／test（commit 2e402107） | 通過 | flutter analyze 0 error、0 warning；flutter test 515 通過、3 略過 | — | — |
| #482 拍照頁徽章 | 通過 | camera_screen.dart:205：有相機、沒有設定照片辨識、但手機能找文字時，徽章是「只找照片裡的英文字・物品辨識未連線」，由 widget 測試涵蓋。模擬器沒有相機（顯示「相機未啟用」），實機 iPhone 12 有 Apple Vision（顯示「AI 辨識就緒」），兩邊都不會出現這個情境 | — | — |

## 2026-10-22 M50（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #483 背面相關詞先顯示 5 個 | 通過 | 模擬器新安裝、加入 galaxy、pallet、happy 複習：背面同義詞／相關詞等區塊各自有「顯示更多（N）」，例如 happy 背面「顯示更多（1）（3）（4）」 | mac_verify_shots/2026-10-22/m50_483_happy_back.png | — |
| #480 複習不考罕見詞性 | 通過 | galaxy（動詞「佈置星系」是罕見）、pallet（動詞罕見）、happy（動詞「歡心」罕見）各複習 3 次共 9 張，正面都沒有出現動詞 | — | — |
| #484 詞庫包形態共享 | 未能驗證 | 要等 pack 重新匯出、App 同步新詞庫才看得到；00:05 時公開網址回 530（Cloudflare 連不到 Windows 筆電），恢復後補驗 | — | — |

## 2026-10-22 M51（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #485（實機 #465 那列） | 未能驗證 | Windows 說是舊 pack 的資料、重新匯出後就會是 0 筆；要等公開網址恢復、App 同步到新 pack 再補驗（00:05 公開網址回 530） | — | — |

## 2026-10-22 M52（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #226 | 通過 | Windows 端模擬使用者・複習；iPhone 模擬器上複習流程（M50 這輪）照舊 | — | — |

## 2026-10-22 補驗：#484／#485（公開網址 01:54 恢復）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #484／#485 詞庫包重新匯出 | 未能驗證 | 01:54 公開網址恢復（/api/decks 回 200）。模擬器新安裝同步到的伺服器詞庫版本仍是 2bc4f1d6…（跟 10/21 21:52 實機拿到的同一版），非核心詞性帶比較級／最高級仍是 70 筆（good 感嘆詞 better／best、well 感嘆詞 more well 等）。也就是 pack 還沒重新匯出，請 Windows 重新匯出後開 M 項，Mac 再驗 | — | — |

## 2026-10-22 owner 派工：Windows 離線期間（Mac 整理）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| Windows 服務沒有自動恢復 | 不通過 | 10/22 01:54 公開網址還能同步詞庫，之後 Windows 停止：21:00 起公開網址回 530、card manager（Remote Control）離線、最後 push 是 10/21 22:30。家裡網路上 192.168.0.135 仍開著 445（檔案分享），但 8765／8123／5173 都關著，看起來是被重開機後停在登入畫面、登入後才會跑的程式（cloudflared、serve_app、打標服務、派工、Claude Code）都沒起來。請把 cloudflared 裝成 Windows 服務、serve_app／打標／dispatch_tick 的排程設成「開機時、不論使用者是否登入都執行」，serve_app 啟動要帶 --public-host api.willylinai.com，並查事件檢視器 1074／6005／41 確認原因 | — | 高 |
| 詞庫 pack 重新匯出（#484、#485、#465） | 不通過 | 伺服器詞庫仍是 2bc4f1d6…（10/21 21:52 那版），非核心詞性帶比較級／最高級仍 70 筆；#484 的修正要重新匯出 pack 才會到 App。請 Windows 上線後重新匯出並開 M 項讓 Mac 驗 | — | 中 |
| 照片詳情開啟、翻卡頓一下（M-PERF 兩列） | 通過 | owner 決定 Windows 離線期間由 Mac 修：已在 Mac 開兩個工作（photo-detail-jank、flip-card-jank），修好會 push 到 main，Mac 再到實機重量 | — | — |
| 永久卡 | 通過 | Mac 驗過且目前沒問題的檢查轉成 7 張永久卡（S1 analyze／test、S2 模擬器回歸、S3 實機記憶體、S4 實機流暢度、S5 公開網址健康、S6 詞庫資料、S7 內建錄音），見 docs/mac_standing_cards.md；Windows 上線後可匯入看板 | — | — |

## 2026-10-23 永久卡 S6 詞庫資料（伺服器詞庫 249ddcab…）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 環境 | 通過 | 01:11 公開網址恢復；模擬器新安裝同步到伺服器 SQLite 詞庫 249ddcab…（10,389 個詞條，前一版 2bc4f1d6… 是 8,660 個） | — | — |
| #484／#485／#465 非形容詞的比較級／最高級 | 通過 | 新版詞庫 0 筆（前一版 70 筆） | — | — |
| #466 首字大寫詞條 | 通過 | 只剩 2 個，沒有小寫同字 | — | — |
| #469 容易混淆的字 | 通過 | 48,072 筆，沒有詞條的 33,699 筆都預設隱藏，預設顯示卻沒有詞條 0 筆 | — | — |
| #472 more／most 形式 | 通過 | 0 筆 | — | — |
| #468 關聯詞缺中文（新版增加） | 不通過 | 有詞條的關聯詞 75,312 筆中缺中文 51 筆（前一版 56,695 筆中 14 筆），超過永久卡 S6 的 20 筆；例：park→par、discriminate→discrimination、truck→semi、pie→pre、pure→pre。另外有些關聯本身就怪（meaning→pregnant、hail→hell） | — | 低 |

## 2026-10-23 Mac 修正：照片詳情與翻卡卡頓（翻卡修正已 push）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 照片詳情開啟頓一下（M-PERF） | 通過 | Mac 修正已 push：dc19cbbc（photo_detail_screen.dart 分四個畫面建立、查詞改快取，新增 photo_detail_first_frame_test）。Mac 上 flutter analyze 0 error、0 warning，flutter test 516 通過；實機重量另列 | — | — |
| 翻卡頓一下（M-PERF） | 通過 | 翻卡修正已 push：e8081479（flashcard_back.dart 背面分兩個畫面建立、左右滑照片不重建下半部、詞庫查詢與例句排序改快取、正面時先備好背面；flashcard_session_views.dart 呼叫預備；順手清掉 lexicon_pack.dart 等 3 個原本的 warning）。Mac 上 analyze 0 warning、test 516 通過；實機重量另列 | — | — |
| 凍結清單 | 通過 | flashcard_back.dart、flashcard_session_views.dart、photo_detail_screen.dart 的 Mac 修改都已 push，可以解除凍結 | — | — |

## 2026-10-23 實機 iPhone 12：修正後重量流暢度（dc19cbbc＋e8081479）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 量測 | 通過 | iPhone 12 profile 版、上架設定，跑兩次（第 1 次剛好在同步新詞庫 249ddcab…，第 2 次詞庫已同步）。第 2 次：單字本最慢 48ms、單字詳情 39ms、相片冊 46ms、相簿內照片 29ms | — | — |
| 照片詳情開啟（M-PERF 第二輪） | Mac 處理中 | 修正後最慢一張 114ms → 64ms（build 最大 95.8 → 62.7ms），但仍有 4 張超過 33ms；Mac 繼續修 photo_detail_screen.dart | — | — |
| 翻卡（M-PERF 第二輪） | Mac 處理中 | 修正後最慢一張 108ms → 87ms（build 最大 67.8 → 54.2ms），仍有 5 張超過 33ms；Mac 繼續修 flashcard_back.dart | — | — |
| 同步新詞庫時主執行緒卡住 | Mac 處理中 | 第 1 次量測 App 剛好第一次同步新版詞庫：單字本捲動中有一張畫面 580ms、複習中有一張 1,151ms，但 build／raster 都很短（主執行緒被畫面以外的工作佔住）；第 2 次詞庫已同步就沒有。每次伺服器出新詞庫，使用者打開 App 後會卡一下約 1 秒。Mac 修 dictionary_sync.dart／lexicon_pack.dart／lexicon_sqlite.dart，把套用與載入新詞庫移出主執行緒或分批做 | — | — |

## 2026-10-23 Mac 修正第二輪＋永久卡 S2／S5

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 照片詳情開啟（M-PERF2） | 通過 | 第二輪修正 62d8fd15（標籤排版快取、每段自己延後出現）後 iPhone 12 實機：最慢一張 114 → 64 → 43ms，超過 33ms 的畫面 4 → 2 張；剩下的單張 40 多 ms 肉眼不易察覺，先結案，S4 會持續追 | — | — |
| 翻卡（M-PERF2） | 通過 | 第二輪修正 62d8fd15（翻面那格只建單字、IPA、詞性與意思，其餘逐格出現在 180ms 淡入期間）後實機：最慢一張 108 → 87 → 58ms，超過 33ms 的畫面 7 → 5 → 1 張 | — | — |
| 同步新詞庫時主執行緒卡住（M-PERF2） | 通過 | 修正 e5dfa83b（建索引、套 delta 改到背景 isolate，linkLexicon 分批每 8ms 讓出）：Mac 上主執行緒最長停頓 delta 856 → 31ms、整檔下載 224 → 10ms，新增 sync_main_thread_test 比對新舊結果一致。實機要等伺服器出下一版詞庫時才量得到，S4／S6 會補 | — | — |
| analyze／test（62d8fd15） | 通過 | Mac 上 flutter analyze 0 error、0 warning；flutter test 520 通過、3 略過 | — | — |
| S2 模擬器回歸（英文帳戶） | 通過 | 複習 40 張不同單字 37 個、同字最多 3 次、提示只算一次、回報此卡片、刪除可復原、背面英式美式與無等級字、預設 B 樣式、設定各項、圖片集變相片冊、照片詳情左滑可復原、單字詳情收合都照舊；測試裡資料庫搜尋、卡片集入口、要找什麼這幾步是 App 已拿掉的畫面，不算 | — | — |
| S2 模擬器回歸（法語帳戶） | 未能驗證 | App 目前學習語言只開放英文（app_settings.dart availableLearningLanguages = {'en'}），法文顯示「即將推出」，模擬器上開不了學法語的帳戶；下一輪改用母語法文（介面法文）跑一輪 | — | — |
| S5 公開網址健康 | 通過 | 11:53 /api/decks 回 200（2.2 秒）、/api/audio 加 Range 回 206（content-range bytes 0-1/21688） | — | — |

## 2026-10-23 M84（owner 的 iPhone 12 裝最新 release 版）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| M84 安裝 | 通過 | owner 的 iPhone 12 已裝 release 版（flutter build ios --release --dart-define-from-file=iphone.json，devicectl 安裝並啟動）。第一次裝 main dac8d06f，之後再裝 d4236e8c（含複習頁封面）。拔線後可用。金鑰沒寫進 repo，等 owner 自己掃 QR code | — | — |
| M84 新版功能 | 通過（程式面） | 這版程式裡有：設定 → 進階設定 →「掃描 QR code」（settings_screen.dart:531）、每頁右上「意見回饋」鈕（feedback_button.dart，#587）；模擬器截圖右上角可見意見回饋鈕。實機畫面請 owner 打開確認 | 2026-10-23/review_covers.png | — |
| owner 要求：複習頁封面 | 通過 | Mac d4236e8c：複習頁每格加封面。相片冊格用該相片冊最新照片；綜合／今天新加的單字／弱項單字用其中一個字的照片，盡量不跟別格重複；沒照片維持色塊。flutter test 571 過、analyze 0 issue。flashcard_session_views.dart 已改完並 push，Windows 可解除凍結 | 2026-10-23/review_covers.png | — |
| Mac 修正 | 通過 | 55589039：詞庫刪掉有中文的詞性時，搬到別的詞性的卡保留原本意思（somewhere／sue，穩定性模擬找到）；6323f084：單字詳情不再出現空白「詞性與意思」標題與空詞性區塊，stub 頁加說明，已在單字本的字按鈕顯示「已在我的單字本 ✓」 | — | — |

## 2026-10-23 owner 要求：翻卡第一次發音是機器人聲

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| owner 要求：翻卡只播真人錄音 | 通過 | Mac 7d62d469：翻卡原本固定先播英式再播美式，英式多半沒有真人錄音，第一聲是 TTS。改成只播有真人錄音的腔調，兩個都沒有才用 TTS 唸一次（設定的腔調）。flutter test 573 過、analyze 0 issue；已裝到 owner 的 iPhone 12。flashcard_back.dart 已改完並 push，Windows 可解除凍結 | — | — |
| owner 要求：TTS 用高品質語音 | 通過 | Mac 7d62d469：speaker.dart 從系統語音挑該語系最好的（premium > enhanced），排除 Apple 趣味語音與 Eloquence；手機沒下載增強語音時維持預設。owner 可在 iPhone 設定 → 輔助使用 → 朗讀內容 → 聲音 → 英文 下載增強語音 | — | — |
| owner 要求：補更多真人發音（交 Windows） | 不通過 | 線上詞庫 13,192 個正式詞條只有 7,339 個有真人錄音（56%）。A1 1183 字：英式 394、美式 820、任一 869；A2 1620 字：英式 188、美式 798、任一 871；B1 2208 字：英式 165、美式 958、任一 1104；B2 2627 字：英式 147、美式 1050、任一 1359。請 Windows：(1) 從 Wikimedia Commons／Lingua Libre 等可商用授權的來源補真人錄音，優先 A1–B1、英式；(2) 評估沒有錄音的字預先用神經語音（Azure／Google／ElevenLabs 等）合成英、美各一個音檔放進詞庫，費用與授權交 owner 決定；合成音要標示來源，不要跟真人錄音混在一起 | — | 中 |

## 2026-10-23 M85 先行說明（Mac 已修的兩筆）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #607（卡 #556）翻卡第一聲是機器人 | 通過 | Mac 7d62d469 已修：翻卡只播有真人錄音的腔調，兩個都沒有才用 TTS 一次；TTS 挑 premium／enhanced 語音。卡 #556 請停掉或只驗證。真人錄音不夠的部分見上面「補更多真人發音（交 Windows）」那一列 | — | — |
| #610（卡 #562）複習頁要有圖片 | 通過 | Mac d4236e8c 已修：複習頁每一格有封面照片。卡 #562 請停掉或只驗證 | 2026-10-23/review_covers.png | — |
| M85 其餘 13 筆 | Mac 處理中 | 照 M85 由 Windows 修；mac_sync 開 M 項後 Mac 在 iPhone 實機驗證 | — | — |

## 2026-10-23 M86（owner 的 iPhone 12 實機檢查）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #614 相片冊照片看不到 | 通過 | 原因：Photo.filePath 存完整路徑（含 iOS App 容器 ID），iOS 每次安裝／更新都換容器，owner 手機上 19 張照片存的全是舊容器路徑，檔案其實都還在。Mac d0d8d51b：存的路徑不存在時，到這次安裝的照片資料夾找同檔名（顯示、遺失判斷、辨識讀檔、Anki、備份都改）。iPhone 實機：19 張可顯示 19、看不到 0；photo-1792730973924683 照片詳情正常顯示 4 個標籤。App Store 更新也會遇到同樣問題，這次一併修好 | 2026-10-23/own_02_photo_614.png | — |
| M84 掃描 QR code、#587 意見回饋鈕 | 通過 | iPhone 實機：設定 → 進階設定 → 照片辨識連線看得到「掃描 QR code」；每頁右上有意見回饋鈕 | 2026-10-23/own_04_advanced.png | — |
| 複習頁封面（實機） | 通過 | iPhone 實機：綜合、哈、水果與蔬菜圖片集、今天新加的單字都有各自的照片當封面；弱項單字沒有字，維持色塊 | 2026-10-23/own_03_review.png | — |
| 相片冊主頁卡片集標籤 | 不通過 | iPhone 實機（d0d8d51b 之前的版本）：水果與蔬菜圖片集封面左上「卡片集 · English Card 編輯部」標籤換行後壓到照片上的字。卡 #564 正在改相片冊封面，請一併檢查；M87 會再驗 | 2026-10-23/own_01_albums.png | 低 |
| owner iPhone 安裝 | 通過 | 實機檢查後重裝 release 版 main e4b1e8c0（含 Windows 6aa0b935 的 #561 #565 #557 #568 #567 #564 與 Mac d0d8d51b） | — | — |
| 模擬檔修正 | 通過 | Mac 0fabd933：detail 讀 SIM_OUT、findings 不為空就不算過、SIM_SEED 分層抽樣（含 stub）、捲到底檢查空白標題、沒有 tagger cache 時 pin 略過／fuzz 跳過照片、pack_update 加 SQLite 分批路徑。SIM_SEED=1023：detail 通過、pack_update 通過、fuzz 通過、pin 略過 | — | — |
| database_simulation：等待提示與實際不符 | 不通過 | 從資料庫加入「本身沒中文、同拼字其他詞性有中文」的字（frightening 名詞、hanging 形容詞），提示說「中文補齊後會自動排進複習」，實際上卡片已拿到其他詞性的中文並排進複習。原因：database_word_detail.dart 的 addDatabaseWord 在 linkLexicon 之前判斷要不要等待 | — | 低 |

## 2026-10-23 M87（iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #565 拍照頁不再有「先選一張照片開始學習」 | 通過 | 模擬器全新安裝、沒有照片時，拍照頁沒有那個按鈕 | 2026-10-23/m87_565_camera.png | — |
| #564 相片冊主頁封面 | 通過 | 水果與蔬菜圖片集卡片有封面圖 | 2026-10-23/m87_564_albums.png | — |
| #564 存到相片冊對話框 | 不通過 | 原本：對話框排版時丟出例外（_RenderLayoutBuilder does not support dry layout），畫面只剩灰色遮罩，存照片時選不了相片冊。Mac dec1e2dd 已修：封面改用固定大小的 Image；新增 save_to_album_cover_test（修正前會失敗）；flutter test 576 過。請 Windows 確認後關卡 | 2026-10-23/m87_564_save_dialog.png | 高 |
| #564 卡片集標籤壓到封面文字 | 不通過 | 相片冊主頁水果與蔬菜圖片集卡片左上「卡片集 · English Card 編輯部」換行後疊在照片上的字上，看不清楚（模擬器與 owner 實機都一樣） | 2026-10-23/m87_564_albums.png | 低 |
| #567 長按點位顯示該字 | 通過 | 照片詳情長按 Tomato 的點，點旁出現黑底「Tomato 番茄、柿子」，放開後消失 | 2026-10-23/m87_567_long_press.png | — |
| #568 單字詳情有圖片和標籤 | 通過 | 沒有自己照片的字：money、face 有「資料庫圖片」，face 有標籤區；happy、glad、blue、bright 詞庫沒有標到它們的圖，所以沒有區塊（照規格不顯示空標題） | 2026-10-23/m87_568_word_detail.png | — |
| #561 句子填空有圖 | 通過 | 複習 30 張裡有 8 張句子填空，8 張都有照片 | 2026-10-23/m87_561_cloze_1.png | — |
| #557 拖曳題標籤不重疊 | 通過 | 拖曳題 2 張：fruit 那張 3 個目標點分開、不重疊；cutting board 那張截圖時圖片還在載入（「正在載入圖片…」，跟 #618 載圖慢同一件事） | 2026-10-23/m87_557_drag_2.png | — |
| happy 的詞形變化有錯（資料） | 不通過 | 單字詳情 happy（形容詞）的「詞形變化」列出 more happy／most happy（已有 happier／happiest）、happied（過去式；過去分詞）、happying（現在分詞）、happies（第三人稱單數），形容詞不該有動詞變化，也不該同時列 more／most。詞庫資料問題，跟 #619（詞形變化要完整）一起修 | 2026-10-23/m87_568_word_detail.png | 中 |

## 2026-10-23 M87（owner 的 iPhone 12 實機，不改資料）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #565 拍照頁（實機） | 通過 | owner 已有照片時拍照頁顯示「AI 辨識就緒」「最近一張照片的單字」，沒有「先選一張照片開始學習」 | 2026-10-23/dev87_565_camera.png | — |
| #564 存到相片冊對話框（實機，含 dec1e2dd） | 通過 | 對話框正常顯示，哈、水果與蔬菜圖片集兩本都有封面小圖 | 2026-10-23/dev87_564_save_dialog.png | — |
| #567 長按點位（實機） | 通過 | owner 照片長按 Laptop 的點，點旁出現黑底「Laptop 筆記型電腦」 | 2026-10-23/dev87_567_long_press.png | — |
| #568 單字詳情（實機） | 通過 | owner 單字本裡沒有自己照片的 happy、glad、blue、bright 詞庫都沒有標到它們的圖，不顯示空區塊；有圖的字已在模擬器確認（money、face） | 2026-10-23/dev87_568_word_detail.png | — |
| #614 照片（實機） | 通過 | 19 張照片全部可顯示 | — | — |
| owner iPhone 安裝 | 通過 | 檢查後重裝 release 版 main e08ae7e6（含 Mac d0d8d51b、dec1e2dd 與 Windows 6aa0b935） | — | — |

## 2026-10-23 #616 長按辨識（Mac 重做）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #616 長按辨識（卡 #567 理解錯，Mac 重做） | 通過 | Mac 8a8e4e2a：照片詳情長按任何位置 → 該點轉圈 → 切出那一塊送 AI 辨識（伺服器或手機內建）→「AI 在這裡看到」清單（最多 6 個，附等級）→ 選一個就在長按位置加標籤和單字；已在照片上的字會移到這裡；可選「都不是，自己輸入」；沒設定辨識時提示去設定。移除 #567 的長按既有點顯示字。新增英法翻譯與 long_press_recognize_test 3 項；flutter test 579 過。photo_detail_screen.dart、photo_widgets.dart 的長按程式改完了，Windows 可解除凍結。已裝到 owner 的 iPhone，等 owner 實際試用 | — | — |

## 2026-10-23 M88

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #571 flutter test 修正 | 通過 | Mac 在 main 8a8e4e2a 上：flutter test 579 過／3 skip／0 失敗，analyze 0 error（screens_test.dart 有 1 個既有 unused_import warning） | — | — |

## 2026-10-23 M89（線上詞庫＋iPhone 模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #558（#605）money 的圖：10290 已退件 | 通過 | 線上詞庫 9bbe4aad…（18,263 詞條、8,464 張圖）：asset 10290 已不在；money 目前 9 張圖，7 張是錢、鈔票、皮夾（7401、8930、9117、9153、9154、9424、10379） | — | — |
| #558（#605）money 仍有文件圖 | 不通過 | money 的圖 7652 是一頁手寫筆記（標籤 text、author、handwriting），跟 #558 要退件的「純文字截圖／文件圖」同類，還沒被濾掉；另外 5431 只看得到兩個人在室內交東西，看不出是錢。建議把有 text／handwriting 標籤、畫面以文字為主的圖再掃一次 | — | 中 |
| #558 附帶 App 修改：複習卡圖片預載 | 通過 | b939df51 改成依實際顯示大小預載前後面照片。模擬器複習 20 張：卡片出現 150ms 時正面還在「正在載入圖片…」2 張（bowl、plant）、背面 0 張。對應 #618（owner 嫌圖片要等 1 秒），請 owner 實機感受 | — | — |
| owner iPhone 安裝 | 通過 | 重裝 release 版 main（含 b939df51 與 Mac 8a8e4e2a 長按辨識） | — | — |

## 2026-10-23 M90（owner 的 iPhone 12）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| owner iPhone 安裝 | 通過 | owner iPhone 已是最新 main 的 release 版（bfb9c470 之後 app/lib 沒有新變動，19:5x 已重裝） | — | — |
| #604 拖曳題重疊 | 通過 | 見 M87（模擬器 m87_557_drag_2） | 2026-10-23/m87_557_drag_2.png | — |
| #605 money 的圖 | 通過 | 見 M89：10290 已移除；手寫筆記圖 7652 已在 M89 另列一列 | — | — |
| #609 填空題有圖 | 通過 | 見 M87：8 張填空題都有圖 | 2026-10-23/m87_561_cloze_1.png | — |
| #612 相片冊封面 | 通過 | 見 M87（實機與模擬器）；存到相片冊對話框 Mac dec1e2dd 已修好 | 2026-10-23/dev87_564_save_dialog.png | — |
| #613 拍照頁按鈕 | 通過 | 見 M87（實機與模擬器） | 2026-10-23/dev87_565_camera.png | — |
| #616 長按辨識 | 通過 | Mac 8a8e4e2a 重做並裝到 owner iPhone；自動測試 3 項通過，等 owner 實際試用 | — | — |
| #617 單字詳情圖片與標籤 | 通過 | 見 M87（實機與模擬器） | 2026-10-23/m87_568_word_detail.png | — |
| #639–#643 | Mac 處理中 | Windows 卡 #572–#576 修好、mac_sync 開 M 項後在 iPhone 驗證 | — | — |

## 2026-10-23 owner 決定 #626：App 畫面給 Mac

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| [待決定] #626 分工 | 通過 | owner 在 Mac 對話中決定：「App 畫面與互動的回報由 Mac 修，詞庫資料與伺服器由 Windows 修。請通知 Windows，並把 #641、#642、#643 從 Windows 收回來由 Mac 馬上做。」請 Windows 把 #626 記成已決定，之後 App 畫面類回報寫進 inbox 標 [給 Mac] | — | — |
| #641 #642 #643（卡 #574 #575 #576） | Mac 處理中 | 由 Mac 修：翻卡背面回正面／上一張按鈕、意思列 1 2 3、例句列 1 2 3。請 Windows 停掉這三張卡，並凍結 flashcard_back.dart、flashcard_screen.dart、flashcard_session_views.dart 給 Mac，Mac 完成後會記一列 | — | — |

## 2026-10-23 M91（Mac 修 #641 #642 #643）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #641 上一張卡片／回到正面 | 通過 | Mac a8829eb7（session 部分參考 Windows 草稿）：上方返回鍵旁「上一張卡片」顯示剛評分的那張背面、不重新評分，底部「回到這張卡片」；背面評分鈕上方「回到正面」。模擬器：回到正面後仍是 bread 的題目；上一張顯示 bread，回到這張卡片後回到原本的卡 | 2026-10-23/m91_previous_card.png | — |
| #642 意思編號 1 2 3 | 通過 | 以「；」分開的多個意思編號 1 2 3，前三個先顯示，其餘在「顯示更多」；逐義釋義版面同樣編號（單元測試） | — | — |
| #643 例句編號 1 2 3 | 通過 | 例句編號 1 2 3、前三句先顯示（原本 5 句），其餘在「顯示更多」；模擬器 bread 背面「顯示更多（3）」 | 2026-10-23/m91_back_numbered_2.png | — |
| 測試與安裝 | 通過 | flutter test 582 過（連跑兩次）、analyze 0 error；已裝 release 版到 owner 的 iPhone。flashcard_back.dart、flashcard_screen.dart、flashcard_session_views.dart 改完，Windows 可解除凍結 | — | — |

## 2026-10-23 M92（Mac 修 #648）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #648 複習頁沒有下載的單字庫 | 通過 | 原因：單字集只加單字、不建相片冊，複習頁只列相片冊；而且卡片集清單只在打開卡片集時才載入。Mac 652af97a：啟動時載入已下載的卡片集；複習頁每個單字集一格，點了只複習該單字集加入的字。模擬器：下載「基礎單字（先行版）」後複習頁出現該格（今天 20 張）。flutter test 583 過；已裝 release 到 owner 的 iPhone | 2026-10-23/m92_review_tiles.png | — |
| 單字集沒有封面圖（交 Windows） | 不通過 | /api/decks 的 9 個單字集（basic-core、basic-3000 與 A1–C2、法語 2000／3000）cover_asset_id 都是 null，複習頁與卡片集頁的單字集格子只能顯示色塊。App 已支援：單字集有 cover_asset_id 就用它當封面。請幫每個單字集挑一張代表圖 | — | 低 |
| 詞庫圖片仍有很多圖表、文件頁（交 Windows） | 不通過 | Mac 試著用詞庫圖片當複習格封面時，A1–A2 名詞的第一張圖常是圖表／心智圖、雜誌內頁、標語海報（例：TOTALITARIAN STATE 海報、手寫筆記 7652、一張只有英文句子的圖），跟 #558 退件的純文字／文件圖同類。建議再掃一次：主標籤是 text／diagram／chart／page／poster、畫面以文字為主的圖退件 | — | 中 |

## 2026-10-23 M94（Mac 修 #651 #652）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #651 藍點跑出圖片外 | 通過 | 原因：照片 cover 置中裁切，標的物在被裁掉的那段時藍點算在框外。Mac 4c5373c6（正面）＋ 8443c1b2（背面）：照片依本題的點移動，讓點留在框內至少 40px 且仍對準標的物，不夾到邊；新增 issue651_cover_focus_test 9 項 | — | — |
| #652 上一張可以一直按 | 通過 | Mac 8443c1b2：「上一張卡片」可連續往前（本輪最多 50 張），顯示「往前第 N 張，已經評分過」，「回到這張卡片」直接回到目前的卡；測試涵蓋連按兩次與回到目前 | — | — |

## 2026-10-23 M95

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #577（#648） | 通過 | Mac 652af97a 已修（見 M92） | 2026-10-23/m92_review_tiles.png | — |

## 2026-10-23 M96

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #579（#650）、卡 #580（#651） | 通過 | Mac 已修，見 M93、M94 | — | — |

## 2026-10-23 M98（Mac 修 #606 畫面部分）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #606 填空題字數與比對 | 通過 | Mac 8443c1b2：填空空格改成每個字母一個、有間隔的底線（_ _ _ _ _，原本全形＿連成一條數不出來）；答錯時背面「你的答案／正確答案」逐字比對，不同的字母你的答案標紅、正確答案標綠；新增 cloze_blank_compare_test | — | — |

## 2026-10-23 M93（Mac 修 #649 #650）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #649 一次兩個發音、第一聲是機器人 | 通過 | Mac 8443c1b2：翻卡英式、美式都唸；有真人錄音的腔調先唸，沒錄音的腔調後面用 TTS（iPhone 高品質語音）。更多真人錄音來源已在 M84 另列一列交 Windows（全庫只有 56% 有真人錄音） | — | — |
| #650 複習圖片要一兩秒 | 通過 | owner iPhone 12 實測（自由加練、不改排程）：修前看圖選單字 1.5–1.6 秒；原因是預載只看今天到期的卡，自由加練時沒有預載。Mac bc839eaf：自由加練順序每輪洗牌一次並記住，預載同順序接下來 3 張卡的照片。修後 15 張：14 張 0 ms、1 張 2 秒（strawberry，可能是答錯後回來的卡）。已裝到 owner 的 iPhone | — | — |

## 2026-10-23 M97（Mac 修 #640）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #640 相片沒出現在相片冊 | 通過 | Windows #573 推斷正確：photos 只收 safetyStatus=safe，辨識沒成功／排隊／沒有辨識器的相片一直 unchecked 被藏起來（451 的相片本來就整張刪除）。Mac 0bf6419e：相片冊顯示所有相片；複習照舊只出有單字的卡；新增 card640_unchecked_photos_test 4 項。owner iPhone 上 photo-1792753703603088 現在是 taggingStatus=done、safetyStatus=safe（後來辨識成功了），已在相簿 album-1792753703602363-2 | — | — |

## 2026-10-23 M99（#618 圖片載入，實機量測）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #618 複習圖片要 1 秒 | 通過 | owner iPhone 12 實測（自由加練、不改排程）：修前看圖選單字照片就緒 1,541–1,649 ms，主因是 (1) 詞庫圖片首次從伺服器下載、且自由加練時預載清單是空的。Mac bc839eaf 讓自由加練也預載接下來 3 張卡的照片後，15 張裡 14 張 0 ms、1 張 2,075 ms。目前不需要伺服器縮圖；若要再降最後那張，可考慮進入複習時批次預熱當天佇列 | — | — |

## 2026-10-23 M100（Mac 修 #619 畫面部分）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #619 詞形變化要有所有時態 | 通過 | Mac 5f4ec6a2：英文動詞加「現在式」「未來式（will＋原形）」，依時間排序；依卡片詞性過濾不屬於它的變化（形容詞不再出現 happied 等）；forms_all_tenses_test。已裝到 owner 的 iPhone | — | — |
| #619 詞庫缺的變化形（交 Windows） | 不通過 | App 不自己產生過去式等規則變化（不規則動詞會錯），詞庫缺的部分要 Windows 補；另外 happy 等形容詞帶動詞變化、名詞帶比較級的資料仍在詞庫裡，App 已過濾但資料應修正。M100 說 App pack 要重新匯出才看得到新形態，請匯出後通知 Mac 驗證 | — | 中 |

## 2026-10-23 M101（線上詞庫）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #563（#611）weather 標籤等級 | 通過 | 線上詞庫 3d5544d5…：weather（A1）的 11 張圖，標籤等級都等於各字自己的詞庫等級（stone A1、texture C1、shadow A2…）。另統計全庫 -ed／-ing 形容詞標籤 1,334 筆，有 454 筆和原形等級不同（polished B2／polish C1、detailed B2／detail A2、covered A1／cover A2…），多半是動詞＋ed，不在這次「名詞＋ed/ing 跟原形」規則內，供 Windows 參考 | — | — |

## 2026-10-23 M102（#619 拿掉未來式）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #619 依決定 #632 A 拿掉「未來式」 | 通過 | Mac 011f9c90：詞形變化不再列「未來式（will＋原形）」，保留「現在式」與依詞性過濾；forms_all_tenses_test 改成確認沒有未來式。flutter test 601 過（連跑兩次）；已重裝 release 到 owner 的 iPhone | — | — |

## 2026-10-23 M103（線上詞庫）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #586（#660）次要詞性的變化形 | 通過 | 線上詞庫 5eb40aa9…已是重新匯出的版本：happy、bright、golden（形容詞）只剩比較級／最高級，沒有動詞變化；shadow（名詞）只剩複數。happy 同時有 happier 與 more happy 兩個比較級，App 只顯示第一個（happier），不影響畫面；若要乾淨可把 more happy 也拿掉 | — | — |

## 2026-10-23 M104

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #584（#625）補真人發音 | 通過 | App 端不用改：翻卡已是真人錄音先唸、沒有錄音的腔調用 TTS（Mac 8443c1b2），詞庫一補上錄音 App 就會自動改用真人 | — | — |

## 2026-10-23 M105（Mac 修 #663）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #663 相片冊要顯示下載的相片庫 | 通過 | owner iPhone 裝的是 food-b1（圖片集，本來就在相片冊）與 basic-3000-c2（單字集，沒有自己的照片所以不出現）。Mac 8669631e：相片冊列出每個單字集（標「單字集」），點開是這些字的詞庫圖片（最多 300 張，可點開看標籤、加入）。模擬器：「基礎單字（先行版）」1706 字、300 張圖。flutter test 602 過；已裝 release 到 owner 的 iPhone | 2026-10-23/m105_word_deck_photos.png | — |

## 2026-10-23 M107（線上詞庫）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #587（#637）happy 的詞形 | 通過 | 線上詞庫 da97767e…：沒有任何字同時有 -er／-est 與 more／most；happy 只剩 happier／happiest，crumbly 只剩 crumblier／crumbliest | — | — |

## 2026-10-23 M109

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #588（#663） | 通過 | 已確認 owner 的 iPhone 裝的是 basic-3000-c2（kind=words，單字集，不會建相簿）與 food-b1（kind=photos，本來就在相片冊）。Mac 8669631e 已讓相片冊列出單字集並可點開看詞庫圖片（見 M105）；問題回報 #663 可結案 | 2026-10-23/m105_word_deck_photos.png | — |

## 2026-10-23 M110

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #588（#663） | 通過 | 已確認 owner 的 iPhone 裝的是 basic-3000-c2（kind=words，單字集，不會建相簿）與 food-b1（kind=photos，本來就在相片冊）。Mac 8669631e 已讓相片冊列出單字集並可點開看詞庫圖片（見 M105）；問題回報 #663 可結案 | 2026-10-23/m105_word_deck_photos.png | — |

## 2026-10-23 M108（Mac 修 #666）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #666 照片詳情多看動詞、難度提高沒有新增標籤 | 通過 | 原因：(1) 卡片集圖片的列表一進來就滿 5 個，選詞器沿用現有字，按「多看動詞」動詞也擠不進去；(2) 只有選詞器判斷候選不足才補字，按了常常沒問辨識伺服器；(3) 不能補字時沒提示，斷線後該類字被記成已問過不再重試。Mac ad8e7ae1：多看動詞／形容詞至少換進 2 個該詞性的字；按了列表沒變就主動補字（卡片集圖片也會）；補字時顯示「AI 正在找更多動詞…」；沒有新字、沒有辨識器、離線各有提示，離線後可重試。新增 card666 測試 7 項；flutter test 611 過。實機待安裝後確認 | — | — |

## 2026-10-23 M114

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #591（#666） | 通過 | Mac ad8e7ae1 已修（見 M108）：多看動詞／難一點會主動向辨識伺服器補字並換進新字，沒有新字時有提示。不需要新的後端 API；問題回報 #666 可結案 | — | — |

## 2026-10-23 M115

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #591（#666） | 通過 | Mac ad8e7ae1 已修（見 M108）：多看動詞／難一點會主動向辨識伺服器補字並換進新字，沒有新字時有提示。不需要新的後端 API；問題回報 #666 可結案 | — | — |

## 2026-10-24 M106（Mac 修 #664 #665）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #664 標籤都跑出去了 | 通過 | 原因：照片詳情照片框固定高 320、cover 置中裁切，owner 這張直式照片（720×1280）上下被切掉，y=0.18／0.76／0.85 的標籤落在框外。Mac af660228：照片框依照片比例（上限螢幕高 62%），改用 contain，點擊／長按／拖曳同一套換算，標籤只排在照片可見範圍內。owner iPhone 實機：photo-1792769785574157 整張可見、所有標籤都在照片上 | 2026-10-23/dev664_photo_detail.png | — |
| #664 回報時附截圖（App 端） | 通過 | Mac ba72d437：意見回饋先截下畫面（小 PNG，可取消勾選），放在報告的 screenshot 欄位，離線時一起排隊 | — | — |
| #664 回報截圖（伺服器與問題回報頁，交 Windows） | 不通過 | serve_app 的 app_report() 只保留 title／detail／lemma，screenshot 欄位被丟掉；問題回報頁也沒有顯示附件的地方。請讓 /api/issues 收 screenshot（data:image/png;base64，App 已控制在 170 KB 內），存下並在問題回報頁顯示（#597） | — | 中 |
| #665 同樣的標籤不要重跑動畫、不要換位置 | 通過 | Mac af660228：layoutPins 加 keep，已有標籤留在原位，只替新標籤找位置；被難度刻度暫時拿掉又回來的字直接在原位出現、不跑動畫。新增 issue664_665_photo_detail_pins_test 8 項；flutter test 619 過 | — | — |

## 2026-10-24 M111

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #589／#590（#664 #665） | 通過 | Mac af660228、ba72d437 已修（見 M106）；問題回報 #664（App 部分）與 #665 可結案，#664 的截圖上傳後端見 M106 另一列 | 2026-10-23/dev664_photo_detail.png | — |

## 2026-10-24 M112

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #589／#590（#664 #665） | 通過 | Mac af660228、ba72d437 已修（見 M106）；問題回報 #664（App 部分）與 #665 可結案，#664 的截圖上傳後端見 M106 另一列 | 2026-10-23/dev664_photo_detail.png | — |

## 2026-10-24 M113

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #589／#590（#664 #665） | 通過 | Mac af660228、ba72d437 已修（見 M106）；問題回報 #664（App 部分）與 #665 可結案，#664 的截圖上傳後端見 M106 另一列 | 2026-10-23/dev664_photo_detail.png | — |

## 2026-10-24 M118

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #550（#587）每頁都有意見回饋 | 通過 | 已在 M84／M87 實機確認每頁右上有意見回饋鈕；截圖附件：伺服器實查 #668、#671 有截圖（#667 生效），#669、#670 在照片詳情截圖逾時沒附上，Mac 4a33e249 已修（0.5 倍起、最多等 2.5 秒），卡片回報也附截圖（cd12c5fb） | — | — |

## 2026-10-24 M116（Mac 修 #668）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #668 單字庫只有四個字 | 通過 | 原因：安裝單字集時只記下「這次新建」的字，單字本原本就有的字被跳過；owner 的單字本已有 basic-3000-c2 大部分的字，所以只剩 4 個。Mac 16c0fd76：InstalledDeck 記下單字集全部的字，相片冊、單字集圖片頁、複習格子、Anki 匯出都改用它；owner 手機上舊的安裝會在啟動後從伺服器補齊（離線時下次再補）；移除單字集仍只刪新建的字。新增 card668 測試；已裝 release 到 owner 的 iPhone | — | — |

## 2026-10-24 M117（Mac 修 #669 #670）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #669 回報都要有截圖 | 通過 | 伺服器實查：#668、#671 有截圖，#669、#670（照片詳情）沒有，原因是照片詳情的 PNG 太大要縮小重編、超過 0.8 秒放棄。Mac 4a33e249：0.5 倍起、上限 180 KB、最多等 2.5 秒；Mac cd12c5fb：卡片回報（複習卡的旗子）也附截圖。兩種回報都有縮圖與「附上這個畫面的截圖」勾選 | — | — |
| #670 重新掃描標籤按鈕 | 通過 | Mac 9da17089：照片詳情難度捷徑列最後一顆「重新掃描標籤」，對整張照片重新辨識（請 AI 找池子裡還沒有的字），只併入候選、不洗掉原本、加星或自己加的字；進行中「AI 正在重新掃描…」，完成提示新增幾個字；卡片集圖片與自己拍的照片都可以。新增 card670 測試 8 項；flutter test 630 過 | — | — |

## 2026-10-24 M119（Mac 修 #671）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #671 按多動詞要重新掃描並給動詞 | 通過 | Mac 9da17089：多看動詞／多看形容詞／難一點／簡單一點每次按都向辨識伺服器重新掃描（同一種同時只送一次），新字最多換進 2 個，不動加星／改過／自己加的字；沒有新字、沒有辨識器、離線時有提示。已裝 release 到 owner 的 iPhone | — | — |

## 2026-10-24 M120

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #593（#668） | 通過 | 原因已確定是 App 的 bug（安裝時只記新建的字），Mac 16c0fd76 已修，單字集格子會顯示全部字數（見 M116）；不需要 owner 在 A/B/C 之間決定，也不需要 Windows 資料卡 | — | — |

## 2026-10-24 M121

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #594（#669） | 通過 | 見 M117：照片詳情截圖逾時已修（4a33e249），卡片回報也附截圖（cd12c5fb）；已裝 release 到 owner 的 iPhone，等 owner 下一筆照片詳情的回報確認伺服器有 screenshot | — | — |

## 2026-10-24 M122

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #595（#670） | 通過 | owner 回報的是自己拍的照片（photo-1792753703603088），Mac 9da17089 的「重新掃描標籤」走 App 的辨識（/tag），自己拍的照片與卡片集圖片都可用（見 M117）。資料庫圖片頁用 retag-short 的重標屬另一個畫面，owner 沒要求，先不做 | — | — |

## 2026-10-24 M123

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #596（#671） | 通過 | 見 M119：Mac 9da17089 多看動詞等每次都重新掃描並換進新字 | — | — |

## 2026-10-24 M124

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #594／#595／#596（#669 #670 #671） | 通過 | Mac 已修並裝到 owner 的 iPhone：截圖 4a33e249、cd12c5fb；重新掃描標籤與多看動詞每次重掃 9da17089（見 M117、M119） | — | — |

## 2026-10-24 M125

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #594／#595／#596（#669 #670 #671） | 通過 | Mac 已修並裝到 owner 的 iPhone：截圖 4a33e249、cd12c5fb；重新掃描標籤與多看動詞每次重掃 9da17089（見 M117、M119） | — | — |

## 2026-10-24 M126（Mac 修 #673）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #673 相片冊：為什麼呢？（C2 單字集頁空白） | 通過 | 截圖 docs/mac_handover/673.png：「基礎 3000 字・C2」頁只有「詞庫還沒有這個單字集的圖片」。伺服器 /api/decks/basic-3000-c2 本來就只有 4 個字（counsel、depress、situate…），都是抽象字、詞庫沒有圖。Mac ce4dc917：沒有圖片時列出單字（點了開單字詳情），說明「這 N 個字在詞庫裡還沒有圖片，可以先看單字」。flutter test 631 過；已裝 release 到 owner 的 iPhone | — | — |
| 基礎 3000 字依程度切的 C1／C2 太少（交 Windows） | 不通過 | /api/decks：基礎 3000 字・B2 358 字、C1 35 字、C2 只有 4 字，下載 C2 的學習者會以為壞掉（#668、#673 都是這個）。建議：(1) C1／C2 改用詞庫裡真正的 C1／C2 常用字另做「進階單字」卡片集；或 (2) 卡片集清單上隱藏字數太少的切片、或在說明寫清楚「基礎字裡 C2 程度的只有 4 個」。屬卡片集資料與伺服器，交 Windows／owner 決定 | — | 中 |

## 2026-10-24 M127（Mac 修 #674 #675 #676）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #674 標籤選項放到難度拖曳列下面 | 通過 | Mac fa493dfa：「多看動詞／多看形容詞／簡單一點／難一點／重新掃描標籤」移到難度列正下方、單字列表上面（取代 #451 的位置）；card450 測試跟著改 | — | — |
| #675 高難度時詞量很少（App 部分） | 通過 | owner 那張照片的候選 15 個全是 A1–B1（名詞 10、動詞 5），沒有 B2 以上，再加上名詞最多 3 個，高難度能顯示的字就少。Mac fa493dfa：難度比照片最難的字還高時，難度列下說明「AI 在這張照片找到的字最難到 B1，按「難一點」或「重新掃描標籤」請 AI 找更難的字」 | — | — |
| #675 辨識伺服器很少給 B2 以上的字（交 Windows） | 不通過 | owner 的照片（photo-1792769785574157，書桌、檯燈、螢幕）候選 15 個沒有一個 B2／C1／C2。請檢查 /tag 的提示詞：一般辨識也要涵蓋到使用者程度以上（例如各級至少 1–2 個），focus=harder 時要真的回 B2–C2 的字（不是同義的簡單字），並用類似的室內照片測 | — | 中 |
| #676 下載的單字庫是空的 | 通過 | 跟 #673 同一件事：basic-3000-c2 只有 4 個抽象字、沒有詞庫圖，頁面空白。Mac ce4dc917 已改成沒有圖時列出單字（01:2x 已裝到 owner 的 iPhone）；C1／C2 切片太小已另列交 Windows（見 M126） | — | — |

## 2026-10-24 owner 決定：進階單字卡片集

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| owner 決定（回覆 M126 不通過列） | 不通過 | owner 原話：「要。請 Windows 用詞庫裡真正的 C1／C2 常用字另做「進階單字」卡片集，基礎 3000 字的 C1／C2 切片從清單拿掉。」請 Windows 做進階單字卡片集（完整詞條、依詞頻、數量夠學），/api/decks 拿掉 basic-3000-c1、basic-3000-c2；完成後開 M 項給 Mac 驗證 | — | 中 |

## 2026-10-24 M129

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #597（#673） | 通過 | 已在 M126 查明並修好（ce4dc917）：截圖是「基礎 3000 字・C2」頁空白，該單字集只有 4 個抽象字、沒有詞庫圖，現在沒有圖時會列出單字；owner 已決定另做進階單字卡片集（#678）。截圖太小（195×422）看不清，Mac 會把截圖預設放大 | docs/mac_handover/673.png | — |

## 2026-10-24 M128（Mac 修 #677）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #677 匯入照片一次多選 | 通過 | Mac d6faaa02：選圖頁可勾選多張（角落顯示順序、上方「已選 N 張」、按鈕「加入 N 張」與進度）；「從相簿選擇」改 pickMultiImage（最多 30 張）；「存到相片冊」只問一次；逐張讀檔存檔、全部存完才交給辨識佇列一張一張辨識；重複照片照原規則逐張問；多張加入後回相片冊並提示「已加入 N 張照片，AI 會一張一張辨識」。縮圖 180px、預覽 1200px 解碼，避免記憶體壓力。新增 card677 測試 3 項；flutter test 635 過；已裝 release 到 owner 的 iPhone（實機多選待 owner 試） | docs/mac_handover/677.png | — |

## 2026-10-24 M130

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #598（#674） | 通過 | Mac fa493dfa 已修（見 M127）：標籤選項在難度拖曳列正下方；已裝到 owner 的 iPhone | — | — |

## 2026-10-24 M131

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #601（#677） | 通過 | Mac d6faaa02 已修（見 M128）：匯入照片可一次多選 | — | — |

## 2026-10-24 M132

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| /api/issues 上限 2 MB | 通過 | Mac e75a00d7：回報截圖改成 1.0 倍（390×844 邏輯尺寸），上限 1.3 MB（base64 約 1.75 MB），超過再縮；已裝到 owner 的 iPhone | — | — |

## 2026-10-24 M133

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #598（#674）、卡 #600（#676） | 通過 | Mac 已修（見 M127）：#674 fa493dfa 標籤選項移到難度列下面；#676 ce4dc917 單字集沒有圖時列出單字（C2 只有 4 個字，進階卡片集已由 Windows #678 製作中） | — | — |

## 2026-10-24 M135

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #601（#677） | 通過 | Mac d6faaa02 已修（見 M128）：匯入照片可一次多選，已裝到 owner 的 iPhone | — | — |

## 2026-10-24 M134（Mac 修 #683 #684）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #683 複習頁直接列出所有相片集，點了就學 | 通過 | 截圖 683.png：複習頁只有「等待詞庫補齊」。原因：顯不顯示格子看「上次選的那一本」，上次選的是還在等中文的 C2 單字集，其他相片冊全被藏起來。Mac 8676be01：有相片冊、單字集或任何可複習的卡就一律列出格子；點到沒卡可複習的那一格會說明原因，不開空的複習。review_grid_always_test | docs/mac_handover/683.png | — |
| #684 單字詳情的聲音要等很久 | 通過 | 原因：錄音每次都用 UrlSource 從伺服器（經 Cloudflare）重新下載。Mac b3e9d44c：錄音存在手機快取（audio_cache，上限 300 檔／50 MB），同網址只下載一次；打開單字詳情與複習卡正面時先預載英美兩個錄音；下載不成功就退回原本串流再退回 TTS。card684 測試 7 項；flutter test 643 過；已裝 release 到 owner 的 iPhone（實機第二聲是否立即待 owner 試） | docs/mac_handover/684.png | — |

## 2026-10-24 M136／M137（進階單字卡片集）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #678 進階單字・C1／C2 上架 | 通過 | /api/decks：新增 advanced-c1、advanced-c2 各 400 字，basic-3000-c1／c2 已不在清單。C1 有 10 個、C2 有 3 個字線上詞庫還沒有中文（如 constitutional、judicial、tactical），中文補齊前不會進複習 | — | — |
| 模擬器下載進階單字・C1 | 通過 | 卡片集頁「已加入「進階單字・C1」，可以開始複習」；相片冊出現「進階單字・C1 · 400 個單字」；複習頁出現該格「今天 20 張」 | 2026-10-24/m137_review_tiles.png | — |
| 單字集圖片頁標示該程度的字 | 通過 | 原本每張圖顯示的多是 tree、sky 等 A1 字；Mac dc9746da：單一程度的單字集只標該程度的字、只列有該程度標籤的圖，C1 頁顯示 threshold、texture、glossy、fender…。已裝 release 到 owner 的 iPhone | 2026-10-24/m137_word_deck_photos.png | — |
| owner iPhone | 通過 | 已裝最新 release；下載進階單字會在 owner 的單字本加 400 個字，Mac 不代下載，由 owner 自己決定要不要加 | — | — |
| CEFR 分級怪字（交 Windows） | 不通過 | Windows 已註記：進階單字・C1 裡有 removed、jersey 這類分級可疑的字；模擬器圖片頁另看到 noodle 標成 C1。請檢查 CEFR 來源（estimate）對常見字的分級 | — | 低 |

## 2026-10-24 M137

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #604（#678） | 通過 | 見 M136：進階單字 C1／C2 已在模擬器驗證並修了圖片頁的標示（dc9746da） | 2026-10-24/m137_word_deck_photos.png | — |

## 2026-10-24 M138（Mac 修 #657 錄音授權標示）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #657 播放時顯示錄音者／授權 | 通過 | Mac b6e1d998：兩種單字詳情在音標下方顯示「發音錄音：錄音者 · 授權（來源網站）」，取設定腔調實際會播的那段錄音的 speaker（沒有就 attribution，但 Own work 不算）、license、source_page。複習卡背面照既有規則不放出處。新增 recording_credit_test；flutter test 645 過；已裝 release 到 owner 的 iPhone | — | — |
| 詞庫沒有 speaker／source_page 欄位（交 Windows） | 不通過 | 線上 pack 14,233 個錄音都有 license，但 speaker、source_page 都是 0 筆（6,036 個 attribution 只寫 Own work）；#657 新加的約 757 個 Wikimedia 錄音也沒有帶出錄音者。請在匯出 pack 時把 audio_assets.speaker／source_page 放進 pronunciations，App 就會自動顯示錄音者與來源 | — | 中 |

## 2026-10-24 M139（Mac：錄音者整理成一行）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #688 Wikimedia 多行錄音者 | 通過 | Mac b3c1f5ee：speaker 的「Speaker: X\nRecorder: Y」整理成一個名字（取 Speaker 後面的名字；沒有就取第一行去掉標籤；最多 60 字），測試涵蓋多行情況；flutter test 645 過；已裝 release 到 owner 的 iPhone。線上 pack（02:5x 下載）還沒有 speaker 欄位，重新匯出後 App 會自動顯示錄音者 | — | — |

## 2026-10-24 M140（線上詞庫）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #608（#688）pack 帶出錄音者與來源頁 | 不通過 | 03:0x 從公開網址抓的線上 pack：JSON（created e3f60392…）與 format=sqlite（解開每筆 body）的 pronunciations 裡，14,243 個錄音的 speaker、source_page 都是 0 筆，欄位只有 kind／default／audio／license／attribution／accent。卡片說匯出已帶出（14,118 個錄音者），可能是 serve_app 還在給舊的 pack 或沒重啟。請確認公開網址 /api/lexicon?target=en&native=zh-TW（含 format=sqlite）回的 pack 有這兩個欄位；App 已就緒（b6e1d998、b3c1f5ee），不需要再改 | — | 中 |

## 2026-10-24 M141（重驗 #688 錄音者）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 線上 pack 帶出 speaker／source_page | 通過 | 03:3x 從公開網址抓 format=sqlite：14,245 個錄音中 speaker 14,120、source_page 14,245。多行的「Speaker: X\nRecorder: Y」有 5,882 筆，App 已整理成一個名字（b3c1f5ee）；另有 304 筆「No machine-readable author provided. X assumed…」，Mac 已改成只取 X（commit 見本列下一個） | — | — |
| 模擬器單字詳情錄音者 | 通過 | 線上 pack 同步後，gold 的單字詳情音標下顯示「發音錄音：Shtooka Project · CC BY 3.0 us」；horn 顯示「My won · Public domain」 | 2026-10-24/m141_recording_credit.png | — |
| owner iPhone | 通過 | 03:2x 手機鎖定，實機檢查沒有啟動；已重裝 release（含錄音者顯示與名字整理）。owner 打開 App 後會同步新詞庫，單字詳情就會出現錄音者 | — | — |

## 2026-10-24 M142（法語學習者，模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #496 法語模擬（英語母語者學法語） | 通過 | main 最新版、FRENCH_LEARNING=true 在模擬器重跑：新手引導選學法語＋母語英文可進主畫面；首頁、單字本、設定頁沒有中文字串；法語詞庫 6,153 詞；複習背面法文字頭不被改大寫、名詞帶冠詞（maison、temps、pomme…） | — | — |

## 2026-10-26 M143（owner 回報）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #690 一次長按多個地方辨識 | 通過 | Mac 5c64fb1c：可連續長按多個點，每點轉圈排隊、一次送一個；完成的點變編號圓點，選字面板依序跳出，可「略過，看下一個位置」；card690 測試 | — | — |

## 2026-10-26 M144（owner 回報）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #691 標籤太少（App） | 通過 | Mac 5c64fb1c：全是名詞的照片在問過動詞後放寬名詞上限補到 5 個；不到 5 個就補問；已存照片重開不到 5 個也會補；card691 測試 3 項 | — | — |
| #691 辨識伺服器候選太少／太簡單（交 Windows） | 不通過 | photo-1792753703603088（C2 街景）伺服器幾乎只給 A1–B1 名詞。請依 level 參數回該程度附近的字、每次至少約 8 個候選且含動詞形容詞、focus=harder／actions 補問要真的回新字；並考慮避開使用者其他照片正在學的常見字 | — | 中 |

## 2026-10-26 M145（owner 回報）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #692 回到正面上下各一 | 通過 | Mac 0744d24b：背面最上方加一顆「回到正面」，底部原本的保留 | — | — |
| #693 滑動照片卡頓 | 通過 | Mac 792f5a02：滑動不再觸發整個複習畫面重建；預載前一張加後三張；PageView 預先建好左右兩頁 | — | — |

## 2026-10-26 M146（owner 回報）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #694 詞性與說明用 1 2 3 | 通過 | Mac 0744d24b：英文說明依「；」拆開編號 1 2 3，前三點先顯示 | — | — |
| #695 為什麼這沒圖片 | 不通過 | 資料：home 名詞（1109）沒有核准圖片，圖 1558 已不在線上詞庫，5504 只標給形容詞 home。請補 1109 的圖或確認 1558 被拿掉是否有意 | — | 中 |

## 2026-10-26 M147（owner 回報）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #696 標籤辨識錯誤，哪有蘋果 | 不通過 | 資料：線上圖 168（砧板）apple 標在 (0.74,0.15) 實際是葡萄籃，應改 grape 或刪 apple；cheese (0.837,0.25) 疑似餐巾。App 另修了拖曳題放置點換算偏移（792f5a02） | — | 中 |
| #697 單字題不要圓圈 | 通過 | Mac 792f5a02：看圖選單字（photoChoice）正面不再畫圓圈與框；拼字回想照舊 | — | — |

## 2026-10-26 M148（owner 回報）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #698 說明並排列點 | 通過 | 依兩分鐘後的 #699 改口：不並排，只用 1 2 3 標示（見 M149） | — | — |

## 2026-10-26 M149（owner 回報）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #699 只要 1 2 3 標示 | 通過 | Mac 0744d24b：單字詳情各詞性的中文意思加 1. 2. 3.，一行一點 | — | — |
| #700 法語學習上線 | 通過 | Mac de2a00ff：FRENCH_LEARNING 預設開啟（依 owner #700，視為 #505 的決定），新手引導與設定都能選學法語；6 個假設法語關閉的測試已更新 | — | — |
| #701 意見回饋清單（App） | 通過 | Mac de2a00ff：設定 →「我的意見回饋」列出這支手機送過的回報（標題、時間、已送出 #編號／排隊中、截圖），可刪除（本機；排隊中的刪了就不送）；card701 測試 | — | — |
| #701 從伺服器刪除回報（交 Windows） | 不通過 | serve_app 的 proxy_issues 只轉 GET／POST／PUT，沒金鑰只放行 POST。請決定 App 怎麼刪伺服器上的回報：有 X-API-Key 時轉 DELETE /api/issues/{id}，或 POST 回應附刪除 token 讓 App 不用金鑰刪自己那筆；並確認沒金鑰的 POST 回應有 id | — | 中 |

## 2026-10-26 M150（owner 回報）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #702 照片 loading 的原因 | 通過 | Mac 792f5a02：App 內建詞庫圖被拿去伺服器下載而 404（主因）已改讀 App 內檔；同網址同時只下載一次；連線中斷／逾時／429／5xx 自動重試兩次 | — | — |
| #702 伺服器沒有縮圖（交 Windows） | 不通過 | /api/image 一律回 1280px 原圖（約 400 KB），w／max／size 參數都沒作用。建議提供約 960px 縮圖，第一次下載與解碼會快很多 | — | 中 |
| #703 標籤位置錯誤 | 不通過 | 資料：線上圖 9564（夜景情侶）city 座標是預設 (0.5,0.5)、沒有框，落在人頭上；同圖 night (0.5,0.4) 也像預設。請移到正確位置並全面檢查座標剛好 (0.5,0.5) 又沒框的場景類標籤；App 換算已核對無誤 | — | 中 |

## 2026-10-26 M151（owner 回報）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #704 每個字都能點到詳情 | 通過 | Mac 0744d24b：單字詳情的近義詞、反義詞、同音詞、近音詞、拼寫相似詞、衍生詞、相關詞、詞形變化，資料庫有的字都能點開該字詳情 | — | — |
| #705 不要重複兩個分級 | 通過 | Mac 0744d24b：標題下「名詞 · 中階（B1）」拿掉等級文字，只留等級標章 | — | — |

## 2026-10-26 M152（owner 回報）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #706 illuminate 說明錯（App） | 通過 | Mac 5c64fb1c：導向詞卡時略過罕用條目，illuminated 改導到 illuminate（動詞）「照亮、照明」；lexicon_pack_test | — | — |
| #706 illuminate 詞庫資料（交 Windows） | 不通過 | illuminate（adj，48818）rare_usage、C2，義項全是 etymology-2／obsolete／archaic，建議降級或移除；illuminated（adj，17587）有正確義項卻因 card=illuminate 被導走，請確認歸併 | — | 中 |

## 2026-10-26 M153（owner 回報）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #707 拿掉難一點／簡單一點 | 通過 | Mac 5c64fb1c：只留多看動詞、多看形容詞、重新掃描標籤 | — | — |

## 2026-10-26 M154（owner 回報）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #708 拖曳條更粗、不標 A1–C2 | 通過 | Mac 5c64fb1c：粗軌道 14px、圓鈕 34px、拖過填色，不顯示刻度；上方寫程度中文名與相對難度（例「精通 · 挑戰」），兩端「簡單／難」 | — | — |

## 2026-10-26 M155（owner 回報）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #709 點照片收合／展開標籤 | 通過 | Mac 5c64fb1c：點照片空白處標籤淡出並顯示「標籤已收起，點照片展開」，再點展開；放位置模式優先；長按辨識不受影響 | — | — |

## 2026-10-26 M156（法語模擬 #496）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #496 法語模擬的 App 畫面部分 | 通過 | #494 中文殘留：Mac de2a00ff 以法語學習者在英文與法文手機各跑設定、單字本、相片冊、照片詳情、單字詳情、複習正反面，補約 40 條翻譯並加 card496_french_ui_test；#499 詞性冠詞：Mac b3b1af16 讓照片詳情、相機、複習正面也用小寫加冠詞；#505 法語已上線（de2a00ff）。#522 照片標籤義項一致需法語 pack 資料，Mac 這次沒驗 | — | — |

## 2026-10-26 M157（法語模擬 #496）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #496 法語模擬的 App 畫面部分 | 通過 | #494 中文殘留：Mac de2a00ff 以法語學習者在英文與法文手機各跑設定、單字本、相片冊、照片詳情、單字詳情、複習正反面，補約 40 條翻譯並加 card496_french_ui_test；#499 詞性冠詞：Mac b3b1af16 讓照片詳情、相機、複習正面也用小寫加冠詞；#505 法語已上線（de2a00ff）。#522 照片標籤義項一致需法語 pack 資料，Mac 這次沒驗 | — | — |

## 2026-10-26 M158（法語模擬 #496）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #496 法語模擬的 App 畫面部分 | 通過 | #494 中文殘留：Mac de2a00ff 以法語學習者在英文與法文手機各跑設定、單字本、相片冊、照片詳情、單字詳情、複習正反面，補約 40 條翻譯並加 card496_french_ui_test；#499 詞性冠詞：Mac b3b1af16 讓照片詳情、相機、複習正面也用小寫加冠詞；#505 法語已上線（de2a00ff）。#522 照片標籤義項一致需法語 pack 資料，Mac 這次沒驗 | — | — |

## 2026-10-26 M159（法語模擬 #496）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #496 法語模擬的 App 畫面部分 | 通過 | #494 中文殘留：Mac de2a00ff 以法語學習者在英文與法文手機各跑設定、單字本、相片冊、照片詳情、單字詳情、複習正反面，補約 40 條翻譯並加 card496_french_ui_test；#499 詞性冠詞：Mac b3b1af16 讓照片詳情、相機、複習正面也用小寫加冠詞；#505 法語已上線（de2a00ff）。#522 照片標籤義項一致需法語 pack 資料，Mac 這次沒驗 | — | — |

## 2026-10-26 M160（法語模擬 #496）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #496 法語模擬的 App 畫面部分 | 通過 | #494 中文殘留：Mac de2a00ff 以法語學習者在英文與法文手機各跑設定、單字本、相片冊、照片詳情、單字詳情、複習正反面，補約 40 條翻譯並加 card496_french_ui_test；#499 詞性冠詞：Mac b3b1af16 讓照片詳情、相機、複習正面也用小寫加冠詞；#505 法語已上線（de2a00ff）。#522 照片標籤義項一致需法語 pack 資料，Mac 這次沒驗 | — | — |

## 2026-10-26 M161（法語模擬 #496）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| 卡 #496 法語模擬的 App 畫面部分 | 通過 | #494 中文殘留：Mac de2a00ff 以法語學習者在英文與法文手機各跑設定、單字本、相片冊、照片詳情、單字詳情、複習正反面，補約 40 條翻譯並加 card496_french_ui_test；#499 詞性冠詞：Mac b3b1af16 讓照片詳情、相機、複習正面也用小寫加冠詞；#505 法語已上線（de2a00ff）。#522 照片標籤義項一致需法語 pack 資料，Mac 這次沒驗 | — | — |
