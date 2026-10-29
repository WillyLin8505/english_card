import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show AssetBundle, rootBundle;
import 'package:path_provider/path_provider.dart';

import '../models/word_candidate.dart';
import '../models/card_template.dart';
import '../models/word_detail.dart';
import '../models/word_entry.dart';
import 'learning_content.dart'
    show formLabel, frenchGenderLabel, frenchWithArticle, posLabel;
import 'lexicon_sqlite_stub.dart' if (dart.library.ffi) 'lexicon_sqlite.dart';

export 'lexicon_sqlite_stub.dart' if (dart.library.ffi) 'lexicon_sqlite.dart'
    show LexiconSqlite;

/// The downloaded language pack (spec section 08, 資料比對階段): one
/// direction (target → native) exported by the lexicon admin as
/// `assets/lexicon/{target}-{native}.sqlite` (phones; card #428) with the
/// JSON twin `{target}-{native}.json` for the web page and tests — the same
/// rows and stable lexeme ids.
///
/// Recognized words are looked up here, never online: target language +
/// normalized lemma + part of speech first, then the lemma alone, then
/// the forms table (apples → apple).
///
/// Memory (問題回報 #423, owner decision B): from a SQLite pack only each
/// word's head (lemma, pos, forms, CEFR…) is kept in memory; senses and the
/// rest are read from the file when a screen asks ([LexEntry.senses],
/// [LexEntry.examples]…) and kept in small caches.
class LexiconPack extends ChangeNotifier {
  LexiconPack();

  static final LexiconPack instance = LexiconPack();

  String? target;
  String? native;
  String? version;

  /// The pack shipped inside the app (set by [load]), not a downloaded one.
  /// It can be older than the server's, so the repository never folds the
  /// learner's words with it (Mac M365: its "boring → bore" deleted boring
  /// at every start, seconds before the downloaded pack said otherwise).
  bool bundled = false;
  String? mediaBase;
  CardTemplate? cardTemplate;
  bool hasCatalog = false;
  List<Map<String, dynamic>> catalogImages = [];

  // Card #780: a review card looked its word's pictures up by scanning every
  // catalog image (tags and all) per card, seconds on a big pack. These
  // tables are built once per catalog and answer in one lookup.
  List<Map<String, dynamic>>? _indexedImages;
  int _indexedCount = -1;
  final Map<String, Map<String, dynamic>> _imageByDbId = {};
  final Map<int, List<Map<String, dynamic>>> _approvedByLexeme = {};

  void _indexCatalog() {
    if (identical(_indexedImages, catalogImages) &&
        _indexedCount == catalogImages.length) {
      return;
    }
    _indexedImages = catalogImages;
    _indexedCount = catalogImages.length;
    _imageByDbId.clear();
    _approvedByLexeme.clear();
    for (final image in catalogImages) {
      _imageByDbId.putIfAbsent('db-${image['id']}', () => image);
      final seen = <int>{};
      for (final tag in (image['tags'] as List? ?? const [])) {
        if (tag is! Map || tag['review_status'] != 'approved') continue;
        final id = tag['lexeme_id'];
        if (id is num && seen.add(id.toInt())) {
          (_approvedByLexeme[id.toInt()] ??= []).add(image);
        }
      }
    }
  }

  /// The catalog image whose card photo id is [dbId] (`db-<id>`).
  Map<String, dynamic>? catalogImageByDbId(String dbId) {
    _indexCatalog();
    return _imageByDbId[dbId];
  }

  /// Catalog images with an approved tag for [lexemeId], in catalog order.
  List<Map<String, dynamic>> approvedImagesOf(int lexemeId) {
    _indexCatalog();
    return _approvedByLexeme[lexemeId] ?? const [];
  }
  List<LexEntry> get catalogWords => _byId.values.toList(growable: false);
  final Map<int, LexEntry> _byId = {};
  final Map<String, List<LexEntry>> _byLemma = {};
  final Map<String, List<LexEntry>> _byForm = {};
  // Forms that share a word's card, by that word (tether: tethered).
  final Map<String, List<LexEntry>> _family = {};
  final Map<int, int> _redirects = {};
  final Map<String, String> labels = {};

  /// Words recognized in photos that the pack doesn't have yet
  /// (missing_lexeme_requests) or has without native text
  /// (missing_localization_requests), for the admin to fill.
  final Map<String, MissingRequest> requests = {};

  /// The open SQLite pack with its per-word caches, or null for a pack
  /// parsed from JSON. Lazy entries point at this object, so [replaceWith]
  /// hands it over to the instance together with them.
  LexSource? _source;
  LexiconSqlite? get _db => _source?.db;

  /// Path of the SQLite pack this instance reads, or null.
  String? get sqlitePath => _db?.path;
  bool get fromSqlite => _source != null;

  bool get isEmpty => _byLemma.isEmpty;

  /// The pack words spelled closest to [word] (card #745 typo hints):
  /// edit distance 1 (2 for words of 7+ letters), nearest first.
  List<String> similarTo(String word, {int max = 1}) {
    final w = normalize(word);
    final limit = w.length >= 7 ? 2 : 1;
    // Swapped neighbouring letters (recieve → receive) are the usual typo.
    for (var i = 0; i + 1 < w.length; i++) {
      final swapped =
          w.substring(0, i) + w[i + 1] + w[i] + w.substring(i + 2);
      if (swapped != w && _byLemma.containsKey(swapped)) return [swapped];
    }
    final found = <(int, String)>[];
    for (final k in _byLemma.keys) {
      if ((k.length - w.length).abs() > limit || k == w) continue;
      final d = _editDistance(w, k, limit);
      if (d <= limit) found.add((d, k));
    }
    found.sort((a, b) {
      final c = a.$1.compareTo(b.$1);
      return c != 0 ? c : a.$2.compareTo(b.$2);
    });
    return [for (final f in found.take(max)) f.$2];
  }

  static int _editDistance(String a, String b, int limit) {
    var prev = List<int>.generate(b.length + 1, (i) => i);
    for (var i = 1; i <= a.length; i++) {
      final cur = List<int>.filled(b.length + 1, 0)..[0] = i;
      var rowMin = i;
      for (var j = 1; j <= b.length; j++) {
        final cost = a.codeUnitAt(i - 1) == b.codeUnitAt(j - 1) ? 0 : 1;
        var v = prev[j - 1] + cost;
        if (prev[j] + 1 < v) v = prev[j] + 1;
        if (cur[j - 1] + 1 < v) v = cur[j - 1] + 1;
        cur[j] = v;
        if (v < rowMin) rowMin = v;
      }
      if (rowMin > limit) return limit + 1;
      prev = cur;
    }
    return prev[b.length];
  }
  int get size => _byId.values.where((e) => e.full).length;

  static String assetFor(String target, String native) =>
      'assets/lexicon/$target-$native.json';
  static String sqliteAssetFor(String target, String native) =>
      'assets/lexicon/$target-$native.sqlite';
  static String manifestAssetFor(String target, String native) =>
      'assets/lexicon/$target-$native.manifest.json';

