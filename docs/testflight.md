# TestFlight（M286，owner 2026-10-27）

目前狀態：**等 owner 加入 Apple Developer Program**。這台 Mac 只有免費的 Apple Development 憑證（Personal Team，描述檔 7 天過期），不能上傳 TestFlight。

## owner 要自己做的（Mac 不代填、不代付）
1. 到 https://developer.apple.com/programs/enroll/ 用 sssss971412@gmail.com 加入 Apple Developer Program（個人，每年 US$99），等 Apple 核准（通常 1–2 天）。
2. 核准後登入 https://appstoreconnect.apple.com ，同意所有條款（協議、稅務與銀行可之後再填，TestFlight 內部測試不需要）。
3. 我的 App → 「＋」新增 App：平台 iOS、名稱（例如 Photo English）、主要語言、Bundle ID 選 com.willylinai.photoflashcard、SKU 隨意（例如 photoflashcard）。
4. 使用者與存取 → 整合 → App Store Connect API → 產生一把金鑰（存取權「App 管理」），下載 AuthKey_XXXX.p8（只能下載一次），記下 Key ID 和 Issuer ID。
5. 把 .p8 放到這台 Mac 的 ~/.appstoreconnect/private_keys/，Key ID 和 Issuer ID 告訴 Mac（不要貼金鑰內容）。
6. TestFlight → 內部測試 → 建一個群組（例如 owner），把自己加進去，勾「自動發佈新版本」。iPhone／iPad 安裝 TestFlight App，用同一個 Apple ID 登入。

## Mac 之後每次上傳
`ASC_KEY_ID=… ASC_ISSUER_ID=… app/tool/testflight.sh`：Release 版、build 號＝git commit 數（自動遞增）、上傳後 App Store Connect 處理約 10–30 分鐘，內部測試群組自動拿到，手機在 TestFlight 自動更新。
