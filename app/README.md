# photo_english_app (拍照學英文)

A phone app built from the Figma mobile screens
(file `T4tRODX2jQrCpRbrsU5vbj`, page "Screens") with behaviour from
`../spec-01-data-sources.html` (sections 1–7): choose a photo → AI finds
candidate words → this device picks at most five for your level → keep,
swipe away or correct them → leaving the page saves them as cards →
review with FSRS in a continuous flashcard flow.

## Run

```bash
flutter pub get
flutter run -d chrome --dart-define-from-file=tagging.local.json   # with the AI service
flutter test
```

Start the AI service first (`../tagger/start_tagger.bat`, see
`../tagger/README.md`). Without it, photos wait in a queue (hourglass)
and are tagged once the service is reachable. On a wide window the app
is shown inside a 402×874 phone frame; on a phone it is full screen.

First launch asks for the learning language, native language and a
self-assessed background, with an optional 18-word vocabulary check.

## Screens ↔ Figma

| Tab / screen | Figma frame | File |
|---|---|---|
| 拍照 · 圖辨單字 | camera-view 11:6 | `screens/camera_screen.dart` |
| 相片冊 · 我的相片冊 | photo-album-page 17:5 | `screens/album_screen.dart` |
| 照片詳情 (+ difficulty dial) | photo-detail-view 24:4, 54:77 | `screens/photo_detail_screen.dart` |
| 選擇照片 | photo-picker-page 17:87 | `screens/photo_picker_screen.dart` |
| 項目照片 / an album's photos / search | Project Photos · Mobile 39:65 | `screens/photo_grid_screen.dart` |
| 單字本 · 單字資料庫 | Word Database · Mobile 35:2 | `screens/word_database_screen.dart` |
| 單字詳情 | word-detail-view 11:173 | `screens/word_detail_screen.dart` |
| 複習 (Flashcard) | — (spec section 7) | `screens/flashcard_screen.dart` |
| 設定 | — | `screens/settings_screen.dart` |
| 首次設定 | — | `screens/onboarding_screen.dart` |

Icons are the SVGs exported from Figma (`assets/figma/mobile/`); the
複習 tab icon (`tab_cards*.svg`) is drawn in the same stroke style.

## How the spec is applied

- **Two-stage recognition (section 3)** — the tagger (Qwen3-VL on
  "Predator") proposes 12–20 candidates per photo: nouns, verbs,
  adjectives, adverbs and phrases, each with its evidence, location,
  visual confidence and usefulness. The pool is stored on the photo.
  `services/word_selector.dart` then scores them on the device —
  30% level fit + 25% unknown probability + 20% picture relevance + 15%
  usefulness + 10% part-of-speech variety − recent exposure — and picks
  at most 5 (at most 3 nouns, synonyms/word families once, one
  challenge word; fewer when nothing fits). 「為什麼是這些字？」 shows
  every score and rejection reason.
- **CEFR from a local word list** — `assets/cefr_en.json` (CEFR-J
  A1–B2 + Octanove C1/C2, wordfreq frequencies, CMUdict IPA; built by
  `../pipeline/build_cefr_list.py`) corrects the model's level guess.
- **Difficulty dial** — collapsed as in the mock; long-press opens the
  A1–C2 scale like a camera ISO dial and dragging swaps words live from
  the pool (the model is only asked again when the pool runs short).
  The choice is saved as the photo's `difficultyOffset`; each new photo
  starts at the learner's level.
- **照片詳情 (section 7)** — no 建立 button: leaving the page (back,
  another tab, backgrounding) saves the list and creates WordEntry,
  PhotoOccurrence and LearningCard. Swipe left = 已學會 (archived, never
  deleted; 顯示已學會單字 shows them with 復原). ☆ keeps a word while
  the dial moves, for this visit only. Drag a pin to move it; tap it to
  correct it (the AI's word is kept). A word already studied from
  another photo only gains this photo as a context. Removing every word
  takes the photo out of the album (not out of the phone's gallery).
- **One card per word (section 4)** — one LearningCard and FSRS state
  per word, whatever the number of photos; the card's back shows one of
  them at random, avoiding recent repeats.
- **複習 tab** — a continuous flow with no counts: front = first letter
  plus underscores, part of speech, native meaning (no photo); back =
  word, IPA, photo, 5–10 examples, template fields; pronunciation plays
  on flip (recording, else TTS). Again brings the card back a few cards
  later; the flow ends when nothing is due. Grades are in the native
  language.
- **Ability model** — Elo-style score (A1 = 0 … C2 = 5) updated by
  recall grades, known-word swipes and dial moves; the level changes
  after 20 signals, past a 0.2 buffer, one step at a time. A dial habit
  (5 of the last 8 photos) suggests a new default level in 設定.
- **Background work** — `TaggingQueue` tags waiting photos whenever the
  service answers (hourglass on thumbnails, no notifications);
  `WordEnricher` fetches definitions, 5–10 examples and translations
  (「AI 翻譯」) for new words, retries failures with back-off, and marks
  words that still fail in the word list. Learner edits are never
  overwritten.
- **Languages** — English, French or Traditional Chinese as learning or
  native language; each learning language has its own boxes (albums,
  words, cards, profile). Changing the native language re-translates
  existing words in the background.
- **Local only** — Hive stores everything; photos stay on the device.

## Deliberate differences from the mock

- Pins sit on the object they name (anchors are fractions of the
  original image); crowded pins flip, lift, or hang below the dot at the
  top edge.
- The camera view's words appear after taking the photo (the tagger
  works on stills).
- The mock's tab bar has four tabs; 複習 is the spec's fifth.
- The word-card ☆ is the spec's session lock, not a 單字本 toggle; the
  word detail's bottom button is 標為已學會 / 復原學習.

## Layout

```
lib/
  main.dart                 opens Hive per language, onboarding, workers
  app/                      shell (5 tabs + per-tab navigation), phone frame, AppScope
  models/                   WordEntry, WordCandidate, Photo/Album, PhotoOccurrence,
                            LearningCard, FsrsState, ReviewLog, CardTemplate,
                            UserVocabularyProfile (Elo)
  services/                 repository, Hive store (schema 3 + v2 migration),
                            word selector, CEFR lexicon, tagging client + queue,
                            word enricher, photo session, flashcard session,
                            FSRS-5, speaker (TTS), settings
  data/                     sample content from the mocks + real candidate pools
  screens/                  one file per screen (table above)
  widgets/mobile/           nav bars, chips, pins, dialogs, tab bar
test/                       87 tests
```

## Not done yet

- **UI text in the native language** — translations, hints and grade
  buttons follow the native language; the rest of the UI is still
  Traditional Chinese.
- **Word data for French / Chinese** comes from the AI only (no local
  word list or dictionary for them yet), and English examples are
  AI-written — Tatoeba (the spec's first source) isn't imported yet.
- **Device photo library** in 選擇照片 (needs `photo_manager`), camera
  on Windows desktop, FSRS parameter optimisation from the ReviewLog,
  the album's recommendation score, and a first-run flow for the
  Predator address (the spec defers these).
