# Project map (read this instead of exploring; card #158)

Line counts as of 2026-10-17. **Big files: search first, then read a range** (see "Reading big files").

## Services and ports
| What | Where | Port |
|---|---|---|
| Admin UI (React/Vite, hot reload) | `lexicon/frontend/` | 5173 (`/ui/`, `/api` → proxy to 8770) |
| Lexicon API (FastAPI) | `lexicon/backend/app/` (`main.py` registers routers) | 8770 — agents use **5173/api** only |
| Workers (text / images / tags lanes) | `lexicon/worker/worker.py` | — |
| Tagger (Qwen via llama-server) | `tagger/tagging_server.py`, config `tagger/tagger_config.py` | 8765 / 8790 |
| Learner app (Flutter) | `app/` | web build on 8123 (`serve_app.py`; `/api/lexicon` = `lexicon_transport.SnapshotStore`: after a restart it serves the newest `.runtime/dictionary-snapshots/*/` pack and rebuilds in the background, #380) |
| Card studio | `card_preview/` | 8772 |
| DB | PostgreSQL 17, `lexicon` + `lexicon_test`; migrations `lexicon/migrations/versions/00NN_*.py` | 5432 |

## Backend (`lexicon/backend/app/`)
- `images.py` **2151 lines** — picture fetch, tagging queue (`tag_pending`, `_tag_asset`), CEFR tag levels. Never read whole.
- `models.py` 877 — all SQLAlchemy tables (`AgentTask`, `IssueReport`, `ImageAsset`, `Lexeme`, `Sense`…).
- `pipeline.py` 805, `exporter.py` 700 (app pack export), `materialize.py` 460, `jobs.py` 577 (import jobs).
- `tasks.py` 649 — 排程 board API (`/tasks`, `/schedule/*`, difficulty, agents-info). `agent_usage.py` — AI usage panel.
- `flow.py` — 統一流程總覽 API (#916; stages come from `tools/flow_tick.py` + `flow_rules.py`).
- `console.py` 730 — 控制台 API (#919: one item per 問題+卡, timeline, 需要你, 介入). `runs.py` — 工作中／等收卡／等你／閒置 from real processes (`tools/proc_identity.py`).
- `issues.py` — 問題回報 API. `quality.py` 495, `qc.py`, `qc_fix.py` — quality rules. `policies.py` 428.
- `adapters/` — dictionary sources (kaikki 810, local 792, ai 311, tatoeba, ecdict, cmudict, oewn, commons…).
- Shared request budgets (one state file per source under `lexicon/state/*_gate.json`, all processes): `wikimedia_gate.py`
  (#339, waits a 429 pause out) and `rate_gate.py` (#360: `api.si.edu`, `api.openverse.org` — a paused source is
  skipped at once, the task completes on the other sources). Measure: `tools/card362_measure.py`; re-queue tasks that
  skipped a paused source: `tools/card362_requeue.py --source smithsonian --dry-run`; per-host profile: `card362_profile.py`.

## Tools (`lexicon/tools/`)
- Board: `task.py` (local, key from env), `launch_agent.py` (dispatch), `pick_card.py`, `grade_cards.py`,
  `card_difficulty.py`, `agent_capabilities.json`, `agent_preamble.md`.
- Quality: `qc.py` (loads .env itself — run it, never open .env), `qc_golden.py` (`--out`, `--force`), `qc_snapshot.py`,
  `quality_ai.py`, `apply_quality_decisions.py`, `recompute_photo_tag_cefr.py`, `enrich_cefr_tags.py`.
  `quality/decisions.json` keeps a #191 strip_cefr until a lint with matching scope withdraws it (#509/#523: the
  proper_or_brand rule had fired on Title-Case lemmas that #460 later lower-cased). After any bulk lemma/pos rewrite:
  `lint_lexicon.py` then `card509_stale_exclusions.py [--apply|--restore]` (withdraws only lint-made decisions the
  current flags no longer support; #318 variants stay); measure `card509_measure.py --live [--qc-out f]`.
  A strip whose lemma has no full entry (brushstrokes → brushstroke) keeps photo labels 「未分級」 (#552/#523):
  `card523_lemma_redirects.py measure|backup|import|plan|apply|restore` imports the lemma (foreground job, no
  audio/AI) and turns the strip into a redirect; `apply_quality_decisions.reconcile(keep=#318 variants)` no longer
  withdraws #318 decisions that sit inside the lint scope.
- Photo labelling fallback (#327/#330): `tag_fallback.py` (status / ask / apply / golden / run, config
  `tag_fallback_config.json`) → backend `app/vision_fallback.py`; Codex/Cursor CLI look at the photo when Qwen
  is paused or the queue is long; cost log `lexicon/logs/tag_fallback/cost.jsonl`.
- Files starting with `_` and `cardNN_*.py` are one-off scripts from earlier cards — reuse them for the same check.

## Flutter app (`app/`)
- `lib/services/word_database_repository.dart` **1371**, `lexicon_pack.dart` 711, `flashcard_session.dart` 675, `photo_word_session.dart` 412.
- `lib/screens/` (photo_detail 605, word_detail 562, camera 550, word_database 529…), `lib/widgets/` (flashcard_back 409…), `lib/models/` (word_entry 648).
- Tests `app/test/` (64 files; screens_test 622, session_test 523). Simulations `app/test/simulation/` + `run_round.py` → `app/build/rounds/<n>/summary.json`.

## French lexicon (fr→en, card #325)
- Same schema and field catalog as English; rows split by `target_language='fr'` / `native_language='en'`.
  Sources, licences and the design decision: `docs/french_sources.md`. Admin UI: sidebar 「法文詞庫」 or `#/lang/fr`.
- Trial / rerun on a few words: `python lexicon/tools/card325_fr_trial.py run <words>` (foreground, fresh code);
  QC for the French pack: `python lexicon/tools/qc.py check --live --target fr --native en --out <file>` (golden `fr_v1`).
- Picture labels by meaning (#347/#350): `serve_app.meaning_index` maps a picture's approved English words to French
  main senses via `images.english_label_terms`. Measure `card349_measure.py --target fr` / `card350_measure.py`;
  missing French words: `card350_candidates.py` → `card350_wordlist.py` → `card350_import.py` (no audio field, ~1 s/word;
  `--words <json>` for another list, e.g. `card352_wordlist.py`'s).
- Sense order (#352): `app/sense_order.py` — materialize() puts out-of-use senses (archaic, dated, historical…) last and,
  for French, a domain sense (Kaikki topics) after the plain ones unless English Wiktionary lists the word under one of
  the English word's first senses. Re-rank existing rows: `card352_reorder.py --lang fr|en --dry-run|--apply|--restore`;
  measure: `card352_measure.py --lang fr`. English (#381): reviewed common senses in `quality/en_common_senses.json`
  → `card381_common.py check|apply|restore`. The exporter numbers senses by senses.ordinal (#389); after a re-rank run
  `card395_def_order.py count|apply|restore` so the definition items follow the ordinals too (admin UI, old servers);
  card fronts: `card381_learner.py --cefr A1,A2 --out f.tsv` (port of learnerMeaning). `meaning_index` also labels pictures from deeper plain senses that English
  Wiktionary confirms (motif 「pattern」).
- Example → sense guesses (#528): with no gloss evidence `adapters/local.py` binds a sentence to the first common sense of its
  part of speech (Kaikki order ≠ frequency) and marks it `evidence: fallback`; `tools/card528_pick.py measure|ask --batch N|judge|apply|restore`
  lets Qwen (tagger kind `pick`, asked twice) choose among that part of speech's senses (A1 words first).
- Relation-word Chinese after the word enters the lexicon (#462/#468): `backend/app/relation_backfill.py` — `process_word` calls `backfill_for_word` after materialize (fills other headwords' `*_native` slots still in `missing` + relation_translations, no AI); sweep `tools/card468_backfill.py measure|apply|restore`.
- Gender / forms / morphemes (#429): the App pack reads field_values (not the forms table). `card429_forms.py` (fr_gender by main sense), `card429_morph.py` (Wiktionary affix templates), `card429_measure.py` (fr vs en coverage); all dry-run|apply|restore.
- English -er/-est and more/most forms Wiktionary over-reports (#463/#465/#472): `adapters/kaikki.py` `degree_form_implausible` (3+ syllables), `degree_entry_unused` (one-word: more-first / not comparable / minor adjective), `degree_pos_minor` (minor adjective sense ≤ 1/4 → no more/most either; reviewed `DEGREE_KEEP`/`DEGREE_DROP`); DB sweeps `tools/card463_…`, `card465_…`, `card472_adj_degree_forms.py` dry-run|apply|restore.
- French inflection senses without `form_of` (#499/#504): Kaikki fr senses often only say 「second-person plural … of aimer」 in the gloss; `adapters/base.py` `is_form_sense` / `form_bases` / `gloss_inflection_base` read it (shared by `inflection_bases`, `card_base`, `kaikki._is_form_of`); `kaikki._form_entry_bases` = a pure form, or a verb with a form-of sense and no own conjugation (permettant, doutes, accusé), takes the base verb's table. Sweep `tools/card499_form_entries.py plan|backup|apply|report|restore` (drop / redirect / share).
- Out-of-use parts of speech (#504/#512): `kaikki.out_of_use_pos` — every sense obsolete/archaic beside a current part of speech (rich/verb, hier/verb) → no entry (`dropped_pos` = that ∪ `inflection_only_pos`, used by the adapter's `pos` / senses). Sweep `tools/card504_stale_pos.py plan|backup|apply|keep_translations|report|restore --lang en|fr [words]` (skips pictures, other-source pos, HELD).
- Example sentences must use the word (#527 / 問題回報 #562): `quality.example_flags` tokenizes Unicode words with
  French elision (l'école → école) and runs for French too (tatoeba.normalize, base validity); the gender letters m / f
  are never query forms. Re-resolve the four example fields of listed words with fresh code (points the adapters at the
  active snapshots, keeps DB-only #494 translations): `tools/card527_fr_examples.py measure|backup|run|report|restore`.
- CEFR (#335, issue #332 decision C): `word_level(w, "fr")` = `backend/app/fr_cefr_reviewed.json` (法語基礎 3000 字,
  Claude-reviewed A1–B1, `cefr_source=ai_reviewed`, app shows 估算) else max(wordfreq, Lexique 3.83 lemma zipf in
  `fr_lexique_lemma_zipf.json`). Rebuild / rewrite DB: `tools/card335_fr_cefr.py build|apply [--dry-run]|restore`;
  review batches `raw-data/card335_review/b0*.txt`, owner diff `raw-data/card335_fr_cefr_diff.tsv`.

## Data you should NOT read whole
- `lexicon/logs/agents/` is ~700 MB: `*pack*.json` are 100+ MB app-pack dumps, `*.jsonl` up to 18 MB. Use Python/jq to
  count or extract; read only `card<ID>.result.md` and the latest `card<ID>.prompt.txt` of a card.
- `lexicon/quality/entry_flags.json` (4.4k lines), `decisions.json` (1.7k) — query with Python.
- `lexicon/raw-data/`, `lexicon/media/` — data files, never open in the editor.
- Secrets — never open: `lexicon/.env`, `tagger/.api_key`, `app/tagging.local.json`.

## Reading big files (token budget)
- Find first: `rg -n "def _tag_asset" lexicon/backend/app/images.py` → read ~60 lines around the hit
  (`Get-Content f | Select-Object -Skip 1180 -First 60`, or your Read tool with offset/limit).
- Board state: `GET /api/tasks/<id>` or `python lexicon/tools/pick_card.py --agent X --all`. **Don't dump**
  `/api/schedule/board` (50 KB+ of JSON) into your context.
- Cap output: `| Select-Object -First 80`, `pytest -q`, `flutter test --reporter compact 2>&1 | Select-Object -Last 40`.

## Standing cards: reuse, don't rewrite
| Card | Check | Reuse |
|---|---|---|
| #3 缺圖 | `GET /api/schedule/board` metric `pictures_missing` | `lexicon/tools/_imgstat.py`, `lexicon/backend/app/image_fetch_audit.py` |
| #4 標籤佇列 | metric `labels_pending` | `lexicon/tools/_qstats.py` |
| #5 標籤分級 | metric `label_levels` | `lexicon/tools/_card97_cefr_audit.py`, `recompute_photo_tag_cefr.py` |
| #12 模擬使用者 | `python app/test/simulation/run_round.py` | `lexicon/docs/agents/simulation_usability.md` |
| #38 相似詞只從已有字 | live audit | `lexicon/logs/agents/card38_cursor_audit.py`, `card38_live_audit.py` |

## 下載完整詞庫（#742，owner 10/27 決定 A）
`https://api.willylinai.com/api/lexicon` 完整 JSON 未壓縮約 600 MB，經 Cloudflare tunnel 要 90 秒以上，中途斷線會得到「HTTP 200 但 JSON 不完整」。伺服器有送 Content-Length（客戶端請比對收到的 bytes）。請帶 `Accept-Encoding: gzip`（約 81 MB，`curl --compressed`）或用 `format=sqlite`（約 57 MB，App 使用）。
