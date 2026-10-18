# Qwen（本機模型）暫停／開始

（從 AGENTS.md 移來，卡 #158；內容不變。）

- 看板 AI 區的 **Qwen** 卡片與其他機器人一樣有「⏸ 暫停／▶ 開始」按鈕；名稱固定為 `Qwen`，狀態寫入同一個 `lexicon/state/paused_agents.json`。
- **暫停時**：`tagger/tagging_server.py` 對**新的** `/tag` `/score` `/translate` 推論回 **503**（`{"error":"Qwen 已暫停","code":"qwen_paused"}`）；已在進行中的請求會做完。標籤佇列（`images.tag_pending`）、tags worker、以及直接打 `:8790` 的品質工具（`quality_ai.py`、`fix_photo_senses.py`）會略過／退避，**不會**把圖片標成 failed。
- tagger 以數秒快取讀取暫停檔（`inference_control.is_qwen_paused`）。按「開始」後清除 `Qwen` 鍵即恢復。
- `/health` 會回 `paused: true|false`。改完 tagger 程式需重啟 tagger 行程才生效；看板後端熱重載或重啟後才看得到 Qwen bot 狀態注入。
