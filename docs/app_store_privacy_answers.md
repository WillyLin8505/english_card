# App Store Connect「App 隱私權」問卷建議答案（卡 #1012／問題回報 #1532）

依據：上架版 build（`app/store.json` 只有 DICTIONARY_URL，不帶 POSTHOG_API_KEY、SENTRY_DSN、TAGGING_URL、TAGGING_API_KEY、DEV_TOOLS）、`docs/privacy.html`、`app/ios/Runner/PrivacyInfo.xcprivacy`（本卡已對齊）。全部「不用於追蹤」。

## 第 1 題：是否收集資料？ → 是

## 第 2 題：逐項資料類型（照填）

| Apple 類別 → 項目 | 連結到使用者身分 | 用於追蹤 | 用途 | 實際來源 |
|---|---|---|---|---|
| Contact Info → Email Address | 是 | 否 | App 功能 | 登入帳號 |
| Contact Info → Name | 是 | 否 | App 功能 | 暱稱 |
| Identifiers → User ID | 是 | 否 | App 功能、分析 | 帳號編號；匿名安裝編號（見下） |
| User Content → Photos or Videos | 是 | 否 | App 功能 | 雲端備份、分享牌組、意見回饋截圖 |
| User Content → Other User Content | 是 | 否 | App 功能 | 單字集、備份檔、意見回饋文字 |
| User Content → Customer Support | 是 | 否 | App 功能 | 意見回饋／卡片回報 |
| Usage Data → Product Interaction | 是 | 否 | 分析 | 登入後的複習數、照片數；匿名事件（install、onboarded、first_photo、first_review、open） |
| Usage Data → Other Usage Data | 是 | 否 | 分析 | 最後使用時間 |

說明：
- 匿名安裝事件（預設開、可關，不與帳號合併）本身是「未連結」，但同一類型只要有登入後的一筆會對到身分，Apple 規定該類型整體答「連結：是」，所以上表為「是」。
- **不要勾**：Location、Contacts、Health、Financial、Browsing/Search History、Purchases、Sensitive Info、Device ID（沒用 IDFA／IDFV）、Advertising Data。
- **Diagnostics（Crash Data、Performance Data）：上架版不勾。** 上架版沒有 SENTRY_DSN，`CrashReporting.run` 不會啟動 Sentry，不送任何當機資料。日後若加上 DSN，要先補回 CrashData／PerformanceData（用途 App 功能、未連結、不追蹤）並改這份文件。
- **Usage Data → 來自 PostHog 的分析：** 上架版沒有 POSTHOG_API_KEY，PostHog 不送；Product Interaction 的內容只剩上表的自家伺服器事件。
- 照片辨識在上架版完全在手機上做（Apple Vision），不離開裝置，不算收集。

## 第 3 題：是否追蹤使用者？ → 否
沒有 IDFA、沒有跨 App／網站串接、沒有給資料仲介。不需要 App Tracking Transparency。`NSPrivacyTracking` = false，`NSPrivacyTrackingDomains` 空。

## 第 4 題：隱私權政策網址
`https://api.willylinai.com/privacy`（內容 = `docs/privacy.html`）。

## PrivacyInfo.xcprivacy 與本表的對應
8 項收集資料類型：EmailAddress、Name、UserID、PhotosorVideos、OtherUserContent、CustomerSupport、ProductInteraction、OtherUsageData，全部 Linked=true、Tracking=false。舊檔的 CrashData、PerformanceData 已移除（上架版不收集）。

Required-reason API：
- App 自己的 Swift（AppDelegate.swift 的 LocalVision／TextRecognition／Memory channel）只用 Vision、ImageIO、`task_info`、`os_proc_available_memory`，這些都不在 Apple 的 required-reason 清單內；沒有 UserDefaults、開機時間、磁碟空間。SceneDelegate 沒有相關呼叫。
- Dart 端 `File.stat().modified`（audio_file_cache、photo_store、photo_cache）讀的是 App 容器內自己建立的檔案，宣告 `NSPrivacyAccessedAPICategoryFileTimestamp`，理由碼 **C617.1**。
- 第三方套件（shared_preferences、path_provider、sentry_flutter 等）自帶各自的 privacy manifest，不用在這裡重列。

## 交 Mac 的驗證
1. Xcode → Product → Archive →「Generate Privacy Report」，確認沒有警告，且報告的資料類型與上表一致。
2. 若報告列出我們漏宣告的 required-reason API，把類別與理由碼回報到問題回報 #1532，由 Windows 補。
