import 'dart:convert';

import 'package:hive/hive.dart';

import '../models/card_template.dart';
import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/vocabulary_profile.dart';
import '../models/word_entry.dart';

/// Everything the word database of one learning language holds, as
/// loaded from a store.
class WordDatabaseData {
  final List<WordEntry> entries;
  final List<Photo> photos;
  final List<Album> albums;
  final List<PhotoOccurrence> occurrences;
  final List<LearningCard> cards;
  final List<ReviewLog> reviewLogs;
  final CardTemplate? template;
  final UserVocabularyProfile? profile;

  const WordDatabaseData({
    this.entries = const [],
    this.photos = const [],
    this.albums = const [],
    this.occurrences = const [],
    this.cards = const [],
    this.reviewLogs = const [],
    this.template,
    this.profile,
  });
}

/// Write side of the word database. WordDatabaseRepository keeps all data
/// in memory for querying and writes every change through to a store.
abstract interface class WordDatabaseStore {
  Future<void> putEntry(WordEntry entry);
  Future<void> deleteEntry(String id);
  Future<void> putPhoto(Photo photo);
  Future<void> deletePhoto(String id);
  Future<void> putAlbum(Album album);
  Future<void> putOccurrence(PhotoOccurrence occurrence);
  Future<void> deleteOccurrence(String id);
  Future<void> putCard(LearningCard card);
  Future<void> deleteCard(String id);
  Future<void> putTemplate(CardTemplate template);
  Future<void> addReviewLog(ReviewLog log);
  Future<void> putProfile(UserVocabularyProfile profile);
}

/// Hive-backed store (spec section 2: 本機保存（Hive）; section 4: 所有資料
/// 只存本機). Each entity is a JSON string in a `Box<String>` keyed by
/// its id, so there are no hand-maintained TypeAdapter field indices to
/// drift out of sync with the models.
///
/// Each learning language has its own boxes (spec section 7: 每個學習語言
/// 分開保存相片冊、單字、已學會清單、能力分數、卡片、FSRS 與複習紀錄);
/// English keeps the original `wd_` names.
class HiveWordDatabaseStore implements WordDatabaseStore {
  /// Bump when the stored shape changes incompatibly.
  /// - 2: photo data moved from PhotoOccurrence onto Photo.
  /// - 3: one LearningCard per word (was one per photo occurrence), and
  ///   photos carry their candidate pool. [open] migrates a version-2
  ///   store in place; anything older is re-seeded.
  static const schemaVersion = 3;

  static const _schemaKey = 'schema';
  static const _templateKey = 'template';
  static const _profileKey = 'profile';

  final Box<String> _entries;
  final Box<String> _photos;
  final Box<String> _albums;
  final Box<String> _occurrences;
  final Box<String> _cards;
  final Box<String> _logs;
  final Box<String> _meta;

  HiveWordDatabaseStore._(
    this._entries,
    this._photos,
    this._albums,
    this._occurrences,
    this._cards,
    this._logs,
    this._meta,
  );

  List<Box<String>> get _all =>
      [_entries, _photos, _albums, _occurrences, _cards, _logs, _meta];

  static String prefixFor(String language) => switch (language) {
        'en' => 'wd_',
        'fr' => 'wd_fr_',
        _ => 'wd_zh_',
      };

  /// Hive must already be initialised (Hive.initFlutter / Hive.init).
  static Future<HiveWordDatabaseStore> open({String language = 'en'}) async {
    final p = prefixFor(language);
    final store = HiveWordDatabaseStore._(
      await Hive.openBox<String>('${p}entries'),
      await Hive.openBox<String>('${p}photos'),
      await Hive.openBox<String>('${p}albums'),
      await Hive.openBox<String>('${p}occurrences'),
      await Hive.openBox<String>('${p}cards'),
      await Hive.openBox<String>('${p}review_logs'),
      await Hive.openBox<String>('${p}meta'),
    );
    if (store._meta.get(_schemaKey) == '2') await store._migrateFrom2();
    return store;
  }

  /// True on first launch, and after an unmigratable schema change.
  bool get needsSeed => _meta.get(_schemaKey) != '$schemaVersion';

  /// True when nothing has been stored for this language yet.
  bool get isEmpty => _meta.isEmpty && _photos.isEmpty && _entries.isEmpty;

  WordDatabaseData load() {
    List<T> decode<T>(Box<String> box, T Function(Map<String, dynamic>) f) => [
          for (final raw in box.values)
            f(jsonDecode(raw) as Map<String, dynamic>),
        ];
    final template = _meta.get(_templateKey);
    final profile = _meta.get(_profileKey);
    return WordDatabaseData(
      entries: decode(_entries, WordEntry.fromJson)
        ..sort((a, b) => a.createdAt.compareTo(b.createdAt)),
      photos: decode(_photos, Photo.fromJson),
      albums: decode(_albums, Album.fromJson)
        ..sort((a, b) => a.createdAt.compareTo(b.createdAt)),
      occurrences: decode(_occurrences, PhotoOccurrence.fromJson),
      cards: decode(_cards, LearningCard.fromJson),
      reviewLogs: decode(_logs, ReviewLog.fromJson)
        ..sort((a, b) => a.reviewedAt.compareTo(b.reviewedAt)),
      template: template == null
          ? null
          : CardTemplate.fromJson(jsonDecode(template) as Map<String, dynamic>),
      profile: profile == null
          ? null
          : UserVocabularyProfile.fromJson(
              jsonDecode(profile) as Map<String, dynamic>),
    );
  }