  /// Where pack files live on the device (`<support dir>/lexicon/`). Tests
  /// point it at a temporary directory; without path_provider (tests, web)
  /// the JSON asset is used instead.
  static Future<Directory> Function() storageDirectory = () async =>
      Directory('${(await getApplicationSupportDirectory()).path}/lexicon');

  /// Loads the pack for this direction; an app without one simply links
  /// nothing (every word becomes a missing-word request).
  ///
  /// Phones copy the bundled SQLite pack to [storageDirectory] once per
  /// version and open it there; the web page (no dart:ffi) and a build
  /// without the SQLite asset parse the JSON twin as before.
  Future<void> load(
      {required String target,
      required String native,
      AssetBundle? bundle}) async {
    if (this.target == target && this.native == native && !isEmpty) return;
    try {
      if (!await _loadBundledSqlite(target, native, bundle ?? rootBundle)) {
        final raw =
            await (bundle ?? rootBundle).loadString(assetFor(target, native));
        // The bundled pack is tens of MB (問題回報 #265): parse it off the
        // UI thread (compute runs inline on the web).
        loadJson(await compute(jsonDecode, raw) as Map<String, dynamic>);
      }
      bundled = true;
    } catch (e) {
      debugPrint('No language pack for $target-$native: $e');
      clear();
    }
    this.target = target;
    this.native = native;
    notifyListeners();
  }

