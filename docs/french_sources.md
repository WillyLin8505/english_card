# 法語資料來源與法語詞庫後台（卡 #325／問題回報 #326）

目標：母語英文的學習者學法語（`target_language='fr'`、`native_language='en'`），方法與英文詞庫相同：
字典＋例句＋圖片＋音檔＋打標籤＋CEFR。本文列出每個來源的網址、授權、涵蓋量、怎麼接，
以及法語後台的架構決定。數字為 2026-10-19 查得（kaikki.org、tatoeba.org、Commons API、各官網）。

授權原則：**只收可商用並可標示的授權**（CC0／PD／CC BY／CC BY-SA／LGPL-LR／MIT／Apache）。
CC BY-SA 的「相同方式分享」只及於該筆資料本身（詞條文字、音檔），與英文詞庫沿用 Wiktionary 的做法一致；
**CC BY-NC（非商用）一律不收**（FLELex 因此出局，見下）。

## 1. 總表

| 類別 | 來源 | 授權 | 涵蓋量 | 狀態 |
|---|---|---|---|---|
| 字典（主） | Kaikki：英文版 Wiktionary 的法語詞條 | CC BY-SA 4.0／GFDL | 390,535 個詞形；名詞 103,588、動詞 284,596（含變位形）、形容詞 49,951 個義項 | **已接**（`adapters/kaikki.py`，`DICT_NAME["fr"]`） |
| 字典（輔） | Kaikki：法文版 Wiktionnaire（frwiktionary） | CC BY-SA 4.0／GFDL | 法語 2,657,554 個義項（含所有變化形） | 未接；釋義是法文，給英文母語者不如英文版；留作變位表、法語例句、Lingua Libre 音檔的補充 |
| 字典（輔） | DBnary（Wiktionnaire 的 Ontolex 萃取） | CC BY-SA 3.0 | 法語版全量；含消歧後的翻譯（`fr_dbnary_enhancement.ttl`） | 未接；只在需要 fr→en 翻譯對照表時用 |
| 詞頻 | wordfreq（fr） | Apache-2.0（程式）／CC BY-SA 4.0（資料） | 法語 zipf 頻率，前 6 萬字表 | **已接**（`wordfreq` 來源、`kaikki_wordlist` 拼字相近） |
| 詞頻 | Lexique 4（lexique.org） | CC BY-SA 4.0 | 190,000 個法語詞形：字幕語料 3.16 億詞的頻率、詞類、陰陽性、單複數、音標、詞幹 | 未接；建議接為 CEFR 估計與陰陽性的第二來源 |
| 詞頻 | FrequencyWords（hermitdave，OpenSubtitles 2018） | 程式 MIT／資料 CC BY-SA 4.0 | 法語 5 萬字頻表 | 未接；與 wordfreq 重疊 |
| CEFR | FLELex（UCLouvain CENTAL） | **CC BY-NC-SA 4.0（非商用）** | 14,236（TreeTagger 版）／17,871（CRF 版）個詞元，A1–C2 各級頻率 | **不能用**（非商用）；可洽 UCLouvain 商用授權 |
| CEFR | 本機頻率估計（`local_calc`，wordfreq zipf 分級） | 自有 | 全部法語字 | **已接**（標 `cefr_source=frequency_estimate`，與英文無 CEFR-J 時相同） |
| 例句 | Tatoeba（fra／eng 週匯出＋ fra-eng 連結） | CC BY 2.0 FR（逐句標示作者） | 法語 735,614 句、英語 2,047,687 句；fra-eng 連結檔 2.7 MB（bz2） | **已接**（快照 #3 `fr:en` 已匯入 3,209,906 列） |
| 音檔 | Lingua Libre（Wikimedia Commons） | CC BY-SA 4.0（逐檔） | Commons 分類「Lingua Libre pronunciation-fra」439,614 個檔 | **已接**：Kaikki 詞條 `sounds` 直接列出 `LL-Q150 (fra)-<speaker>-<word>.wav` 的 ogg／mp3 網址 |
| 音檔 | Wiktionary 傳統錄音（Commons `Fr-<mot>.ogg`、`Fr-Paris--<mot>.ogg`） | 逐檔（多為 CC BY-SA） | Commons 分類「French pronunciation」3,558 個檔 | **已接**（`adapters/commons.py` 法語檔名樣式） |
| 圖片 | Wikidata＋Wikimedia Commons、Open Images、Smithsonian、Openverse | 同英文（只收 CC0／PD／CC BY） | 語言無關 | **已接**：法語字以該義項的英文詞義搜圖（`images.english_search_term`） |
| 詞形變化 | Kaikki `forms`（英文版 Wiktionary 法語詞條） | CC BY-SA 4.0 | 動詞完整變位表、名詞／形容詞陰性與複數 | **已接**（`kaikki.form_field`：`fr_present_1s…3p`、`fr_past_participle`、`fr_feminine`、`fr_plural`、`fr_feminine_plural`） |
| 詞形變化 | Lefff 3.4（Benoît Sagot） | LGPL-LR | 約 11 萬詞元／50 餘萬詞形（接入前再核對版本數字） | 未接；離線補洞用 |
| 詞形變化 | Morphalou 3（ORTOLANG） | LGPL-LR | 約 16 萬詞元／97 萬詞形（接入前再核對） | 未接；與 Lefff 二選一 |
| 詞形變化 | GLÀFF（Wiktionnaire 萃取） | CC BY-SA 3.0 | 約 140 萬詞形 | 未接 |
| 詞彙關係 | WOLF／WoNeF（法語 WordNet） | CeCILL-C（LGPL 類，可商用） | 法語同義詞集 | 未接；目前同義／反義／上下位詞來自 Kaikki |

