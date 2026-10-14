# 詞庫品質系統設計（根因分析 + 自動偵測／修正架構）

> 2026-10-14 · 數字來自 `lexicon/tools/quality_diagnose.py`（唯讀）與 #174–#200 的調查。
> 目的：停止一字一字修補，把錯誤擋在進入點，並自動偵測、分級修正。

## 1. 資料來源（provenance）

| 資料 | 來源 | 數量 | 備註 |
|---|---|---|---|
| 詞條 lexemes | Kaikki（Wiktionary）+ 關係詞 | full 3,671；**stub 46,928** | stub 中 45,013 是「關係詞目標」自動建立 |
| 英文義項 | Kaikki 13,129、OEWN 30 | 13,160 | 義項順序 = Wiktionary 原順序（含多個詞源） |
| 中文義項 | **AI（Qwen）8,843**、Kaikki 2,462、ECDICT 192 | 11,499／13,160 | 77% AI；1,661 個義項無中文；215 個 full 詞條完全沒中文 |
| 第一義項中文是 AI | — | 1,791／3,671 | 主義項近半是 AI 翻譯 |
| CEFR（full） | CEFR-J 879、**頻率估計 1,191** | 2,070 | 58% 是估計值 |
| CEFR（stub） | 關係詞的頻率估計 | **37,563** | stub 本不該有等級 |
| 例句 | Tatoeba 23,201、AI 8,396、Kaikki 3,207、OEWN 1,422 | 36,226 | Tatoeba 以字串比對，不知道義項 |
| 圖片 | Wikimedia Commons | 1,840 | 已打標 771、**未打標 1,069** |
| 照片標籤綁定 | `images.share()` | approved 4,173／pending 1,486／rejected 614 | 綁到 AI 譯義項 759；非主義項 320 |

## 2. 根因（依問題類別）

| # | 問題 | 進入點（程式） | 錯誤假設 | 缺少的驗證 | 規模 |
|---|---|---|---|---|---|
| R1 | 空殼 stub、雜訊詞條（#181 #182） | `materialize.py` L258–278：每個同義/衍生詞都 `lexeme_for(create_stub=True)` | 「關係詞目標也是可學的字」 | 詞條進 pack 前沒有「至少 1 個義項 + 中文」的契約 | 46,928 stub；16,613 詞性 unknown |
| R2 | CEFR 不合理（#183 #196） | 同上 L277 `tgt.cefr = it["cefr"]`；`base.py` 頻率估計 | 「頻率 → CEFR」可代替官方等級 | 沒標記等級來源；照片標籤與詞卡各自取等級 | stub 帶等級 37,563；full 58% 估計；標籤/詞卡不一致 296 |
| R3 | 義項順序、罕用義項在前（#184） | Kaikki 匯入照原順序；多詞源合併 | 「Wiktionary 第 1 義 = 最常用」 | 無義項排序規則／AI 譯義項沒降權 | 主義項 AI 1,791 |
| R4 | 照片標籤義項錯（#195：螢幕→屏風） | `images.share()`：**一律取 ordinal 0 的義項**，`semantic_score=0.95` 寫死；照片若已有核可就自動核可 | 「第一義項就是照片裡的意思」 | 沒有用同圖上下文選義；沒有「綁定義項須有中文、非 low」契約 | 4,173 綁定中 AI 義項 759、無中文 17 |
| R5 | 缺中文／中文品質差（#187） | `adapters/ai.py` 批次翻譯補洞 | 「AI 譯一次就可以」 | 無 AI 譯文抽查、無與 ECDICT 交叉比對 | AI 8,843（77%） |
| R6 | 例句不符（#185 #193） | Tatoeba 以字串比對、AI 例句 | 「含該字串 = 該義項的例句」 | 無「完整句／含詞形／對應義項」驗證 | not_sentence 553、missing_lemma 234、odd_name 981 |
| R7 | 圖片不符（#186 #192） | `images.match_concept` 關鍵字分數 + Commons 搜尋 | 「Wikidata 標題比對 = 有代表性」 | 相關性檢查沒接到匯入流程；Ollama 被佔滿 | pending 1,486 |
| R8 | 打標亂分級、太少、太泛（#197–#199） | `tagger/tagging_server.py` CEFR prompt：**「每個 CEFR 級別各給 EXACTLY 3 個」**，由視覺模型自己判斷等級 | 「模型會判 CEFR」「每張圖都有 C2 可標的東西」 | 不以詞庫 CEFR 覆核；沒有「標籤須是 full 詞條」的閘門 | 綁定 ≤2 個的照片 58 張；未打標 1,069 |
| R9 | 打標超時（#200） | 8123 代理 115 s、Ollama 被 `worker.py --lane tags` 佔滿 | 「GPU 隨時有空」 | 沒有排程與優先權 | 單張 80–100 s |
| R10 | **修正造成回歸**（#194） | #191 的 lint 規則 `inflected_form` 直接 redirect | 「-ed/-ing 形都只是動詞變化」 | **沒有對照片標籤的不變量測試、沒有修改前後快照比較**；單元測試只用合成資料 | 208 個錯誤 redirect、268 個照片標籤受影響 |

