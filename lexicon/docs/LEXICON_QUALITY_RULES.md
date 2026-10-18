# 詞庫品質規則（Lexicon Quality Rules）

來源：問題回報 #182–#186（使用者角度掃描 50 單字，2026-10-14）。
程式：`backend/app/quality.py`（規則本體）、`tools/lint_lexicon.py`（全庫檢查）、
`tools/quality_ai.py`（本機 Qwen 抽樣審核）、測試 `tests/test_quality_rules.py`。

**原則：不刪資料。** 規則只「標記」：lint 輸出 `exports/quality/lexicon-lint-<日期>.csv`
與 `quality/entry_flags.json`，app pack 把旗標放到詞條的 `quality_flags`；人工/AI 審核結果放在
`quality/overrides.json`，圖片退件用 `sense_images.review_status='rejected'`（可改回 approved）。

## 1. 收錄規則（Inclusion）— 以下不得成為「有 CEFR 等級的學習詞條」

| 規則代碼 | 條件 | 例子 | 處理 |
|---|---|---|---|
| `person_name` | Kaikki 有 `name` 詞性、不在 CEFR-J 表、且沒有任何「實質的」一般義項（非罕用、非 form-of/alt-of/縮寫） | chen、BQ | 只保留為專有名詞，不給 CEFR |
| `inflected_form` | 單字詞，Kaikki 的義項是屈折形（plural/past/participle/gerund/third-person/比較級），本身不在 CEFR-J 表，且基本形在表內或沒有其他實質義項 | tore→tear、fleeing→flee、tenants→tenant | 併入基本形（lexeme_redirects / card），不單獨成條 |
| `phrase_fragment` | 多字詞、不在 CEFR-J 表，且首尾是受詞代名詞（her/him/them/it/one's…）或 Kaikki 查無 | contain her | 移除或改成完整片語 |
| `proper_or_brand` | 詞性 name、含數字、Title Case 多字詞（不在表內）、全大寫 2–5 字母、或首字大寫且 Kaikki 有 name | Windows、South China Sea、V-8 juice | 不給 CEFR |
| `abbreviation` | 全大寫 2–5 字母且不在表內，或 Kaikki 所有義項都是縮寫/首字母詞 | BQ | 不給 CEFR |
| `excluded_has_cefr` | 命中上列任一規則且仍有 CEFR 等級 | — | lint 報錯，待清理 |

## 2. CEFR 規則

參考表：`app/assets/cefr_en.json`（CEFR-J Wordlist + Octanove，8,845 字，含各詞性等級與 zipf）。

| 規則代碼 | 條件 | 例子 |
|---|---|---|
| `cefr_above_list` | 字在 CEFR-J 表內，詞條等級高於表上該詞性（無該詞性時取最低）等級，且為 C1/C2 或高出兩級以上 | laptop 表上 B2 → 不得 C1/C2 |
| `common_word_too_hard` | 不在表內的單字被標 C1/C2，但 wordfreq zipf ≥ 3.5，或由 A1/A2 基本字加 -y/-ful/-less/-ness/-ly/-er/-ish 衍生 | grassy（grass A1）→ ≤B1 |
| `idiom_too_easy` | 多字的動詞片語/成語（pos = verb/phrase/adv）標 A1–B1；成語至少 B2 | make light of A1 → ≥B2 |

複合名詞（rose garden、black ice）不算成語，不受 `idiom_too_easy` 限制。

## 3. 義項排序（Sense priority）

`quality.rank_senses()` 在每次產生 app pack 時執行：
- **low**：標籤含 obsolete/archaic/dated/rare/slang/informal/colloquial/dialectal/vulgar/derogatory/offensive/
  euphemistic/poetic/humorous/nonstandard/historical；或是 AI 翻譯、且前面已有字典翻譯的主要義項
  （沿用問題回報 #84 的決定）；或列在 `overrides.json` 的 `low_priority_senses`（Qwen/人工審核）。
- main 義項維持原順序排前面，low 義項排後面、加上 `priority: "low"` 與標籤 `low_priority`；
  App 的 `learnerMeaning` 會跳過 `low_priority`，學習者只看到主要意思。
- 例：steep「昂貴的」(informal)、hinged「藥物過量」(slang)、helmet「化學燒瓶上部」、scarlet「淫亂的」。

## 4. 例句規則（Examples）

`quality.example_flags()`：
- `missing_lemma`：句子沒有該字或其屈折形。
- `not_sentence`：少於 3 個字、不是大寫/引號開頭，或沒有句末標點（a scarlet woman）。
- `pos_mismatch`：形容詞 -ed 字被當動詞用（it hinged on my finances）。
- `low_priority_sense`：例句掛在 low 義項上。
- `odd_name`：Tatoeba 佔位人名（Ziri、Mennad、Baya…），只降低排序。
有問題的例句排到後面；`overrides.json` 的 `rejected_examples` 會被標為 `rejected` 排最後；
`examples["word|pos"]` 是 Qwen 重寫、再通過驗證的新例句，排第一。

## 5. 圖片規則（Images）

一張圖只有在本機 Qwen-VL 確認「該字是照片的主要主體」時才保留為該義項的圖
（`tools/quality_ai.py`）。否定的配對設為 `review_status='rejected'`，匯出時不再出現（可改回）。
新圖片綁定應走同一檢查；尚未接入自動匯入流程（見問題回報）。

## 執行

    python lexicon/tools/lint_lexicon.py <pack.json 或 http://127.0.0.1:8123/api/lexicon>
    python lexicon/tools/quality_ai.py steep hinged rosemary ...   # 加 --dry-run 只看不改

## 粗俗／冒犯詞：保留並標「粗俗」，不刪除（2026-10-15 使用者決定）

- 英文詞（如 prick、bastard）不因為是髒話就移出詞庫或丟掉中文；保留並標成粗俗。
- 義項標籤含 vulgar / offensive / derogatory / slang，而且中文是粗俗字（`text.ZH_OFFENSIVE`）時，輸出包**保留**該中文，義項加 `vulgar` 標籤，`register` 設為 `vulgar`，App 顯示「粗俗」。
- 義項標籤含 vulgar / offensive 時一律 `register = vulgar`。
- 中性義項的中文混進粗俗字（例如 underdog 的「屌絲」）仍照 #116 濾掉，只留下乾淨的部分。
- 例句、相關詞的髒話過濾（#89／#92）不變：學習者不會在例句或相關詞裡意外看到髒話。
- 實作在 `backend/app/text.py` 的 `sense_native()`（`COARSE_SENSE_LABELS`、`VULGAR_SENSE_LABELS`），由 `exporter.py` 呼叫；標籤顯示名稱是 `catalog.LABELS["register:vulgar"]`。
