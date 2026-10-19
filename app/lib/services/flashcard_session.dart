import 'dart:math' as math;
import 'dart:ui' show Offset, Rect;

import 'package:flutter/foundation.dart';

import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/word_entry.dart';
import 'learning_content.dart';
import 'license_links.dart';
import 'fsrs_scheduler.dart';
import 'word_database_repository.dart';
import 'lexicon_pack.dart';
import 'dictionary_sync.dart';
import 'photo_store.dart';

/// One photo the card back can show: the photo, where the word is on it
/// (null when unknown) and a learner-facing credit for the pack's pictures.
typedef CardPhoto = (Photo, LabelPoint?, String?);

enum ReviewExerciseType {
  sentenceCloze,
  photoChoice,
  similarMatch,
  photoRecall,
  imageDrag,
}

class ExercisePair {
  final String word;
  final String meaning;
  const ExercisePair(this.word, this.meaning);
}

class ExerciseTarget {
  final String word;
  final String meaning;
  final LabelPoint anchor;
  const ExerciseTarget(this.word, this.meaning, this.anchor);
}

class ReviewExercise {
  final ReviewExerciseType type;
  final String prompt;
  final String answer;
  final String? translation;
  final List<String> options;
  final List<ExercisePair> pairs;
  final List<ExerciseTarget> targets;

  const ReviewExercise({
    required this.type,
    required this.prompt,
    required this.answer,
    this.translation,
    this.options = const [],
    this.pairs = const [],
    this.targets = const [],
  });
}

/// Due cards are scheduled once, with optional unlimited extra practice.
/// The app enables [continuous]: future cards and already reviewed cards
/// remain playable without repeatedly changing their memory schedule.
/// Due-only consumers can retain the finite session default.
class FlashcardSession extends ChangeNotifier {
  /// How many cards later an Again card returns.
  static const againGap = 3;

  /// Maximum same-run appearances after the card's first appearance.
  static const maxAgainRepeats = 2;

  /// Most times one word shows in a run, counting correct repeats too
  /// (問題回報 #319 decision A): after that it waits for FSRS tomorrow.
  static const maxRunAppearances = 1 + maxAgainRepeats;

  final WordDatabaseRepository repo;
  final math.Random _random;
  final LexiconPack _lexicon;
  final bool continuous;

  /// Cards to show first, in this order, before the usual pick — the
  /// learner asked to practise these (學習洞察「複習這些字」, 問題回報 #307).
  /// A focus card that is not due is extra practice like any future card.
  final List<String> focus;
  final Set<String> _scheduledThisRun = {};
  bool _practice = false;
  bool get isExtraPractice => _practice;

  FlashcardSession(this.repo,
      {math.Random? random,
      LexiconPack? lexicon,
      this.continuous = false,
      this.focus = const []})
      : _random = random ?? math.Random(),
        _lexicon = lexicon ?? LexiconPack.instance {
    repo.addListener(_repositoryChanged);
    _advance();
  }

  bool _rating = false;
  bool _disposed = false;
  bool _photoGuarded = false;
  bool _photoReady = true;
  bool _photoFailed = false;
  int _photoAttempt = 0;

  bool get canAnswer => !_photoGuarded || _photoReady;
  bool get photoFailed => _photoFailed;
  int get photoAttempt => _photoAttempt;

  /// Called by the card renderer before rendering its controls. Headless
  /// sessions have no image renderer; rendered photo questions wait for pixels.
  void guardPhoto() {
    if (_photoGuarded || _back) return;
    if (_exercise?.type == ReviewExerciseType.photoChoice ||
        _exercise?.type == ReviewExerciseType.photoRecall ||
        _exercise?.type == ReviewExerciseType.imageDrag) {
      _photoGuarded = true;
      _photoReady = false;
    }
  }

  void reportPhotoState(int attempt, bool ready) {
    if (_disposed ||
        finished ||
        _back ||
        !_photoGuarded ||
        attempt != _photoAttempt) {
      return;
    }
    if (_photoReady == ready && _photoFailed == !ready) {
      return;
    }
    _photoReady = ready;
    _photoFailed = !ready;
    notifyListeners();
  }

