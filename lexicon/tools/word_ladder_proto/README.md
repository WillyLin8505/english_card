# 單字上下游（word ladder）原型 — Manager 2026-11-27

Owner 11/27：以單字為主，替每個字的每個常用意思，列出 A1–C2 各級「同一個意思」的字，
排成「詞性 × CEFR」表格；照片標籤拉難度條時用它換字（#1876），並顯示在後台單字頁。

這個資料夾是 12 輪迭代的原型（每輪 owner 都看過結果）。`ladderN.py` 用 `exec` 串前一版的
函式，**最後版是 `ladder30.py`**（實際邏輯分散在 ladder8 → 9 → 12/15 → 16 → 20 → 21 → 22 →
24 → 25 → 26 → 28 → 29 → 30）。正式版請整理成一支乾淨的 `lexicon/tools/word_ladder.py`，不要
沿用 exec 鏈。

## 需要的資料
- WordNet：系統 Python 的 `wn` 套件，`wn.Wordnet('oewn:2024')`（已下載）。
- 維基詞典（Kaikki）意思、標註、例句：`lexicon/exports/language-data-en-zh-TW-20261028-0929/*.sqlite`
  的 `lexemes / senses / examples` 表。原型把它複製成 `lex.sqlite` 並加索引
  （`lexemes(normalized,pos)`、`senses(lexeme_id)`、`sense_translations(sense_id)`），
  不加索引每查一字要掃全表，非常慢。
- 程度：`app/assets/cefr_en.json`（CEFR-J＋Oxford；鍵是 noun / verb / adj. / adv.），
  表上沒有的字用 `tagger/tagging_server.py` 的 `word_cefr`／`_wordfreq_zipf`。
- 中文：ECDICT `lexicon/raw-data/ecdict.sqlite3`（表 `e`，簡體 → OpenCC `s2twp`），
  但常取錯意思，最終中文由 Claude 依意思給（標 AI）。
- Qwen：llama-server `ts.LLAMACPP_URL`（:8790），`enable_thinking=false`，`json_schema`。

## 最終流程（round 12 ＋ owner 同意的 5 項優化）
1. **列意思**（程式）：WordNet 全部 synset（前 12）＋維基詞典意思（前 20，去掉 dated / obsolete /
   slang / vulgar / offensive / derogatory / rare / nonstandard；archaic 保留給後面判斷），
   用字根（前 5 字母，排除原字）比對合併重複的。
2. **找候選字**（Qwen，4 個字平行 = llama-server 4 slots）：替**全部**意思找候選字
   （easier ≤8、harder ≤10，給 WordNet／維基例句，要求「能在例句裡替換」）。
3. **程式過濾**：片語、空泛字（go/get/thing…）、變化形、拼法變體（-ise/-ize、jewellery）、
   冒犯字（維基標註＋封鎖清單）、WordNet 反義字、太罕見（zipf < 2.5，學術字尾更嚴；
   harder 清單與 WordNet 下位詞放寬到 2.0）、詞性不符（名詞→名詞、動詞→動詞、
   形容詞→形容詞或副詞）。WordNet 上位詞只標「廣」，不刪（cover 之於 wrap 是好字）。
   副詞只從原字與 WordNet 同義字變出來，並記來源（hardly←hard 那種要一起刪）。
4. **Claude 一次處理**（每張卡 75 字，精簡 JSON 輸出）：挑學習者會遇到的常用意思
   （補漏掉的現代意思，如 charge＝充電、caller＝打電話的人）、合併重複意思、
   逐字檢查「能否在句子裡直接替換」、補字、給每個保留字在這個意思下的台灣中文。
5. **程度**：CEFR 表；表上沒有這個詞性時往上調一級；比字頻難兩級以上時降一級。

先篩掉：月份、星期、數字、人名、功能字、單位這類沒有梯子的字；同一組同義字只做一次。

## 實測（round 12，5 字）
Qwen 平均約 8 秒／字（4 個意思時約 17 秒）；Claude 約 40 秒／字（優化後估 20–25 秒）。
`sample_round12.json` 是 round 12 Qwen＋程式過濾後、Claude 檢查前的輸出範例。
