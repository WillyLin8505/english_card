import 'dart:collection';
import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../models/card_template.dart';
import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/vocabulary_profile.dart';
import 'learning_insights.dart';
import '../models/word_candidate.dart';
import '../models/word_detail.dart';
import '../models/word_entry.dart';
import 'fsrs_scheduler.dart';
import 'fsrs_optimizer.dart';
import 'lexicon_pack.dart';
import 'pack_media.dart';
import 'photo_store.dart';
import 'word_database_query.dart';
import 'word_database_store.dart';
import 'word_selector.dart';
import 'analytics.dart';

class DuplicateWordException implements Exception {
  final WordEntry existing;
  DuplicateWordException(this.existing);

  @override
  String toString() => '「${existing.word}（${existing.pos}）」已在單字資料庫中';
}

/// A word on a photo's list when it is saved: the candidate it came
/// from, where its pin is, and — for a word that was on the list before —
/// its occurrence.
class ListedWord {
  final WordCandidate candidate;
  final LabelPoint anchor;

  /// What the AI originally called it, when the learner corrected the
  /// word or its meaning (spec: AI 原始標籤 / 使用者修正版).
  final String? aiLabel;
  final bool edited;

  /// Typed in by the learner (問題回報 #323): no AI label behind it.
  final bool added;

  /// False when an added word was never put on the photo (no pin).
  final bool placed;

  /// The learner typed the meaning: stored as their edit even when a new
  /// entry starts with it, so background updates keep it.
  final bool ownMeaning;

  const ListedWord(this.candidate, this.anchor,
      {this.aiLabel,
      this.edited = false,
      this.added = false,
      this.placed = true,
      this.ownMeaning = false});

  String get word => candidate.word;
}

/// The word database of one learning language: photos and albums,
/// WordEntries, their PhotoOccurrences and LearningCards, review
/// history, the card template and the learner's vocabulary profile.
///
/// Everything is held in memory (screens filter and sort on every
/// keystroke) and each change is written through to [store] — Hive in
/// the app, nothing in most tests.
class WordDatabaseRepository extends ChangeNotifier {
  /// The learning language ("en", "fr", "zh-TW").
  final String language;

  final _VersionedList<WordEntry> _entries;
  final List<Photo> _photos;
  final List<Album> _albums;
  final _VersionedList<PhotoOccurrence> _occurrences;
  final _VersionedList<LearningCard> _cards;
  final List<ReviewLog> _reviewLogs;
  CardTemplate _template;
  UserVocabularyProfile _profile;

  final WordDatabaseStore? store;
  final _pendingWrites = <Future<void>>{};
  (Object, StackTrace)? _writeFailure;

  /// Replaced when the learner changes 期望記憶率 (AppSettings).
  FsrsScheduler scheduler;

  FsrsOptimization? fsrsOptimization;
  Future<void>? _optimizationFuture;
  int _lastOptimizationSize = 0;
  int _effectiveReviewCount = 0;
  bool _disposed = false;

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  /// Retention is independent of the learned memory model.
  void setDesiredRetention(double retention) {
    scheduler = FsrsScheduler(FsrsParameters(
      w: fsrsOptimization?.weights ?? FsrsParameters.defaultWeights,
      desiredRetention: retention,
      maximumInterval: scheduler.params.maximumInterval,
    ));
  }

  /// Runs off the UI isolate on native platforms; compute is synchronous on
  /// web. Coalesce calls and retrain after 100 more logs, never per button.
  Future<void> optimizeFsrs({FsrsOptimization? saved}) {
    if (_optimizationFuture != null) return _optimizationFuture!;
    final snapshot = List<ReviewLog>.of(_reviewLogs);
    _lastOptimizationSize = _effectiveReviewCount;
    final future = _runFsrsOptimization(snapshot, saved);
    _optimizationFuture = future;
    return future;
  }

  Future<void> _runFsrsOptimization(
      List<ReviewLog> snapshot, FsrsOptimization? saved) async {
    // Ensure the field above is assigned even when a test compute fails early.
    await Future<void>.delayed(Duration.zero);
    FsrsOptimization? result;
    try {
      result = await compute(_fitFsrs, (snapshot, saved));
      final destination = store;
      if (destination is FsrsOptimizationStore) {
        await (destination as FsrsOptimizationStore)
            .putFsrsOptimization(result);
      }
    } catch (_) {
      result = null;
    }
    if (!_disposed) {
      fsrsOptimization = result;
      setDesiredRetention(scheduler.params.desiredRetention);
      // Reconstruct memory using the same model as offline evaluation. Keep
      // existing due dates and counters; new intervals start on the next grade.
      // No historical ReviewLog or stored card is rewritten by calibration.
      final histories = FsrsOptimizer.histories(_reviewLogs);
      final states = <String, FsrsState>{};
      for (final rows in histories) {
        var state = FsrsState.initial;
        for (final row in rows) {
          state = scheduler.next(state, row.rating, row.reviewedAt).state;
        }
        states[rows.first.cardId] = state;
      }
      for (var i = 0; i < _cards.length; i++) {
        final c = _cards[i], old = _cards[i].fsrs;
        final state = states[c.id];
        if (state == null || state.lastReview != old.lastReview) continue;
        _cards[i] = c.copyWith(
            fsrs: FsrsState(
          state: old.state,
          stability: state.stability,
          difficulty: state.difficulty,
          due: old.due,
          lastReview: old.lastReview,
          scheduledDays: old.scheduledDays,
          reps: old.reps,
          lapses: old.lapses,
          algorithmVersion: old.algorithmVersion,
        ));
      }
      notifyListeners();
    }
    _optimizationFuture = null;
  }

  /// Looks up the offline pipeline's data for a word (WordDetailService)
  /// so a new word arrives with IPA, forms, related words and examples.
  final WordDetail? Function(String word)? lookupDetail;

  /// Timestamps new records; injectable for tests.
  final DateTime Function() clock;

  int _nextId = 0;
  LexiconPack? _linkedPack;
  String? _linkedVersion;

  /// Words a dictionary update filled in, by entry id → the fields
  /// ([missingFieldNames]) that were missing before it and are there now
  /// (問題回報 #300: the 單字本 shows a one-time notice instead of a
  /// silent update). Only a new pack version counts; linking the same pack
  /// again after adding a word is not an update.
  final Map<String, Set<String>> _filledByUpdate = {};

  Map<String, Set<String>> get filledByUpdate => {
        for (final x in _filledByUpdate.entries)
          if (entry(x.key) != null) x.key: Set.unmodifiable(x.value),
      };

  /// The learner has seen the notice; [notify] is false while a widget is
  /// being disposed.
  void dismissPackUpdateNotice({bool notify = true}) {
    if (_filledByUpdate.isEmpty) return;
    _filledByUpdate.clear();
    if (notify) notifyListeners();
  }

  WordDatabaseRepository({
    this.language = 'en',
    List<WordEntry> entries = const [],
    List<Photo> photos = const [],
    List<Album> albums = const [],
    List<PhotoOccurrence> occurrences = const [],
    List<LearningCard> cards = const [],
    List<ReviewLog> reviewLogs = const [],
    CardTemplate? template,
    UserVocabularyProfile? profile,
    this.store,
    FsrsOptimization? fsrsOptimization,
    this.scheduler = const FsrsScheduler(),
    this.lookupDetail,
    this.clock = DateTime.now,
  })  : _entries = _VersionedList([...entries]),
        _photos = [...photos],
        _albums = [...albums],
        _occurrences = _VersionedList([...occurrences]),
        _cards = _VersionedList([...cards]),
        _reviewLogs = [...reviewLogs],
        _template = template ?? CardTemplate.photoWordCard,
        _profile = profile ?? UserVocabularyProfile.start('A1', now: clock()) {
    _normalizeLegacyPhotoWordLimits();
    _effectiveReviewCount = _reviewLogs.where(FsrsOptimizer.effective).length;
    if (_effectiveReviewCount >= FsrsOptimizer.minimumReviews) {
      unawaited(optimizeFsrs(saved: fsrsOptimization));
    }
  }

  /// Older persisted/sample builds could save more than the current
  /// five-word maximum on one photo. Preserve every occurrence, card and
  /// FSRS record, but turn overflow labels into context-only links so they
  /// no longer appear as extra learning words on that photo.
  void _normalizeLegacyPhotoWordLimits() {
    final knownEntries = {for (final e in _entries) e.id};
    final archived = {
      for (final c in _cards)
        if (c.archived) c.wordEntryId
    };
    final byPhoto = <String, List<PhotoOccurrence>>{};
    for (final o in _occurrences) {
      if (o.contextOnly ||
          !knownEntries.contains(o.wordEntryId) ||
          archived.contains(o.wordEntryId)) {
        continue;
      }
      (byPhoto[o.photoId] ??= []).add(o);
    }
    for (final listed in byPhoto.values) {
      for (final overflow in listed.skip(WordSelector.maxWords)) {
        final i = _occurrences.indexWhere((o) => o.id == overflow.id);
        if (i < 0) continue;
        final context = _occurrences[i].copyWith(contextOnly: true);
        _occurrences[i] = context;
        _persist((s) => s.putOccurrence(context));
      }
    }
  }

