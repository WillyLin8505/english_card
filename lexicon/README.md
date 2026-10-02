# 語言資料來源管理與擷取後台 (lexicon)

The admin for spec-01 section 08 (「可執行規格：語言資料來源管理與擷取後台」).
It builds the bilingual word database offline. Image recognition in the
app later only looks words up in the exported SQLite; it never calls
Kaikki, WordNet, CMUdict, Tatoeba or Datamuse.

| Part | What | Where |
|---|---|---|
| Admin UI | React + TypeScript + Vite | `frontend/` → http://127.0.0.1:5173/ui/ |
| API | FastAPI, SQLAlchemy 2, Pydantic, Alembic | `backend/app/` → http://127.0.0.1:8770 (X-API-Key) |
| Worker | separate Python process, queue in PostgreSQL | `worker/worker.py` |
| Database | PostgreSQL 17 (+ `pg_trgm`) | `lexicon` and `lexicon_test` |
| Files | raw source data · word audio · exports | `raw-data/` · `media/audio/{language}/` · `exports/` |

No Redis or Celery. Jobs are rows in `import_jobs`. Audio and images are
files; the database keeps only paths, hashes and licences.

## 1. PostgreSQL

Either install PostgreSQL 17 locally (this machine: Windows service
`postgresql-x64-17`, port 5432), or run `docker compose --env-file .env up -d`.
Then create the role and databases once:

