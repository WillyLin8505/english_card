# 拍照學英文 — 單字資料來源集成管線

Implements section 3 of `spec-01-data-sources.html` ("英文學習資料來源"):
for each of the 12 word-detail data categories, try the ① 首選 source,
fall back to ② 次選, then ③ 補充, and record which source actually
answered. Output matches the fields the Figma `word-detail-view` screen
shows (單字/釋義/詞性, 音標, 單字真人發音, 近義字, 同音字, 拼字相近,
詞形變化, 詞性衍生, 字根字尾, 例句, 例句翻譯, 整句發音).

## Layout

```
pipeline/
  schema.py            WordDetail output dataclass (+ *_source provenance fields)
  priority.py           the spec's source-priority table, as data
  merge.py               resolves each category by walking priority.py
  sources/
    base.py              adapter interface (unimplemented method = "no data")
    cmudict_adapter.py    real, offline — ARPABET pronunciation + exact-phoneme homophones
    wordnet_adapter.py    real, offline — synonyms / definitions / derivations / examples
    wordlist_adapter.py   real, offline — edit-distance similar-spelling over any word list
    kaikki_adapter.py     real parser, offline-dump based (Kaikki has no per-word API)
    datamuse_adapter.py   live API — synonyms / homophones / similar-spelling fallback
    tatoeba_adapter.py    live API — example sentences + zh translation + sentence audio
  download_data.py       fetches CMUdict + WordNet; filters a local Kaikki dump
  build_word_db.py       CLI: word list -> word-detail JSON
tests/                   38 tests; run `pytest` from this directory
```

## Setup

```bash
pip install -r requirements.txt
python pipeline/download_data.py          # fetches data/raw/cmudict.dict + WordNet corpus
python pipeline/build_word_db.py --words apple,example,happy --out data/cache/word_db.json --verbose
pytest
```

## ⚠️ Network caveat from where this was built

This pipeline was written and tested inside a sandboxed agent
environment whose egress policy allow-lists `raw.githubusercontent.com`
and `pypi.org` but blocks `api.datamuse.com`, `tatoeba.org` and
`kaikki.org` outright (confirmed: `CONNECT tunnel failed, 403`). So:

- **CMUdict and WordNet are real, downloaded, and tested here** — see
  `data/raw/` after running `download_data.py`, and
  `tests/test_wordnet_adapter.py` / `tests/test_cmudict_adapter.py`,
  which run against the real corpora (skipped automatically if you
  haven't run `download_data.py` yet). `pipeline/build_word_db.py
  --words happy --no-network` was run end-to-end here and correctly
  resolved `happy → happiness` via WordNet's
  `derivationally_related_forms()` — the exact worked example from the
  spec.
- **Datamuse and Tatoeba adapters are written to each API's documented
  contract but were never exercised against a live response** — their
  tests mock `requests.Session.get`, which proves the parsing logic but
  not that the live endpoints still return that shape. Run
  `pipeline/build_word_db.py` (without `--no-network`) from your own
  machine or CI, where these hosts are reachable, and diff a couple of
  real responses against `tests/test_datamuse_adapter.py` /
  `tests/test_tatoeba_adapter.py` before depending on them in production.
- **Kaikki has no per-word API at all** (by design — it publishes a
  full-language JSONL dump). `kaikki_adapter.py` parses the documented
  dump schema and is tested against a hand-built fixture
  (`tests/fixtures/kaikki_sample.jsonl`) that mirrors real entries, but
  has not been run against the actual multi-GB kaikki.org dump. To wire
  it up for real:
  1. Download the English extract from
     https://kaikki.org/dictionary/English/ on a machine that can reach
     it.
  2. Filter it down to just this app's vocabulary (the full dump is too
     big to ship or scan per-word):
     `python pipeline/download_data.py --filter-kaikki <full-dump.jsonl> --words apple,example,happy,...`
  3. `build_word_db.py` will then pick up `data/raw/kaikki_subset.jsonl`
     automatically.

## Why WordNet via NLTK instead of Open English WordNet directly

`en-word.net` and the `globalwordnet/english-wordnet` GitHub release are
both blocked in the same sandbox. NLTK's mirror of Princeton WordNet
(`raw.githubusercontent.com/nltk/nltk_data`) is reachable and is the
dataset Open English WordNet itself was forked from, so
`wordnet_adapter.py` reads it via NLTK's corpus reader as a practical,
license-compatible stand-in. If you get the official WN-LMF file
separately, only `wordnet_adapter.py`'s loader needs to change — its
public methods (`get_lexical`, `get_synonyms`, `get_derivations`,
`get_example_sentences`) stay the same.

## Design notes

- **Every category is resolved independently** by `merge.resolve()`
  walking `priority.py`'s ordered adapter list and taking the first
  non-empty answer — this is a literal implementation of the spec
  table, not an approximation of it. Add/reorder a source for a
  category by editing `priority.py` only.
- **Every resolved field carries a `*_source`** (e.g.
  `definitions_source: "kaikki"`) so a reviewer — or the Flutter app's
  QA — can audit exactly which source answered which field, matching
  the spec's per-field licensing/coverage caveats ("需確認口音、覆蓋率
  與個別授權" etc.).
- **A source raising never breaks the build** — `merge.resolve()`
  catches and logs, then falls through to the next source in priority
  order (see `tests/test_merge.py::test_falls_back_when_source_raises`).
- **CMUdict/WordNet/wordlist adapters are pure and offline**, so they're
  safe to run in CI or bundle into a build step with no network
  dependency; only Datamuse/Tatoeba need live network.

## Related: the Flutter app and the AI service

`app/` is the phone app built from the Figma mobile screens and spec
sections 1–7: photos → AI candidate words → on-device selection by level
→ one card per word → continuous FSRS flashcards, all stored locally
with Hive. See `app/README.md`.

`tagger/` is the photo-tagging API on "Predator" (Ollama + Qwen3-VL-4B):
stage-1 candidates (`/tag`) and word data (`/enrich`). See
`tagger/README.md`.

`lexicon/` is the section 08 admin (語言資料來源管理與擷取後台): PostgreSQL,
a FastAPI service on 127.0.0.1:8770, a separate worker and a React admin
UI. Every exact field has its own source order per language direction,
jobs fetch and resolve words in the background, and the result is
exported as a versioned SQLite package for Flutter. See
`lexicon/README.md` (or run `lexicon/start_lexicon.bat`).

`wordbase/` is the earlier, simpler word database survey app (spec
sections 5–6), superseded by `lexicon/`; it now runs on port 8771. See
`wordbase/README.md`.

`pipeline/build_cefr_list.py` builds the app's local CEFR word list
(CEFR-J + Octanove C1/C2, wordfreq, CMUdict IPA via `pipeline/ipa.py`):

```bash
pip install wordfreq            # optional, adds word frequency
python pipeline/build_cefr_list.py
```

## Not built yet

- A real end-to-end run of the Kaikki/Datamuse/Tatoeba adapters against
  live data (see network caveat above); the app's examples are
  AI-written until Tatoeba is imported.
