import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;

import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/word_candidate.dart';
import '../models/word_entry.dart';
import 'dictionary_sync.dart';
import 'photo_intake.dart';
import 'word_database_repository.dart';

/// 卡片集／圖片集 (card #323, 問題回報 #320): decks other people curated —
/// a word list ("基礎單字") or a set of labelled pictures ("B1 水果與蔬菜")
/// — that the learner browses, adds to their own collection and removes
/// again. The list is read-only and keyless on the dictionary server
/// (same rate-limited route family as the dictionary, 問題回報 #287).

/// A deck as the server lists it.
class DeckInfo {
  final String slug;
  final String kind; // words / photos
  final String title;
  final String? cefr;
  final String? topic;
  final String? description;
  final String? author;
  final int? coverAssetId;
  final int count;

  const DeckInfo({
    required this.slug,
    required this.kind,
    required this.title,
    this.cefr,
    this.topic,
    this.description,
    this.author,
    this.coverAssetId,
    required this.count,
  });

  bool get isPhotos => kind == 'photos';

  factory DeckInfo.fromJson(Map<String, dynamic> j) => DeckInfo(
        slug: j['slug'] as String,
        kind: j['kind'] as String,
        title: j['title'] as String,
        cefr: j['cefr'] as String?,
        topic: j['topic'] as String?,
        description: j['description'] as String?,
        author: j['author'] as String?,
        coverAssetId: (j['cover_asset_id'] as num?)?.toInt(),
        count: (j['count'] as num?)?.toInt() ?? 0,
      );

  Map<String, dynamic> toJson() => {
        'slug': slug,
        'kind': kind,
        'title': title,
        'cefr': cefr,
        'topic': topic,
        'description': description,
        'author': author,
        'cover_asset_id': coverAssetId,
        'count': count,
      };
}

/// "Author · Licence · page" of a deck picture, or null when the server
/// sent none (問題回報 #329).
String? _credit(Map<String, dynamic> i) {
  String? s(String k) {
    final v = (i[k] as String?)?.trim();
    return v == null || v.isEmpty ? null : v;
  }

  final parts = [s('author'), s('license'), s('page_url') ?? s('license_url')]
      .whereType<String>();
  return parts.isEmpty ? null : parts.join(' · ');
}

/// One deck with its items: [words] for a word deck, [pictures] for a
/// picture deck.
class DeckContent {
  final DeckInfo info;
  final List<({String word, String pos, String? level})> words;
  final List<({int assetId, List<WordCandidate> labels, String? credit})> pictures;

  const DeckContent(this.info,
      {this.words = const [], this.pictures = const []});

  factory DeckContent.fromJson(Map<String, dynamic> j) {
    final info = DeckInfo.fromJson(j);
    final items =
        (j['items'] as List? ?? const []).cast<Map<String, dynamic>>();
    if (info.isPhotos) {
      return DeckContent(info, pictures: [
        for (final i in items)
          (
            assetId: (i['asset_id'] as num).toInt(),
            credit: _credit(i),
            labels: [
              for (final l in (i['labels'] as List? ?? const [])
                  .cast<Map<String, dynamic>>())
                _label(l, info.cefr),
            ],
          ),
      ]);
    }
    return DeckContent(info, words: [
      for (final i in items)
        (
          word: i['word'] as String,
          pos: shortPos(i['pos'] as String? ?? ''),
          level: i['cefr'] as String?,
        ),
    ]);
  }

  static WordCandidate _label(Map<String, dynamic> l, String? deckLevel) {
    final point = (l['point'] as List).cast<num>();
    return WordCandidate(
      word: l['word'] as String,
      pos: shortPos(l['pos'] as String? ?? ''),
      meaning: '',
      level: l['cefr'] as String? ?? deckLevel ?? 'B1',
      levelSource: 'deck',
      point: LabelPoint(point[0].toDouble(), point[1].toDouble()),
    );
  }
}