  factory WordDatabaseRepository.fromData(
    WordDatabaseData data, {
    String language = 'en',
    WordDatabaseStore? store,
    WordDetail? Function(String word)? lookupDetail,
    DateTime Function() clock = DateTime.now,
    UserVocabularyProfile? profile,
  }) =>
      WordDatabaseRepository(
        language: language,
        entries: data.entries,
        photos: data.photos,
        albums: data.albums,
        occurrences: data.occurrences,
        cards: data.cards,
        reviewLogs: data.reviewLogs,
        fsrsOptimization: data.fsrsOptimization,
        template: data.template,
        profile: data.profile ?? profile,
        store: store,
        lookupDetail: lookupDetail,
        clock: clock,
      );

  /// Fire-and-forget write: the in-memory copy is already updated, so the
  /// UI never waits on disk. A failed write is logged, not surfaced.
  void _persist(Future<void> Function(WordDatabaseStore s) write) {
    final s = store;
    if (s == null) return;
    final future = Future<void>.sync(() => write(s));
    _pendingWrites.add(future);
    unawaited(future.then<void>((_) {
      _pendingWrites.remove(future);
    }, onError: (Object e, StackTrace st) {
      _pendingWrites.remove(future);
      _writeFailure = (e, st);
      debugPrint('WordDatabaseStore write failed: $e\n$st');
    }));
  }

  /// Wait before an orderly close/reopen. This also drains writes started
  /// during the wait and reports failures that the UI logged asynchronously.
  /// It cannot guarantee storage after a process is forcibly terminated.
  Future<void> flush() async {
    await _optimizationFuture;
    while (_pendingWrites.isNotEmpty) {
      await Future.wait(_pendingWrites.toList());
    }
    final failure = _writeFailure;
    if (failure != null) Error.throwWithStackTrace(failure.$1, failure.$2);
  }

  String _newId(String prefix) =>
      '$prefix-${clock().microsecondsSinceEpoch}-${_nextId++}';

  // ── Reads ────────────────────────────────────────────────────────────

  List<WordEntry> get entries => List.unmodifiable(_entries);
  int get wordCount => _entries.length;
  int get cardCount => _cards.where((c) => !c.archived).length;
  int get photoCount => photos.length;
  CardTemplate get template => _template;
  UserVocabularyProfile get profile => _profile;

  /// Newest first. Photos still waiting for their first safety check
  /// ([PhotoSafetyStatus.unchecked]: queued offline, no tagger, or the
  /// tagger failed) are shown too (問題回報 #640, owner chose A): they used
  /// to stay hidden forever when tagging never succeeded. Only the photos
  /// the server rejects as unsafe (HTTP 451) are hidden, and TaggingQueue
  /// removes those from the repository outright, so nothing here can show
  /// them.
  List<Photo> get photos =>
      [..._photos]..sort((a, b) => b.takenAt.compareTo(a.takenAt));

  /// Same as [photos]; kept for the queue and the duplicate check, which
  /// read every photo whatever its safety state.
  List<Photo> get allPhotos => photos;

  List<Album> get albums => List.unmodifiable(_albums);

  List<String> get partsOfSpeech => {
        for (final e in _entries) ...e.partsOfSpeech.where((p) => p.isNotEmpty),
      }.toList(growable: false);

  // Lookup tables, rebuilt whenever their list changes (any write bumps the
  // list's version). Screens filter on every keystroke and the review picks
  // among thousands of cards: linear scans per item made both O(n²).
  int _entriesSeen = -1, _cardsSeen = -1, _occSeen = -1;
  Map<String, WordEntry> _entryById = const {};
  Map<String, LearningCard> _cardById = const {}, _cardByWord = const {};
  Map<String, List<PhotoOccurrence>> _occByWord = const {},
      _occByPhoto = const {};

  void _indexEntries() {
    if (_entriesSeen == _entries.version) return;
    final m = <String, WordEntry>{};
    for (final e in _entries) {
      m.putIfAbsent(e.id, () => e);
    }
    _entryById = m;
    _entriesSeen = _entries.version;
  }

  void _indexCards() {
    if (_cardsSeen == _cards.version) return;
    final byId = <String, LearningCard>{}, byWord = <String, LearningCard>{};
    for (final c in _cards) {
      byId.putIfAbsent(c.id, () => c);
      byWord.putIfAbsent(c.wordEntryId, () => c);
    }
    _cardById = byId;
    _cardByWord = byWord;
    _cardsSeen = _cards.version;
  }

  void _indexOccurrences() {
    if (_occSeen == _occurrences.version) return;
    final byWord = <String, List<PhotoOccurrence>>{};
    final byPhoto = <String, List<PhotoOccurrence>>{};
    for (final o in _occurrences) {
      (byWord[o.wordEntryId] ??= []).add(o);
      (byPhoto[o.photoId] ??= []).add(o);
    }
    _occByWord = byWord;
    _occByPhoto = byPhoto;
    _occSeen = _occurrences.version;
  }

  WordEntry? entry(String id) {
    _indexEntries();
    return _entryById[id];
  }

  /// The entry spelled [word] (normalized), whatever its part of speech.
  WordEntry? entryByWord(String word) {
    final w = word.trim().toLowerCase();
    return _entries.where((e) => e.word == w).firstOrNull;
  }

  Photo? photo(String id) => _photos.where((p) => p.id == id).firstOrNull;
  Album? album(String id) => _albums.where((a) => a.id == id).firstOrNull;
  PhotoOccurrence? occurrence(String id) =>
      _occurrences.where((o) => o.id == id).firstOrNull;
  LearningCard? card(String id) {
    _indexCards();
    return _cardById[id];
  }

  /// The word's one card, if it has been saved from a photo or added.
  LearningCard? cardOf(String wordEntryId) {
    _indexCards();
    return _cardByWord[wordEntryId];
  }

  bool isArchived(String wordEntryId) => cardOf(wordEntryId)?.archived ?? false;

  /// Words with an active card — being studied (spec: 已學習).
  Set<String> get studyingWords => {
        for (final c in _cards)
          if (!c.archived)
            if (entry(c.wordEntryId) case final e?) e.word,
      };

  List<PhotoOccurrence> occurrencesOf(String wordEntryId) {
    _indexOccurrences();
    return [...?_occByWord[wordEntryId]];
  }

  List<PhotoOccurrence> occurrencesInPhoto(String photoId) {
    _indexOccurrences();
    return [...?_occByPhoto[photoId]];
  }

  /// The photo's labels that show by default: words not archived as 已學會
  /// (spec: 照片詳情預設隱藏已學會單字; 相片冊縮圖不顯示已學會標籤).
  List<({PhotoOccurrence occ, WordEntry entry})> activeLabels(String photoId) =>
      [
        for (final o in occurrencesInPhoto(photoId))
          if (entry(o.wordEntryId) case final e?)
            if (!isArchived(e.id)) (occ: o, entry: e),
      ];

  /// Labels that may be drawn on a photo. Context-only occurrences keep the
  /// photo available to a word/card but never become visible learning pins.
  List<({PhotoOccurrence occ, WordEntry entry})> visibleLabels(
          String photoId) =>
      [
        for (final l in activeLabels(photoId))
          if (!l.occ.contextOnly) l
      ];

  /// Photos the word appears in (the 項目照片 screen), newest first.
  List<Photo> photosOfWord(String wordEntryId) {
    final ids = {for (final o in occurrencesOf(wordEntryId)) o.photoId};
    return [
      for (final p in photos)
        if (ids.contains(p.id)) p
    ];
  }

  List<Photo> photosInAlbum(String albumId) => [
        for (final p in photos)
          if (p.albumId == albumId) p
      ];

  /// Distinct words being learned across the album's photos ("18 個單字").
  int albumWordCount(String albumId) {
    final photoIds = {
      for (final p in _photos)
        if (p.albumId == albumId) p.id
    };
    return {
      for (final o in _occurrences)
        if (photoIds.contains(o.photoId) && !isArchived(o.wordEntryId))
          o.wordEntryId,
    }.length;
  }

  /// The cover shown on an album card: the newest photo that can be shown
  /// (a photo whose original file is gone is skipped, 問題回報 #283).
  Photo? albumCoverPhoto(String albumId) =>
      photosInAlbum(albumId).where(PhotoStore.canShow).firstOrNull;

