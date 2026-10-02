# 字卡 App 自動詞庫更新

執行 `python serve_app.py --port 8123`（或 `start_app.bat`），開啟 http://127.0.0.1:8123/。
請使用這個啟動方式取代 `python -m http.server`；後者只提供靜態網頁，沒有詞庫 API。

App 啟動及使用中每 30 秒檢查 PostgreSQL 詞庫。後台完成來源擷取、重新整理或人工修正後，內容自動更新，不必重新匯出或編譯。首次取得完整詞庫約需 10～15 秒；內容未改變時使用版本檢查避免重複傳輸。資料庫連線資訊沿用 `lexicon/.env`，金鑰與密碼留在伺服器。

離線時使用該瀏覽器上次保存的詞庫；設定頁可查看狀態並立即重試。個人修改的欄位優先，更新不改動字卡識別碼、複習排程或歷史。字卡與照片仍存於瀏覽器，這不是跨裝置帳號同步，也不會把個人修改寫進共用詞庫。

只有已有翻譯、符合程度的資料才會出現在延伸學習區；未補齊的內容清楚標示，不用不可靠的詞彙填滿頁面。前台篩選不會刪除後台原始資料。

網頁版未指定辨識網址時，會自動使用同一個 App 服務的 `/tag`。伺服器轉接本機 `127.0.0.1:8765`，從 `TAGGER_API_KEY` 或 `tagger/.api_key` 讀取金鑰；瀏覽器不需要保存金鑰。請保持 Ollama 與 `tagger/tagging_server.py` 啟動。自訂辨識網址仍優先使用；清空網址即可恢復自動連線。辨識服務離線時，照片保留在待處理佇列並定期重試。

驗證：`flutter analyze`、`flutter test`（在 app 目錄）；`python -m pytest tests/test_app_server.py -q`（專案根目錄）；`python -m pytest tests/test_app_live_sync.py -q`（lexicon 目錄，使用獨立的 lexicon_test 資料庫）。
