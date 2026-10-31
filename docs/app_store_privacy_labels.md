# App Store 隱私標籤（App Privacy）要勾的項目（card #911）

依 docs/privacy.html。皆「不用於追蹤（Tracking: No）」。

| 資料類型 | 勾 | 連結到使用者 | 用途 |
|---|---|---|---|
| Contact Info → Email Address | 是（登入時） | 是 | App Functionality |
| Contact Info → Name（暱稱） | 是 | 是 | App Functionality |
| User Content → Photos or Videos（分享／雲端備份） | 是 | 是 | App Functionality |
| User Content → Other User Content（單字集、備份檔） | 是 | 是 | App Functionality |
| Identifiers → User ID | 是 | 是 | App Functionality |
| Usage Data → Product Interaction（複習數、打開照片數、相片冊名稱） | 是（登入時） | 是 | Analytics |
| Usage Data → Product Interaction（匿名：安裝、完成引導、第一次拍照、第一次複習、每日開啟） | 是（預設開，可關閉） | 否 | Analytics |
| Identifiers → User ID（隨機安裝編號，不與帳號或 Email 合併） | 是（預設開，可關閉） | 否 | Analytics |
| Usage Data → Other Usage Data（最後使用時間） | 是 | 是 | Analytics |
| Diagnostics → Crash Data（若啟用崩潰回報） | 依實際 | 否 | App Functionality |
| Location / Contacts / Health / Financial / Browsing / Search | 否 | — | — |

匿名安裝與留存（card #914）跟上面「登入才傳」的使用數字是兩條：沒登入也會送，只有隨機安裝編號與事件名稱、日期，預設打開、設定可關，不跟 Email 合併。App Store 同一種資料若有任何一筆會對到身分，該類型仍答「連結到使用者：是」（帳號與登入後的使用數字已經是）。`app/ios/Runner/PrivacyInfo.xcprivacy` 已宣告 Product Interaction 與 User ID（Analytics、未連結、不追蹤），這項匿名事件落在這兩種裡，沒有新增資料類型。
