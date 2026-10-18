# Mac / iPhone 模擬器驗證（給 Mac 上的 Claude Code session）

目的：在 Mac 的 iPhone 模擬器實際跑原生 App，確認 Windows 那邊十幾個 Claude CLI 的改動在 iOS 上正常。
後端在 owner 的 Windows 筆電，經 `https://api.willylinai.com`（Cloudflare Tunnel）連過去。

## 每一輪
1. `git pull`（repo：WillyLin8505/english_card，Mac 路徑 `/Users/willylin/vibe_coding flash card`）。
2. 環境：Xcode、Flutter、CocoaPods（缺什麼 `app/run_ios_sim.sh` 會說）。第一次跑 `flutter doctor`，把問題列出來。
3. `cd app && flutter analyze && flutter test`，記下失敗。
4. `./run_ios_sim.sh` 在 iPhone 模擬器跑。打標金鑰由 owner 在 App 的「設定」輸入（或掃 QR code，卡 #280），不要寫進檔案。
5. 照學習者會做的事走一遍，每步截圖（縮小存檔即可）：
   - 首次啟動與新手引導；設定頁填網址／金鑰（或 QR code）。
   - 詞庫同步：資料庫分頁要有字；不能常駐顯示技術性同步文字。
   - 拍照／選照片 → 打標（經 api.willylinai.com，可能要 1–2 分鐘；超過 100 秒會被 Cloudflare 切斷，記下來）。
   - 複習：正面要標出單字在圖中的位置（不洩漏答案）；背面：自動播英式＋美式發音、沒有 A2 等級字、沒有「照片情境」字、例句間距緊、詞形變化全列、同義／相關／近音／拼字相近不留右半邊空白、構詞拆解字塊、圖片左右滑、點英文字可連到單字詳情；刪除卡片有確認與復原。
   - 學習洞察（#277）、備份還原（#278）、原圖遺失改用同字其他圖（#279）、隱私權設定與政策頁（#268）、資料來源頁（#269）。
   - 照片載入速度（#252）：捲動相片冊、翻卡是否卡頓。
   - 音檔與詞庫圖片在原生 iOS 能載入（#270）。
6. 每個問題寫進 `docs/mac_verify_results.md`（日期、步驟、預期、實際、截圖檔名、嚴重度），commit 並 push
   （只 commit 這個檔與截圖資料夾 `docs/mac_verify_shots/`，不要改 App 程式碼）。
   Windows 端的 manager 會把它轉成問題回報並派工。看板 127.0.0.1:5173 只在 Windows 上，Mac 連不到。

## 規則
- 不要修 App 程式碼（Windows 上的 CLI 同時在改，會衝突）；只驗證與回報。
- 不讀、不寫任何金鑰（*.local.json、.api_key）。
- 繁體中文、台灣用語。
