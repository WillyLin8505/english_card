# Windows → Mac 指令

Windows 端 manager（Claude · Manager）寫，Mac 端每幾分鐘 `git fetch` 看有沒有新項目。
做完一項就在 `docs/mac_verify_results.md` 記結果並 push，然後在下面把那項的 `狀態` 改成 `完成`（同一個 commit）。
問題回報頁 API（`https://api.willylinai.com/api/issues`，`X-API-Key: $ENGLISH_CARD_KEY`）照舊可用：
要 Windows 修的 bug 直接開 `[Mac]` 問題回報最快（會自動派給一個 Claude CLI）。

---

## M1（2026-10-18 22:50）狀態：待做
第 1 輪的 flutter test／analyze 結果收到了：已開問題回報 #294（Windows 也重現 6 個失敗），會派 CLI 修。
1. 等 Xcode 裝好後 `git pull`，繼續第 1 輪的第 4、5 步（`./run_ios_sim.sh`、學習者流程），照 docs/mac_verify.md。
2. 金鑰：owner 會在 Mac 終端機設 `ENGLISH_CARD_KEY`；App 設定頁填打標服務 `https://api.willylinai.com/tag` 與同一把金鑰。
3. 每個新問題開一筆 `[Mac]` 問題回報（API），或寫進 results 檔（Windows 會轉成問題回報）。
4. #294 修好後（GET /api/issues/294 狀態 fixed）`git pull` 重跑 `flutter analyze && flutter test`，結果寫進 results 檔。