不收：Verbiste（GPL）、Le Robert／Larousse 等商業字典、Référentiels（Beacco，版權）、FLELex（NC）。

## 2. 各來源細節與接法

### 2.1 Kaikki（英文版 Wiktionary 的法語詞條）— 主字典
- 網址：https://kaikki.org/dictionary/French/ ；逐字 JSONL：`https://kaikki.org/dictionary/French/meaning/c/ch/chat.jsonl`；
  全量 JSONL 556.6 MB（`kaikki.org-dictionary-French.jsonl`）。
- 授權：CC BY-SA 4.0 與 GFDL 雙授權（Wiktionary 貢獻者；經 wiktextract／Tatu Ylonen）。
- 每筆 `lang_code='fr'`：`pos`、`senses[].glosses`（**英文**釋義 → 直接當 fr→en 的母語釋義）、`forms[]`（`tags` 含
  `first-person/singular/present/indicative`、`feminine`、`plural`、`participle/past`）、`sounds[]`（IPA＋`audio`
  檔名＋`ogg_url`／`mp3_url`，Lingua Libre 檔含在內）、`synonyms/antonyms/hypernyms/hyponyms/related`、
  `derived`、`etymology_text`、例句（`senses[].examples`）。
- 接法：既有 `adapters/kaikki.py` 已支援 `target='fr'`；本卡把 `hypernyms`、`hyponyms`、`homophones`、
  `accent_labels` 加進 `_KAIKKI_FR_TARGET`，並讓檔名 `Fr-Paris--…`／`Fr-ca-…` 認出口音。
  下一張卡（2000–3000 字）建議先建本機索引（`kaikki_index`，目前只索引英文），避免逐字打 kaikki.org。

### 2.2 Kaikki（法文版 Wiktionnaire）與 DBnary — 輔助
- https://kaikki.org/frwiktionary/ （法語 2,657,554 個義項）；原始 JSONL 在 rawdata 頁。釋義是法文，
  例句多且道地，變位表完整，但英文母語者需要英文釋義，所以只做補充（例句、變位、音檔）。
- DBnary：https://kaiko.getalp.org/about-dbnary/ ，CC BY-SA 3.0，Turtle／Ontolex，SPARQL 端點可查；
  `fr_dbnary_enhancement.ttl.bz2` 是消歧後的翻譯，可當 fr→en 翻譯對照的第二來源。