  void retryPhoto() {
    if (_disposed || finished || _back || !_photoFailed) return;
    _photoAttempt++;
    _photoReady = false;
    _photoFailed = false;
    notifyListeners();
  }

  void _repositoryChanged() {
    if (_rating || finished) return;
    final current = card;
    if (current == null ||
        current.archived ||
        repo.entry(current.wordEntryId) == null) {
      _advance();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    repo.removeListener(_repositoryChanged);
    _watch.stop();
    super.dispose();
  }

  int _step = 0;
  final _shownAt = <String, int>{};
  final _again = <String, int>{};
  final _againRepeats = <String, int>{};
  final _appearances = <String, int>{};
  final _recentPhotos = <String>[];
  String? _lastPhoto;

  String? _cardId;
  String? _usageId;
  String? _senseId;
  Photo? _photo;
  LabelPoint? _anchor;
  Rect? _box;
  String? _photoCredit;
  bool _back = false;
  ReviewExercise? _exercise;
  bool? _correct;
  String? _submittedAnswer;
  int _attempts = 0;
  int _hintCount = 0;
  final _watch = Stopwatch();
  int _reviewed = 0;

  LearningCard? get card => _cardId == null ? null : repo.card(_cardId!);
  bool get finished => _cardId == null;
  bool get showingBack => _back;
  ReviewExercise? get exercise => _exercise;

  /// The usage/sense this exercise actually tests (spec section 7: 每次作答
  /// 保存實際測驗的 usage_id、sense_id). The card back must show this one's
  /// part of speech and meaning, not the entry's default usage.
  String? get usageId => _usageId;
  String? get senseId => _senseId;
  bool? get answerCorrect => _correct;
  String? get submittedAnswer => _submittedAnswer;
  int get attempts => _attempts;
  int get hintCount => _hintCount;

  /// The photo shown on the back: one of the word's photos, avoiding the
  /// ones shown recently (多張相關照片在背面隨機輪流顯示，避免連續重複).
  Photo? get photo => _photo;
  LabelPoint? get anchor => _anchor;

  /// The tagger's box around this word in [photo] (0–1 of the image), when
  /// it has a real one; the front draws it around the dot (卡 #253).
  Rect? get box => _box;
  String? get photoCredit => _photoCredit;

  int get reviewed => _reviewed;

  Rating _effectiveRating(Rating rating) {
    final recognition = _exercise?.type == ReviewExerciseType.photoChoice ||
        _exercise?.type == ReviewExerciseType.similarMatch;
    return recognition && _correct == true && rating.value > 2
        ? Rating.values[rating.index - 1]
        : rating;
  }

  /// Each button previews the exact grade that this exercise will record.
  Map<Rating, SchedulingResult> get ratingPreviews {
    final id = _cardId;
    if (id == null) return const {};
    final predictions = repo.previewReview(id);
    return {
      for (final rating in Rating.values)
        rating: predictions[_effectiveRating(rating)]!,
    };
  }

  void showAnswer() {
    if (finished || _back || !canAnswer) return;
    _attempts = math.max(1, _attempts);
    _back = true;
    notifyListeners();
  }

  void useHint() {
    // The hint (first letter) never changes, so it counts once per card.
    if (finished || _back || !canAnswer || _hintCount > 0) return;
    _hintCount++;
    notifyListeners();
  }

  void submitAnswer(String answer) {
    final x = _exercise;
    if (x == null || _back || !canAnswer) return;
    _attempts++;
    _submittedAnswer = answer.trim();
    _correct = answer.trim().toLowerCase() == x.answer.trim().toLowerCase();
    _back = true;
    notifyListeners();
  }

  void completeInteraction({required bool correct, required int attempts}) {
    if (_exercise == null || _back || !canAnswer) return;
    _attempts = math.max(1, attempts);
    _correct = correct;
    _back = true;
    notifyListeners();
  }

  void rate(Rating rating) {
    final id = _cardId;
    if (id == null || !_back) return;
    // Reviewing notifies the repository synchronously. Advance exactly once
    // after recording this grade, rather than inside that notification.
    _rating = true;
    try {
      if (!_practice) {
        repo.review(id, _effectiveRating(rating),
            requestedRating: rating,
            usageId: _usageId,
            senseId: _senseId,
            duration: _watch.elapsed,
            templateType: _exercise?.type.name,
            correct: _correct,
            hintCount: _hintCount,
            attempts: math.max(1, _attempts));
        _scheduledThisRun.add(id);
      }
    } finally {
      _rating = false;
    }
    _reviewed++;
    if (rating == Rating.again) {
      final repeats = _againRepeats[id] ?? 0;
      // Continuous mode caps returns too (問題回報 #319): past the cap the
      // card is left to its FSRS schedule instead of coming back every few
      // cards. Focus picks are not counted — they never come from this queue.
      if (repeats < maxAgainRepeats) {
        _againRepeats[id] = repeats + 1;
        _again[id] = _step + againGap;
      }
    }
    _step++;
    _advance();
  }

  void _advance() {
    _photoAttempt++;
    _photoGuarded = false;
    _photoReady = true;
    _photoFailed = false;
    _back = false;
    _correct = null;
    _submittedAnswer = null;
    _attempts = 0;
    _hintCount = 0;
    _exercise = null;
    _usageId = null;
    _senseId = null;
    _cardId = _pick();
    if (_cardId != null) {
      _practice = continuous &&
          (_scheduledThisRun.contains(_cardId) ||
              !repo.isEligible(card!, repo.clock()));
      _shownAt[_cardId!] = _step;
      _appearances[_cardId!] = (_appearances[_cardId!] ?? 0) + 1;
      _choosePhoto();
      // A card with no buildable interactive exercise falls back to the
      // traditional flip (word → native meaning) instead of being skipped
      // (問題回報 #207 decision A): skipping shrank the practice pool to
      // whichever handful of words always had a safe exercise.
      _exercise = _buildExercise();
    } else {
      _photo = null;
      _anchor = null;
      _box = null;
      _photoCredit = null;
    }
    _watch
      ..reset()
      ..start();
    notifyListeners();
  }

  ReviewExercise? _buildExercise() {
    final c = card;
    final original = c == null ? null : repo.entry(c.wordEntryId);
    if (original == null) return null;
    final usages = original.effectiveUsages;
    for (var i = 0; i < usages.length; i++) {
      final usage = usages[(_step + i) % usages.length];
      final senses =
          usage.senses.where((s) => s.meaning.trim().isNotEmpty).toList();
      for (final sense in senses) {
        _usageId = usage.id;
        _senseId = sense.id;
        final entry = original.copyWith(
            pos: usage.pos,
            meaning: sense.meaning,
            examples: usage.examples
                .where((e) =>
                    e.senseId == sense.id ||
                    (e.senseId == null && usage.senses.length == 1))
                .toList());
        final found = _exerciseFor(entry);
        if (found != null) return found;
      }
    }
    _usageId = null;
    _senseId = null;
    return null;
  }

  ReviewExercise? _exerciseFor(WordEntry entry) {
    final builders = <ReviewExercise? Function()>[
      () => _cloze(entry),
      () => _photoChoice(entry),
      () => _similarMatch(entry),
      () => _photoRecall(entry),
      () => _imageDrag(entry),
    ];
    for (var offset = 0; offset < builders.length; offset++) {
      final found = builders[(_step + offset) % builders.length]();
      if (found != null) return found;
    }
    return null;
  }

  ReviewExercise? _cloze(WordEntry entry) {
    final forms = <String>{entry.word, ...entry.forms.map((f) => f.form)}
        .where((f) => f.trim().isNotEmpty)
        .toList()
      ..sort((a, b) => b.length.compareTo(a.length));
    for (final example in learningExamples(entry, repo.profile.cefr)) {
      for (final form in forms) {
        final pattern = RegExp(r'(?<!\w)' + RegExp.escape(form) + r'(?!\w)',
            caseSensitive: false);
        final matches = pattern.allMatches(example.text).toList();
        if (matches.length != 1) continue;
        final prompt = example.text
            .replaceRange(matches.single.start, matches.single.end, '＿＿＿＿');
        // Use the same strict substring policy as the preview: another form
        // or a compound must not leave the answer visible after masking.
        final remaining = prompt.toLowerCase();
        if (forms.any((other) => remaining.contains(other.toLowerCase()))) {
          continue;
        }
        return ReviewExercise(
          type: ReviewExerciseType.sentenceCloze,
          prompt: prompt,
          answer: matches.single.group(0)!,
          translation: example.translation,
        );
      }
    }
    return null;
  }

  /// The only candidate source for comparison/choice exercises. A lexicon
  /// relation or a catalog image label does not mean the user owns that word.
  Map<String, WordEntry> _ownedExerciseEntries() => {
        for (final e in repo.entries)
          if (!repo.isArchived(e.id) &&
              LexiconPack.normalize(e.word).isNotEmpty)
            LexiconPack.normalize(e.word): e,
      };

  ReviewExercise? _photoChoice(WordEntry entry) {
    if (_photo == null) return null;
    final visible = <String>{LexiconPack.normalize(entry.word)};
    final photoId = _photo!.id;
    if (photoId.startsWith('db-')) {
      // Catalog images can show several valid labels even when only one of
      // them belongs to this review card. None can be a wrong answer.
      for (final image in _lexicon.catalogImages) {
        if ('db-${image['id']}' != photoId) continue;
        for (final label in [
          ...(image['tags'] as List? ?? []),
          ...(image['labels'] as List? ?? []),
        ]) {
          if (label is! Map) continue;
          final id = label['lexeme_id'];
          final linked = id is num ? _lexicon.byId(id.toInt()) : null;
          if (linked != null) visible.add(LexiconPack.normalize(linked.lemma));
          for (final key in ['word', 'cefrLemma']) {
            final word = label[key];
            if (word is String && word.trim().isNotEmpty) {
              visible.add(LexiconPack.normalize(word));
            }
          }
        }
      }
    } else {
      for (final o in repo.occurrencesInPhoto(photoId)) {
        final word = repo.entry(o.wordEntryId)?.word;
        if (word != null) visible.add(LexiconPack.normalize(word));
      }
    }
    final choices = _ownedExerciseEntries()
        .values
        .where((e) =>
            !visible.contains(LexiconPack.normalize(e.word)) &&
            e.meaning.trim().isNotEmpty &&
            e.pos == entry.pos &&
            (levelIndex(e.level) - levelIndex(entry.level)).abs() <= 1)
        .toList()
      ..shuffle(_random);
    if (choices.length < 2) return null;
    final options = [entry.word, choices[0].word, choices[1].word]
      ..shuffle(_random);
    return ReviewExercise(
        type: ReviewExerciseType.photoChoice,
        prompt: '哪個單字最適合這張照片？',
        answer: entry.word,
        options: options);
  }

  ReviewExercise? _similarMatch(WordEntry entry) {
    final related = <WordEntry>[];
    final owned = _ownedExerciseEntries();
    for (final relation in entry.related) {
      final found = owned[LexiconPack.normalize(relation.word)];
      if (found != null &&
          !relation.hideByDefault &&
          LexiconPack.normalize(found.word) !=
              LexiconPack.normalize(entry.word) &&
          found.meaning.trim().isNotEmpty &&
          !nativeGlossesOverlap(entry.meaning, found.meaning) &&
          related.every((e) =>
              LexiconPack.normalize(e.word) !=
                  LexiconPack.normalize(found.word) &&
              !nativeGlossesOverlap(e.meaning, found.meaning))) {
        related.add(found);
      }
    }
    if (related.length < 2) return null;
    final entries = [entry, ...related.take(2)];
    return ReviewExercise(
      type: ReviewExerciseType.similarMatch,
      prompt: '把三個意思和單字配對',
      answer: entry.word,
      pairs: [for (final e in entries) ExercisePair(e.word, e.meaning)],
    );
  }

  ReviewExercise? _photoRecall(WordEntry entry) {
    if (_photo == null || entry.meaning.trim().isEmpty) return null;
    return ReviewExercise(
      type: ReviewExerciseType.photoRecall,
      prompt: entry.meaning,
      answer: entry.word,
      translation: posLabel(entry.pos),
    );
  }

  /// A drag question always has this many labels (owner 2026-10-14): the
  /// card's word and two others on the same photo. A photo with fewer
  /// labelled words gives another kind of question.
  static const dragTargets = 3;

  ReviewExercise? _imageDrag(WordEntry entry) {
    final photo = _photo;
    if (photo == null) return null;
    final targets = <ExerciseTarget>[];
    final owned = _ownedExerciseEntries();
    void add(String word, String meaning, LabelPoint anchor) {
      final key = LexiconPack.normalize(word);
      final personal = owned[key];
      if (personal == null ||
          meaning.trim().isEmpty ||
          targets.any((t) => LexiconPack.normalize(t.word) == key)) {
        return;
      }
      targets.add(ExerciseTarget(personal.word, meaning, anchor));
    }

    if (!photo.id.startsWith('db-')) {
      final occurrences = repo.occurrencesInPhoto(photo.id);
      for (final o in [
        ...occurrences.where((o) => o.wordEntryId == entry.id),
        ...occurrences.where((o) => o.wordEntryId != entry.id),
      ]) {
        final e = repo.entry(o.wordEntryId);
        // A word added without a spot on the photo has nowhere to drag to.
        if (e != null && o.placed && !repo.isArchived(e.id)) {
          add(e.word, e.meaning, o.anchor);
        }
      }
    } else if (_anchor != null) {
      add(entry.word, entry.meaning, _anchor!);
      // The catalog picture's other reviewed labels.
      for (final image in _lexicon.catalogImages) {
        if ('db-${image['id']}' != photo.id) continue;
        for (final label in (image['labels'] as List? ?? [])) {
          final id = label is Map ? label['lexeme_id'] : null;
          final point = label is Map ? label['point'] : null;
          final lex = id is num ? _lexicon.byId(id.toInt()) : null;
          if (lex == null ||
              point is! List ||
              point.length != 2 ||
              !point.every((p) => p is num && p.isFinite && p >= 0 && p <= 1)) {
            continue;
          }
          add(
              lex.normalized,
              lex.learnerMeaning ?? '',
              LabelPoint(
                  (point[0] as num).toDouble(), (point[1] as num).toDouble()));
        }
      }
    }
    if (targets.length < dragTargets || targets.first.word != entry.word) {
      return null;
    }
    // The card's word is not always the first label to drag.
    final chosen = targets.take(dragTargets).toList()..shuffle(_random);
    return ReviewExercise(
      type: ReviewExerciseType.imageDrag,
      prompt: '把單字拖到照片中的正確位置',
      answer: entry.word,
      targets: chosen,
    );
  }

  /// Step at which an Again card last came back, so returns are spaced out.
  int _lastAgainReturn = -againGap;

  String? _takeAgain(String id) {
    _again.remove(id);
    _lastAgainReturn = _step;
    return id;
  }

  /// True once a word has used up its appearances in this run.
  bool _worn(String id) => (_appearances[id] ?? 0) >= maxRunAppearances;

  String? _pick() {
    // A queued Again card may have been marked learned from word details.
    _again.removeWhere((id, _) {
      final c = repo.card(id);
      return c == null || c.archived || repo.entry(c.wordEntryId) == null;
    });
    // An Again card whose turn has come — at most one return per [againGap]
    // steps. Serving every due Again card first let three forgotten words
    // refill the queue every three steps and crowd out the whole database
    // (問題回報 #315: 複習一直重複同幾個字); the other slots are fresh cards.
    final back = _again.entries.where((e) => e.value <= _step).toList()
      ..sort((a, b) => a.value.compareTo(b.value));
    if (back.isNotEmpty && _step - _lastAgainReturn >= againGap) {
      return _takeAgain(back.first.key);
    }
    for (final id in focus) {
      if (_shownAt.containsKey(id) || _again.containsKey(id)) continue;
      if (_worn(id)) continue;
      final c = repo.card(id);
      if (c != null && !c.archived && repo.entry(c.wordEntryId) != null) {
        return id;
      }
    }
    final now = repo.clock();
    final eligible = [
      for (final c in repo.eligibleCards())
        if (!_shownAt.containsKey(c.id) && !_again.containsKey(c.id)) c,
    ];
    if (eligible.isEmpty) {
      if (continuous) {
        // Extra practice: the card not shown for longest. Queued Again cards
        // wait for their own turn instead of being recycled here too — unless
        // the database is so small that the practice card was itself just
        // shown; then the Again card comes back early rather than repeating.
        // A word that reached [maxRunAppearances] waits for FSRS, not for
        // this pool (問題回報 #319); when no word is left the run ends.
        final pool = [
          for (final c in repo.eligibleCards(includeFuture: true))
            if (!_again.containsKey(c.id) && !_worn(c.id)) c,
        ];
        final practice = pool..shuffle(_random);
        practice.sort(
            (a, b) => (_shownAt[a.id] ?? -1).compareTo(_shownAt[b.id] ?? -1));
        final best = practice.firstOrNull;
        if (best != null &&
            (_again.isEmpty ||
                _step - (_shownAt[best.id] ?? -againGap) >= againGap)) {
          return best.id;
        }
      }
      // Only Again cards left: show the next one now rather than stop.
      if (_again.isEmpty) return null;
      final next = (_again.entries.toList()
            ..sort((a, b) => a.value.compareTo(b.value)))
          .first;
      return _takeAgain(next.key);
    }
    final photosByWord = repo.photoIdsByWord();
    double score(LearningCard c) {
      final r = repo.scheduler.retrievability(c.fsrs, now);
      final forgetting = r == null ? 0.5 : 1 - r;
      final photos = photosByWord[c.wordEntryId] ?? const <String>{};
      final variety =
          _lastPhoto != null && photos.contains(_lastPhoto) ? 0.0 : 1.0;
      return 0.6 * forgetting + 0.3 * variety + 0.1 * _random.nextDouble();
    }

    // Each card scored once (sort would call it again for every comparison).
    final scores = {for (final c in eligible) c.id: score(c)};
    eligible.sort((a, b) => scores[b.id]!.compareTo(scores[a.id]!));
    return eligible.first.id;
  }

  /// Every photo of the card's word — the learner's own first, then the
  /// language pack's approved pictures — so the back can swipe between
  /// them (card #251). Empty when the word has no photo.
  List<CardPhoto> get photoOptions => _photoOptions;
  List<CardPhoto> _photoOptions = const [];

  /// The learner swiped to another of the word's photos on the back.
  void selectPhoto(int index) {
    if (index < 0 || index >= _photoOptions.length) return;
    final chosen = _photoOptions[index];
    if (chosen.$1.id == _photo?.id) return;
    _photo = chosen.$1;
    _anchor = chosen.$2;
    _box = _boxes[chosen.$1.id];
    _photoCredit = chosen.$3;
    _lastPhoto = chosen.$1.id;
    notifyListeners();
  }

  void _choosePhoto() {
    final c = card;
    if (c == null) return;
    final seenIds = <String>{};
    final options = _photoOptions = [
      for (final o in [
        for (final o in repo.occurrencesOf(c.wordEntryId))
          // A learner's photo whose original file is gone is skipped, so the
          // card shows another picture of the word (問題回報 #279).
          if (repo.photo(o.photoId) case final p? when PhotoStore.canShow(p))
            (p, o.placed ? o.anchor : null, p.credit),
        ..._databasePhotos(c.wordEntryId),
      ])
        if (seenIds.add(o.$1.id)) o,
    ];
    if (options.isEmpty) {
      _photo = null;
      _anchor = null;
      _box = null;
      _photoCredit = null;
      return;
    }
    final fresh =
        options.where((o) => !_recentPhotos.contains(o.$1.id)).toList();
    final pickFrom = fresh.isEmpty ? options : fresh;
    final chosen = pickFrom[_random.nextInt(pickFrom.length)];
    _photo = chosen.$1;
    _anchor = chosen.$2;
    _box = _boxes[chosen.$1.id];
    _photoCredit = chosen.$3;
    _lastPhoto = chosen.$1.id;
    _recentPhotos.add(chosen.$1.id);
    if (_recentPhotos.length > 3) _recentPhotos.removeAt(0);
  }

  /// Database photos' label boxes, by photo id (see [box]).
  final _boxes = <String, Rect>{};

  List<CardPhoto> _databasePhotos(String wordId) {
    final entry = repo.entry(wordId);
    final lexemeId = entry?.lexemeId;
    if (entry == null ||
        lexemeId == null ||
        _lexicon.target != repo.language ||
        _lexicon.byId(lexemeId)?.normalized != entry.word) {
      return [];
    }
    final base = DictionarySync.instance
        .endpoint(repo.language, _lexicon.native ?? 'zh-TW');
    final found = <(Photo, LabelPoint?, String?)>[];
    final seen = <String>{};
    for (final image in _lexicon.catalogImages) {
      final url = image['url'];
      if (image['status'] != 'ready' ||
          url is! String ||
          url.trim().isEmpty ||
          !(image['tags'] as List? ?? []).any((tag) =>
              tag is Map &&
              tag['lexeme_id'] == lexemeId &&
              tag['review_status'] == 'approved')) {
        continue;
      }
      final id = 'db-${image['id']}';
      if (!seen.add(id)) continue;
      LabelPoint? anchor;
      for (final label in (image['labels'] as List? ?? [])) {
        if (label is! Map || label['lexeme_id'] != lexemeId) continue;
        final point = label['point'];
        if (point is List &&
            point.length == 2 &&
            point.every((p) => p is num && p.isFinite && p >= 0 && p <= 1)) {
          anchor = LabelPoint(
              (point[0] as num).toDouble(), (point[1] as num).toDouble());
          final b = label['box'];
          if (b is List &&
              b.length == 4 &&
              b.every((v) => v is num && v.isFinite && v >= 0 && v <= 1)) {
            final r = Rect.fromLTRB(
                (b[0] as num).toDouble(),
                (b[1] as num).toDouble(),
                (b[2] as num).toDouble(),
                (b[3] as num).toDouble());
            // The model's "middle of the picture" means the middle of its
            // box (as database_image_data.dart does).
            if (anchor.x == 0.5 && anchor.y == 0.5) {
              anchor = LabelPoint(r.center.dx, r.center.dy);
            }
            // A box around (nearly) the whole picture, or one the dot is
            // not in, says nothing: the dot alone is shown.
            if (r.width > 0 &&
                r.height > 0 &&
                r.width * r.height <= 0.9 &&
                r.inflate(0.02).contains(Offset(anchor.x, anchor.y))) {
              _boxes[id] = r;
            }
          }
          break;
        }
      }
      // Learner-facing credit for long-press only: author / attribution /
      // license. Skip raw source codes and numeric ids (#123).
      final creditParts = <String>[];
      for (final raw in [
        image['author'],
        image['attribution'],
        image['license'],
      ]) {
        if (raw is! String) continue;
        final s = raw.trim();
        if (s.isEmpty) continue;
        if (RegExp(r'^#?\d+$').hasMatch(s)) continue;
        if (creditParts.any((p) => p.toLowerCase() == s.toLowerCase())) {
          continue;
        }
        creditParts.add(s);
      }
      // Card #259: the license text and the picture's Commons/source page.
      final licenseRaw = image['license'];
      final licenseUrl = image['license_url'];
      final links = [
        licenseUrl is String && licenseUrl.trim().isNotEmpty
            ? licenseUrl.trim()
            : licenseUrlFor(licenseRaw is String ? licenseRaw : null),
        image['page_url'],
      ];
      final credit = [
        creditParts.join(' · '),
        for (final l in links)
          if (l is String && l.trim().isNotEmpty) l.trim(),
      ].join('\n');
      found.add((
        Photo(
            id: id,
            title: '',
            takenAt: DateTime(2000),
            createdAt: DateTime(2000),
            networkUrl: base.resolve(url).toString(),
            width: (image['width'] as num?)?.toInt(),
            height: (image['height'] as num?)?.toInt()),
        anchor,
        credit.isEmpty ? null : credit
      ));
    }
    return found;
  }
}