  /// The picture on a 複習 tile with no album of its own (綜合, 今天新加的,
  /// 弱項): the newest photo that can be shown of one of [cardIds]' words,
  /// or of any word being learned when [cardIds] is null. A photo outside
  /// [avoid] (already on another tile) is preferred.
  Photo? reviewCoverPhoto(Set<String>? cardIds,
      {Set<String> avoid = const {}}) {
    final words = {
      for (final c in _cards)
        if (!c.archived && (cardIds == null || cardIds.contains(c.id)))
          c.wordEntryId,
    };
    final ids = {
      for (final o in _occurrences)
        if (words.contains(o.wordEntryId)) o.photoId,
    };
    final shown = [
      for (final p in photos)
        if (ids.contains(p.id) && PhotoStore.canShow(p)) p
    ];
    return shown.where((p) => !avoid.contains(p.id)).firstOrNull ??
        shown.firstOrNull;
  }

  /// 學習洞察: review counts, level changes and weak words.
  LearningInsights insights() {
    final wordOfCard = {for (final c in _cards) c.id: c.wordEntryId};
    return LearningInsights.compute(
      logs: _reviewLogs,
      profile: _profile,
      now: clock(),
      wordOf: (cardId) {
        final id = wordOfCard[cardId];
        return id == null ? null : entry(id)?.word;
      },
    );
  }

  /// The last [n] grades, oldest first (問題回報 #533: the review time
  /// estimate goes by the learner's own pace).
  List<ReviewLog> recentReviewLogs(int n) => List.unmodifiable(
      _reviewLogs.sublist(_reviewLogs.length > n ? _reviewLogs.length - n : 0));

  List<ReviewLog> logsOf(String cardId) => [
        for (final l in _reviewLogs)
          if (l.cardId == cardId) l,
      ];

  /// All rows matching [filter], sorted — paging is left to the caller
  /// (PageSlice.of) so the footer can show the full match count.
  List<DatabaseRow> query(WordDatabaseFilter filter) {
    final rows = <DatabaseRow>[];
    // Lookup tables built once (the list used to scan every card and photo
    // label for each word).
    final cardsByWord = {for (final c in _cards) c.wordEntryId: c};
    final occByWord = <String, List<PhotoOccurrence>>{};
    for (final o in _occurrences) {
      (occByWord[o.wordEntryId] ??= []).add(o);
    }
    final photoById = {for (final p in _photos) p.id: p};
    for (final entry in _entries) {
      // Words saved before adj / adj. were unified match either spelling.
      if (filter.pos != null &&
          !entry.partsOfSpeech.contains(shortPos(filter.pos!))) {
        continue;
      }
      if (filter.level != null && entry.level != filter.level) continue;
      if (filter.missing != null && !filter.missing!.isMissingIn(entry)) {
        continue;
      }
      final occurrences = occByWord[entry.id] ?? const <PhotoOccurrence>[];
      final photosOfEntry = [
        for (final o in occurrences)
          if (photoById[o.photoId] case final p?) p,
      ];
      if (!matchesSearch(filter.search, entry, photosOfEntry)) continue;
      if (filter.album != null &&
          !photosOfEntry.any((p) => p.albumId == filter.album)) {
        continue;
      }
      final card = cardsByWord[entry.id];
      rows.add(DatabaseRow(
        id: entry.id,
        entry: entry,
        card: card,
        photoCount: photosOfEntry.length,
        status: StudyStatus.of(card),
      ));
    }
    final status = filter.status;
    if (status != null) rows.removeWhere((r) => r.status != status);
    rows.sort((a, b) => compareRows(filter.sort, a, b));
    return rows;
  }

  // ── Profile ──────────────────────────────────────────────────────────

  void _setProfile(UserVocabularyProfile p) {
    _profile = p;
    _persist((s) => s.putProfile(p));
  }

  /// One behaviour signal for the ability model (see UserVocabularyProfile).
  void recordSignal(AbilitySignal signal) {
    _setProfile(_profile.update(signal, clock()));
    notifyListeners();
  }

  /// Sets the overall level by hand (設定) or from onboarding.
  void setLevel(String cefr, {String source = 'user'}) {
    _setProfile(_profile.withLevel(cefr, source, clock()));
    notifyListeners();
  }

  // ── Words ────────────────────────────────────────────────────────────

  WordEntry _createEntry({
    required String word,
    String? pos,
    required String meaning,
    String? level,
    String? levelSource,
    String? ipa,
    String? ipaSource,
    double? frequency,
    WordDataStatus dataStatus = WordDataStatus.complete,
    int? lexemeId,
  }) {
    final normalized = word.trim().toLowerCase();
    final pack = _linkedPack ?? LexiconPack.instance;
    final entry = WordEntry.fromUserInput(
      id: _newId('word'),
      word: normalized,
      pos: pos,
      language: language,
      meaning: meaning,
      level: level,
      levelSource: levelSource,
      ipa: ipa,
      ipaSource: ipaSource,
      frequency: frequency,
      detail: language == 'en' ? lookupDetail?.call(normalized) : null,
      dataStatus: dataStatus,
      lexemeId: lexemeId,
      now: clock(),
    ).copyWith(
        entryType: pack.target == language
            ? pack.lookup(normalized, pos: pos)?.entry.entryType ?? 'word'
            : 'word',
        usages:
            pack.target == language ? pack.usagesFor(normalized) : const []);
    _entries.add(entry);
    _persist((s) => s.putEntry(entry));
    return entry;
  }

  LearningCard _ensureCard(String wordEntryId) {
    final existing = cardOf(wordEntryId);
    if (existing != null) return existing;
    final now = clock();
    final card = LearningCard(
      id: LearningCard.idFor(wordEntryId),
      wordEntryId: wordEntryId,
      templateId: _template.id,
      language: language,
      createdAt: now,
      updatedAt: now,
    );
    _cards.add(card);
    _persist((s) => s.putCard(card));
    return card;
  }

  /// 新增單字 in the word list. Rejects a spelling that already exists, in
  /// any part of speech: spec section 7 (which overrides section 5's
  /// spelling + POS key) keeps one LexicalEntry and one card per spelling.
  /// The word gets its card at once, so it can be reviewed even before it
  /// appears in a photo.
  WordEntry addWord({
    required String word,
    required String pos,
    required String meaning,
    String? level,
  }) {
    final normalized = word.trim().toLowerCase();
    final existing = _entries.where((e) => e.word == normalized).firstOrNull;
    if (existing != null) throw DuplicateWordException(existing);
    final entry = _createEntry(
      word: normalized,
      pos: pos,
      meaning: meaning,
      level: level,
      levelSource: level == null ? null : 'user',
      dataStatus: WordDataStatus.pending,
    );
    _ensureCard(entry.id);
    _attachOwnPhotos([entry]);
    _setProfile(
        _profile.withFamiliarity(entry.word, Familiarity.learning, clock()));
    notifyListeners();
    Analytics.instance
        .capture('word_added', {'source': 'manual', 'pos': pos}, clock());
    return entry;
  }

  void _putEntry(WordEntry updated) {
    final i = _entries.indexWhere((e) => e.id == updated.id);
    _entries[i] = updated;
    _persist((s) => s.putEntry(updated));
  }

  /// A learner's edit (spec section 7: 使用者可編輯所有 AI 與字典資料).
  /// [fields] (WordField names) are marked as user-edited, so background
  /// updates never overwrite them.
  void editEntry(WordEntry updated, Set<String> fields) {
    final current = entry(updated.id);
    if (current == null) return;
    _putEntry(updated.copyWith(
      userEdited: {...current.userEdited, ...fields},
      updatedAt: clock(),
    ));
    notifyListeners();
  }