### 2.3 詞頻與 CEFR
- **wordfreq**（已接）：`zipf_frequency(word, "fr")`，`local_calc` 以頻率分級估 CEFR（A1–C2），標記為估計值。
- **Lexique 4**：http://www.lexique.org/ ，CC BY-SA 4.0，TSV；欄位 `ortho/phon/lemme/cgram/genre/nombre/freqlemfilms2/freqlemlivres`。
  可同時給陰陽性（`genre`）、詞類與頻率；建議接為 `fr` 的第二頻率來源並用於 CEFR 估計校正。
- **FLELex**：https://cental.uclouvain.be/cefrlex/flelex/ ，CC BY-NC-SA 4.0 → **不能商用**。它是目前唯一按 CEFR
  教材語料分級的法語詞表（Beacco 版另有一欄推得的 CEFR 等級）。**需要 owner 決定**：接受頻率估計（現況），
  或洽 UCLouvain 取得商用授權，或自建（以 wordfreq＋Lexique 頻率＋教材字表人工校正 A1–B1 約 3000 字）。
- Kelly 法語詞表、Français fondamental（Gougenheim 1954，1er degré 1,475 字）：授權不明／年代久，列為參考，不直接匯入。

### 2.4 例句 — Tatoeba
- https://downloads.tatoeba.org/exports/per_language/fra/ ：`fra_sentences_detailed.tsv.bz2`（14.9 MB）、
  `fra-eng_links.tsv.bz2`（2.7 MB）；eng 句子檔 34.9 MB。CC BY 2.0 FR，逐句標示作者（`owner` 欄已存）。
- 接法：`adapters/tatoeba.py` 已有 `CODE3["fr"]="fra"`；快照用 `POST /api/snapshots {"source":"tatoeba","language":"fr:en"}`
  （本卡已建 #3，匯入 3,209,906 列，fra 句子進 `tatoeba_sentences`）。例句難度在非英文用句長分級（`length_level`）。

### 2.5 音檔 — Lingua Libre、Commons
- Lingua Libre：https://lingualibre.org/ ，錄音上傳到 Commons，檔名 `LL-Q150 (fra)-<speaker>-<word>.wav`，CC BY-SA 4.0；
  Commons 分類 `Lingua Libre pronunciation-fra` 有 439,614 檔。Kaikki 的 `sounds` 已帶這些檔的 ogg／mp3 網址，
  所以不必另外查 Lingua Libre 的 SPARQL（https://lingualibre.org/bigdata/namespace/wdq/sparql 可查講者與地區）。
- Commons 直接查檔名：`Fr-<mot>.ogg`、`Fr-Paris--<mot>.ogg`、`Fr-ca-<mot>.ogg`（本卡加入 `AUDIO_TITLES_BY_LANGUAGE["fr"]`）。
- 口音槽：法語沒有英式／美式目標（`AUDIO_ACCENTS` 只在 en 生效）；`FR`／`CA`／`BE`／`CH` 由檔名判斷，Lingua Libre 講者未標地區者進 `other`。

### 2.6 圖片
- 與英文完全相同的四個來源與授權白名單。差別只在搜尋詞：Wikidata 標籤、Open Images 類別、Openverse 查詢都是英文，
  所以法語義項改用它的英文詞義搜圖（`english_search_term("cat (feline)") → "cat"`，fr→en 時用母語釋義，
  否則用英文版 Wiktionary 釋義）。圖片候選進審核佇列的流程不變。
- 待辦（問題回報）：圖片 AI 標籤與「標籤認出這個字」的自動核准目前只對英文詞條綁定（`images._resolve_lexeme`
  只查 `language='en'`）；法語圖片要以英文詞義比對標籤，下一張卡再做。