```sql
CREATE ROLE lexicon LOGIN PASSWORD '…';
CREATE DATABASE lexicon OWNER lexicon;
CREATE DATABASE lexicon_test OWNER lexicon;
-- in each database:
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Copy `.env.example` to `.env` and fill in:
- the database password
- `LEXICON_API_KEY`: any long random string
- `LEXICON_AI_KEY`: the tagging service's key (`tagger/.api_key`), for the
  **AI 翻譯** source. Definitions, examples, pronunciation and word
  breakdowns come from dictionary sources only; AI only translates into
  the native language, as the last source of each translation field, when
  no dictionary has the translation. Every AI value is marked as AI.

### 台灣用語

All Chinese is written the Taiwan way, from every source: `to_taiwan()` in
`backend/app/text.py` runs before validation. It uses OpenCC's Taiwan tables
plus a list of everyday words (意大利麵 → 義大利麵, 芝士 → 起司, 視頻 → 影片,
土豆 → 馬鈴薯). Values stored earlier are converted on 重新解析.

`.env` is git-ignored, and keys never go into code or the database.

## 2. Install and migrate

```bash
pip install -r lexicon/requirements.txt
cd lexicon
python -m alembic upgrade head              # initial schema (migrations/versions/0001…)
python -m alembic -x test=1 upgrade head    # the test database
npm --prefix frontend install
```

## 3. Run

```bash
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8770   # API
python worker/worker.py                                                        # worker
npm --prefix frontend run dev                                                  # UI
```

`start_lexicon.bat` starts the API, four workers and the UI, then opens it. The Vite dev server
adds the API key on the server side (from `.env`), so the browser never
holds it.

`npm --prefix frontend run build` builds the UI into `frontend/dist`, and
the API then also serves it at http://127.0.0.1:8770/ui/. In that mode
the page asks for the key once and keeps it in that tab only.

The workers keep going when the browser is closed. Stopping them
(Ctrl+C) leaves a running job at its checkpoint, and the next worker
continues from there. The UI divides a large import into four word shards;
each shard is claimed with `FOR UPDATE SKIP LOCKED`, so the workers process
different words. Image acquisition is queued separately and interleaved
after text slices, so Wikimedia does not hold up a finished word card.

## 4. Source policies (來源順位)

Every exact field is its own policy for a target + native language
pair, for example `en → zh-TW · verb_past`. The Source Policies page
groups the fields into blocks, and each block can be collapsed. Its
header shows counts: 完成, 未設定, 需注意 and 錯誤.

The blocks: 基本資料, 發音, 詞形變化, 詞彙關係 (each relation type plus
its own native-meaning field), 衍生詞, 字根與詞源 (including 構詞拆解), 例句
and 詞義圖片.

Each field row has its own editor:

- **Enabled sources.** Drag to reorder, or use the keyboard: Space,
  then arrows, then Space. A drop is saved at once, in one transaction.
  Positions are gapped integers (1000, 2000, …), so a move rewrites one
  row.
- **Per-source settings.** Enable or disable the source, and set the
  timeout, retries, minimum confidence, maximum results, and whether to
  continue after a failure.
- **Other sources.** 可加入來源 lists only sources that declare support
  for this field and direction. The ones that don't are listed below it
  with the reason.
- **Strategy and limit.** Pick one of the five strategies and a limit
  for the field. These edits stay 未儲存 until saved.
  - `FIRST_VALID`: the first source with a valid value wins.
  - `MERGE_UNIQUE`: all sources, merged in order, duplicates removed.
  - `FILL_MISSING`: each sense, example or word is taken from the first
    source that has it.
  - `BEST_SCORE`: the highest confidence per item.
  - `APPEND_LIMITED`: append sources in order until the limit, then stop.
- **測試單字.** Runs just this field for one word, using the saved policy
  or your unsaved draft. It shows each source's raw result, normalized
  candidates, validation failures, the adopted value and a bilingual
  preview. Nothing is written.
- **複製此順位到⋯** You pick the target fields and confirm before
  anything changes. Sources a target field doesn't support are dropped
  and shown.
- **恢復預設** resets this one field.

### 構詞拆解 (word parts)

The 字根與詞源 block has two extra fields: 構詞拆解 and 構詞部件母語意思.

**構詞拆解** splits every word into its parts, in order, each with a meaning:
- exterior → ex + -ter + -ior
- transportation → trans- + port + -ation
- unhappiness → un- + happy + -ness

A single-morpheme word such as apple stays one root.

Sources, in order:
1. **Kaikki (Wiktionary).** Its affix markup (`af`, `prefix`, `suffix`,
   `compound`, `ety|:af`) gives the first split. English-word parts are
   then split further, unless the word is very common (happy and national
   stay whole).
2. **本機構詞分析.** Matches the word against the table in
   `backend/app/morph_data.py`: prefixes, suffixes and Latin/Greek roots
   with English and 繁中 meanings.
   - It undoes spelling changes (happi→happy, dropped e, doubled consonant).
   - It picks the meaning from context: in-/un- mean 「不」 before an
     adjective, but 「向內／反轉」 in income or unlock.
   - It uses the etymology. Old English words are never cut into Latin
     roots. If Wiktionary has an etymology but no affix markup, it
     doesn't invent English derivations (butter is not butt + -er).
**構詞部件母語意思** comes from the table (繁中), then from the lexicon or
Kaikki for parts that are English words, then from AI 翻譯.

字根／字首／字尾 now take 本機構詞分析 as their second source.

A field with no enabled source is 「未設定」. It is recorded that way:
nothing is inherited from another field and no default source is called.

The English defaults follow the spec's table. Other directions start
from the same table, keeping only sources that support them.

## 5. Source snapshots (來源快照)

On the 來源快照 page, choose a source and language and press 下載並匯入.
The worker then downloads it into `raw-data/<source>/…/<timestamp>/`. It
records the URL, SHA-256, size, row count, licence and time, and makes
the snapshot active. From that page you can re-hash a snapshot (校驗),
compare two, or make an older one active again (設為使用中).

| Source | Snapshot |
|---|---|
| Tatoeba | Weekly per-language exports, target and native sentences plus the pair's links (e.g. `en:zh-TW`), COPY'd into `tatoeba_sentences` / `tatoeba_links`. Without it, Tatoeba falls back to its API. |
| CMUdict | `cmudict.dict` from GitHub. Without it, `data/raw/cmudict.dict` is used. |
| OEWN | Open English WordNet 2024 (WN-LMF) through `wn`. |
| Kaikki | Uses `raw-data/kaikki-index.sqlite3` when installed, otherwise per-headword JSONL from kaikki.org. Network responses are still cached in `raw-data/cache/kaikki/`. Build the index with `python tools/build_kaikki_index.py https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl --language en --replace`; it is written as `.building` and becomes active atomically only when complete. |
| CEFR-J, wordfreq | Records the bundled files and versions. |

All network access has a timeout, exponential backoff with jitter, a
per-source rate limit and a circuit breaker. Responses are cached in
`raw-data/cache/`.

## 6. The first job: dry run, then import

On **開始擷取**:
1. Pick the target and native language. Both are required.
2. Pick a word list (seeded from `backend/app/seed_words.txt`) or type
   words.
3. Pick the fields and mode. The estimate shows completeness, request
   count and storage, separately for target-language and native-language
   data.

The modes:
- 缺值補齊: only incomplete fields, or fields whose policy changed
- 強制刷新: bypass the cache
- 只驗證: re-check stored candidates, fetch nothing
- 乾跑: fetch and resolve, write nothing
- 重新解析: re-select from stored candidates under the current policies,
  without downloading again

Start with 乾跑. **工作佇列** and the job page show:
- progress and the checkpoint
- each field × source step
- errors grouped by type, with a CSV download
- live logs

Pause, resume, cancel and 重試失敗項目 take effect between words. If a
source is down, the job ends as `completed_with_errors`, naming every
failed field.

What happens to each word:
1. Candidates from every source are stored with source, record id,
   confidence, licence, attribution, raw value and time
   (`field_candidates`).
2. The Resolver adopts values under the current policy (`field_values`,
   `field_provenance`).
3. The values are projected into the dictionary tables: lexemes (one per
   language, lemma and part of speech), senses, sense-bound translations,
   forms, pronunciations, audio, examples with paired translations,
   relations and derived words linked to real lexemes, and etymology.

Target-language candidates are shared by all native languages. Adopted
values are kept per direction, so en→zh-TW and en→fr never overwrite
each other.

A manual value (「手動修改」 on the word page) goes into `user_overrides`,
and no later import replaces it.

**單字覆蓋率** shows each word's target and native fields side by side:
- every sense, example, derived word and related word, and whether its
  native text exists
- named gaps such as 「例句 #3 缺翻譯」 or 「同義詞 fruit 缺繁體中文詞義」
- 重抓 and 來源紀錄 for each field

## 7. Export for Flutter

On **匯出給 Flutter**, pick the language direction and whether to
include audio. This writes to `exports/`:

```
language-data-{target}-{native}-{yyyyMMdd-HHmm}/
  language-data-{target}-{native}-{yyyyMMdd-HHmm}.sqlite
  media-{target}.json          audio files: path, sha256, bytes
  manifest.json                schema version, languages, active snapshots, policy
                               versions + hash, card template version (null for now),
                               time, completeness per field, counts, file hashes,
                               licences and attribution, AI value count, checks
  media/audio/{target}/…       when audio is included
