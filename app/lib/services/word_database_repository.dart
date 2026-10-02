import 'dart:collection';
import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../models/card_template.dart';
import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/vocabulary_profile.dart';
import '../models/word_candidate.dart';
import '../models/word_detail.dart';
import '../models/word_entry.dart';
import 'fsrs_scheduler.dart';
import 'lexicon_pack.dart';
import 'word_database_query.dart';
import 'word_database_store.dart';
import 'word_selector.dart';

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

  const ListedWord(this.candidate, this.anchor,
      {this.aiLabel, this.edited = false});

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

  /// Looks up the offline pipeline's data for a word (WordDetailService)
  /// so a new word arrives with IPA, forms, related words and examples.
  final WordDetail? Function(String word)? lookupDetail;

  /// Timestamps new records; injectable for tests.
  final DateTime Function() clock;

  int _nextId = 0;

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
  int get photoCount => _photos.length;
  CardTemplate get template => _template;
  UserVocabularyProfile get profile => _profile;

  /// Newest first.
  List<Photo> get photos =>
      [..._photos]..sort((a, b) => b.takenAt.compareTo(a.takenAt));

  List<Album> get albums => List.unmodifiable(_albums);

  List<String> get partsOfSpeech => {
        for (final e in _entries)
          if (e.pos.isNotEmpty) shortPos(e.pos),
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

  /// The cover shown on an album card: the newest photo with an image.
  Photo? albumCoverPhoto(String albumId) =>
      photosInAlbum(albumId).where((p) => p.hasImage).firstOrNull;

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
      if (filter.pos != null && shortPos(entry.pos) != shortPos(filter.pos!)) {
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
    );
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
    _setProfile(
        _profile.withFamiliarity(entry.word, Familiarity.learning, clock()));
    notifyListeners();
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

  Album addAlbum({required String name, String? category}) {
    final album = Album(
      id: _newId('album'),
      name: name.trim(),
      category: category,
      createdAt: clock(),
    );
    _albums.add(album);
    _persist((s) => s.putAlbum(album));
    notifyListeners();
    return album;
  }

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
    if (pack.isEmpty) return 0;
    var changed = 0;
    for (final p in [..._photos]) {
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
        changed++;
      }
    }
    for (final e in [..._entries]) {
      if (e.language != pack.target) continue;
      final hit = pack.lookup(e.word, pos: e.pos);
      if (hit == null) continue;
      final x = hit.entry;
      if (x.pos != LexiconPack.packPos(e.pos)) continue;
      final detail = x.toDetail();
      final fresh = WordEntry.fromUserInput(
        id: e.id,
        word: e.word,
        pos: e.pos,
        language: e.language,
        meaning: x.learnerMeaning ?? '',
        level: x.cefr,
        levelSource: 'lexicon',
        detail: detail,
        now: e.createdAt,
      ).toJson();
      final merged = e.toJson();
      for (final field in [
        'meaning',
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
        'affixes'
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
      merged['lexemeId'] = x.id;
      if (pack.mediaBase != null) {
        merged['audioUrl'] = x.audio == null
            ? null
            : Uri.base
                .resolve(pack.mediaBase!)
                .replace(queryParameters: {'path': x.audio!}).toString();
      }
      merged['translatedFor'] = pack.native;
      // A dictionary gap is explicit, not an endless background loading state.
      merged['dataStatus'] = x.nativeMeaning == null ? 'failed' : 'complete';
      merged['dataError'] = x.nativeMeaning == null ? '詞庫尚未提供中文意思' : null;
      if (jsonEncode(merged) != jsonEncode(e.toJson())) {
        _putEntry(WordEntry.fromJson(merged));
        changed++;
      }
    }
    notifyListeners();
    return changed;
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

  /// Drops a word nobody needs any more: no photo, never reviewed, not
  /// edited by hand — e.g. a suggestion replaced by the difficulty dial
  /// after it had been saved once.
  void _dropIfUnused(String wordEntryId) {
    if (occurrencesOf(wordEntryId).isNotEmpty) return;
    final e = entry(wordEntryId);
    final card = cardOf(wordEntryId);
    if (e == null || e.userEdited.isNotEmpty) return;
    if (card != null && (card.fsrs.reps > 0 || logsOf(card.id).isNotEmpty)) {
      return;
    }
    // 已學會 (swiped away) is an archive, never a deletion (spec section 7:
    // 左滑採封存，不做不可逆刪除) — even when its last photo goes.
    if (card != null && card.archived) return;
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

  PhotoOccurrence _addOccurrence(String photoId, WordEntry e, ListedWord w,
      {bool contextOnly = false}) {
    final occ = PhotoOccurrence(
      id: _newId('occ'),
      photoId: photoId,
      wordEntryId: e.id,
      anchor: w.anchor,
      aiLabel: w.aiLabel ?? w.word,
      userEdited: w.edited,
      evidence: w.candidate.evidence.isEmpty ? null : w.candidate.evidence,
      confidence: w.candidate.visualConfidence,
      contextOnly: contextOnly,
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
        if (w.anchor.x != o.anchor.x || w.anchor.y != o.anchor.y) {
          moveLabel(o.id, w.anchor);
        }
        if (o.contextOnly) {
          // Listed on this photo now (e.g. restored): one of its words.
          final i = _occurrences.indexWhere((x) => x.id == o.id);
          if (i >= 0) {
            final listedOcc = _occurrences[i].copyWith(contextOnly: false);
            _occurrences[i] = listedOcc;
            _persist((s) => s.putOccurrence(listedOcc));
          }
        }
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
          w.candidate.meaning != e.meaning) {
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
    return [
      for (final e in _entries)
        if (!before.contains(e.id)) e,
    ];
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
  ReviewLog review(String cardId, Rating rating, {Duration? duration}) {
    final i = _cards.indexWhere((c) => c.id == cardId);
    if (i < 0) throw ArgumentError.value(cardId, 'cardId', 'no such card');
    final before = _cards[i];
    final now = clock();
    final expectedRecall = scheduler.retrievability(before.fsrs, now);
    final result = scheduler.next(before.fsrs, rating, now);
    final after = before.copyWith(fsrs: result.state, updatedAt: now);
    final log = ReviewLog(
      cardId: cardId,
      reviewedAt: now,
      rating: rating,
      before: before.fsrs,
      after: result.state,
      elapsedDays: result.elapsedDays,
      scheduledDays: result.scheduledDays,
      durationMs: duration?.inMilliseconds,
    );
    _setCard(i, after);
    _reviewLogs.add(log);
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

  List<LearningCard> eligibleCards() {
    final now = clock();
    // One lookup table, not a scan of every word per card: with a few
    // thousand words the 複習 tab waited seconds for each next card.
    final byId = {for (final e in _entries) e.id: e};
    return [
      for (final c in _cards)
        if (_eligible(c, byId[c.wordEntryId], now)) c,
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