### 2.7 詞形變化
- 名詞／形容詞：陰性、複數、陰性複數（Kaikki `forms` tags）。動詞：直陳式現在六個人稱＋過去分詞（欄位 `fr_present_1s…3p`、`fr_past_participle`）。
  其他時態（imparfait、futur、passé composé 組合）暫不入欄位；要的話再加欄位（catalog `Field(..., languages=("fr",))`）。
- 離線補洞：Lefff（https://github.com/sagot/lefff ，LGPL-LR）或 Morphalou（https://www.ortolang.fr/market/lexicons/morphalou ，LGPL-LR）。

## 3. 法語後台的架構決定

**決定：同一個 schema、同一套欄位目錄，資料以 `target_language='fr'`＋`native_language='en'` 分隔；後台用「語言切換」而不是獨立頁面。**

理由：
1. 現有 schema 本來就是語言對驅動：`lexemes.language`、`field_values/field_candidates/source_lookups/source_policies/
   import_jobs/image_fetch_tasks/dictionary_releases` 全部帶 `target_language`＋`native_language`，`senses/examples` 的
   翻譯表帶 `native_language`。獨立 schema 要複製 60 多張表、所有 migration、exporter、QC、golden 工具，卻換不到任何隔離
   （兩邊本來就不會互相讀到）。
2. 欄位目錄（`catalog.FIELDS`）用 `languages=("fr",)` 標語言專屬欄位，`fields_for("fr")` 已能給出法語的 69 → 61 個欄位；
   來源順位（`source_policies`）每個語言對各一套（fr→en 已有 61 條預設）。
3. 後台前端所有 API 都帶語言對（`/words/{t}/{n}`、`/coverage/{t}/{n}`、`/policies/{t}/{n}`、`/exports/sqlite`）。
   本卡在側欄加「英文詞庫／法文詞庫」切換（也可用 `#/lang/fr`），切換後總覽以外的頁面（單字資料庫、來源順位、
   開始擷取、工作佇列、圖片庫、匯出）都只看該語言對；法文後台側欄改藍色以便一眼分辨。
4. QC／golden：`python lexicon/tools/qc.py check --live --target fr --native en --out …` 用同一套規則跑法語包，
   golden 檔獨立（`lexicon/quality/golden/fr_v1.json`）；母語是英文時不做「夾雜拉丁字母」檢查。

## 4. 這張卡改了什麼（程式）
- `catalog.py`：`FORM_POS` 加法語詞形（變位→動詞；陰性／複數→名詞或形容詞），`MAY_BE_EMPTY` 加法語詞形，
  `_KAIKKI_FR_TARGET` 加 hypernyms／hyponyms／homophones／accent_labels。
- `pipeline.not_applicable`：詞形欄位可對應多個詞性。
- `adapters/local.py`：`local_calc` 的 CEFR 頻率估計支援 fr。`adapters/base.py`：法語例句也要 ≥ 3 個字。
- `adapters/commons.py`：法語錄音檔名；`adapters/kaikki.py`：`Fr-Paris--`／`Fr-ca-` 口音。
- `images.py`：`english_search_term`，非英文詞條以英文詞義搜圖。
- `qc.py`（backend）：母語非中文不做拉丁字母檢查；`tools/qc.py`：`--target/--native/--golden`。
- 前端：`App.tsx` 後台語言切換＋`#/lang/<code>`；`Images.tsx`、`Jobs.tsx` 依語言對過濾；`styles.css`。
- 工具：`tools/card325_fr_trial.py`（前景跑 fr→en 工作與圖片）、`tools/card325_backup.py`（pg_dump）。
- 測試：`tests/test_card325_french.py`。

## 5. 下一張卡（法語基礎 2000–3000 字）要先做的事
1. 決定 CEFR 來源（§2.3）。2. 建 Kaikki 法語本機索引，不要逐字打 kaikki.org。3. 重啟 API 與 workers 載入法語程式
（workers 會把舊程式留在記憶體，問題回報 #285）。4. 圖片標籤綁定支援法語（§2.6）。5. 字表：以 wordfreq fr 前 3000
（排除專有名詞、功能詞）或 Lexique 4 頻率建 `wordlists(language='fr')`。