```

The package contains what this direction's policies adopted, with
stable `lexeme_id`s and a `lexeme_redirects` table. It is indexed for
`language + normalized + pos` lookups, form → lemma lookups and prefix
search.

Before the package is published, the exporter checks:
- foreign keys
- orphan audio
- required fields
- translation pairing
- that the SQLite file is readable

It builds in a temp folder and renames it into place only after these
checks pass. A failed export leaves nothing behind that looks finished.

## Tests

```bash
cd lexicon && python -m pytest tests -q
```

51 tests. Unit tests cover:
- each adapter's normalization, and the validation rules (IPA vs
  ARPAbet, Simplified vs Traditional)
- the five strategies and deduplication
- audio hashing and dedupe

Integration tests run against `lexicon_test`, with fake adapters and no
network. They cover:
- migrations
- one field's policy change leaving all other fields and directions
  alone
- 未設定 fields calling nothing
- user overrides surviving re-imports
- re-resolving without re-downloading
- two workers not double-claiming
- pause, resume and cancel
- checkpoint recovery
- a dead source ending as `completed_with_errors`
- API idempotency (`Idempotency-Key`)
- the SQLite export and its manifest hash

## Not done yet

- **詞義圖片.** Policies, fields and tables (`image_assets`,
  `sense_images`, …) exist. The four image adapters (Wikidata/Commons,
  Open Images, Smithsonian, Openverse) are declared but not written.
  They show as 「adapter 尚未實作」 and are skipped.
- **Card Template Editor.** The tables exist; the editor and the
  `/card-templates` endpoints are not built.
- **拼字相近 word list.** The spec names the full Kaikki word list. Until
  that dump is imported, the list is wordfreq's top 60k words plus
  CEFR-J.
- **Flutter.** The app does not yet read the exported SQLite or send
  `missing_lexeme_requests` / `missing_localization_requests`. The API
  endpoints for those requests exist.
