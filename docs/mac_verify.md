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
6. **跟 Windows 溝通：git ＋ 問題回報 API 兩條都用**（owner 10/18）：
   - git：結果寫 `docs/mac_verify_results.md` 並 push；Windows 的指令在 `docs/mac_inbox.md`，每幾分鐘 `git fetch` 檢查，
     做完把該項狀態改成「完成」並 push。
   - 問題回報 API（下面）：要 Windows 修的 bug 直接開 `[Mac]` 問題回報，會自動派工。
   - 網址 `https://api.willylinai.com/api/issues`，每個請求帶標頭 `X-API-Key: $ENGLISH_CARD_KEY`
     （owner 在 Mac 的終端機設環境變數 `ENGLISH_CARD_KEY`，不要寫進檔案或 commit）。
   - 開問題：`POST /api/issues`，JSON：`{"kind":"bug"|"todo"|"decision","severity":"high|medium|low","area":"app",
     "title":"[Mac] …","detail":"步驟／預期／實際／iOS 版本與模擬器機型","reporter":"Mac Claude"}`。
     開了就會自動派給 Windows 上的一個 Claude CLI 修，不用另外通知。
   - 看回覆：`GET /api/issues/<id>`，看 `status`（fixed＝已修）、`resolution`、`history`；修好後 `git pull` 再驗一次，
     沒修好就 `PUT /api/issues/<id>` 加 `{"status":"open","note":"[Mac] 重驗仍失敗：…","by":"Mac Claude"}`。
   - Windows 給 Mac 的請求：標題開頭是「[給 Mac]」、reporter 是「Claude · Manager」；先 `GET /api/issues` 找
     `status` 不是 fixed 的「[給 Mac]」項目來做，做完 `PUT` `{"status":"fixed","resolution":"[Mac] …","by":"Mac Claude"}`。
   - 先 GET 再 PUT，只在要改狀態時送 status（Windows 端的 AI 也在改同一份清單）。
   - 截圖放 `docs/mac_verify_shots/`，commit 並 push（只 commit 截圖，不要改 App 程式碼），在問題的 detail 寫檔名。

## 每張卡都要在 iPhone 上驗證（owner 10/18）
- Windows 每完成一批改到 App 的卡，`mac_sync.py` 會在 Windows 跑過 flutter analyze＋test 後 push，並在
  `docs/mac_inbox.md` 加一項 M<n>，列出要驗的卡。每一項都要：`git pull` → iPhone 模擬器跑 → 每張卡照它的結果實際操作 →
  results 檔每張卡一列（第一欄卡號 #N、「結果」欄寫 通過／不通過／注意、「裝置」欄寫 iPad 或 模擬器，＋原因＋截圖；階段依這幾欄自動前進，卡 #916），不通過的開 `[Mac]` 問題回報（標題寫卡號）→ 把 M 項狀態改「完成」並 push。
- 實機：owner 把 iPhone 接上 Mac 時，也用 `flutter run -d <iPhone>`（`flutter devices` 找 id）跑一次。第一次要在 Xcode
  打開 `app/ios/Runner.xcworkspace`，Runner → Signing & Capabilities 選 owner 的 Apple ID Team（Bundle ID
  `com.willylinai.photoflashcard`），iPhone 上「設定 → 一般 → VPN 與裝置管理」信任開發者。簽章要 owner 本人登入，不要代填密碼。

## 規則
- 不要修 App 程式碼（Windows 上的 CLI 同時在改，會衝突）；只驗證與回報。
- 不讀、不寫任何金鑰（*.local.json、.api_key）。
- 繁體中文、台灣用語。

## 報告格式（卡 #918，owner 10/31）

結果只寫進 `docs/mac_verify_results.md`，不靠對話。每輪一個 `## 日期 M編號（模擬器或 iPad）` 標題，下面是這張表，欄位固定：

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 | 裝置 |

- **卡／步驟**：第一格寫卡號（`#930（#1180）…` 或 `M10`）。新發現沒有卡號就寫一句話名稱，系統會自己開卡。
- **結果**只能是三種開頭：`通過`（推進階段）、`不通過`（自動開 Windows 問題回報，回到派工）、`注意`（結果不是壞掉但有發現，自動開低嚴重度的 `[Mac 注意]` 待辦）。
- **裝置**（可省略）：`模擬器` 或 `iPad`；沒寫時系統從「實際」文字猜，猜錯會讓階段過早通過，建議一律寫。
- 「注意」只用在要 Windows 處理的發現。只是「還沒驗、等下一輪、owner 已決定不動」直接寫在實際欄，系統看到這些字樣不會開卡。
- 同一項（第一格相同）還有未結案的問題時，不會重複開；修好後再驗，寫新的一列。
- Mac 只驗證、不改程式。發現要改的東西，只寫進上表。
