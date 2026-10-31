# App Store 隱私標籤草案（卡 #258／問題回報 #268）

查證來源：Apple「App Privacy Details」（developer.apple.com/app-store/app-privacy-details，2026-10-18 讀取）。「Collect」是指資料離開裝置，而且留得比即時處理該次請求更久。追蹤是指拿去跟別家 App／網站的資料串來做廣告，或交給資料仲介。

## 要填的標籤（建議照填，不要用「可選擇不揭露」豁免）

PostHog 的 `distinct_id` 是安裝時產生、存在 Hive 的隨機代號，每次事件都帶著。它不是 IDFA／IDFV（那才是 Device ID），但是 Apple 對 User ID 的定義包含 “assigned user ID … that can be used to identify a particular user”。所以 **Identifiers › User ID 要填**。沒有帳號、姓名、電子郵件，也不跟裝置廣告碼合併，因此選「未連結身分」。

| 資料類型 | 用途 | 連結身分 | 用來追蹤 |
|---|---|---|---|
| Usage Data › Product Interaction | Analytics | 否 | 否 |
| Identifiers › User ID | Analytics | 否 | 否 |

| Diagnostics › Crash Data | App Functionality | 否 | 否 |
| Diagnostics › Performance Data | App Functionality | 否 | 否 |

（卡 #913）Sentry 當機回報：只有填了 `SENTRY_DSN` 的 build 才啟用，且「分享使用統計」打開才送。內容是錯誤類型、堆疊、App 版本與 build 號、OS 與裝置型號（Sentry 會附裝置型號、記憶體等，歸在 Performance Data 較保險）。不送照片、單字、email、使用者、操作軌跡、錯誤訊息文字。Sentry 不當作追蹤（不串其他 App）。沒填 DSN 的 build（含目前的 TestFlight）不用勾這兩列。

Product Interaction 涵蓋：`app_opened`、`$screen`、`onboarding_completed`（學習語言、母語、程度、程度來源）、`photo_added`、`word_added`（詞性）、`card_reviewed`（評分、題型、對錯、hints、duration_ms、scheduled_days）、`review_started`／`review_finished`。

Data Used to Track You：無。不需 ATT。`app/ios/Runner/PrivacyInfo.xcprivacy` 已設 `NSPrivacyTracking=false`、`NSPrivacyTrackingDomains` 空、上述兩種資料類型（Analytics、未連結、不追蹤）。Info.plist 沒有 `NSUserTrackingUsageDescription`。

「產品改善、使用者明確打開、可隨時關閉、不影響功能」這組條件理論上可以選擇不揭露。因為事件帶著持久的 User ID，「未連結身分」站得住的前提是之後不把這個代號跟帳號或裝置身份接回去。為避免審查來問，仍建議照上表揭露。

## 照片不要填進 Photos or Videos

辨識時照片會離開裝置，但只在伺服器記憶體裡處理該次請求，不寫成照片檔（`tagger/tagging_server.py` 的 `prepare_image` 用記憶體緩衝）。依 Apple 的 Collect 定義，即時處理完就丟的照片不算收集。磁碟上留的是辨識結果的文字快取（單字與分數，鍵是雜湊，不含照片）。政策已寫明這一點。若審查把文字快取當成使用者內容，再補 Other User Content、用途 App Functionality、未連結、不追蹤。

## App Store Connect 要貼的網址

1. 政策網址（owner 已決定）：`https://api.willylinai.com/privacy`，內容就是 `docs/privacy.html`，聯絡信箱已填 sssss971412@gmail.com。不動 willylinai.com 根網域與其 DNS。
2. 放置方式：`serve_app.py` 回 `/privacy`（不需金鑰），走既有的 api.willylinai.com tunnel 規則，不需新增 DNS 或 tunnel 規則。serve_app 載入這版程式後（重啟一次）即生效。
3. App Store Connect → App 資訊 → 隱私權政策 URL 貼上那個網址。App 內入口是設定頁「查看隱私權政策」（5.1.1(i)）；開關是「分享使用統計」，預設關（5.1.1(ii)）。