/// A deck the learner added: what it put into the database, so 移除集合
/// can take exactly that out again.
class InstalledDeck {
  final DeckInfo info;
  final DateTime installedAt;
  final List<String> photoIds;
  final List<String> wordEntryIds;

  /// Every word of a word deck, normalized (問題回報 #668): [wordEntryIds]
  /// holds only the words this install created — the ones 移除集合 may
  /// delete — so a deck whose words were mostly in the 單字本 already
  /// looked like it had four words. Null for decks installed before this
  /// field existed, until [DeckLibrary] fills it from the server.
  final List<String>? words;

  /// The 相片冊 album of a picture deck (問題回報 #403); null for word
  /// decks and for picture decks installed before albums existed.
  final String? albumId;

  const InstalledDeck({
    required this.info,
    required this.installedAt,
    this.photoIds = const [],
    this.wordEntryIds = const [],
    this.words,
    this.albumId,
  });

  /// How many words the deck has (all of them, not only the new ones).
  int get wordCount => words?.length ?? wordEntryIds.length;

  /// The 單字本 entries of the deck's words: those it created and those
  /// that were there already. Without [words] (an old install, offline)
  /// it falls back to the created ones.
  List<String> entryIds(WordDatabaseRepository repo) {
    final all = words;
    if (all == null) return wordEntryIds;
    // One pass over the 單字本 rather than a lookup per word: a deck can
    // have 3000 words.
    final byWord = <String, String>{};
    for (final e in repo.entries) {
      byWord.putIfAbsent(e.word, () => e.id);
    }
    final ids = <String>{
      for (final w in all)
        if (byWord[w] case final id?) id,
      ...wordEntryIds.where((id) => repo.entry(id) != null),
    };
    return ids.toList();
  }

  InstalledDeck withAlbum(String id) => InstalledDeck(
        info: info,
        installedAt: installedAt,
        photoIds: photoIds,
        wordEntryIds: wordEntryIds,
        words: words,
        albumId: id,
      );

  InstalledDeck withWords(List<String> all) => InstalledDeck(
        info: info,
        installedAt: installedAt,
        photoIds: photoIds,
        wordEntryIds: wordEntryIds,
        words: all,
        albumId: albumId,
      );

  factory InstalledDeck.fromJson(Map<String, dynamic> j) => InstalledDeck(
        info: DeckInfo.fromJson(j['info'] as Map<String, dynamic>),
        installedAt: DateTime.parse(j['installedAt'] as String),
        photoIds: (j['photoIds'] as List).cast<String>(),
        wordEntryIds: (j['wordEntryIds'] as List).cast<String>(),
        words: (j['words'] as List?)?.cast<String>(),
        albumId: j['albumId'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'info': info.toJson(),
        'installedAt': installedAt.toIso8601String(),
        'photoIds': photoIds,
        'wordEntryIds': wordEntryIds,
        if (words != null) 'words': words,
        'albumId': albumId,
      };
}

class DeckException implements Exception {
  final String message;
  const DeckException(this.message);
  @override
  String toString() => message;
}

class DeckLibrary extends ChangeNotifier {
  static DeckLibrary instance = DeckLibrary();

  final http.Client client;
  final bool? _remoteOverride;

  /// Whether installed decks are kept in Hive (tests keep them in memory).
  final bool _persist;

  DeckLibrary({http.Client? client, bool? remote, bool persist = true})
      : client = client ?? http.Client(),
        _remoteOverride = remote,
        _persist = persist;

  bool get remote => _remoteOverride ?? DictionarySync.defaultRemote;

  Box<String>? _box;
  final _installed = <String, InstalledDeck>{};
  String? _loadedFor;

  Uri _api(String path, [Map<String, String>? query]) =>
      DictionarySync.instance
          .endpoint('en', 'zh-TW')
          .replace(path: path, queryParameters: query ?? const {});

  Uri imageUri(int assetId) => _api('/api/image', {'id': '$assetId'});