  /// Background word data (local dictionary / AI). Fields the learner
  /// edited are left alone; examples are only added. With [translatedFor]
  /// the meaning, definition and example translations are replaced by
  /// ones in that native language (母語變更後重新翻譯).
  void applyWordData(
    String wordEntryId, {
    String? meaning,
    String? definition,
    String? ipa,
    String? ipaSource,
    List<WordExample> newExamples = const [],
    Map<int, String> translations = const {},
    String? translatedFor,
    required WordDataStatus status,
    String? error,
  }) {
    final e = entry(wordEntryId);
    if (e == null) return;
    final replace = translatedFor != null && translatedFor != e.nativeOfData;
    bool free(String field) => !e.userEdited.contains(field);
    final examples = [...e.examples];
    if (free(WordField.examples)) {
      for (final t in translations.entries) {
        if (t.key < examples.length &&
            (replace || (examples[t.key].translation ?? '').isEmpty) &&
            t.value.trim().isNotEmpty) {
          examples[t.key] = examples[t.key]
              .copyWith(translation: t.value, aiTranslated: true);
        }
      }
      for (final x in newExamples) {
        if (examples.length >= 10) break;
        if (examples.any((y) => y.text.toLowerCase() == x.text.toLowerCase())) {
          continue;
        }
        examples.add(x);
      }
    }
    _putEntry(e.copyWith(
      meaning: free(WordField.meaning) &&
              (replace || e.meaning.isEmpty) &&
              (meaning ?? '').isNotEmpty
          ? meaning
          : null,
      definition: free(WordField.definition) &&
              (replace || e.definition == null) &&
              definition != null
          ? () => definition
          : null,
      translatedFor: status == WordDataStatus.complete ? translatedFor : null,
      ipa: free(WordField.ipa) && e.ipa == null && ipa != null
          ? () => ipa
          : null,
      ipaSource: free(WordField.ipa) && e.ipa == null && ipa != null
          ? () => ipaSource
          : null,
      examples: examples,
      dataStatus: status,
      dataError: () => error,
      dataAttempts:
          status == WordDataStatus.failed ? e.dataAttempts + 1 : e.dataAttempts,
      updatedAt: clock(),
    ));
    notifyListeners();
  }

  /// Marks a word's data fetch as pending again (manual 重試).
  void retryWordData(String wordEntryId) {
    final e = entry(wordEntryId);
    if (e == null) return;
    _putEntry(
        e.copyWith(dataStatus: WordDataStatus.pending, dataError: () => null));
    notifyListeners();
  }

  /// Entries whose full data still has to be fetched.
  List<WordEntry> get entriesNeedingData => [
        for (final e in _entries)
          if (e.dataStatus != WordDataStatus.complete) e,
      ];

  // ── 已學會 (archive) ─────────────────────────────────────────────────

  /// Swiped away as known: the card is archived — never deleted — and the
  /// word joins the language's 已學會 list.
  void archiveWord(String wordEntryId) {
    final e = entry(wordEntryId);
    if (e == null) return;
    final i = _cards.indexWhere((c) => c.wordEntryId == wordEntryId);
    if (i >= 0) {
      _setCard(i, _cards[i].copyWith(archived: true, updatedAt: clock()));
    }
    _setProfile(_profile
        .withFamiliarity(e.word, Familiarity.mastered, clock())
        .update(KnownWordSignal(e.level ?? 'B1'), clock()));
    notifyListeners();
  }

  /// A suggested word (no card yet) swiped away as known.
  void markKnown(WordCandidate c) {
    _setProfile(_profile
        .withFamiliarity(c.word, Familiarity.mastered, clock())
        .update(KnownWordSignal(c.level), clock()));
    notifyListeners();
  }

  /// 復原: the card comes back with its review history and FSRS state.
  void restoreWord(String word) {
    final e = entryByWord(word);
    final now = clock();
    if (e != null) {
      final i = _cards.indexWhere((c) => c.wordEntryId == e.id);
      if (i >= 0) {
        _setCard(i, _cards[i].copyWith(archived: false, updatedAt: now));
      }
      // A photo that filled its list again after this word was swiped
      // away keeps it as a context only, so the list stays at five words.
      for (final o in occurrencesOf(e.id)) {
        if (o.contextOnly) continue;
        final listed =
            activeLabels(o.photoId).where((l) => !l.occ.contextOnly).length;
        if (listed <= WordSelector.maxWords) continue;
        final j = _occurrences.indexWhere((x) => x.id == o.id);
        if (j < 0) continue;
        final context = _occurrences[j].copyWith(contextOnly: true);
        _occurrences[j] = context;
        _persist((s) => s.putOccurrence(context));
      }
      _setProfile(_profile.withFamiliarity(e.word, Familiarity.learning, now));
    } else {
      _setProfile(_profile.withoutFamiliarity(word.trim().toLowerCase(), now));
    }
    notifyListeners();
  }

  // ── Photos, albums and labels ────────────────────────────────────────

  Album addAlbum({
    required String name,
    String? category,
    String? deckSlug,
    String? author,
  }) {
    final album = Album(
      id: _newId('album'),
      name: name.trim(),
      category: category,
      createdAt: clock(),
      deckSlug: deckSlug,
      author: author,
    );
    _albums.add(album);
    _persist((s) => s.putAlbum(album));
    notifyListeners();
    return album;
  }

  /// Renames an album; its group label is then the name the owner chose.
  void renameAlbum(String albumId, String name) {
    final i = _albums.indexWhere((a) => a.id == albumId);
    final clean = name.trim();
    if (i < 0 || clean.isEmpty) return;
    final a = _albums[i];
    _albums[i] = Album(
      id: a.id,
      name: clean,
      category: a.category,
      coverAsset: a.coverAsset,
      createdAt: a.createdAt,
      deckSlug: a.deckSlug,
      author: a.author,
    );
    _persist((s) => s.putAlbum(_albums[i]));
    notifyListeners();
  }

  /// The group an album sits in on the 相片冊, worked out from what is in
  /// it (問題回報 #404): a stored [Album.category] from older data wins, a
  /// 卡片集 album goes under 圖片集, otherwise the scene most of its
  /// recognised words point to, otherwise the month it was made.
  String albumGroup(Album album) {
    if (album.category != null && album.category!.isNotEmpty) {
      return album.category!;
    }
    if (album.deckSlug != null) return deckAlbumGroup;
    final photoIds = {for (final p in photosInAlbum(album.id)) p.id};
    final scores = <String, int>{};
    for (final o in _occurrences) {
      if (!photoIds.contains(o.photoId)) continue;
      final word = entry(o.wordEntryId)?.word.toLowerCase();
      if (word == null) continue;
      for (final e in albumSceneWords.entries) {
        if (e.value.contains(word)) scores[e.key] = (scores[e.key] ?? 0) + 1;
      }
    }
    if (scores.isNotEmpty) {
      return scores.entries.reduce((a, b) => b.value > a.value ? b : a).key;
    }
    final at = photosInAlbum(album.id)
        .map((p) => p.takenAt)
        .fold<DateTime>(album.createdAt, (a, b) => b.isAfter(a) ? b : a);
    return '${at.year} 年 ${at.month} 月';
  }

  /// Distinct groups of all albums, newest group first.
  List<String> albumGroups() {
    final seen = <String>[];
    for (final a in _albums.reversed) {
      final g = albumGroup(a);
      if (!seen.contains(g)) seen.add(g);
    }
    return seen;
  }

  /// Takes the album out (a 卡片集 album goes with its deck). Its photos
  /// are removed by the caller first.
  void removeAlbum(String albumId) {
    _albums.removeWhere((a) => a.id == albumId);
    _persist((s) => s.deleteAlbum(albumId));
    notifyListeners();
  }

  /// The cards of the album's words that are being learned: the 複習這本相簿
  /// run draws only from these (問題回報 #403).
  Set<String> cardIdsInAlbum(String albumId) {
    final photoIds = {for (final p in photosInAlbum(albumId)) p.id};
    return {
      for (final o in _occurrences)
        if (photoIds.contains(o.photoId))
          if (cardOf(o.wordEntryId) case final c? when !c.archived) c.id,
    };
  }

  /// Cards of words saved today (問題回報 #412 複習範圍「今天新加的」).
  Set<String> cardIdsAddedToday() {
    final now = clock();
    return {
      for (final e in _entries)
        if (e.createdAt.year == now.year &&
            e.createdAt.month == now.month &&
            e.createdAt.day == now.day)
          if (cardOf(e.id) case final c? when !c.archived) c.id,
    };
  }

  /// Cards of the 學習洞察 weak words (問題回報 #412 複習範圍「弱項單字」).
  Set<String> weakCardIds() => {
        for (final w in insights().weakWords) w.cardId,
      };

  void addPhoto(Photo photo) {
    _photos.add(photo);
    _persist((s) => s.putPhoto(photo));
    notifyListeners();
  }

  /// Links every photo's recognized words and every saved word to the
  /// language pack: lexeme ids, native meanings from the pack, and IPA and
  /// examples the entry is still missing (spec section 08: 命中後只保存
  /// photo ↔ lexeme_id；釋義、發音、例句直接由詞庫讀取). Learner edits are
  /// kept. Returns how many photos and words changed.
  int linkLexicon(LexiconPack pack) {
    _finishLink();
    var changed = 0;
    for (final n in _linkSteps(pack)) {
      changed += n;
    }
    return changed;
  }

