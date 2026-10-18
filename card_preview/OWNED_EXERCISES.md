# 練習題的個人詞庫範圍

相似詞與圖片選擇題只能使用個人已加入且未封存的詞。字典存在、圖片標籤、關聯詞或已審核題包都不代表使用者持有。至少需要本題單字及兩個合法候選；不足時回傳 `available: false`，不補入全字典候選。

手機端兩種題型共用 `FlashcardSession._ownedExerciseEntries()`，資料來自個人 repository；預覽端即時出題與題包驗證共用 `owned_candidates()`。已審核的選擇式 cloze 也受限制；純輸入 cloze、圖片回想、圖片拖曳沒有新增干擾選項，不套用這次限制。

本機工作室沒有個人使用者登入／手機持有資料，因此既有 GET 預覽不推測持有範圍，相似詞與圖片選擇題會顯示缺少詞庫。串接個人詞庫的呼叫端應以目前使用者、目前語言的有效持有 lexeme IDs 呼叫：

```text
POST /api/exercise/<id>?target=en&native=zh-TW&kind=similar&sense=<sense_id>
Content-Type: application/json
X-Preview-Token: <由 /api/catalog 取得的 token>

{"owned_lexeme_ids": [1, 2, 3]}
```

此本機 API 沿用同源與 token 限制；傳入的是呼叫端個人詞庫快照，不是伺服器全字典查詢結果。未提供、空清單、本題不在清單、篩選後少於兩個候選，皆不出該題。清單不可包含已封存詞。Python 整合可直接使用 `PreviewService.exercise(..., owned_lexeme_ids=ids)`。

回歸檢查：`python -m pytest card_preview/tests -q`。固定資料量測：`python card_preview/tests/audit_owned_options.py --out <報告.json>`，先前凍結的資料位於 `lexicon/logs/agents/card38.owned-fixture.json`；它是從真實字典建立的測試詞庫，並非真實使用者收藏。
