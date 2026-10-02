# 單字資料庫 (wordbase)

> **Superseded by [`lexicon/`](../lexicon/README.md)** — the section 08 admin
> (PostgreSQL, per-field source policies, worker, Flutter export). This
> quick source-survey app still runs on port 8771 for comparison.

A local web app for the word database in `spec-01-data-sources.html`,
separate from the learning app:

- **Section 6 — 英文學習資料來源.** Every word is fetched from the
  sources the spec names, and each field is filled in the spec's order:
  ① 首選 first, ② 次選 fills the gaps, ③ 補充 extends.
- **Section 5 — 完整單字資訊欄位 and 單字管理中心.** Every item keeps the
  source it came from, the source's licence and the fetch time. You can
  edit any field; the fetched value is kept as the original and a re-fetch
  never overwrites your edit. Fields can be marked 已核對.

```bash
pip install wn wordfreq opencc-python-reimplemented
python wordbase/server.py          # http://127.0.0.1:8771/  (or start_wordbase.bat)
python -m pytest tests/test_wordbase.py
```

On first start the database (`data/wordbase/wordbase.sqlite`) is seeded
with `seed_words.txt`: the app's photo words, the pasta photo's words, and
8 words per CEFR level. `# 標題` lines become tags. Add more with 「＋ 新增單字」.

## Sources per field

| 欄位 | ① 首選 | ② 次選 | ③ 補充 |
|---|---|---|---|
| 詞性、英文定義與義項 | Kaikki／Wiktionary | Open English WordNet | |
| 中文釋義 | Kaikki（Wiktionary 翻譯表，華語） | | |
| IPA 與口音 | Kaikki | CMUdict（轉成 IPA） | |
| 音素 | CMUdict | | |
| 單字真人發音 | Kaikki（Wikimedia Commons 音檔） | | |
| 近義字 | Open English WordNet | Kaikki | Datamuse |
| 同音字／發音相近 | CMUdict | Datamuse | Kaikki |
| 拼字相近 | 本機字表比對 | Datamuse | |
| 詞形變化、字根字尾、詞源 | Kaikki | | |
| 詞性衍生 | Kaikki | Open English WordNet | |
| 例句與翻譯 | Tatoeba | Kaikki | Open English WordNet |

Notes:
- **Tatoeba.** Single words are matched in their exact form, so
  "potted" doesn't match "pots". Traditional Chinese translations come
  first. A Simplified translation is also shown converted to Taiwan usage
  (OpenCC `s2twp`), marked 簡→繁.
- **Kaikki.** Only everyday usage examples are kept. Dated literary
  quotations (書證) are counted but not listed.
- **拼字相近.** The spec says "Kaikki 字表＋自行比對", but Kaikki's
  full word list only comes as a 3 GB dump. This app compares against
  CMUdict and CEFR-J headwords (126k words) instead.
- **Extra fields.** The CEFR level (CEFR-J list) and word frequency
  (wordfreq, Zipf) are shown on each entry.

Responses are cached in `data/cache/sources/`. 「重新抓取」 asks the
services again.

## What the 單字管理中心 does

- **Find words.** Search words, meanings and definitions. Filter by tag,
  CEFR level, part of speech, missing field (缺中文釋義, 例句不足 5 句,
  缺繁中翻譯例句 …), source, status, or possible duplicates. Sort by
  alphabet, level, example count, or last update.
- **Entry view.** Grouped as in section 5 (識別, 釋義, 發音, 詞彙關係, 構詞,
  例句). Every item carries a coloured source mark, and each field shows
  which sources supplied how many items and their rank. Empty fields are
  hidden, as the spec requires; 「顯示空白欄位」 shows which sources were
  asked.
- **Per-word actions.** Edit a field (and 還原 it), mark it 核對, choose
  the main sense (主要義項) and the default accent, add or remove tags,
  re-fetch, archive.
- **Delete and merge.**
  - Deleting shows how many photos and cards use the word, and is refused
    while any do (archive instead), per section 5's consistency rule.
  - Merge combines two duplicate entries.
- **Batch actions.** Tag, untag, re-fetch, archive, restore, delete, or
  merge two entries.
- **來源覆蓋率.** For every field and source, the share of words that
  source could supply, overall or per tag, plus the targets the learning
  app needs.

Photo contexts and FSRS cards live in the learning app. The database has
`photo_refs` and `card_refs` counts for them, 0 until the two are
connected.