  /// The bundled SQLite pack, copied beside the app's data once per version
  /// (`{pair}.bundled.sqlite`; the asset bundle has no file paths). False
  /// when this build has no SQLite pack or no file system.
  Future<bool> _loadBundledSqlite(
      String target, String native, AssetBundle bundle) async {
    if (!LexiconSqlite.supported) return false;
    final Directory dir;
    final String bundledVersion;
    try {
      dir = await storageDirectory();
      final manifest =
          jsonDecode(await bundle.loadString(manifestAssetFor(target, native)))
              as Map<String, dynamic>;
      bundledVersion = manifest['created_at'] as String;
    } catch (e) {
      debugPrint('LexiconPack: no bundled SQLite pack for $target-$native: $e');
      return false;
    }
    final path = bundledSqlitePath(dir, target, native);
    final current = LexiconSqlite.inspect(path);
    if (current == null ||
        current.version != bundledVersion ||
        current.target != target ||
        current.native != native) {
      final data = await bundle.load(sqliteAssetFor(target, native));
      await dir.create(recursive: true);
      final tmp = File('$path.part');
      await tmp.writeAsBytes(
          data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes),
          flush: true);
      if (_db?.path == path) _closeDb();
      await tmp.rename(path);
    }
    replaceWith(await openSqlite(path));
    return true;
  }

  static String bundledSqlitePath(
          Directory dir, String target, String native) =>
      '${dir.path}/$target-$native.bundled.sqlite';

  /// Opens a SQLite pack file and indexes its heads. Throws when the file is
  /// not a pack (the caller keeps the previous pack).
  void loadSqlite(String path) {
    final db = _db?.path == path && !(_db?.closed ?? true)
        ? _db!
        : LexiconSqlite.open(path);
    _installFromDb(db);
  }

  void _installFromDb(LexiconSqlite db) {
    final source = identical(db, _source?.db) ? _source! : LexSource(db);
    _install(db.meta(), db.heads(),
        (raw) => LexEntry.fromJson(raw, lazyFrom: source),
        source: source);
  }

  /// [loadSqlite] off the UI thread: the file is opened and its heads
  /// indexed on a background isolate; only the open connection is made
  /// here. Before indexing, the file is copied from [copyFrom] and patched
  /// with [deltaJson] (a server delta as UTF-8 JSON) — a failed copy is
  /// deleted. A pack that is not [target]-[native] with a version throws;
  /// a good one is then renamed to [renameTo]. Install with [replaceWith].
  /// 問題回報：Mac 實機量測同步新詞庫時主執行緒卡 1,151ms（M-PERF2）。
  static Future<LexiconPack> openSqlite(String path,
      {String? copyFrom,
      Uint8List? deltaJson,
      String? target,
      String? native,
      String? renameTo}) async {
    final pack = await compute(_indexSqlite, (
      path: path,
      copyFrom: copyFrom,
      deltaJson: deltaJson,
      target: target,
      native: native,
      renameTo: renameTo,
    ));
    pack._source!.attach(LexiconSqlite.open(renameTo ?? path));
    return pack;
  }

  /// Applies a server delta to the open SQLite pack and re-indexes it.
  void applySqliteDelta(Map<String, dynamic> patch) {
    final db = _db;
    if (db == null || db.closed) {
      throw StateError('No SQLite pack to patch');
    }
    db.applyDelta(patch);
    // Same file, new rows: cached senses/details are stale (card #449).
    _source?.invalidate();
    _installFromDb(db);
  }

  void _closeDb() {
    _source?.close();
    _source = null;
  }

  /// Computes every word's [LexEntry.learnerMeaning] in the background, a
  /// few hundred words per frame, so the first search in the 資料庫單字本
  /// does not read 9k sense rows at once. Stops when the pack changes.
  /// A slice also ends after [budget]: 300 words took 15 ms on a Mac,
  /// several times that on a phone (M-PERF2).
  Future<void> warmMeanings(
      {int chunk = 300,
      Duration budget = const Duration(milliseconds: 4)}) async {
    final source = _source;
    if (source == null) return;
    final watch = Stopwatch()..start();
    var n = 0;
    for (final e in catalogWords) {
      if (!identical(source, _source)) return;
      if (e.full) e.learnerMeaning;
      if (++n >= chunk || watch.elapsed >= budget) {
        await Future<void>.delayed(Duration.zero);
        n = 0;
        watch.reset();
      }
    }
  }

  /// Drops the per-word senses and bodies read from the SQLite pack; they
  /// are read again when asked for (問題回報 #824: memory warning).
  void releaseCaches() => _source?.invalidate();

  void clear() {
    bundled = false;
    _closeDb();
    _byId.clear();
    _byLemma.clear();
    _byForm.clear();
    _family.clear();
    _redirects.clear();
    labels.clear();
    version = null;
    mediaBase = null;
    cardTemplate = null;
    hasCatalog = false;
    catalogImages = [];
  }

  void loadJson(Map<String, dynamic> j) => _install(
      j,
      (j['lexemes'] as List? ?? const []).cast<Map>(),
      (raw) => LexEntry.fromJson(raw));

  /// Replaces the pack: metadata from [j] (a JSON pack or SQLite meta), one
  /// entry per row of [rows] (pointer rows become redirects).
  void _install(Map<String, dynamic> j, Iterable<Map> rows,
      LexEntry Function(Map<String, dynamic>) make,
      {LexSource? source}) {
    final template = j['card_template'] == null
        ? null
        : CardTemplate.fromPublished(
            j['card_template'] as Map<String, dynamic>);
    // clear() must not close the pack being re-read (delta, same path).
    if (source != null && identical(source, _source)) _source = null;
    clear();
    _source = source;
    cardTemplate = template;
    target = j['target_language'] as String?;
    native = j['native_language'] as String?;
    version = j['created_at'] as String?;
    mediaBase = j['media_base'] as String?;
    hasCatalog = j['catalog_version'] == 1;
    catalogImages = [
      for (final image in (j['catalog_images'] as List? ?? []))
        Map<String, dynamic>.from(image as Map)
    ];
    (j['labels'] as Map? ?? {}).forEach((k, v) => labels['$k'] = '$v');
    (j['redirects'] as Map? ?? {})
        .forEach((k, v) => _redirects[int.parse('$k')] = (v as num).toInt());
    // 問題回報 #191: an inflected form (tore) is a pointer to its lemma
    // (tear), not a card: its id resolves to the lemma, its spelling finds it.
    final pointers = <String, int>{};
    for (final raw in rows) {
      final to = raw['redirect_to'];
      if (to is num) {
        _redirects[(raw['id'] as num).toInt()] = to.toInt();
        pointers['${raw['normalized']}'] = to.toInt();
        continue;
      }
      final e = make(
          raw is Map<String, dynamic> ? raw : Map<String, dynamic>.from(raw));
      _byId[e.id] = e;
      if (!e.full) continue;
      _byLemma.putIfAbsent(e.normalized, () => []).add(e);
      for (final f in e.forms) {
        _byForm.putIfAbsent(f.normalized, () => []).add(e);
      }
      if (e.card != null) _family.putIfAbsent(e.card!, () => []).add(e);
    }
    // The spelling's main part of speech first, so a lookup without a part
    // of speech gets sunshine 陽光, not the rare adjective (card #393).
    for (final list in _byLemma.values) {
      if (list.length < 2) continue;
      final order = {for (var i = 0; i < list.length; i++) list[i]: i};
      list.sort((a, b) => a.usageRank != b.usageRank
          ? a.usageRank.compareTo(b.usageRank)
          : order[a]!.compareTo(order[b]!));
    }
    pointers.forEach((form, id) {
      final base = _byId[id];
      if (base == null || !base.full) return;
      final list = _byForm.putIfAbsent(form, () => []);
      if (!list.contains(base)) list.add(base);
    });
    notifyListeners();
  }

  /// Install an already validated pack without parsing every entry twice.
  /// A SQLite pack moves over with its entries; [candidate] is left empty.
  void replaceWith(LexiconPack candidate) {
    if (identical(candidate._source, _source)) candidate._source = null;
    clear();
    _source = candidate._source;
    candidate._source = null;
    target = candidate.target;
    native = candidate.native;
    version = candidate.version;
    mediaBase = candidate.mediaBase;
    cardTemplate = candidate.cardTemplate;
    hasCatalog = candidate.hasCatalog;
    catalogImages = candidate.catalogImages;
    labels.addAll(candidate.labels);
    _byId.addAll(candidate._byId);
    _byLemma.addAll(candidate._byLemma);
    _byForm.addAll(candidate._byForm);
    _family.addAll(candidate._family);
    _redirects.addAll(candidate._redirects);
    notifyListeners();
  }

  List<LexemeUsage> usagesFor(String word) => [
        for (final e in _byLemma[normalize(word)] ?? const <LexEntry>[])
          LexemeUsage(
              id: 'pack:$target:${e.id}',
              pos: shortPos(e.pos),
              rare: e.rareUsage,
              senses: [
                for (final s in e.senses)
                  WordSense(
                      id: 'pack:$target:${s.id}',
                      meaning: s.native ?? '',
                      definition: s.definition)
              ],
              examples: [
                for (final x in e.examples)
                  WordExample(
                      text: x.text,
                      translation: x.translation,
                      senseId: x.senseId == null
                          ? null
                          : 'pack:$target:${x.senseId}',
                      source: x.source,
                      difficulty: x.difficulty,
                      aiGenerated: x.aiGenerated,
                      aiTranslated: x.translationAi)
              ]),
      ];

  LexEntry? byId(int id) => _byId[_redirects[id] ?? id];

  /// Every part of speech stored for one spelling, for the full dictionary
  /// detail page. The returned list cannot mutate the loaded pack.
  List<LexEntry> entriesFor(String word) =>
      List.unmodifiable(_byLemma[normalize(word)] ?? const <LexEntry>[]);

  /// The entry for a recognized word, or null. [pos] is the app's
  /// part of speech (noun, verb, adj., adv., phrase). A form that shares
  /// its word's card (tethered → tether, 問題回報 #51) gives that word,
  /// via 'family'.
  LexiconHit? lookup(String word, {String? pos}) {
    final hit = _lookup(word, pos: pos);
    final base = _byLemma[hit?.entry.card];
    if (hit == null || base == null || base.isEmpty) return hit;
    // A form sends the learner to its word's card, and to the word's common
    // entry there (問題回報 #706: city lights are illuminated → illuminate
    // 照亮, not the rare adjective illuminate 「（宗教）受啟蒙的」, C2).
    final ordered = _prefer(base, pos);
    return LexiconHit(
        ordered.firstWhere((e) => !e.rareUsage, orElse: () => ordered.first),
        'family');
  }

  static List<LexEntry> _prefer(List<LexEntry> list, String? pos) {
    if (pos == null) return list;
    final p = packPos(pos);
    return [...list.where((e) => e.pos == p), ...list.where((e) => e.pos != p)];
  }

  /// The forms that share [e]'s card (tethered, for tether).
  List<LexEntry> familyOf(LexEntry e) => _family[e.normalized] ?? const [];

  /// [e] as the app's [WordDetail], with the meanings of the forms that
  /// share its card.
  WordDetail detailFor(LexEntry e) => e.toDetail(family: familyOf(e));

  LexiconHit? _lookup(String word, {String? pos}) {
    final w = normalize(word);
    final p = pos == null ? null : packPos(pos);
    List<LexEntry> prefer(List<LexEntry> list) => _prefer(list, pos);
    final exact = _byLemma[w];
    final viaForm = _byForm[w];
    if (exact != null && exact.isNotEmpty) {
      final best = prefer(exact).first;
      if (p != null && best.pos != p) {
        // A dog lying on the grass is lie the verb, not lying 說謊的: the
        // form of a word with that part of speech wins (問題回報 #51).
        final form = viaForm?.where((e) => e.pos == p).firstOrNull;
        if (form != null) return LexiconHit(form, 'form');
      }
      return LexiconHit(
          best, best.pos == p || p == null ? 'lemma+pos' : 'lemma');
    }
    if (viaForm != null && viaForm.isNotEmpty) {
      return LexiconHit(prefer(viaForm).first, 'form');
    }
    return null;
  }

  /// A recognized candidate linked to the pack: lemma (inflected forms
  /// looked up through the forms table), native meaning and lexeme id.
  /// Words the pack lacks are recorded as missing-word requests.
  WordCandidate link(WordCandidate c) {
    final hit = lookup(c.word, pos: c.pos);
    if (hit == null) {
      _request('missing_lexeme', c.word, c.pos);
      return c.lexemeId == null ? c : c.copyWith(lexemeId: () => null);
    }
    final e = hit.entry;
    final meaning = e.learnerMeaning;
    if (meaning == null) {
      _request('missing_localization', e.lemma, e.pos, lexemeId: e.id);
    }
    return c.copyWith(
      word: hit.via == 'form' || hit.via == 'family' ? e.normalized : null,
      meaning: meaning ?? (c.meaning.isEmpty ? null : c.meaning),
      lexemeId: () => e.id,
    );
  }

  List<WordCandidate> linkAll(List<WordCandidate> cs) =>
      [for (final c in cs) link(c)];

  /// The pack entry as the app's [WordDetail], for new word entries.
  WordDetail? detail(String word) {
    final e = lookup(word)?.entry;
    return e == null ? null : detailFor(e);
  }

  void _request(String kind, String lemma, String pos, {int? lexemeId}) {
    final key = '$kind:${normalize(lemma)}:$pos';
    final r = requests[key];
    requests[key] = MissingRequest(
      kind: kind,
      lemma: normalize(lemma),
      pos: pos,
      lexemeId: lexemeId,
      target: target,
      native: native,
      count: (r?.count ?? 0) + 1,
    );
  }

  static String normalize(String word) =>
      word.trim().toLowerCase().replaceAll('’', "'");

  /// App part of speech → pack part of speech.
  static String packPos(String pos) =>
      switch (pos.replaceAll('.', '').toLowerCase()) {
        'adjective' => 'adj',
        'adverb' => 'adv',
        final p => p,
      };
}

