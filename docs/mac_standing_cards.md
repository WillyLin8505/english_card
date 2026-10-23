# Mac 永久卡（常態檢查）

owner 2026-10-22：Mac 驗證過、目前沒有問題的項目轉成永久卡，照下面的頻率重跑；
重跑發現問題就在 `docs/mac_verify_results.md` 寫「不通過」（Windows 會自動開問題回報派工），沒問題就只記一列「通過」。
Windows 上線後可以把這些卡匯入看板當 standing card。工作時段照 M-RULE2（09:30–19:30、00:00–06:00）。

| 卡 | 頻率 | 內容 | 通過標準 |
|----|------|------|----------|
| S1 analyze／test | 每次 Windows sync（有改到 app/） | Mac 上 `flutter analyze`、`flutter test` | 0 error、0 warning；測試全過 |
| S2 模擬器回歸 | 每天一次，或有改到 app/ 時 | iPhone 18 Pro 模擬器新安裝，跑本機 integration test（新手引導、複習 40 張、同字最多 3 次、提示、回報、刪除與復原、背面九項、設定各項、相片冊、圖片集、照片詳情） | 每一項跟上一輪一樣通過 |
| S3 實機記憶體 | 每天一次 | iPhone 12 實機啟動後完全不碰 5 分鐘，再看 JetsamEvent | App 沒被系統結束、沒有 Runner 的 per-process-limit 紀錄 |
| S4 實機流暢度 | 每週一次，或改到複習／照片詳情畫面時 | iPhone 12 profile 版 framePolicy fullyLive 量 6 個情境（單字本、單字詳情、相片冊、相簿內照片、照片詳情、翻卡）的 build／raster | 每個情境 99.5% 以上畫面在 16.7ms 內；開照片詳情、翻卡沒有超過 33ms 的畫面 |
| S5 公開網址健康 | 工作時段內每 3 分鐘 | `https://api.willylinai.com/api/decks` 回 200；`/api/audio` 加 Range 回 206 | 200／206；連續 3 次不是就回報 |
| S6 詞庫資料 | 每次伺服器詞庫 pack 版本變更 | 模擬器同步伺服器 SQLite 詞庫後讀：首字大寫詞條、容易混淆的字預設顯示卻沒有詞條、關聯詞缺中文、非形容詞的比較級／最高級、more／most 形式 | 大寫 ≤ 2、混淆字 0、缺中文 ≤ 20、非形容詞比較級 0、more／most 0 |
| S7 內建錄音 | 每天一次 | 實機用 DeviceSpeaker 播一段內建錄音 | 回傳 true、不改用 TTS |