  /// [linkLexicon] in slices of about [budget], yielding to the UI between
  /// them: a new pack linked into 300 words took 120 ms in one go on a
  /// Mac. 問題回報：Mac 實機量測同步新詞庫時主執行緒卡 1,151ms（M-PERF2）。
  /// A [linkLexicon] call meanwhile finishes this one first.
  Future<int> linkLexiconInBatches(LexiconPack pack,
      {Duration budget = const Duration(milliseconds: 8)}) async {
    _finishLink();
    final steps = _linkSteps(pack).iterator;
    _pendingLink = steps;
    var changed = 0;
    final watch = Stopwatch()..start();
    try {
      while (identical(_pendingLink, steps) && !_disposed) {
        if (!steps.moveNext()) break;
        changed += steps.current;
        if (watch.elapsed >= budget) {
          _linkPauses++;
          await Future<void>.delayed(Duration.zero);
          watch.reset();
        }
      }
    } finally {
      if (identical(_pendingLink, steps)) _pendingLink = null;
    }
    return changed;
  }

  Iterator<int>? _pendingLink;

  /// Counts the pauses of [linkLexiconInBatches]: after one, the steps
  /// re-read the photos and words the learner may have changed meanwhile.
  int _linkPauses = 0;

  void _finishLink() {
    final pending = _pendingLink;
    _pendingLink = null;
    if (pending == null) return;
    while (pending.moveNext()) {}
  }

  /// The work of [linkLexicon], one photo or word per step (each yields how
  /// many changed).
  Iterable<int> _linkSteps(LexiconPack pack) sync* {
    final update = _linkedPack != null &&
        pack.version != null &&
        pack.version != _linkedVersion;
    _linkedPack = pack;
    _linkedVersion = pack.version;
    if (pack.cardTemplate != null) updateTemplate(pack.cardTemplate!);
    if (pack.isEmpty) return;
    var pauses = _linkPauses;
    // The snapshot as it is now, or after a pause as the repository has it.
    Map<String, T>? afterPause<T>(Iterable<T> items, String Function(T) id) {
      if (pauses == _linkPauses) return null;
      return {for (final x in items) id(x): x};
    }

    Map<String, Photo>? photoNow;
    for (final snap in [..._photos]) {
      photoNow = afterPause(_photos, (p) => p.id) ?? photoNow;
      pauses = _linkPauses;
      final p = photoNow == null ? snap : photoNow[snap.id];
      if (p == null) continue;
      final editedWords = {
        for (final o in occurrencesInPhoto(p.id))
          if (o.userEdited && entry(o.wordEntryId) != null)
            entry(o.wordEntryId)!.word,
        for (final e in _entries)
          if (e.userEdited.contains(WordField.meaning)) e.word,
      };
      final linked = [
        for (final c in p.candidates)
          editedWords.contains(c.word) ? c : pack.link(c)
      ];
      var differs = false;
      for (var i = 0; i < linked.length; i++) {
        final a = p.candidates[i], b = linked[i];
        if (a.lexemeId != b.lexemeId ||
            a.meaning != b.meaning ||
            a.word != b.word) {
          differs = true;
        }
      }
      if (differs) {
        updatePhoto(p.copyWith(candidates: linked));
        yield 1;
      } else {
        yield 0;
      }
    }
    // One card per word (owner 2026-10-14, 問題回報 #51): a word saved
    // under one of its forms (runs, tethered) joins its word's card.
    Map<String, WordEntry>? entryNow;
    for (final snap in [..._entries]) {
      entryNow = afterPause(_entries, (e) => e.id) ?? entryNow;
      pauses = _linkPauses;
      final e = entryNow == null ? snap : entryNow[snap.id];
      if (e == null || e.language != pack.target) continue;
      final hit = pack.lookup(e.word, pos: e.pos);
      if (hit == null || hit.entry.normalized == e.word) {
        yield 0;
        continue;
      }
      if (hit.via == 'form' || hit.via == 'family') {
        _foldInto(e, hit.entry);
        yield 1;
      } else {
        yield 0;
      }
    }
    entryNow = null;
    for (final snap in [..._entries]) {
      entryNow = afterPause(_entries, (e) => e.id) ?? entryNow;
      pauses = _linkPauses;
      final e = entryNow == null ? snap : entryNow[snap.id];
      if (e == null || e.language != pack.target) continue;
      final hit = pack.lookup(e.word, pos: e.pos);
      if (hit == null) {
        yield 0;
        continue;
      }
      final x = hit.entry;
      // The pack dropped this part of speech for the word (問題回報 #436):
      // the card moves to the pos the pack kept, so it keeps updating. A pos
      // the learner set themselves stays as it is.
      final moved = x.pos != LexiconPack.packPos(e.pos);
      if (moved && e.userEdited.contains(WordField.pos)) continue;
      final pos = !moved
          ? e.pos
          : switch (x.pos) { 'adj' => 'adj.', 'adv' => 'adv.', final p => p };
      final detail = pack.detailFor(x);
      final fresh = WordEntry.fromUserInput(
        id: e.id,
        word: e.word,
        pos: pos,
        language: e.language,
        meaning: x.learnerMeaning ?? '',
        level: x.cefr,
        levelSource: 'lexicon',
        detail: detail,
        now: e.createdAt,
      ).toJson();
      final merged = e.toJson();
      // A move onto a pos the pack gives no meaning for keeps the meaning
      // the card already shows (pack_update_simulation seed 1023: somewhere
      // adv「到某處」→ noun, sue verb「起訴」→ noun), instead of blanking it
      // into 「詞庫尚未提供中文意思」. A learner-edited meaning is kept below
      // as before.
      final keepMeaning = moved &&
          x.nativeMeaning == null &&
          e.meaning.trim().isNotEmpty &&
          !e.userEdited.contains(WordField.meaning);
      for (final field in [
        if (!keepMeaning) 'meaning',
        'register',
        'definition',
        'definitionEn',
        'ipa',
        'ipaSource',
        'level',
        'levelSource',
        'examples',
        'related',
        'forms',
        'root',
        'affixes',
        WordField.morphology,
        WordField.etymology,
      ]) {
        if (e.userEdited.contains(field)) continue;
        if (field == 'ipaSource' && e.userEdited.contains(WordField.ipa)) {
          continue;
        }
        if (field == 'levelSource' && e.userEdited.contains(WordField.level)) {
          continue;
        }
        merged[field] = fresh[field];
      }
      merged['lexeme_usages'] = [
        for (final u in pack.usagesFor(e.word)) u.toJson()
      ];
      merged['pos'] = pos;
      merged['lexemeId'] = x.id;
      merged['entry_type'] = x.entryType;
      if (pack.mediaBase != null) {
        merged['audioUrl'] =
            x.audio == null ? null : packRecordingUrl(pack.mediaBase, x.audio!);
      }
      merged['translatedFor'] = pack.native;
      // A dictionary gap is explicit, not an endless background loading state.
      if (!keepMeaning) {
        merged['dataStatus'] = x.nativeMeaning == null ? 'failed' : 'complete';
        merged['dataError'] = x.nativeMeaning == null ? '詞庫尚未提供{N}意思' : null;
      }
      if (jsonEncode(merged) != jsonEncode(e.toJson())) {
        final next = WordEntry.fromJson(merged);
        _putEntry(next);
        if (update) {
          final filled = missingFieldNames(e).toSet()
            ..removeAll(missingFieldNames(next));
          if (filled.isNotEmpty) {
            (_filledByUpdate[e.id] ??= {}).addAll(filled);
          }
        }
        yield 1;
      } else {
        yield 0;
      }
    }
    notifyListeners();
  }

  void updatePhoto(Photo photo) {
    final i = _photos.indexWhere((p) => p.id == photo.id);
    if (i < 0) return;
    _photos[i] = photo;
    _persist((s) => s.putPhoto(photo));
    notifyListeners();
  }

  /// Takes the photo out of the app's albums (spec section 7: 照片最後一個
  /// 單字被刪除後，從 App 相片冊移除照片參照，但不刪除手機系統相簿中的原始
  /// 照片). Its occurrences go too; cards keep their history.
  void removePhoto(String photoId) {
    final affected = {
      for (final o in occurrencesInPhoto(photoId)) o.wordEntryId
    };
    for (final o in occurrencesInPhoto(photoId)) {
      _persist((s) => s.deleteOccurrence(o.id));
    }
    _occurrences.removeWhere((o) => o.photoId == photoId);
    _photos.removeWhere((p) => p.id == photoId);
    _persist((s) => s.deletePhoto(photoId));
    for (final id in affected) {
      _dropIfUnused(id);
    }
    notifyListeners();
  }

  // ── 卡片集 (card #323, 問題回報 #320) ─────────────────────────────────