/// An open SQLite pack and the per-word data read from it, most recently
/// used last (internal to [LexiconPack] and [LexEntry]). Senses are asked for every word of the 資料庫單字本
/// (learnerMeaning, then cached as a string on the entry); the body
/// (examples, relations…) only for the word on screen.
class LexSource {
  LexSource(LexiconSqlite this._db);

  /// Built on a background isolate ([LexiconPack.openSqlite]): the file is
  /// [attach]ed on the UI isolate before any entry reads it.
  LexSource.detached();

  LexiconSqlite? _db;
  LexiconSqlite? get db => _db;

  void attach(LexiconSqlite db) => _db = db;
  final _senses = <int, List<LexSense>>{};
  final _details = <int, LexDetail>{};
  static const senseCacheSize = 3000;
  static const detailCacheSize = 400;

  List<LexSense> senses(int id) {
    final cached = _senses.remove(id);
    if (cached != null) return _senses[id] = cached;
    final parsed = LexEntry.parseSenses(_db?.senses(id));
    if (_senses.length >= senseCacheSize) _senses.remove(_senses.keys.first);
    return _senses[id] = parsed;
  }

  LexDetail detail(int id) {
    final cached = _details.remove(id);
    if (cached != null) return _details[id] = cached;
    final parsed = LexDetail.fromJson(_db?.body(id) ?? const {});
    if (_details.length >= detailCacheSize) {
      _details.remove(_details.keys.first);
    }
    return _details[id] = parsed;
  }

  void invalidate() {
    _senses.clear();
    _details.clear();
  }

  void close() {
    invalidate();
    _db?.close();
  }
}

class LexiconHit {
  final LexEntry entry;

  /// lemma+pos, lemma, or form (an inflected form led to the lemma).
  final String via;

  const LexiconHit(this.entry, this.via);
}

class MissingRequest {
  final String kind; // missing_lexeme / missing_localization
  final String lemma;
  final String pos;
  final int? lexemeId;
  final String? target;
  final String? native;
  final int count;

  const MissingRequest({
    required this.kind,
    required this.lemma,
    required this.pos,
    this.lexemeId,
    this.target,
    this.native,
    this.count = 1,
  });

  Map<String, dynamic> toJson() => {
        'kind': kind,
        'lemma': lemma,
        'pos': pos,
        'lexeme_id': lexemeId,
        'target_language': target,
        'native_language': native,
        'count': count,
      };
}

class LexSense {
  final int id;
  final String definition;
  final String? native;
  final bool nativeAi;
  final String? register;

  /// Usage labels from the dictionary (obsolete, slang, informal…).
  final List<String> labels;

  const LexSense(this.id, this.definition, this.native, this.nativeAi,
      {this.register, this.labels = const []});

  /// Where a sense goes in a detail page's list (卡 #227 第 124 輪): 0 common,
  /// 1 only ranked low (#184), 2 slang, obsolete, offensive and the like —
  /// bank 動詞「把東西藏在直腸內」 after 「傾斜轉彎」.
  int get displayTier {
    final rare = labels.where(LexEntry.isRareLabel).toList();
    if (rare.isEmpty) return 0;
    return rare.every((l) => l.toLowerCase() == 'low_priority') ? 1 : 2;
  }
}

class LexForm {
  final String field;
  final String form;
  final String normalized;
  final String? label;

  const LexForm(this.field, this.form, this.normalized, this.label);
}

class LexMorpheme {
  final String part;
  final String kind; // prefix / root / suffix
  final String? meaning;
  final String? native;

  /// A root that is a word on its own (flap in flapping): 單字, not 字根.
  final bool free;

  /// [native] was written by the AI (shown with an AI mark, as in the admin).
  final bool nativeAi;

  const LexMorpheme(this.part, this.kind, this.meaning, this.native,
      {this.free = false, this.nativeAi = false});
}

class LexRelation {
  final String relation;
  final String word;
  final int? lexemeId;
  final String? native;
  final String? cefr;
  final double? zipf;
  final String? rarity;
  final bool hideByDefault;

  /// The sense of this lexeme the relation belongs to, when the pack says.
  final int? senseId;

  const LexRelation(this.relation, this.word, this.lexemeId, this.native,
      {this.cefr,
      this.zipf,
      this.rarity,
      this.hideByDefault = false,
      this.senseId});
}

class LexExample {
  final String text;
  final String? translation;
  final bool translationAi;
  final String? source;
  final String? difficulty;

  /// The sense the sentence was bound to, when the pack says.
  final int? senseId;

  const LexExample(this.text, this.translation, this.translationAi, this.source,
      this.difficulty,
      {this.senseId, this.license});

  /// The sentence's license as the pack stores it ("CC BY 2.0 FR"), for
  /// credits outside the app (匯出到 Anki, 問題回報 #325).
  final String? license;

  /// The sentence itself was written by AI (a CEFR level the dictionaries
  /// left short), not only its translation.
  bool get aiGenerated => source == 'ai_translate';
}

/// Where the word comes from (Wiktionary), with its native-language text
/// when the admin has one.
class LexEtymology {
  final String text;
  final String? native;
  final String? originLanguage;
  final String? originalForm;

