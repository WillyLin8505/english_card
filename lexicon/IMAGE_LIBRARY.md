# 圖片庫

入口：`http://127.0.0.1:5173/ui/#/images`。

已接入 Wikimedia Commons：選擇現有 sense 與 Wikidata QID，取得 P18 圖片並補充概念標籤搜尋。候選不自動視為語意相符；必須逐張確認。Open Images、Smithsonian 與 Openverse 尚未接入此頁。

`image_candidates` 保留概念 ID、原始 imageinfo 授權資料及候選資訊。下載到 `media/images/wikimedia_commons/`，PostgreSQL 的 `image_assets` 記錄雜湊、尺寸、作者、授權、原始網址與相對路徑，`sense_images` 綁定詞義。未修改既有資料表。依規格媒體不放 BLOB。

新下載圖片預設 pending / unchecked。後台核准後寫入 `image_reviews`，並允許字卡預覽讀取。拒絕後保留檔案及審核紀錄。取得圖片不等於建立圖片選擇題／物件框題；照片回想及背面圖片可直接使用核准圖片。

API：GET /images、GET /images/senses、POST /images/search、POST /images/candidates/{id}/import、POST /images/{id}/review。沿用 X-API-Key；GET /images/{asset_id}/file 與既有音檔相同為本機媒體展示路由。網路取得限官方 HTTPS 主機，重新檢查逐檔授權、限制下載大小、Pillow 解碼驗證、尺寸驗證、SHA-256 去重、暫存後原子寫入、產生 WebP 縮圖。依規格只接受 CC0、Public Domain、CC BY。

新增依賴 Pillow。啟動方式沿用 lexicon API / frontend。已實際下載 CC0 的 `File:Apples fruit.jpg` 到 apple sense #1，圖片 ID 1，待管理者審核。

驗證：圖片政策測試 3 項、前端 TypeScript / Vite build、實際資料庫候選搜尋與下載、檔案 SHA-256 核對、API list / senses / file，以及瀏覽器圖片展示。批次 worker 及正式匯出整合不在本次變更範圍。