  /// Adds the words of a downloaded deck, each with its card so it can be
  /// reviewed at once. Words already in the database stay as they are.
  /// Returns the entries this call created (the deck remembers them so 移除
  /// 集合 can take them out again); their meanings are filled by the
  /// enricher like any word added by hand.
  List<WordEntry> addDeckWords(
      List<({String word, String pos, String? level})> words) {
    final created = <WordEntry>[];
    for (final w in words) {
      final normalized = w.word.trim().toLowerCase();
      if (normalized.isEmpty) continue;
      var e = entryByWord(normalized);
      if (e == null) {
        e = _createEntry(
          word: normalized,
          pos: w.pos,
          meaning: '',
          level: w.level,
          levelSource: w.level == null ? null : 'deck',
          dataStatus: WordDataStatus.pending,
        );
        created.add(e);
      }
      _ensureCard(e.id);
      if (_profile.familiarityOf(e.word) == Familiarity.unknown) {
        _setProfile(
            _profile.withFamiliarity(e.word, Familiarity.learning, clock()));
      }
    }
    _attachOwnPhotos(created);
    notifyListeners();
    return created;
  }

  /// Adds a downloaded deck picture with its labels already saved as the
  /// photo's word list (no tagging needed). Returns the entries created.
  List<WordEntry> addDeckPhoto(Photo photo, List<WordCandidate> labels) {
    addPhoto(photo.copyWith(candidates: labels));
    return savePhotoWords(
      photo.id,
      [
        for (final c in labels.take(WordSelector.maxWords))
          ListedWord(c, c.point, placed: c.grounded),
      ],
      difficultyOffset: 0,
      source: 'database_album',
    );
  }

  /// 移除集合: takes the deck's pictures and the words it created out
  /// again. A word that was reviewed, edited or is still on another photo
  /// stays (with its history).
  void removeDeckContent({
    Iterable<String> photoIds = const [],
    Iterable<String> wordEntryIds = const [],
    String? albumId,
  }) {
    for (final id in photoIds.toList()) {
      if (photo(id) != null) removePhoto(id);
    }
    if (albumId != null) removeAlbum(albumId);
    for (final id in wordEntryIds) {
      _dropIfUnused(id, withImportedPhotos: true);
    }
    notifyListeners();
  }

  /// Moves a word saved under one of its forms ([form]: runs, tethered) to
  /// its word's card ([base]: run, tether). Without a card for the word
  /// yet, the form's entry simply becomes the word's. Otherwise its photo
  /// labels join the word's entry; of the two cards the one reviewed more
  /// stays (with its id, so its review history), and the learner's edits
  /// on the form fill fields the word has not been edited in.
  void _foldInto(WordEntry form, LexEntry base) {
    final now = clock();
    final word = base.normalized;
    final target = entryByWord(word);
    var familiarity = _profile.familiarityOf(form.word);
    if (target == null) {
      _putEntry(WordEntry.fromJson({
        ...form.toJson(),
        'word': word,
        'pos': switch (base.pos) {
          'adj' => 'adj.',
          'adv' => 'adv.',
          final p => p
        },
        'lexemeId': base.id,
        'updatedAt': now.toIso8601String(),
      }));
    } else {
      for (final o in occurrencesOf(form.id)) {
        final i = _occurrences.indexWhere((x) => x.id == o.id);
        if (i < 0) continue;
        if (occurrencesInPhoto(o.photoId)
            .any((x) => x.wordEntryId == target.id)) {
          _occurrences.removeAt(i); // the photo already shows the word
          _persist((s) => s.deleteOccurrence(o.id));
        } else {
          final moved = o.copyWith(wordEntryId: target.id);
          _occurrences[i] = moved;
          _persist((s) => s.putOccurrence(moved));
        }
      }
      final mine = cardOf(form.id), theirs = cardOf(target.id);
      if (mine != null) {
        final keepMine = theirs == null || mine.fsrs.reps > theirs.fsrs.reps;
        final dropped = keepMine ? theirs : mine;
        if (dropped != null) {
          _cards.remove(dropped);
          _persist((s) => s.deleteCard(dropped.id));
        }
        if (keepMine) {
          final i = _cards.indexWhere((c) => c.id == mine.id);
          _setCard(i, mine.copyWith(wordEntryId: target.id, updatedAt: now));
        }
      }
      final edits = form.userEdited.difference(target.userEdited);
      if (edits.isNotEmpty) {
        final from = form.toJson();
        _putEntry(WordEntry.fromJson({
          ...target.toJson(),
          for (final f in edits)
            if (from.containsKey(f)) f: from[f],
          'userEdited': [...target.userEdited, ...edits],
          'updatedAt': now.toIso8601String(),
        }));
      }
      _entries.remove(form);
      _persist((s) => s.deleteEntry(form.id));
      final theirsFamiliarity = _profile.familiarityOf(word);
      if (theirsFamiliarity.index > familiarity.index) {
        familiarity = theirsFamiliarity;
      }
    }
    var profile = _profile.withoutFamiliarity(form.word, now);
    if (familiarity != Familiarity.unknown) {
      profile = profile.withFamiliarity(word, familiarity, now);
    }
    _setProfile(profile);
  }

  /// Drops a word nobody needs any more: no photo, never reviewed, not
  /// edited by hand — e.g. a suggestion replaced by the difficulty dial
  /// after it had been saved once.
  ///
  /// [withImportedPhotos]: the learner's photos the import put the word on
  /// ([PhotoOccurrence.fromImport]) do not keep it, and go with it.
  void _dropIfUnused(String wordEntryId, {bool withImportedPhotos = false}) {
    final occurrences = occurrencesOf(wordEntryId);
    if (occurrences.any((o) => !withImportedPhotos || !o.fromImport)) return;
    final e = entry(wordEntryId);
    final card = cardOf(wordEntryId);
    if (e == null || e.userEdited.isNotEmpty) return;
    if (card != null && (card.fsrs.reps > 0 || logsOf(card.id).isNotEmpty)) {
      return;
    }
    // 已學會 (swiped away) is an archive, never a deletion (spec section 7:
    // 左滑採封存，不做不可逆刪除) — even when its last photo goes.
    if (card != null && card.archived) return;
    for (final o in occurrences) {
      _occurrences.removeWhere((x) => x.id == o.id);
      _persist((s) => s.deleteOccurrence(o.id));
    }
    if (card != null) {
      _cards.remove(card);
      _persist((s) => s.deleteCard(card.id));
    }
    _entries.remove(e);
    _persist((s) => s.deleteEntry(e.id));
    if (_profile.familiarityOf(e.word) == Familiarity.learning) {
      _setProfile(_profile.withoutFamiliarity(e.word, clock()));
    }
  }

  /// Whether [p] is a photo the learner took or picked, not a word-database
  /// or 卡片集 picture (問題回報 #864).
  bool isOwnPhoto(Photo p) {
    if (p.id.startsWith('db-') || p.id.startsWith('photo-deck-')) return false;
    if (p.networkUrl != null || p.credit != null || p.assetPath != null) {
      return false;
    }
    final albumId = p.albumId;
    return albumId == null || album(albumId)?.deckSlug == null;
  }