  const LexEtymology(this.text, this.native,
      {this.originLanguage, this.originalForm});
}

/// The per-word data a SQLite pack reads on demand (everything but the head
/// that [LexiconPack] indexes at launch).
/// The credit of one recording: speaker (or attribution) and license, and
/// the page it came from.
class RecordingCredit {
  final String text;
  final String? sourcePage;

  /// A synthetic (Azure neural-voice) clip: shown as is, without the
  /// 「發音錄音：」 speaker/license prefix.
  final bool isSynthetic;

  const RecordingCredit(this.text, {this.sourcePage, this.isSynthetic = false});

  /// The credit of an Azure synthetic clip (卡 #695), instead of a speaker
  /// and license.
  static const synthetic = RecordingCredit('Azure 神經語音（合成）', isSynthetic: true);

  /// One name from Wikimedia's speaker text (M139: "Speaker: X\nRecorder: Y"
  /// showed both lines): the name after `Speaker:`, else the first line
  /// without its label; at most 60 characters.
  static String? cleanSpeaker(String? raw) {
    if (raw == null) return null;
    final lines = [
      for (final l in raw.split(RegExp(r'[\r\n]+')))
        if (l.trim().isNotEmpty) l.trim()
    ];
    if (lines.isEmpty) return null;
    final labelled = RegExp(r'^([A-Za-z ]+)\s*[:：]\s*(.+)$');
    String? name;
    for (final l in lines) {
      final m = labelled.firstMatch(l);
      if (m != null && m.group(1)!.trim().toLowerCase() == 'speaker') {
        name = m.group(2);
        break;
      }
    }
    name ??= labelled.firstMatch(lines.first)?.group(2) ?? lines.first;
    // Commons' "No machine-readable author provided. X assumed (based on
    // copyright claims)." names X.
    final assumed = RegExp(
            r'^No machine-readable author provided\.\s*(.+?)\s+assumed\b',
            caseSensitive: false)
        .firstMatch(name.trim());
    if (assumed != null) name = assumed.group(1)!;
    name = name.trim();
    if (name.isEmpty) return null;
    return name.length > 60 ? '${name.substring(0, 59)}…' : name;
  }

  static RecordingCredit? fromJson(Map<String, dynamic> p) {
    String? field(String k) {
      final v = (p[k] as String? ?? '').trim();
      return v.isEmpty ? null : v;
    }

    final attribution = field('attribution');
    final who = cleanSpeaker(field('speaker')) ??
        (attribution == null || attribution.toLowerCase() == 'own work'
            ? null
            : attribution);
    final license = field('license');
    final parts = [
      if (who != null) who,
      if (license != null) license,
    ];
    if (parts.isEmpty) return null;
    return RecordingCredit(parts.join(' · '), sourcePage: field('source_page'));
  }
}

/// One pack recording: its path (relative to the media base), accent
/// label, and whether it is a synthetic voice (Windows 卡 #584/#695/#759:
/// Azure neural-voice files are written into the pack as pronunciations,
/// and play only after every real recording).
typedef LexRecording = ({String path, String? accent, bool synthetic});

/// Whether a pronunciation row is a synthesized (TTS) clip rather than a
/// person's recording. Lenient on purpose, since the Windows pack format
/// may name it any of these ways — accepted:
///   * `"source": "tts"`, `"azure"` or `"azure_tts"` (any case),
///   * `"synthetic": true`,
///   * `"kind": "tts_audio"`.
/// A row with none of these (every pack before Azure) is a real recording.
bool isSyntheticPronunciation(Map<String, dynamic> p) {
  final source = p['source'];
  if (source is String &&
      // Windows exports Azure files as source=azure_tts (M300, #759).
      const {'tts', 'azure', 'azure_tts'}
          .contains(source.trim().toLowerCase())) {
    return true;
  }
  return p['synthetic'] == true || p['kind'] == 'tts_audio';
}

class LexDetail {
  final String? ipa;

  /// Every IPA with its accent, pack order (卡 #227 第 147 輪): the screens
  /// show the one in 設定's accent rather than always the first ([ipa]).
  final List<({String value, String? accent})> ipas;
  final String? audio; // relative to assets/lexicon/media/
  final List<LexRecording> recordings;
  final String? audioCredit;

  /// Who recorded each recording and under what license, by its path
  /// (問題回報 #657 / M138: CC BY-SA recordings must credit the speaker).
  final Map<String, RecordingCredit> recordingCredits;
  final List<LexExample> examples;
  final List<LexRelation> relations;
  final List<LexMorpheme> morphemes;
  final LexEtymology? etymology;
  final Map<String, String> missing;

  const LexDetail({
    this.ipa,
    this.ipas = const [],
    this.audio,
    this.recordings = const [],
    this.recordingCredits = const {},
    this.audioCredit,
    this.examples = const [],
    this.relations = const [],
    this.morphemes = const [],
    this.etymology,
    this.missing = const {},
  });

  static const empty = LexDetail();

