# 重定位逐圖審核（卡 #675）

JSON 完整與框大小合格不代表定位正確。所有候選（含 visible=false）必須對照原圖目視檢查。

1. 小批產生提案：`python lexicon/tools/card631_relocate.py --limit 2 --backup-prefix card675`。遵守 Qwen 暫停與 worker 使用限制。`card675_proposals_*.json` 不寫資料。
2. 檢查每個詞與框；visible=false 也要確認無可定位區域。拒絕的圖片保持 approved_digest 空白，不納入寫入檔。
3. 通過的圖片填 reviewer，以工具模組的 review_digest(proposal) 填 approved_digest。這是明確的人工審核記錄，不是品質分數；不得自動批次核准。
4. 通過的完整提案存成 JSON 陣列，執行 `python lexicon/tools/card631_relocate.py --apply --review-file reviewed.json --limit 2 --backup-prefix card675`。不再呼叫模型；驗證原圖及標籤雜湊，鎖定後重驗，寫前備份原標籤與 after_tags。
5. 每批比較 golden 300 詞＋50 圖與 live QC。退步則還原該批備份，先確認現有 tags 等於備份 after_tags，以免覆蓋別人的修改。

細長框與共用框只是疑點，不能自動刪除。既有錯框未因本關卡自動修正，小批目視未通過前不得續跑全庫。