  /// The decks the server offers. Throws [DeckException] when it can't be reached.
  /// [target] is the learning language: the server lists only that language's
  /// decks (問題回報 #501).
  Future<List<DeckInfo>> fetchList({String? target, String? native}) async {
    final j = await _getJson(_api('/api/decks', {
      if (target != null) 'target': target,
      if (native != null) 'native': native,
    }));
    return [
      for (final d in (j['decks'] as List).cast<Map<String, dynamic>>())
        DeckInfo.fromJson(d),
    ];
  }

  Future<DeckContent> fetchDeck(String slug) async =>
      DeckContent.fromJson(await _getJson(_api('/api/decks/$slug')));

  Future<Map<String, dynamic>> _getJson(Uri uri) async {
    if (!remote) throw const DeckException('目前沒有連線到卡片集伺服器');
    try {
      final r = await client.get(uri).timeout(const Duration(seconds: 20));
      if (r.statusCode == 429) throw const DeckException('太頻繁了，請稍後再試');
      if (r.statusCode != 200) {
        throw DeckException('卡片集暫時無法使用（${r.statusCode}）');
      }
      return jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
    } on DeckException {
      rethrow;
    } catch (e) {
      debugPrint('DeckLibrary: $uri failed: $e');
      throw const DeckException('無法連線，請檢查網路後再試');
    }
  }

  // ── What is installed (kept per learning language, works offline) ────

  Future<void> load(String language) async {
    if (_loadedFor == language) return;
    _installed.clear();
    if (!_persist) {
      _loadedFor = language;
      return;
    }
    try {
      _box ??= await Hive.openBox<String>('installed_decks_v1');
      final raw = _box!.get(language);
      if (raw != null) _restore(raw);
    } catch (e) {
      debugPrint('DeckLibrary: load failed: $e');
    }
    _loadedFor = language;
    notifyListeners();
    unawaited(fillDeckWords(language));
  }

  void _restore(String raw) {
    for (final d in (jsonDecode(raw) as List).cast<Map<String, dynamic>>()) {
      final deck = InstalledDeck.fromJson(d);
      _installed[deck.info.slug] = deck;
    }
  }

  /// Loads installed decks saved as [raw] (the Hive value), for tests of
  /// older formats.
  @visibleForTesting
  void restoreForTest(String language, String raw) {
    _installed.clear();
    _restore(raw);
    _loadedFor = language;
    notifyListeners();
  }

  /// Word decks installed before [InstalledDeck.words] existed get their
  /// full word list from the server (問題回報 #668). Offline, they keep
  /// going by [InstalledDeck.wordEntryIds] and try again next launch.
  Future<void> fillDeckWords(String language) async {
    var changed = false;
    for (final deck in _installed.values.toList()) {
      if (deck.info.isPhotos || deck.words != null) continue;
      try {
        final content = await fetchDeck(deck.info.slug);
        if (_loadedFor != language) return;
        if (_installed[deck.info.slug] != deck) continue;
        _installed[deck.info.slug] = deck.withWords(_normalized(content));
        changed = true;
      } catch (e) {
        debugPrint('DeckLibrary: words of ${deck.info.slug}: $e');
      }
    }
    if (!changed) return;
    await _save(language);
    notifyListeners();
  }

  static List<String> _normalized(DeckContent deck) => {
        for (final w in deck.words)
          if (w.word.trim().toLowerCase() case final n when n.isNotEmpty) n,
      }.toList();

  List<InstalledDeck> get installed => _installed.values.toList()
    ..sort((a, b) => b.installedAt.compareTo(a.installedAt));

  InstalledDeck? installedDeck(String slug) => _installed[slug];

  Future<void> _save(String language) async {
    try {
      await _box?.put(language,
          jsonEncode([for (final d in _installed.values) d.toJson()]));
    } catch (e) {
      debugPrint('DeckLibrary: save failed: $e');
    }
  }