  /// From a pack row or its body (`examples`, `relations`, `morphemes`,
  /// `etymology`, `pronunciations`, `missing`).
  factory LexDetail.fromJson(Map<String, dynamic> j) {
    List<Map<String, dynamic>> list(String k) => [
          for (final x in (j[k] as List? ?? const [])) x as Map<String, dynamic>
        ];
    final prons = list('pronunciations');
    final ipa = prons.where((p) => p['kind'] == 'ipa').firstOrNull;
    final audio = prons
        .where((p) =>
            (p['kind'] == 'audio' || p['kind'] == 'tts_audio') &&
            p['audio'] != null)
        .toList()
      // Real recordings before synthetic ones, then the default one first.
      ..sort((a, b) {
        final real = (isSyntheticPronunciation(a) ? 1 : 0) -
            (isSyntheticPronunciation(b) ? 1 : 0);
        if (real != 0) return real;
        return (b['default'] == true ? 1 : 0) - (a['default'] == true ? 1 : 0);
      });
    final ety = j['etymology'] as Map<String, dynamic>?;
    final etyText = (ety?['text'] as String? ?? '').trim();
    final etyNative = (ety?['native'] as String? ?? '').trim();
    return LexDetail(
      ipa: ipa?['value'] as String?,
      ipas: [
        for (final p in prons)
          if (p['kind'] == 'ipa' && p['value'] is String)
            (value: p['value'] as String, accent: p['accent'] as String?),
      ],
      audio: audio.firstOrNull?['audio'] as String?,
      recordings: [
        for (final p in audio)
          if ((p['audio'] as String).isNotEmpty)
            (
              path: p['audio'] as String,
              accent: p['accent'] as String?,
              synthetic: isSyntheticPronunciation(p),
            ),
      ],
      recordingCredits: {
        for (final p in audio)
          if ((p['audio'] as String).isNotEmpty)
            if (isSyntheticPronunciation(p)
                    ? RecordingCredit.synthetic
                    : RecordingCredit.fromJson(p)
                case final c?)
              p['audio'] as String: c,
      },
      audioCredit: () {
        final first = audio.firstOrNull;
        if (first != null && isSyntheticPronunciation(first)) {
          return RecordingCredit.synthetic.text;
        }
        final parts = [
          for (final k in ['license', 'attribution'])
            if ((first?[k] as String? ?? '').trim().isNotEmpty)
              (first![k] as String).trim(),
        ];
        return parts.isEmpty ? null : parts.join(' · ');
      }(),
      examples: [
        for (final e in list('examples'))
          LexExample(
              e['text'] as String,
              e['translation'] as String?,
              e['translation_ai'] == true,
              e['source'] as String?,
              (e['level'] ?? e['difficulty']) as String?,
              senseId: (e['sense_id'] as num?)?.toInt(),
              license: e['license'] as String?),
      ],
      relations: [
        for (final r in list('relations'))
          LexRelation(r['relation'] as String, r['word'] as String,
              (r['lexeme_id'] as num?)?.toInt(), r['native'] as String?,
              cefr: r['cefr'] as String?,
              zipf: (r['zipf'] as num?)?.toDouble(),
              rarity: r['rarity'] as String?,
              hideByDefault: r['hide_by_default'] == true,
              senseId: (r['sense_id'] as num?)?.toInt()),
      ],
      morphemes: [
        for (final m in list('morphemes'))
          LexMorpheme(m['part'] as String, m['kind'] as String,
              m['meaning'] as String?, m['native'] as String?,
              free: m['free'] == true, nativeAi: m['native_ai'] == true),
      ],
      etymology: etyText.isEmpty && etyNative.isEmpty
          ? null
          : LexEtymology(etyText, etyNative.isEmpty ? null : etyNative,
              originLanguage: ety?['origin_language'] as String?,
              originalForm: ety?['original_form'] as String?),
      missing: {
        for (final e in (j['missing'] as Map? ?? {}).entries)
          '${e.key}': '${e.value}',
      },
    );
  }
}

class LexEntry {
  final String entryType;
  final int id;
  final String lemma;
  final String normalized;
  final String pos;
  final String status;
  final String? cefr;
  final double? zipf;
  final List<LexForm> forms;

  // A JSON entry holds its senses and detail; a SQLite entry reads them
  // from [_source] when asked (card #428). A hand-made (const) entry gives
  // the detail fields one by one.
  final List<LexSense>? _senses;
  final LexDetail? _detail;
  final LexSource? _source;
  final String? _ipa;
  final String? _audio;
  final List<LexRecording> _recordings;
  final String? _audioCredit;
  final List<LexExample> _examples;
  final List<LexRelation> _relations;
  final List<LexMorpheme> _morphemes;
  final LexEtymology? _etymology;
  final Map<String, String> _missing;

  List<LexSense> get senses => _senses ?? _source?.senses(id) ?? const [];
  LexDetail get detail =>
      _detail ??
      _source?.detail(id) ??
      LexDetail(
          ipa: _ipa,
          audio: _audio,
          recordings: _recordings,
          audioCredit: _audioCredit,
          examples: _examples,
          relations: _relations,
          morphemes: _morphemes,
          etymology: _etymology,
          missing: _missing);

  String? get ipa => detail.ipa;
  List<({String value, String? accent})> get ipas => detail.ipas;
  String? get audio => detail.audio; // relative to assets/lexicon/media/
  List<LexRecording> get recordings => detail.recordings;

  /// License and attribution of [audio] ("CC BY-SA 4.0 · Own work"), for
  /// credits outside the app (匯出到 Anki, 問題回報 #325).
  String? get audioCredit => detail.audioCredit;
  Map<String, RecordingCredit> get recordingCredits => detail.recordingCredits;
  List<LexExample> get examples => detail.examples;
  List<LexRelation> get relations => detail.relations;
  List<LexMorpheme> get morphemes => detail.morphemes;
  LexEtymology? get etymology => detail.etymology;
  Map<String, String> get missing => detail.missing;

  /// A rarer part of speech of a spelling (問題回報 #16): its CEFR is a
  /// frequency estimate and database lists put it after the main usages.
  final bool rareUsage;

  /// 0 = the spelling's main part of speech (the pack ranks them).
  final int usageRank;

  /// [cefr] is a frequency estimate, not from the CEFR-J / Octanove lists:
  /// shown as 「估算」 (問題回報 #139 decision, #132).
  final bool cefrEstimated;

  /// The word whose card this form shares (tethered: tether), or null
  /// (owner decision 2026-10-14, 問題回報 #51).
  final String? card;

  /// This part of speech is only [card]'s form (dried the verb), so it adds
  /// no meaning to that card; dried the adjective (乾燥的) does.
  final bool cardForm;

  /// Lexeme ids whose pictures this entry shows (picture_need). Null on a
  /// pack built before that field: show this entry's own tags. Empty: this
  /// part of speech has no noun picture to share.
  final List<int>? pictureIds;

  const LexEntry({
    this.entryType = 'word',
    required this.id,
    required this.lemma,
    required this.normalized,
    required this.pos,
    required this.status,
    this.cefr,
    this.zipf,
    List<LexSense>? senses,
    this.forms = const [],
    LexDetail? detail,
    LexSource? source,
    // Detail fields given one by one (tests, hand-made entries).
    String? ipa,
    String? audio,
    List<LexRecording> recordings = const [],
    String? audioCredit,
    List<LexExample> examples = const [],
    List<LexRelation> relations = const [],
    List<LexMorpheme> morphemes = const [],
    LexEtymology? etymology,
    Map<String, String> missing = const {},
    this.rareUsage = false,
    this.usageRank = 0,
    this.cefrEstimated = false,
    this.card,
    this.cardForm = false,
    this.pictureIds,
  })  : _senses = senses ?? (source == null ? const [] : null),
        _detail = detail,
        _source = source,
        _ipa = ipa,
        _audio = audio,
        _recordings = recordings,
        _audioCredit = audioCredit,
        _examples = examples,
        _relations = relations,
        _morphemes = morphemes,
        _etymology = etymology,
        _missing = missing;

  bool get full => status == 'full';

  /// The native meaning shown on labels: the first sense that has one.
  String? get nativeMeaning => senses
      .map((s) => s.native)
      .firstWhere((t) => (t ?? '').isNotEmpty, orElse: () => null);

  static const _rareLabels = {
    'obsolete',
    'archaic',
    'dated',
    'rare',
    'slang',
    'humorous',
    'nonstandard',
    'historical',
    'vulgar',
    'derogatory',
    'offensive',
    'euphemistic',
    'poetic',
    // brown 「（幼兒用語）拉屎」 (問題回報 #341).
    'childish',
    // Quality rules (#184): senses ranked low by lexicon/backend/app/quality.py.
    'low_priority',
  };

  static bool isRareLabel(String label) =>
      _rareLabels.contains(label.toLowerCase());

