# 卡 #1227：法文例句 Piper

## 本輪狀態
owner 已於 2026-11-20 在 #1679 選 A，20 句試聽核准已執行 approve-listening。
第 2 輪法文 QC 無退步；英文 QC 540.6 秒逾時，追蹤既有 #1601。
listening_reviewed=true、quality_ready=false；仍缺 49,521 句，正式 Piper 0 句。
排除 #1601 並完成 EN/FR 前後快照、quality-gate 後，原夜間流程才可續補。iPad 尚未驗收。
不更動 examples.text；Azure 優先，其次 Piper。未知等級排在 C2 後。

## 試聽
Windows： http://127.0.0.1:5173/ui/card1227-piper.html
離線檔：lexicon/raw-data/card1227_piper/preview.html（20 個 MP3 內嵌，直接開啟即可）。
原文與 hash：preview.json；包含 250、11、25、300、95 mph、ADN、PIN、EPO、省略形。
請實際聽完 20 句，確認全文完整、數字、縮寫及省略形；不能以檔案存在或音訊長度代替。
有疑義先記錄該句，不放行全量；不要更改例句文字。
聽審者確認後才由 Windows 執行：
`python lexicon/tools/card1227_piper_tts.py approve-listening --reviewer "實際聽審者" --notes "20 句與數字／縮寫／省略形的實際結論"`

## 品質與夜間續跑
QC 都需有成功輸出的報告；英文用 v1（300 詞＋50 照片），法文用 fr_v1。
跑 `qc.py check --live --out ...`，法文另加 `--target fr --native en`，後測加 `--before 前測路徑`。
全部比對無退步後：
`python lexicon/tools/card1227_piper_tts.py quality-gate --en-before EN_BEFORE --en-after EN_AFTER --fr-before FR_BEFORE --fr-after FR_AFTER`
每個 dispatch_tick 呼叫 `card1227_piper_tts.py night`，僅 01:00–06:30 開始合成。
每批不超過 200，三個 tick 分別做法文批前 QC、合成＋寫入、批後 QC；最後一步可在白天完成。
一個 ONNX CPU 執行緒，繼承 ai_watch job，不使用 GPU/BREAKAWAY。resource_guard 過載或過期就等待。
共用 piper.lock；若英文 Piper worker 還活著就等，不會同時合成。英文既有下載不受影響。
每個前景步驟有上限（合成 450 秒、QC 480 秒），夜間下次 tick 續跑，不需另開 CLI。
`report` 列全庫缺口、各級數量、音檔秒數／bytes、失敗嘗試、合成耗時；量測經 heavy_lock 執行。
失敗或逾時的 QC 未完成前不會開始下一批；若 QC 有退步，僅還原該批並寫 paused.json。

## 備份與還原
寫入前記錄 insert_journal.jsonl（先前不存在、URL、path、sha256）；不覆寫既有音檔資料列。
`python lexicon/tools/card1227_piper_tts.py rollback`
僅刪 journal 所有、hash 未改、fr/speaker 相符的資料列，先將資料列與 MP3 備份到 rollback_時間/。
不碰英文 Piper 或 Azure；還原後 paused.json 阻止再次產生。檢查完再另行解除暫停。
程式修改前備份在 raw-data/card1227_piper/code_before/，不要整批覆寫共用工作目錄。

## 授權查核（2026-11-19）
SIWIS French Speech Synthesis Database，作者 Junichi Yamagishi、Pierre-Edouard Honnet、Philip Garner、Alexandros Lazaridis（2017）。
資料集官方 README 與 End-user Licence 均寫 CC BY 4.0；Piper siwis MODEL_CARD 亦如此。
- 資料來源：https://doi.org/10.7488/ds/1705
- 官方 README：https://datashare.ed.ac.uk/server/api/core/bitstreams/a15e775d-abd6-496f-815b-68d3a9229e90/content
- 授權：https://creativecommons.org/licenses/by/4.0/
- 聲音模型：https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD
- 舊 Piper：https://github.com/rhasspy/piper/blob/master/LICENSE.md （MIT）
- 本機實際套件 piper-tts 1.8.0：GPL-3.0-or-later，https://github.com/OHF-Voice/piper1-gpl
App 僅提供產生後音檔；資料來源與授權頁及 audio_assets 保留資料集出處、作者、CC BY 4.0 及 AI 合成／MP3 轉換說明。
不要把目前執行的 1.8.0 引擎標為 MIT。原始例句授權維持原值。

## iPad 驗收（待做）
卡 #1227：先完成 20 句聽審；首批資料寫入、匯出更新後，再驗法文例句播放鈕與 Piper 音檔播放。
檢查一筆 Azure 既有例句仍使用 Azure，一筆原無發音例句使用 Piper；查看資料來源與授權頁。
Mac 結果列第一欄寫 #1227，另有「結果」「裝置」，裝置以 owner 的 iPad A16 為準。
