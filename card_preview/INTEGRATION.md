# 字卡工作室與語言資料後台

## 正式版型發布（卡 #17，取代下方舊版 SQLite 模板說明）

工作室目前透過 `PublishedState` 呼叫後台 `/card-templates`、
`/card-templates/create`、`/card-templates/save`、`/card-templates/publish`。
預設走 `http://127.0.0.1:5173/api` 的既有伺服器端認證代理，
可用 `CARD_TEMPLATE_ADMIN_URL` 指向其他已設定認證的本機代理。
瀏覽器仍須通過工作室的同源與 Preview Token 檢查。
API 無法使用時會顯示錯誤，不會把本機版本冒充正式發布。

草稿與不可變歷史版本改存 PostgreSQL，所有語言共用一個目前發布版本。
舊 `preview.sqlite` 的草稿、版本與問題紀錄保留，未自動遷移或覆寫。
正式發布不修改詞條、學習紀錄或 FSRS。

SQLite 匯出 meta、manifest、App JSON pack 均包含發布版型資訊。
即時詞庫的 fingerprint 包含版型表；發布後最多等既有 120 秒快取到期，
再由 App 的 30 秒同步取得。離線則使用已快取的版型。
尚未發布時沿用 App 原版型。App 保留練習題自身的作答 UI；
共用版型控制一般字卡提示與背面資料區塊。

部署時需讓後台、工作室、serve_app 載入新程式並重建 App。
本次依使用者規則沒有重啟任何執行中的服務。

## 入口
- 工作室：http://127.0.0.1:8772/
- 後台內嵌工作室：http://127.0.0.1:5173/ui/#/card-studio

後台新增 `CardWorkspace.tsx`，App.tsx 只新增一個導覽項目與路由。後台透過 iframe 使用預覽服務，不依賴新增的後台 API，也不更動爬蟲、工作佇列與 PostgreSQL schema。需同時啟動後台前端與 card_preview/start_preview.bat。正式建置 /ui 也包含入口。

後台的「字卡資料檢查」頁（/card-data、admin.html）已拿掉（卡 #36）：完整性檢查、來源授權、問題標記這些 UI 不再出現。`card_preview/server.py` 的 `/api/issues` 與 `state.py` 的問題紀錄仍保留（單元測試仍覆蓋 `state.add_issue`／`state.issues`），但目前沒有任何頁面會呼叫，純粹是資料層。preview.sqlite 既有問題紀錄沒有刪除。

## 模板
新增 `template_names` 表；原有 drafts / versions 不改寫。預設模板沿用原 pair key，新模板使用 pair + UUID。新增模板及其草稿在同一交易建立，每份模板有獨立的草稿和不可變版本。模板與問題仍由預覽服務的 SQLite 管理，並非後台 PostgreSQL 正式發布資料。

`POST /api/templates/create?target=en&native=zh-TW` 接受 name 和可選 layout。GET templates 與 POST save/publish 支援 template_id，省略時仍是原預設模板。所有寫入延用本機來源和 token 驗證。

拖曳區塊到正面、背面、未使用區，或拖到另一區塊前排序。滑鼠及觸控使用 Pointer Events，另保留原生拖曳、選單、勾選與箭頭操作。正面限制提示內容，背面保留答案。新模板預設只啟用提示、答案、發音與例句；複製目前版面則保留所有設定。

## 驗證
25 項 Python 測試通過，涵蓋語言與模板隔離、舊版本保留、錯誤建立不留半成品、HTTP 保護等。前端 TypeScript / Vite build 通過。瀏覽器已實測新增模板、重新載入、保存、拖曳未使用區塊至背面指定位置、後台 iframe 檢查頁及既有問題紀錄。

## 即時文字練習
沒有預先審核的題目檔時，句子填空使用目前義項的實際例句與合法詞形，採輸入核對原句，不宣稱其他填法必然錯誤。相似詞比較用本題單字加 2 個有母語詞義、意思不重疊的語意關係詞，組成 3 組母語／目標語言連線題。原有已驗證題目檔流程仍保留。詞条無可用圖片時，圖片題入口停用。新增即時題型驗證後，共 27 項測試通過；改為連線題並移除回想字卡後共 35 項。