  /// What a learner recalls from (問題回報 #18, owner decision 2026-10-01):
  /// the Chinese of the first two common senses, skipping obsolete, slang
  /// and similar ones, each word once — tea → 茶樹；茶葉、茶、茶水.
  ///
  /// Owner decision 問題回報 #84: senses with a dictionary translation come
  /// first; an AI-filled one (often a description of a sub-sense: door
  /// 「有門的建築物」) only when no dictionary translation is left.
  /// Computed once per entry (the 資料庫單字本 filters 30k entries on every
  /// keystroke — 問題回報 #141); an entry never changes after loading.
  static final _learnerCache = Expando<Object>('learnerMeaning');
  static final _searchCache = Expando<String>('searchText');
  static const _noMeaning = Object();

  String? get learnerMeaning {
    final cached = _learnerCache[this];
    if (cached != null) {
      return identical(cached, _noMeaning) ? null : cached as String;
    }
    final value = _learnerMeaning();
    _learnerCache[this] = value ?? _noMeaning;
    return value;
  }

  /// The headword and its meaning, lower case, for search boxes.
  String get searchText =>
      _searchCache[this] ??= '$lemma ${learnerMeaning ?? ''}'.toLowerCase();

  static final _searchPartsCache = Expando<List<String>>('searchParts');
  static final _searchWordBreak = RegExp(r'[\s\-–—/、，,；;：:（）()「」]+');

  /// How the 資料庫單字本 search box matches this entry (問題回報 #417):
  /// 0 = the headword or meaning itself (rat), 1 = a word of it (rat race),
  /// 2 = the start of a word (rate), 3 = letters inside a word (accurate),
  /// null = no match. [query] is trimmed and lower case; empty matches all.
  int? searchRank(String query) {
    if (query.isEmpty) return 0;
    final head = lemma.trim().toLowerCase();
    final meaning = (learnerMeaning ?? '').trim().toLowerCase();
    if (head == query || meaning == query) return 0;
    final parts = _searchPartsCache[this] ??= [
      for (final text in [head, meaning])
        ...text.split(_searchWordBreak).where((p) => p.isNotEmpty)
    ];
    int? best;
    for (final part in parts) {
      if (part == query) return 1;
      if (part.startsWith(query)) best = 2;
    }
    return best ?? (searchText.contains(query) ? 3 : null);
  }

  String? _learnerMeaning() {
    final usable = [
      for (var i = 0; i < senses.length; i++)
        if ((senses[i].native ?? '').trim().isNotEmpty &&
            !senses[i].labels.any((l) =>
                _rareLabels.contains(l.toLowerCase()) ||
                // Another etymology: a different word with the same
                // spelling — unless the lexicon put it first (問題回報
                // #341: date 「日期」, pen 「筆」, plane 「飛機」).
                (i > 0 && l.startsWith('etymology-'))))
          senses[i]
    ];
    final dictionary = usable.where((s) => !s.nativeAi).toList();
    final common =
        (dictionary.isNotEmpty ? dictionary : usable).take(2).toList();
    if (common.isEmpty) return nativeMeaning;
    // A meaning that spells the answer gives it away on the front (問題回報
    // #118: toll 「徵收 toll」).
    final answer = RegExp(
        '(?<![A-Za-z])(${[
          lemma,
          ...forms.map((f) => f.form)
        ].map(RegExp.escape).join('|')})(?![A-Za-z])',
        caseSensitive: false);
    // An English meaning (the fr→en pack) keeps English punctuation; a
    // Chinese one uses 、 and ； (問題回報 #363).
    final chinese = common.any((s) => _cjk.hasMatch(s.native!));
    List<String> build({required bool hideAnswer}) {
      final seen = <String>{};
      return [
        for (final sense in common)
          [
            for (final word in _meaningWords(sense.native!))
              if (word.isNotEmpty &&
                  !(hideAnswer && answer.hasMatch(word)) &&
                  seen.add(word))
                word
          ].join(chinese ? '、' : ', '),
      ].where((part) => part.isNotEmpty).toList();
    }

    var parts = build(hideAnswer: true);
    // A cognate's meaning is its own spelling (moment → moment, boss →
    // boss): showing it beats a card with no meaning at all.
    if (parts.isEmpty) parts = build(hideAnswer: false);
    return parts.isEmpty ? null : parts.join(chinese ? '；' : '; ');
  }

  static final _cjk = RegExp(r'[一-鿿]');

  /// The comma-separated words of a meaning, never split inside brackets:
  /// "capacity (to hold, receive or absorb)" is one word.
  static List<String> _meaningWords(String text) {
    final out = <String>[];
    var depth = 0, start = 0;
    for (var i = 0; i < text.length; i++) {
      final c = text[i];
      if (c == '(' || c == '（') depth++;
      if ((c == ')' || c == '）') && depth > 0) depth--;
      if (depth == 0 && (c == ',' || c == '，' || c == '、')) {
        out.add(text.substring(start, i).trim());
        start = i + 1;
      }
    }
    out.add(text.substring(start).trim());
    return out;
  }

  /// 構詞拆解 as one line: ex- + -ter + -ior.
  String get breakdown => morphemes.map((m) => m.part).join(' + ');

  /// The senses of a pack row (`senses` list), in pack order.
  static List<LexSense> parseSenses(List<dynamic>? raw) => [
        for (final s in (raw ?? const []).cast<Map<String, dynamic>>())
          LexSense((s['id'] as num).toInt(), s['definition'] as String? ?? '',
              s['native'] as String?, s['native_ai'] == true,
              register: s['register'] as String?,
              labels: [
                for (final l in (s['labels'] as List? ?? const [])) '$l'
              ]),
      ];

  /// A full pack row, or — with [lazyFrom] — only its head: senses and the
  /// rest are read from that SQLite pack when first asked.
  factory LexEntry.fromJson(Map<String, dynamic> j, {LexSource? lazyFrom}) {
    List<Map<String, dynamic>> list(String k) => [
          for (final x in (j[k] as List? ?? const [])) x as Map<String, dynamic>
        ];
    return LexEntry(
      source: lazyFrom,
      senses: lazyFrom == null ? parseSenses(j['senses'] as List?) : null,
      detail: lazyFrom == null ? LexDetail.fromJson(j) : null,
      id: (j['id'] as num).toInt(),
      lemma: j['lemma'] as String,
      entryType: j['entry_type'] as String? ?? 'word',
      normalized: j['normalized'] as String,
      pos: j['pos'] as String,
      status: j['status'] as String? ?? 'full',
      cefr: j['cefr'] as String?,
      cefrEstimated: j['cefr_source'] == 'frequency_estimate' ||
          j['cefr_source'] == 'estimate' ||
          j['cefr_source'] == 'ai_reviewed',
      card: j['card'] as String?,
      cardForm: j['card_form'] == true,
      zipf: (j['zipf'] as num?)?.toDouble(),
      forms: [
        for (final f in list('forms'))
          LexForm(f['field'] as String, f['form'] as String,
              f['normalized'] as String? ?? '', f['label'] as String?),
      ],
      rareUsage: j['rare_usage'] == true,
      usageRank: (j['usage_rank'] as num?)?.toInt() ?? 0,
      pictureIds: j.containsKey('picture_ids')
          ? [
              for (final id in (j['picture_ids'] as List? ?? const []))
                (id as num).toInt()
            ]
          : null,
    );
  }

  static const _relationFields = {
    'synonyms': 'synonyms',
    'homophones': 'homophones',
    'near_homophones': 'homophones',
    'similar_spelling': 'similarSpelling',
  };

  /// The app's [WordDetail]. [family] are the forms sharing this card:
  /// each one's own meaning joins its form, listed first —
  /// tethered（過去分詞・形容詞：被拴住的）.
  WordDetail toDetail({List<LexEntry> family = const []}) {
    List<String> rel(String appField) => [
          for (final r in relations)
            if (_relationFields[r.relation] == appField) r.word,
        ];
    final ownMeaning = <String, List<String>>{};
    final formOf = <String, LexEntry>{};
    for (final m in family) {
      final meaning = m.learnerMeaning;
      if (meaning == null || m.cardForm) continue;
      formOf.putIfAbsent(m.normalized, () => m);
      (ownMeaning[m.normalized] ??= []).add('${posLabel(m.pos)}：$meaning');
    }
    final listed = {for (final f in forms) f.normalized};
    return WordDetail(
      word: normalized,
      definitions: [
        for (final s in senses)
          Definition(pos: pos, gloss: s.definition, register: s.register)
      ],
      definitionsSource: 'lexicon',
      ipa: ipa,
      ipaSource: ipa == null ? null : 'lexicon',
      wordAudioUrl: audio == null ? null : 'assets/lexicon/media/$audio',
      wordAudioSource: audio == null ? null : 'lexicon',
      synonyms: rel('synonyms'),
      homophones: rel('homophones'),
      similarSpelling: rel('similarSpelling'),
      inflections: [
        // French noun gender (card #429): the headword with its article first
        // — le chat（陽性）, la table（陰性）, un arbre（陽性）.
        for (final f in forms)
          if (f.field == 'fr_gender')
            Inflection(
                form: frenchWithArticle(normalized, f.form),
                label: frenchGenderLabel(f.form)),
        for (final f in [
          ...forms.where((f) =>
              f.field != 'fr_gender' && ownMeaning.containsKey(f.normalized)),
          ...forms.where((f) =>
              f.field != 'fr_gender' && !ownMeaning.containsKey(f.normalized)),
        ])
          Inflection(
              form: f.form,
              label: ownMeaning[f.normalized] == null
                  ? f.label ?? f.field
                  : '${formLabel(f.label ?? f.field)}・'
                      '${ownMeaning[f.normalized]!.join('；')}'),
        for (final MapEntry(:key, :value) in ownMeaning.entries)
          if (!listed.contains(key))
            Inflection(form: formOf[key]!.lemma, label: value.join('；')),
      ],
      derivations: [
        for (final r in relations)
          if (r.relation == 'derived_terms') Derivation(word: r.word),
      ],
      root: morphemes
          .where((m) => m.kind == 'root')
          .map((m) => m.part)
          .firstOrNull,
      affixes: [
        for (final m in morphemes)
          if (m.kind != 'root') m.part,
      ],
      morphologySource: morphemes.isEmpty ? null : 'lexicon',
      morphology: morphemes.length < 2
          ? null
          : morphemes
              .map((m) => (m.native ?? '').trim().isEmpty
                  ? m.part
                  : '${m.part}（${m.native!.split(RegExp('[、；]')).first}）')
              .join(' ＋ '),
      etymology: etymology?.native,
      exampleSentences: [
        for (final e in examples)
          ExampleSentence(
              en: e.text,
              zh: e.translation,
              source: e.source,
              zhSource: e.translationAi ? 'ai_translate' : null,
              difficulty: e.difficulty),
      ],
      relations: [
        for (final r in relations)
          RelatedTerm(
              native: r.native,
              word: r.word,
              relation: r.relation,
              cefr: r.cefr,
              zipf: r.zipf,
              rarity: r.rarity,
              hideByDefault: r.hideByDefault),
      ],
    );
  }
}

