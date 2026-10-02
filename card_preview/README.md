# 卡片預覽工作室

實作 `spec-01-data-sources.html` 的成品字卡預覽。主要內容位於 `card_preview/`；後台前端新增了字卡檢查與工作室入口。完整性檢查及問題標記現在集中於語言資料後台。整合方式、命名模板與儲存位置請見 [INTEGRATION.md](INTEGRATION.md)。

## 啟動

在專案根目錄執行：

```powershell
python -m pip install -r card_preview/requirements.txt
python card_preview/server.py --port 8772
```

瀏覽 http://127.0.0.1:8772/ ，或雙擊 `start_preview.bat`。使用獨立 8772 埠，不停止既有 8770／8765 服務。

連線設定沿用 `lexicon/.env`，不修改該檔；也可透過 `CARD_PREVIEW_DATABASE_URL` 指向專用唯讀帳號。媒體目錄沿用 `LEXICON_MEDIA`。每個 PostgreSQL transaction 都設為 **REPEATABLE READ, READ ONLY**，只 rollback、不 commit。沒有任何學習狀態或正式詞庫寫入路由。

## 已提供

- 同一拼字只顯示一列、一張字卡（規格 07「同一拼字的不同詞性與用法」）。詞庫目前仍把每個詞性存成獨立 lexeme，預覽讀取時依 `language + normalized` 合併：清單以「名詞・動詞」標示用法；詞義選單與背面逐義釋義按詞性分區；例句、詞形、關係詞、發音、圖片合併去重，每項保留來源 `lexeme_id`。題目依所選詞義所屬的詞性 lexeme 產生；最常用的用法（已完整匯入、有翻譯、例句最多）排第一。
- 目標語言／母語方向、單字／母語／ID 搜尋、已匯入／有母語釋義／全部資料範圍、分頁、上一張／下一張／全範圍隨機抽样。
- 字卡正面提示（「母語說明＋照片」顯示在圖片下方）：詞性、母語提示、首字母與底線；正面不顯示答案、例句或來源。短字至少遮住一個字母，片語保留空格。
- 背面：單字、IPA、真人單字音檔、逐義釋義、例句與翻譯、词形、各類關係詞、詞源、來源與授權；空區塊隱藏。
- 手機直向／橫向／桌面預覽、翻面、手動／答案後自動播放、同義項圖片切換。
- 本機模板區塊排序（拖曳及上下按鈕）、正反面位置、隱藏、數量、預設收合、展開全部、每類關係詞獨立上限。
- 本機草稿保存、不可變預覽版本、歷史版本切換／複製為草稿再發布。**發布預覽版本不等於發布正式 App。**
- 唯讀載入後台 `card_templates`／`card_template_versions`；僅接受下述 v1 layout，未知格式明確拒絕，絕不靜默代用。
- 五種模板入口：句子填空、看圖選單字、相似詞比較、母語說明＋照片、拖曳單字到圖片。回想字卡模板已移除。相似詞比較依問題 #27 的產品決定，顯示一個有母語翻譯的真實情境句，遮住目前單字，再提供本題單字與 2 個有詞彙關係依據的相近詞；使用者選出在句中最自然的答案，作答後才顯示完整原句、各詞母語詞義與差異說明。湊不到 2 個相近詞或沒有合格例句時列出原因，仍可查看現有背面資料。
- 精確義項、例句、關係詞缺漏清單；問題標記連結詞條、義項、欄位／媒體、模板與版本。

## 與 Claude 的整合分界

Claude 可繼續負責 `lexicon/backend`、`worker`、資料表、匯入及正式發布。此模組只讀其已存在的正規化資料表。

`card_preview/data/preview.sqlite` **只**保存預覽草稿、版本與 QA 問題；不寫入主資料庫的 `card_templates`、`card_preview_issues` 或 `ready_for_export`。這是為避免兩邊同時修改 schema 的明確暫時整合界線。後台接手時可透過此模組 API 匯入這些 metadata，或替換 `state.py` 為正式儲存 adapter。

這個畫面使用「即時建置資料」，顯示最新發布資料包資訊作參考，並不聲稱目前資料等同於某個歷史資料包。若要重現舊資料包，需對接正式快照／匯出服務。目前不修改 Flutter renderer，因此跨平台像素一致性仍須整合驗證。