  /// 問題回報 #864: a word the learner imports (單字集匯入、手動新增) gets
  /// the learner's own photo that already shows it — a saved label or one
  /// of the photo's recognized words, counting forms of the word (cups →
  /// cup) — as its picture, before any word-database picture. Of several
  /// photos the newest is used. The photo's label list is not changed: the
  /// word joins it as a context only ([PhotoOccurrence.fromImport]).
  void _attachOwnPhotos(List<WordEntry> words) {
    if (words.isEmpty) return;
    final pack = _linkedPack ?? LexiconPack.instance;
    final usePack = pack.target == language;
    String? normPos(String? pos) => pos == null || pos.trim().isEmpty
        ? null
        : LexiconPack.packPos(pos.trim());
    String key(String word, String? pos) {
      final w = word.trim().toLowerCase();
      if (!usePack) return w;
      return pack.lookup(w, pos: pos)?.entry.normalized ?? w;
    }

    final wanted = <String, List<WordEntry>>{};
    for (final e in words) {
      wanted.putIfAbsent(key(e.word, e.pos), () => []).add(e);
    }
    // One look through the learner's photos per import, newest first.
    final own = [
      for (final p in _photos)
        if (isOwnPhoto(p) && PhotoStore.canShow(p)) p
    ]..sort((a, b) => b.takenAt.compareTo(a.takenAt));
    final found = <String, PhotoOccurrence>{};
    void offer(Photo p, String word, String? pos, PhotoOccurrence label,
        {String? lemma}) {
      if (p.rejectedWords.contains(word)) return;
      for (final e in [
        ...?wanted[key(word, pos)],
        if (lemma != null && lemma != word) ...?wanted[key(lemma, pos)],
      ]) {
        if (found.containsKey(e.id)) continue;
        final a = normPos(e.pos), b = normPos(pos);
        if (a != null && b != null && a != b) continue;
        found[e.id] = label;
      }
    }

    for (final p in own) {
      for (final o in occurrencesInPhoto(p.id)) {
        final e = entry(o.wordEntryId);
        if (e == null) continue;
        offer(p, e.word, e.pos, o);
      }
      for (final c in p.candidates) {
        // Only what the photo really shows (as 照片詳情 keeps contexts).
        if (c.inferred || c.visualConfidence < 0.6) continue;
        offer(
            p,
            c.word,
            c.pos,
            PhotoOccurrence(
              id: '',
              photoId: p.id,
              wordEntryId: '',
              anchor: c.point,
              aiLabel: c.word,
              evidence: c.evidence.isEmpty ? null : c.evidence,
              confidence: c.visualConfidence,
              placed: c.grounded,
            ),
            lemma: c.lemma);
      }
      if (found.length == words.length) break;
    }
    for (final e in words) {
      final hit = found[e.id];
      if (hit == null) continue;
      if (occurrencesInPhoto(hit.photoId).any((o) => o.wordEntryId == e.id)) {
        continue;
      }
      final occ = PhotoOccurrence(
        id: _newId('occ'),
        photoId: hit.photoId,
        wordEntryId: e.id,
        anchor: hit.anchor,
        aiLabel: hit.aiLabel,
        evidence: hit.evidence,
        confidence: hit.confidence,
        contextOnly: true,
        placed: hit.placed,
        fromImport: true,
      );
      _occurrences.add(occ);
      _persist((s) => s.putOccurrence(occ));
    }
  }

  PhotoOccurrence _addOccurrence(String photoId, WordEntry e, ListedWord w,
      {bool contextOnly = false}) {
    final occ = PhotoOccurrence(
      id: _newId('occ'),
      photoId: photoId,
      wordEntryId: e.id,
      anchor: w.anchor,
      aiLabel: w.added ? null : (w.aiLabel ?? w.word),
      userEdited: w.edited || w.added,
      evidence: w.candidate.evidence.isEmpty ? null : w.candidate.evidence,
      confidence: w.candidate.visualConfidence,
      contextOnly: contextOnly,
      placed: w.placed,
    );
    _occurrences.add(occ);
    _persist((s) => s.putOccurrence(occ));
    return occ;
  }

  WordEntry _entryFor(WordCandidate c) =>
      entryByWord(c.word) ??
      _createEntry(
        word: c.word,
        pos: c.pos,
        meaning: c.meaning,
        level: c.level,
        levelSource: c.levelSource,
        ipa: c.ipa,
        ipaSource: c.ipa == null ? null : 'cmudict',
        frequency: c.zipf,
        dataStatus: WordDataStatus.pending,
        lexemeId: c.lexemeId,
      );

  /// Saves a photo's word list when the learner leaves 照片詳情 (spec
  /// section 7: 照片詳情頁不設「建立」按鈕…自動保存列表中剩下的詞並建立尚未
  /// 存在的卡片). Words on the list get a WordEntry, PhotoOccurrence and
  /// LearningCard unless they already have them; a word already studied
  /// from another photo only gains this photo as a context (新照片只加入
  /// 該單字的照片情境). [alsoSeen] are such studied words the photo shows
  /// without listing them. Words that left the list since the last save
  /// lose this photo's occurrence, except 已學會 ones, which stay for
  /// 「顯示已學會單字」.
  ///
  /// Returns the entries created, whose full data still has to be fetched.
  List<WordEntry> savePhotoWords(
    String photoId,
    List<ListedWord> words, {
    required int difficultyOffset,
    List<ListedWord> alsoSeen = const [],
    String source = 'photo',
  }) {
    final photo = this.photo(photoId);
    if (photo == null) return const [];
    final now = clock();
    final before = {for (final e in _entries) e.id};
    final listed = {for (final w in words) w.word: w};
    final seen = {for (final w in alsoSeen) w.word: w};

    for (final o in occurrencesInPhoto(photoId)) {
      final e = entry(o.wordEntryId);
      if (e == null) continue;
      final w = listed[e.word];
      if (w != null) {
        if (w.placed &&
            (!o.placed ||
                w.anchor.x != o.anchor.x ||
                w.anchor.y != o.anchor.y)) {
          moveLabel(o.id, w.anchor);
        }
        if (o.contextOnly) {
          // Listed on this photo now (e.g. restored): one of its words.
          final i = _occurrences.indexWhere((x) => x.id == o.id);
          if (i >= 0) {
            final listedOcc =
                _occurrences[i].copyWith(contextOnly: false, fromImport: false);
            _occurrences[i] = listedOcc;
            _persist((s) => s.putOccurrence(listedOcc));
          }
        }
      } else if (o.fromImport) {
        // The learner's photo an imported word was given (問題回報 #864):
        // not on this photo's list, but stays the word's picture.
      } else if (!isArchived(e.id) && !seen.containsKey(e.word)) {
        _occurrences.remove(o);
        _persist((s) => s.deleteOccurrence(o.id));
        _dropIfUnused(e.id);
      } else if (!o.contextOnly && seen.containsKey(e.word)) {
        // No longer listed here but studied elsewhere: kept as a context
        // only, so the list stays at five words (restore can push one out).
        final i = _occurrences.indexWhere((x) => x.id == o.id);
        if (i >= 0) {
          final context = _occurrences[i].copyWith(contextOnly: true);
          _occurrences[i] = context;
          _persist((s) => s.putOccurrence(context));
        }
      }
    }
    var profile = _profile;
    for (final w in [...words, ...alsoSeen]) {
      var e = _entryFor(w.candidate);
      if (w.edited &&
          w.candidate.meaning.isNotEmpty &&
          (w.candidate.meaning != e.meaning ||
              (w.ownMeaning && !e.userEdited.contains(WordField.meaning)))) {
        e = e.copyWith(
          meaning: w.candidate.meaning,
          userEdited: {...e.userEdited, WordField.meaning},
          updatedAt: now,
        );
        _putEntry(e);
      }
      if (!occurrencesInPhoto(photoId).any((o) => o.wordEntryId == e.id)) {
        _addOccurrence(photoId, e, w, contextOnly: !listed.containsKey(w.word));
      }
      _ensureCard(e.id);
      if (profile.familiarityOf(e.word) == Familiarity.unknown) {
        profile = profile.withFamiliarity(e.word, Familiarity.learning, now);
      }
    }
    profile = profile
        .exposed(listed.keys, now)
        .keptPos([for (final w in words) w.candidate.pos], now);
    if (photo.wordsSavedAt == null ||
        photo.difficultyOffset != difficultyOffset) {
      profile = profile.dialled(difficultyOffset, now);
    }
    _setProfile(profile);
    updatePhoto(photo.copyWith(
      difficultyOffset: difficultyOffset,
      wordsSavedAt: photo.wordsSavedAt ?? now,
    ));
    final created = [
      for (final e in _entries)
        if (!before.contains(e.id)) e,
    ];
    for (final e in created) {
      Analytics.instance
          .capture('word_added', {'source': source, 'pos': e.pos}, now);
    }
    return created;
  }

  /// Drags a label to a new spot (spec: 照片標籤可拖曳重新定位).
  void moveLabel(String occurrenceId, LabelPoint anchor) {
    final i = _occurrences.indexWhere((o) => o.id == occurrenceId);
    if (i < 0) return;
    final moved = _occurrences[i].copyWith(anchor: anchor, userEdited: true);
    _occurrences[i] = moved;
    _persist((s) => s.putOccurrence(moved));
    notifyListeners();
  }

  /// Corrects a label (spec: AI 標籤「可改」). A different spelling moves
  /// the label to that word's entry (and card); a new meaning is stored
  /// on the shared WordEntry as a user edit.
  void editLabel(String occurrenceId,
      {required String word, required String meaning}) {
    final i = _occurrences.indexWhere((o) => o.id == occurrenceId);
    if (i < 0) return;
    final current = _occurrences[i];
    final currentEntry = entry(current.wordEntryId)!;
    var target = entryByWord(word);
    if (target == null) {
      target = _createEntry(
        word: word,
        meaning: meaning,
        level: currentEntry.level,
        levelSource: currentEntry.levelSource,
        dataStatus: WordDataStatus.pending,
      );
    } else if (meaning.trim().isNotEmpty && meaning.trim() != target.meaning) {
      target = target.copyWith(
        meaning: meaning.trim(),
        userEdited: {...target.userEdited, WordField.meaning},
        updatedAt: clock(),
      );
      _putEntry(target);
    }
    if (target.id != current.wordEntryId) {
      final moved = PhotoOccurrence(
        id: current.id,
        photoId: current.photoId,
        wordEntryId: target.id,
        anchor: current.anchor,
        aiLabel: current.aiLabel,
        userEdited: true,
        evidence: current.evidence,
        confidence: current.confidence,
        placed: current.placed,
      );
      _occurrences[i] = moved;
      _persist((s) => s.putOccurrence(moved));
      _ensureCard(target.id);
      _dropIfUnused(currentEntry.id);
    }
    notifyListeners();
  }