**共通根因**：
1. 每個匯入器只做「填資料」，沒有「進 pack 前必須滿足的契約」，錯誤一路流到 app。
2. 等級、義項、例句都缺 *來源與信心* 欄位，無法區分「字典確認」與「估計／AI」。
3. 批次修正只跑單元測試，沒有黃金集與全域指標比較，所以修一處壞一處。

## 3. 系統設計

### 3.1 一條品質管線（`lexicon/backend/app/qc/`）

```
import / enrich / tag / pack
        │
        ▼
 [validators]  每個實體跑契約 → violations(rule, entity, severity, evidence)
        │
        ▼
 [fixers]      deterministic → model-assisted(佇列) → needs-human
        │
        ▼
 [guard]       黃金集 + 全域指標，修改前後快照；變差就擋
        │
        ▼
 [report]      dashboard 指標 + 依規則彙整到本地 issue（不逐字）
```

### 3.2 資料契約（invariants）

| 實體 | 契約（違反即 violation） |
|---|---|
| 詞條 entry | full 才可進 pack；有 ≥1 義項且主義項有中文；有詞性（非 unknown）；CEFR 帶來源（cefrj/estimate）；stub 不得有 CEFR；redirect 目標必為 full；有獨立義項的屈折形不得 redirect |
| 義項 sense | 主義項非 low／非 etymology-N／非 AI-only（若同詞有字典譯）；中文無英文殘字、非空 |
| 例句 example | 完整句、含詞形、長度範圍、對應義項；AI 例句標記 |
| 圖片 image | 授權允許、相關性分數 ≥ 門檻、已審核 |
| 照片標籤 photo tag | 指到 full 詞條（非 redirect）；義項有中文且非 low；義項由上下文選出（記錄 `chosen_by`、`confidence`）；標籤等級 = 詞卡等級；每張 ≥ N 個、每級上限；同圖無近義重複 |

每條規則一個函式 + 一個 pytest，用**真實 pack 快照**跑（不只合成資料）。

### 3.3 自動修正分三級

| 等級 | 例 | 條件 |
|---|---|---|
| deterministic（直接改、可回滾） | stub 去 CEFR；redirect 到 full；標籤等級改用詞卡等級；無中文義項 fallback；`share()` 用 `choose_sense` | 規則明確、可由備份還原 |
| model-assisted（Qwen，背景批次） | 照片義項近分時確認；AI 中文重譯/抽查；例句是否符合義項；圖片相關性 | confidence ≥ 0.8 自動套用；0.5–0.8 進人工；<0.5 不動 |
| needs-human | 字典與 AI 衝突、刪詞、合併 | 進 issue 頁（彙整） |

每次修正寫 `qc_changes(rule, entity, before, after, by, confidence, batch_id)`，任一批次可整批回滾。

### 3.4 回歸防護（regression guard）

- **黃金集**：照片 50 張（含 71、26、85、702、680、723、616）+ 單字 300 個（A1–C2 各 50），存「期望的義項／中文／等級」。
- 每次批次修正前後各產生快照，比較：黃金集正確率、全域指標（下表）。**任一指標變差且超過容忍值 → 擋下，不寫入**（dry-run 才放行）。
- CI：`pytest lexicon/tests/test_invariants.py` 對最新 pack 檢查全部契約。

### 3.5 指標與儀表板

