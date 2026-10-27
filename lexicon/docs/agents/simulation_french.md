# 法語使用者模擬（native=en、learning=fr）

沿用 `simulation_usability.md`。這是檢查卡；新根因開問題回報，不在此卡大量改詞庫或開放正式語言。

1. 讀本卡與關聯問題的 decision、上一輪 result.md。不要讀完整 pack 或 events。
2. `python app/test/simulation/run_round.py --lang fr --only fr_learner_a1,fr_learner_b1 --no-posthog`。
   記下輪次 N，再跑 `python app/test/simulation/run_round.py N --lang fr --only card_draw,fr_media --no-posthog`。
   每個測試最多 9 分鐘；分批前景執行，不呼叫 Qwen。
3. 同輪共用 serve_app `/api/lexicon?target=fr&native=en` 的快照；產物在 `app/build/rounds_fr/N/`。
   `summary.json` 含程式通過數、全庫欄位覆蓋與本地事件數／rating／平均作答毫秒。
   比較上一輪；抽卡事件與 A1/B1 畫面操作分開統計，毫秒是測試時間，不是真人速度。
4. 檢查 A1/B1 JSON 的 onboarding、tabs、checks、chinese_in_english_ui。
   每輪完整讀至少 3 個同時有 front/back/detail 的字，對照 pack 統計畫面例句／近義詞／相關詞數。
   看 `fr_review_back.png`、`fr_word_detail.png`（0.5 倍；為 Flutter widget 畫面，非實機）。
   非 Windows 可設 `SIM_FONT` 指向支援中法英文的字型。
5. `fr_media.json` 檢查全庫可顯示 pins 與 25 張圖片詳情頁、實際卡片集清單快照。
   `card_draw.json` 是真實法語詞庫的 8 組 7/30 天模擬；核對 language=fr、詞樣本、覆蓋率、連續重複、最多重複與 top5 占比。
6. 分別判斷新手引導、相機、圖片標籤、複習正反面、單字本、相片冊、卡片集、設定、抽卡分布。
   測試程式成功不等於學習需求通過：缺冠詞、變位人稱、翻譯、錯誤語言、混入中文均需列出。
   每頁只依本輪 JSON／截圖判斷，不沿用上一輪結論。「英文裝置引導／設定中文殘留」已在 55af1b20
   修好（模擬傳 uiLanguage: 'en'；Mac M242：A1/B1 皆 0 個中文畫面），本輪 chinese_in_english_ui 為 0 就寫通過、不要再列入「需要 Mac」。
   尚未開放法語時保留正式設定，以 inMemory(fr/en) + pack 直接載入測試；記錄正式上線的缺口。
7. 至少 1–3 項具體 UX 建議；先找重複回報，再用 5173 `/api/issues` 建立（reporter=claude-simulation-fr）。
   已有回報補本輪證據，不另開同根因。需要修改資料先量全庫、備份並前後跑 golden/QC。
8. 寫本卡 result.md（≤40 行）：每頁通過／不通過、輪次與數字、issue IDs、UX 建議、限制與下一輪工作。

限制：圖片 bytes 在 widget test 不會從網路下載，不能把圖片載入失敗當成正式服務故障。
語音測試核對 Speaker 呼叫的 language/audio URL，不能宣稱已聽過音檔或裝置 TTS。
相機只測畫面；新照片辨識、實機拍照與音訊播放仍需裝置驗收。卡片集只重播清單，不把未過濾的英文集匯入法語帳戶。
預設 `--no-posthog` 避免讀取憑證與外送；本地事件已足夠供每輪比較。