/// The background half of [LexiconPack.openSqlite]: copy, patch, then index
/// the heads into a pack whose entries read from a detached [LexSource].
LexiconPack _indexSqlite(
    ({
      String path,
      String? copyFrom,
      Uint8List? deltaJson,
      String? target,
      String? native,
      String? renameTo,
    }) job) {
  final path = job.path, copyFrom = job.copyFrom, deltaJson = job.deltaJson;
  if (copyFrom != null) File(copyFrom).copySync(path);
  try {
    if (deltaJson != null) {
      final db = LexiconSqlite.open(path);
      try {
        db.applyDelta(
            jsonDecode(utf8.decode(deltaJson)) as Map<String, dynamic>);
      } finally {
        db.close();
      }
    }
    final pack = LexiconPack();
    final db = LexiconSqlite.open(path, readOnly: true);
    try {
      final source = LexSource.detached();
      pack._install(db.meta(), db.heads(),
          (raw) => LexEntry.fromJson(raw, lazyFrom: source),
          source: source);
    } finally {
      db.close();
    }
    if ((job.target != null && pack.target != job.target) ||
        (job.native != null && pack.native != job.native) ||
        (job.target != null && pack.version == null)) {
      throw const FormatException('Wrong dictionary language');
    }
    if (job.renameTo != null) File(path).renameSync(job.renameTo!);
    return pack;
  } catch (_) {
    if (copyFrom != null) {
      try {
        File(path).deleteSync();
      } catch (_) {}
    }
    rethrow;
  }
}

/// A word as the screens show it in the learning [language] (問題回報 #499,
/// 卡 #496): English capitalised ("Cutting Board"); French in its lowercase
/// spelling, a noun with its article ("la pomme") — the same headword the
/// card back and 單字詳情 show.
String shownWord(String word, String language, {String? pos}) {
  if (language != 'fr') return displayWord(word);
  final pack = LexiconPack.instance;
  final hit = pack.lookup(word, pos: pos)?.entry;
  return headword(word, language,
      inflections: hit == null ? const [] : pack.detailFor(hit).inflections,
      pos: pos ?? hit?.pos);
}

/// Whether a catalog picture's label (or a tagger candidate) was marked by
/// the tagger as not really placed on the picture (問題回報 #703, Windows
/// 卡 #631): the model answered its default centre with no box for a scene
/// word (night, city, sky…). Such a label is treated like one with no
/// point — no pin, 「整張圖」, skipped by the drag exercise. Both
/// spellings are accepted (`pointUngrounded`, `point_ungrounded`).
bool labelPointUngrounded(Map label) =>
    label['pointUngrounded'] == true || label['point_ungrounded'] == true;