  void _setCard(int i, LearningCard card) {
    _cards[i] = card;
    _persist((s) => s.putCard(card));
  }

  void updateTemplate(CardTemplate template) {
    _template = template;
    _persist((s) => s.putTemplate(template));
    notifyListeners();
  }

  // ── Review ───────────────────────────────────────────────────────────

  /// What each grade would schedule for [cardId] right now (the interval
  /// shown on the quiz's rating buttons).
  Map<Rating, SchedulingResult> previewReview(String cardId) =>
      scheduler.preview(card(cardId)!.fsrs, clock());

  /// Records one graded recall: the only thing that updates FSRS state
  /// (spec section 4 — browsing the album never counts as a review). It
  /// is also a strong signal for the ability model.
  ReviewLog review(String cardId, Rating rating,
      {String? usageId,
      String? senseId,
      Duration? duration,
      Rating? requestedRating,
      String? templateType,
      bool? correct,
      int hintCount = 0,
      int attempts = 1}) {
    final i = _cards.indexWhere((c) => c.id == cardId);
    if (i < 0) throw ArgumentError.value(cardId, 'cardId', 'no such card');
    final before = _cards[i];
    final now = clock();
    final expectedRecall = scheduler.retrievability(before.fsrs, now);
    final result = scheduler.next(before.fsrs, rating, now);
    final after = before.copyWith(fsrs: result.state, updatedAt: now);
    final log = ReviewLog(
      usageId: usageId,
      senseId: senseId,
      cardId: cardId,
      reviewedAt: now,
      rating: rating,
      requestedRating: requestedRating ?? rating,
      before: before.fsrs,
      after: result.state,
      elapsedDays: result.elapsedDays,
      scheduledDays: result.scheduledDays,
      durationMs: duration?.inMilliseconds,
      templateType: templateType,
      correct: correct,
      hintCount: hintCount,
      attempts: attempts,
    );
    _setCard(i, after);
    _reviewLogs.add(log);
    Analytics.instance.capture(
        'card_reviewed',
        {
          'rating': rating.name,
          // No exercise = the plain flip card (問題回報 #207 decision A).
          'template': templateType ?? 'flip',
          'correct': correct,
          'hints': hintCount,
          'duration_ms': duration?.inMilliseconds,
          'scheduled_days': result.scheduledDays,
        },
        now);
    if (FsrsOptimizer.effective(log)) _effectiveReviewCount++;
    if (_effectiveReviewCount >= FsrsOptimizer.minimumReviews &&
        (_lastOptimizationSize == 0 ||
            _effectiveReviewCount - _lastOptimizationSize >= 100)) {
      unawaited(optimizeFsrs());
    }
    _persist((s) => s.addReviewLog(log));
    final level = entry(before.wordEntryId)?.level ?? 'B1';
    // Ability observes binary recall: Hard/Good/Easy all mean the learner did
    // recall the answer. Their distinction belongs to FSRS scheduling. This is
    // true on first encounter too; treating Good as 0.9 creates a systematic
    // downward bias over hundreds of new cards.
    final strength = rating == Rating.again ? 0.0 : 1.0;
    _setProfile(_profile.update(
        RecallSignal(level, strength, expectedRecall: expectedRecall), now));
    notifyListeners();
    return log;
  }

  /// Whether [card] is up for review now: not archived, and new or due
  /// by the end of today (spec: 沒有達到複習條件的卡片時停止).
  bool isEligible(LearningCard card, DateTime now) =>
      _eligible(card, entry(card.wordEntryId), now);

  bool _eligible(LearningCard card, WordEntry? word, DateTime now) {
    if (card.archived || word == null || word.meaning.trim().isEmpty) {
      return false;
    }
    if (card.fsrs.state == FsrsCardState.newCard) return true;
    final due = card.fsrs.due;
    if (due == null) return true;
    return !DateTime(due.year, due.month, due.day)
        .isAfter(DateTime(now.year, now.month, now.day));
  }

  /// Cards already first-learned / reviewed today (distinct cards, from the
  /// review log) — what the 每日上限 counts against (問題回報 #398).
  ({int newCards, int reviews}) doneToday() {
    final now = clock();
    final start = DateTime(now.year, now.month, now.day);
    final fresh = <String>{}, seen = <String>{};
    for (var i = _reviewLogs.length - 1; i >= 0; i--) {
      final l = _reviewLogs[i];
      if (l.reviewedAt.isBefore(start)) {
        if (l.reviewedAt.isBefore(start.subtract(const Duration(days: 1)))) {
          break; // logs are appended in time order
        }
        continue;
      }
      if (l.before.state == FsrsCardState.newCard) {
        fresh.add(l.cardId);
      } else {
        seen.add(l.cardId);
      }
    }
    seen.removeAll(fresh);
    return (newCards: fresh.length, reviews: seen.length);
  }

  /// Cards to schedule now. With [newLimit]/[reviewLimit] (每日上限) only the
  /// remaining budget of today's new cards and due reviews is offered, the
  /// most overdue first; the rest wait for tomorrow.
  List<LearningCard> eligibleCards(
      {bool includeFuture = false, int? newLimit, int? reviewLimit}) {
    final now = clock();
    // One lookup table, not a scan of every word per card: with a few
    // thousand words the 複習 tab waited seconds for each next card.
    final byId = {for (final e in _entries) e.id: e};
    var due = [
      for (final c in _cards)
        if (_eligible(c, byId[c.wordEntryId], now)) c,
    ];
    if (newLimit != null || reviewLimit != null) {
      final done = doneToday();
      bool isNew(LearningCard c) => c.fsrs.state == FsrsCardState.newCard;
      DateTime dueOf(LearningCard c) =>
          c.fsrs.due ?? DateTime.fromMillisecondsSinceEpoch(0);
      List<LearningCard> cap(List<LearningCard> l, int? limit, int used) {
        if (limit == null) return l;
        final room = (limit - used).clamp(0, l.length);
        l.sort((a, b) => dueOf(a).compareTo(dueOf(b)));
        return l.take(room).toList();
      }

      due = [
        ...cap(due.where(isNew).toList(), newLimit, done.newCards),
        ...cap(due.where((c) => !isNew(c)).toList(), reviewLimit, done.reviews),
      ];
    }
    if (!includeFuture) return due;
    final ids = {for (final c in due) c.id};
    return [
      ...due,
      for (final c in _cards)
        if (!ids.contains(c.id) &&
            !c.archived &&
            (byId[c.wordEntryId]?.meaning.trim().isNotEmpty ?? false))
          c,
    ];
  }

  /// Every word's photos, in one pass (photo ids per word entry id).
  Map<String, Set<String>> photoIdsByWord() {
    final out = <String, Set<String>>{};
    for (final o in _occurrences) {
      (out[o.wordEntryId] ??= <String>{}).add(o.photoId);
    }
    return out;
  }

  /// Cards are created as soon as a photo is saved, but a recall prompt is
  /// unusable until the native-language meaning arrives from the dictionary.
  /// They remain intact and automatically become eligible after enrichment.
  bool get hasCardsWaitingForMeaning => _cards.any((card) {
        final word = entry(card.wordEntryId);
        return !card.archived && word != null && word.meaning.trim().isEmpty;
      });
}

/// A list that counts its writes, so lookup tables built from it know when
/// they are stale.
class _VersionedList<T> extends ListBase<T> {
  final List<T> _items;
  int version = 0;

  _VersionedList(this._items);

  @override
  int get length => _items.length;

  @override
  set length(int n) {
    _items.length = n;
    version++;
  }

  @override
  T operator [](int i) => _items[i];

  @override
  void operator []=(int i, T value) {
    _items[i] = value;
    version++;
  }

  @override
  void add(T element) {
    _items.add(element);
    version++;
  }

  @override
  void addAll(Iterable<T> iterable) {
    _items.addAll(iterable);
    version++;
  }
}

FsrsOptimization? _fitFsrs((List<ReviewLog>, FsrsOptimization?) input) {
  final (logs, saved) = input;
  if (saved != null) return FsrsOptimizer.validate(saved, logs) ? saved : null;
  return FsrsOptimizer.optimize(logs);
}