  /// Adds [deck] to the learner's collection. Pictures are downloaded and
  /// kept on the device, so the deck works offline afterwards. All or
  /// nothing: if one picture can't be fetched, what was added is taken out.
  /// Returns the entries whose data still has to be filled by the enricher.
  Future<List<WordEntry>> install(
    DeckContent deck, {
    required WordDatabaseRepository repository,
    required PhotoIntake intake,
    void Function(int done, int total)? onProgress,
  }) async {
    await load(repository.language);
    final slug = deck.info.slug;
    if (_installed.containsKey(slug)) return const [];
    final created = <WordEntry>[];
    final photoIds = <String>[];
    String? albumId;
    try {
      if (deck.info.isPhotos) {
        // The deck's own 相片冊 album holds its pictures (問題回報 #403).
        albumId = _addAlbum(repository, deck.info).id;
        for (var i = 0; i < deck.pictures.length; i++) {
          onProgress?.call(i, deck.pictures.length);
          final p = deck.pictures[i];
          final bytes = await _picture(p.assetId);
          final saved = await intake.addDeckPicture(bytes,
              title: deck.info.title,
              place: deck.info.topic,
              labels: p.labels,
              credit: p.credit,
              albumId: albumId);
          photoIds.add(saved.photo.id);
          created.addAll(saved.created);
        }
        onProgress?.call(deck.pictures.length, deck.pictures.length);
      } else {
        created.addAll(repository.addDeckWords(deck.words));
      }
    } catch (e) {
      repository.removeDeckContent(
          photoIds: photoIds,
          wordEntryIds: [for (final w in created) w.id],
          albumId: albumId);
      if (e is DeckException) rethrow;
      throw const DeckException('下載失敗，請檢查網路後再試');
    }
    _installed[slug] = InstalledDeck(
      info: deck.info,
      installedAt: repository.clock(),
      photoIds: photoIds,
      wordEntryIds: [for (final w in created) w.id],
      words: deck.info.isPhotos ? null : _normalized(deck),
      albumId: albumId,
    );
    await _save(repository.language);
    notifyListeners();
    return created;
  }

  Album _addAlbum(WordDatabaseRepository repository, DeckInfo info) =>
      repository.addAlbum(
          name: info.title, deckSlug: info.slug, author: info.author);

  /// Picture decks installed before their 相片冊 album (問題回報 #403) get
  /// one now, and their pictures join it.
  Future<void> ensureAlbums(WordDatabaseRepository repository) async {
    await load(repository.language);
    var changed = false;
    for (final deck in _installed.values.toList()) {
      if (!deck.info.isPhotos || deck.albumId != null) continue;
      final albumId = _addAlbum(repository, deck.info).id;
      for (final id in deck.photoIds) {
        if (repository.photo(id) case final p?) {
          repository.updatePhoto(p.copyWith(albumId: () => albumId));
        }
      }
      _installed[deck.info.slug] = deck.withAlbum(albumId);
      changed = true;
    }
    if (!changed) return;
    await _save(repository.language);
    notifyListeners();
  }

  Future<Uint8List> _picture(int assetId) async {
    final r = await client
        .get(imageUri(assetId))
        .timeout(const Duration(seconds: 30));
    if (r.statusCode == 429) throw const DeckException('太頻繁了，請稍後再試');
    if (r.statusCode != 200 || r.bodyBytes.isEmpty) {
      throw const DeckException('有圖片下載不到，請稍後再試');
    }
    return r.bodyBytes;
  }

  /// 移除集合: the deck's pictures and the words it added go; words you
  /// reviewed or edited stay.
  Future<void> remove(String slug, WordDatabaseRepository repository) async {
    await load(repository.language);
    final deck = _installed.remove(slug);
    if (deck == null) return;
    repository.removeDeckContent(
        photoIds: deck.photoIds,
        wordEntryIds: deck.wordEntryIds,
        albumId: deck.albumId);
    await _save(repository.language);
    notifyListeners();
  }
}