`/api/quality/metrics`（lexicon 前端加一頁）：
stub 帶等級數、full 無中文數、主義項 AI 比率、CEFR 估計比率、照片標籤違規（redirect／無中文／low／等級不符）、每張照片標籤數分布、未打標照片數、例句違規數、黃金集正確率；保留每日歷史。

### 3.6 issue 自動建檔

每條規則一張 issue（如「photo_tag.level_mismatch：296 筆」），reporter `qc-bot`；數字更新於同一張 issue 的 note；歸零時自動標 fixed；**不逐字開單**。

### 3.7 觸發與排程

| 時機 | 跑什麼 |
|---|---|
| 匯入／enrich 每批結束 | 該批詞條的 validators + deterministic fixers |
| 打標每張完成 | 照片標籤契約；`share()` 內即用上下文選義 |
| pack 建置（8123 /api/lexicon） | 全部契約（快速版），違規只降級顯示、不讓 app 看到錯 |
| 夜間／GPU 閒置 | model-assisted 佇列；全域快照與指標 |
| 任何批次修正 | guard 前後比較 |

Ollama 排程：一個優先權佇列（互動打標 > 品質確認 > 背景 tags lane），閒置偵測（無互動請求 N 分鐘）才跑背景。

## 4. Qwen 產能估計

- 目前 Ollama 被 `worker.py --lane tags` 佔滿，單張打標 80–100 s。
- 閒置時：視覺打標約 20–40 s／張 → 1,069 張未打標約 **6–12 小時 GPU**。
- 文字判斷（短 prompt，批 10 項）：約 3–6 s／批 → 每小時約 6,000–12,000 項。
  - 照片義項近分確認（估約 300–600 個）：< 10 分鐘。
  - 主義項 AI 中文抽查／重譯 1,791 個：約 15–30 分鐘。
  - 例句是否符合義項（約 8,400 AI 例句 + 有疑慮者）：約 1–2 小時。
- 結論：全部 model-assisted 工作在 **1–2 個夜間時段**可跑完，但前提是排程器讓背景 tags lane 讓路。

## 5. 建置階段與工時

| 階段 | 內容 | 估計 |
|---|---|---|
| P1 | 契約 validators + 真實 pack 不變量測試 + metrics 指令；黃金集初版 | 1–1.5 天 |
| P2 | 修根因：`share()` 用上下文選義；stub 不帶 CEFR、stub 不進 pack；標籤等級統一由詞卡；tagger 改成「列可見物 → 詞庫定級」 | 1.5–2 天 |
| P3 | deterministic fixers + `qc_changes` 回滾 + guard 快照比較 | 1 天 |
| P4 | Ollama 優先權佇列 + model-assisted fixers（義項、中文、例句、圖片相關性） | 2 天 |
| P5 | 儀表板頁、issue 自動彙整、排程 | 1 天 |
| 合計 | | 約 6.5–7.5 天 |

## 6. 需要使用者決定

1. **stub 處理**：46,928 個 stub 是否全部移出 pack（只留 full + redirect），或保留但不顯示等級？
2. **tagger 改法**：是否改成「模型只列看得到的東西，等級一律由詞庫決定」，放棄「每級剛好 3 個」？（會讓高級標籤變少但正確）
3. **AI 自動套用門檻**：confidence ≥ 0.8 自動改，可以嗎？
4. **黃金集**：由我先建 50 照片 + 300 字的初版，您抽審即可？
5. **GPU 優先權**：是否允許品質工作在閒置時暫停 `worker.py --lane tags`？
6. CEFR 估計值：app 是否顯示「估」標記，或估計值一律不顯示？

## 7. 已確認決策（2026-10-14）

1. **stub**：46,928 個 stub **全部移出 pack**（只保留 full + 指向 full 的 redirect pointer）。
2. **tagger**：只列出可見物；**等級一律由詞庫決定**，取消「每級剛好 3 個」。
3. **model-assisted**：confidence ≥ 0.8 自動套用；低於此門檻進人工。
4. **黃金集**：先建 50 照片 + 300 字（`lexicon/quality/golden/v1.json` + `v1_review.md`），由使用者抽審。
5. **GPU**：閒置時品質工作優先於 `worker.py --lane tags`（`.runtime/qc_gpu_claim`，10 分鐘內有效）。
6. **CEFR 估計值**：app 顯示「估」標記（`進階（C1）・估`）。