图片只接受已核准、已下載且授權為 CC0／Public Domain／CC BY 的本機資產；僅從受限媒體端點供應，沒有任意 URL 代理。沒有已核准圖片時不使用相簿示範圖冒充詞義圖片。

## 預覽 API

讀取：`GET /api/catalog`、`/api/words?target=en&native=zh-TW&scope=full&q=apple`、`/api/card/1?target=en&native=zh-TW`、`/api/exercise/1?target=en&native=zh-TW&kind=similar&sense=1`、`/api/templates?target=en&native=zh-TW`。

僅寫預覽 metadata：`POST /api/templates/save`、`POST /api/templates/publish`、`POST /api/issues`，必須帶語言方向 query、JSON body 與 `X-Preview-Token`（由同源 catalog 取得）。這些不是正式後台的同名 API，也不會建立 exercise attempt 或 review log。

### 模板格式 v1

格式由 `domain.default_layout()` 定義：`schema_version: 1`、`sections`（每區 `key, side, visible, limit, collapsed, expand_all`）、`relation_limits`、`show_ratings`、`show_translation`、`show_sources`。每個區塊必須存在且不可重複；正面只允許 `hint`／`meaning`；`answer` 必须保留背面。正式後台可將這份 layout 放入現有模板版本資料欄位，即可唯讀預覽。

### 已驗證練習的接入契約

圖片／選項生成與語意審核由資料端提供；本模組不猜測答案唯一性。將通過審核的 **ID 參照包** 放入 `exercise-input/{lexeme_id}-{sense_id}-{kind}-{native_language}.json`。請勿提交示範詞條到正式資料庫。

必要欄位：

```json
{
  "id": "your-reviewed-exercise-id",
  "kind": "cloze",
  "target_language": "en",
  "native_language": "zh-TW",
  "lexeme_id": 1,
  "sense_id": 1,
  "lexeme_updated_at": "必須與 GET /api/card 回傳值完全一致",
  "example_id": 1,
  "answer_form": "資料庫中合法詞形",
  "validation": {
    "status": "approved",
    "reviewer": "審核者識別",
    "checked_at": "ISO 時間",
    "reason": "為何只有一個答案成立"
  },
  "options": [
    {
      "lexeme_id": 1,
      "sense_id": 1,
      "lexeme_updated_at": "選項詞條更新時間",
      "form": "資料庫中合法詞形",
      "reason": "適用情境或不適用於本題的原因"
    }
  ]
}
```

上面是**格式說明，不是可用題目**。cloze／photo_choice 需 3–5 個選項；similar 需剛好 3 個（含本題單字），三個母語詞義不可重疊，不需要例句與 `answer_form`；相似詞必須有資料庫關係依據。正確選項必須恰一個，詞性相容、CEFR 相差最多一級，義項母語配對完整。cloze 的例句必須明確綁定選中 sense，目標詞形在句子中恰好出現一次。詞條或選項更新時間不同時拒絕舊驗證。

photo_choice／drag 另帶 `sense_image_id`，必須是目前義項的核准圖片。drag 的每個 option 加 `box: [x,y,width,height]`（0–1 正規化座標），1–5 個詞籤；支持滑鼠拖曳與點詞籤再點區域。photo_recall 不需包，當同義項已有翻譯及核准圖片即可使用。

**目前資料端尚未提供核准圖片和已驗證選項包，因此相關模板會顯示缺項。** 這不是以假資料展示的完成狀態。題目總量統計、正式學習模板版本庫、匯出資格及 Flutter 發布由後台流程整合；預覽目前版本選擇控制共用字卡 layout。

## 驗證

```powershell
python -m unittest discover -s card_preview/tests -v
node --check card_preview/static/app.js
```

測試涵蓋正面洩漏限制、必留答案、數量限制、翻譯逐項缺漏、審核圖片、答案唯一性／詞性／義項／更新版本驗證、拖曳框、語言隔離、不可變模板版本、CSRF 及不建立學習資料。測試 fixture 僅存在測試程式，不會載入預覽頁或正式資料庫。