  /// Replaces everything with [data] and records the schema version.
  Future<void> seed(WordDatabaseData data) async {
    for (final box in _all) {
      await box.clear();
    }
    String enc(Object json) => jsonEncode(json);
    await _entries
        .putAll({for (final e in data.entries) e.id: enc(e.toJson())});
    await _photos.putAll({for (final p in data.photos) p.id: enc(p.toJson())});
    await _albums.putAll({for (final a in data.albums) a.id: enc(a.toJson())});
    await _occurrences
        .putAll({for (final o in data.occurrences) o.id: enc(o.toJson())});
    await _cards.putAll({for (final c in data.cards) c.id: enc(c.toJson())});
    await _logs.addAll([for (final l in data.reviewLogs) enc(l.toJson())]);
    if (data.template != null) await putTemplate(data.template!);
    if (data.profile != null) await putProfile(data.profile!);
    await _meta.put(_schemaKey, '$schemaVersion');
  }

  /// Version 2 → 3: merges each word's per-photo cards into one card,
  /// keeping the most-reviewed card's FSRS state, and points every
  /// review log at it. Photos that already had labels count as saved.
  Future<void> _migrateFrom2() async {
    Map<String, dynamic> dec(String raw) =>
        jsonDecode(raw) as Map<String, dynamic>;
    final oldCards = [for (final raw in _cards.values) dec(raw)];
    final best = <String, Map<String, dynamic>>{};
    final newId = <String, String>{};
    for (final c in oldCards) {
      final word = c['wordEntryId'] as String;
      newId[c['id'] as String] = LearningCard.idFor(word);
      final fsrs = FsrsState.fromJson(c['fsrs'] as Map<String, dynamic>);
      final current = best[word];
      final currentReps = current == null
          ? -1
          : FsrsState.fromJson(current['fsrs'] as Map<String, dynamic>).reps;
      if (fsrs.reps > currentReps) best[word] = c;
    }
    final cards = [
      for (final e in best.entries)
        LearningCard(
          id: LearningCard.idFor(e.key),
          wordEntryId: e.key,
          templateId: e.value['templateId'] as String,
          fsrs: FsrsState.fromJson(e.value['fsrs'] as Map<String, dynamic>),
        ),
    ];
    final logs = [
      for (final raw in _logs.values)
        {
          ...dec(raw),
          'cardId': newId[dec(raw)['cardId']] ?? dec(raw)['cardId']
        },
    ];
    final labelled = {
      for (final raw in _occurrences.values) dec(raw)['photoId'] as String
    };
    final photos = [
      for (final raw in _photos.values)
        if (Photo.fromJson(dec(raw)) case final p)
          labelled.contains(p.id)
              ? p.copyWith(
                  taggingStatus: TaggingStatus.done, wordsSavedAt: p.createdAt)
              : p,
    ];
    await _cards.clear();
    await _cards.putAll({for (final c in cards) c.id: jsonEncode(c.toJson())});
    await _logs.clear();
    await _logs.addAll([for (final l in logs) jsonEncode(l)]);
    await _photos
        .putAll({for (final p in photos) p.id: jsonEncode(p.toJson())});
    await _meta.put(_schemaKey, '$schemaVersion');
  }

  @override
  Future<void> putEntry(WordEntry entry) =>
      _entries.put(entry.id, jsonEncode(entry.toJson()));

  @override
  Future<void> deleteEntry(String id) => _entries.delete(id);

  @override
  Future<void> putPhoto(Photo photo) =>
      _photos.put(photo.id, jsonEncode(photo.toJson()));

  @override
  Future<void> deletePhoto(String id) => _photos.delete(id);

  @override
  Future<void> putAlbum(Album album) =>
      _albums.put(album.id, jsonEncode(album.toJson()));

  @override
  Future<void> putOccurrence(PhotoOccurrence occurrence) =>
      _occurrences.put(occurrence.id, jsonEncode(occurrence.toJson()));

  @override
  Future<void> deleteOccurrence(String id) => _occurrences.delete(id);

  @override
  Future<void> putCard(LearningCard card) =>
      _cards.put(card.id, jsonEncode(card.toJson()));

  @override
  Future<void> deleteCard(String id) => _cards.delete(id);

  @override
  Future<void> putTemplate(CardTemplate template) =>
      _meta.put(_templateKey, jsonEncode(template.toJson()));

  @override
  Future<void> addReviewLog(ReviewLog log) =>
      _logs.add(jsonEncode(log.toJson()));

  @override
  Future<void> putProfile(UserVocabularyProfile profile) =>
      _meta.put(_profileKey, jsonEncode(profile.toJson()));

  Future<void> close() async {
    for (final box in _all) {
      await box.close();
    }
  }
}
