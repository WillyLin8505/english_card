import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'app_settings.dart';
import 'background_errors.dart';
import 'lexicon_pack.dart';
import 'word_database_repository.dart';

/// Reconstruct the exact next snapshot, including deletions and ordering.
/// Never accept a patch for a different cached version.
Map<String, dynamic> applyDictionaryDelta(
    Map<String, dynamic> base, Map<String, dynamic> patch) {
  if (patch['delta_version'] != 1 ||
      patch['base_version'] != base['created_at'] ||
      patch['metadata'] is! Map ||
      patch['order'] is! List ||
      patch['upserts'] is! List) {
    throw const FormatException('Invalid dictionary delta');
  }
  final rows = <int, dynamic>{
    for (final row in base['lexemes'] as List) row['id'] as int: row,
  };
  for (final row in patch['upserts'] as List) {
    rows[row['id'] as int] = row;
  }
  final order = (patch['order'] as List).cast<int>();
  if (order.toSet().length != order.length ||
      order.any((id) => !rows.containsKey(id))) {
    throw const FormatException('Incomplete dictionary delta');
  }
  return {
    ...Map<String, dynamic>.from(patch['metadata'] as Map),
    'lexemes': [for (final id in order) rows[id]],
  };
}

/// Read-only master dictionary updates. Personal edits and review state remain
/// in the learner repository. Never send admin credentials to the browser.
class DictionarySync extends ChangeNotifier {
  static final instance = DictionarySync();
  final http.Client client;

  /// Whether this build has a dictionary server to poll: the web page's own
  /// server, or a build with DICTIONARY_URL. The store build has none and
  /// reads only the bundled pack (問題回報 #265, owner decision 2026-10-18).
  static const hasServer =
      kIsWeb || String.fromEnvironment('DICTIONARY_URL') != '';

  /// The owner's backend (Cloudflare Tunnel today, Cloudflare later: change
  /// only this). The dictionary there is read-only, keyless and rate-limited,
  /// so every build (store builds too) polls it and the bundled pack is just
  /// the offline fallback (問題回報 #287). A key from 設定 is still sent.
  static const defaultServer = 'https://api.willylinai.com/api/lexicon';

  final bool? _remoteOverride;

  /// Polls a server (true) or serves the bundled pack (false).
  /// Tests switch this off so widget tests never reach the network.
  static bool defaultRemote = true;

  bool get remote => _remoteOverride ?? defaultRemote;

  DictionarySync({http.Client? client, bool? remote})
      : client = client ?? http.Client(),
        _remoteOverride = remote;
  Timer? _timer;

  /// A healthy cache holds one pack (~30-60 MB); anything bigger is leftover.
  static const maxCacheFileBytes = 100 * 1024 * 1024;
  LazyBox<String>? _cache;
  AppSettings? _settings;
  WordDatabaseRepository Function()? _repository;
  bool _running = false;
  bool _disposed = false;
  String status = '正在連接詞庫…';
  DateTime? lastSuccess;

  /// True only while [status] holds a failure message. Screens that show the
  /// connecting/connected text as permanent chrome should hide it otherwise —
  /// those two states are debugging noise, not something learners need
  /// (問題回報 #260); the failure message is.
  bool hasError = false;

  /// 問題回報 #856: a fresh install fetches the whole pack (~62 MB) in its
  /// first minutes; the 資料庫 pages show this progress instead of an empty
  /// list. [downloadTotalBytes] is null when the server sends no length.
  bool downloading = false;
  int downloadedBytes = 0;
  int? downloadTotalBytes;
  String? _activePair;
  final _forceFull = <String>{};

  Uri endpoint(String target, String native) {
    const base = String.fromEnvironment('DICTIONARY_URL');
    final uri = base.isNotEmpty
        ? Uri.parse(base)
        : kIsWeb
            ? Uri.base.resolve('/api/lexicon')
            : Uri.parse(defaultServer);
    return uri.replace(queryParameters: {'target': target, 'native': native});
  }

  /// Where 缺詞條 go (spec section 7): the same local server, which saves
  /// them in the admin's missing_lexeme / missing_localization requests.
  Uri get missingEndpoint => endpoint('en', 'zh-TW')
      .replace(path: '/api/missing', queryParameters: {});

  /// The tagger key from 設定: a server reached over the internet
  /// (serve_app.py --public-host) needs it for the dictionary too.
  Map<String, String> get _keyHeader {
    final key = _settings?.apiKey.trim() ?? '';
    return key.isEmpty ? const {} : {'X-API-Key': key};
  }

  final _sentMissing = <String>{};

  /// Sends the words the pack lacked since the last call. Returns how many
  /// were sent; failures are retried on the next refresh.
  Future<int> sendMissing() async {
    if (!remote) return 0;
    final pending = {
      for (final e in LexiconPack.instance.requests.entries)
        if (!_sentMissing.contains(e.key)) e.key: e.value,
    };
    if (pending.isEmpty) return 0;
    final response = await client
        .post(missingEndpoint,
            headers: {'Content-Type': 'application/json', ..._keyHeader},
            body: jsonEncode({
              'requests': [
                for (final r in pending.values.take(500))
                  {...r.toJson(), 'target': r.target, 'native': r.native},
              ]
            }))
        .timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) return 0;
    final sent = pending.keys.take(500).toList();
    _sentMissing.addAll(sent);
    return sent.length;
  }

  Future<void> _sendMissingQuietly() async {
    try {
      await sendMissing();
    } catch (e) {
      debugPrint('DictionarySync: sendMissing failed: $e');
      // Offline: try again on the next refresh.
    }
  }

  Future<void> start(AppSettings settings,
      WordDatabaseRepository Function() repository) async {
    _settings = settings;
    _repository = repository;
    settings.addListener(_kick);
    if (!remote) {
      await _useBundled();
      return;
    }
    await _startPolling();
    await refresh();
  }

  /// Opens the cache and the 30 s timer once; also runs when a tagger key is
  /// added later and a bundled-only build starts to qualify for updates.
  Future<void> _startPolling() async {
    if (_timer != null) return;
    // Lazy + always-compact: the pack is one ~30 MB string rewritten on each
    // update, and Hive only appends, so an eager Box grew to 261 MB and ran
    // out of memory on open on a phone (問題回報 #414).
    await _dropOversizedCache();
    _cache ??= await Hive.openLazyBox<String>('dictionary_cache_v1',
        compactionStrategy: (entries, deleted) => deleted > 0);
    if (_disposed) return;
    _timer ??= Timer.periodic(const Duration(seconds: 30), (_) => refresh());
  }

  /// Old builds appended every update to one file (261 MB on an iPhone, #425).
  /// Opening such a file scans all of it and compacting copies it in memory,
  /// which iOS kills at launch. The cache is only a copy of the server pack,
  /// so an oversized file is deleted and the next sync rebuilds it.
  Future<void> _dropOversizedCache() async {
    if (kIsWeb) return;
    try {
      final dir = await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/dictionary_cache_v1.hive');
      if (await file.exists() && await file.length() > maxCacheFileBytes) {
        await Hive.deleteBoxFromDisk('dictionary_cache_v1');
        if (await file.exists()) await file.delete();
      }
    } catch (e) {
      debugPrint('DictionarySync: cache size check failed: $e');
    }
  }

  void _kick() {
    unawaited(refresh());
  }

  /// The pack shipped in the app for the current language pair; a language
  /// switch loads the other direction's pack. No polling, nothing sent.
  Future<void> _useBundled() async {
    if (_disposed || _running || _settings == null || _repository == null) {
      return;
    }
    _running = true;
    try {
      final repo = _repository!();
      final target = repo.language, native = _settings!.nativeLanguage;
      final pair = '$target-$native';
      if (_activePair != pair) {
        await LexiconPack.instance.load(target: target, native: native);
        if (_disposed) return;
        if (identical(repo, _repository!()) &&
            native == _settings!.nativeLanguage) {
          await repo.linkLexiconInBatches(LexiconPack.instance);
          _activePair = pair;
          unawaited(LexiconPack.instance.warmMeanings());
        }
      }
      lastSuccess = DateTime.now();
      status = '使用內建詞庫';
      hasError = false;
    } finally {
      _running = false;
      if (!_disposed) notifyListeners();
    }
  }

  void _succeeded() {
    lastSuccess = DateTime.now();
    status = '已連接詞庫 · 每 30 秒自動更新';
    hasError = false;
    BackgroundErrors.instance.clear(this);
  }

  /// Phones take the dictionary as a SQLite file (card #428, 問題回報 #423):
  /// `format=sqlite` downloads go to [LexiconPack.storageDirectory] as
  /// `{pair}.server.<time>.sqlite` and are opened there, deltas are applied
  /// to that file. The web page (no dart:ffi) keeps the JSON pack in Hive;
  /// a server that answers JSON is still handled the old way.
  static bool useSqlite = LexiconSqlite.supported && !kIsWeb;

  /// The newest usable downloaded SQLite pack for [pair], or null.
  static Future<String?> _serverCopy(
      String pair, String target, String native) async {
    final dir = await LexiconPack.storageDirectory();
    if (!await dir.exists()) return null;
    final copies = <File>[
      for (final f in dir.listSync())
        if (f is File && _isServerCopy(f.path, pair)) f
    ]..sort((a, b) => b.path.compareTo(a.path)); // newest time stamp first
    for (final f in copies) {
      final info = LexiconSqlite.inspect(f.path);
      if (info != null && info.target == target && info.native == native) {
        return f.path;
      }
      try {
        await f.delete();
      } catch (_) {}
    }
    return null;
  }

  static bool _isServerCopy(String path, String pair) {
    final name = path.split(Platform.pathSeparator).last;
    return name.startsWith('$pair.server.') && name.endsWith('.sqlite');
  }

  static String _newServerCopyPath(Directory dir, String pair) =>
      '${dir.path}/$pair.server.${DateTime.now().millisecondsSinceEpoch}.sqlite';

  /// Deletes downloaded packs other than [keep] (a replaced file that is
  /// still open is deleted on a later run).
  static Future<void> _pruneServerCopies(String pair, String? keep) async {
    try {
      final dir = await LexiconPack.storageDirectory();
      if (!await dir.exists()) return;
      for (final f in dir.listSync()) {
        if (f is File && _isServerCopy(f.path, pair) && f.path != keep) {
          try {
            await f.delete();
          } catch (_) {}
        }
      }
    } catch (e) {
      debugPrint('DictionarySync: prune failed: $e');
    }
  }

  Future<void> refresh() async {
    if (!remote) return _useBundled();
    if (_timer == null && _settings != null) await _startPolling();
    if (_disposed || _running || _settings == null || _repository == null) {
      return;
    }
    _running = true;
    final repo = _repository!();
    final target = repo.language, native = _settings!.nativeLanguage;
    final pair = '$target-$native';
    bool current() =>
        !_disposed &&
        identical(repo, _repository!()) &&
        native == _settings!.nativeLanguage;
    try {
      if (_activePair != pair) {
        String? saved;
        var opened = false;
        if (useSqlite) {
          // The last downloaded SQLite pack, else the bundled one; the JSON
          // cache a phone kept before #428 is dropped (~60 MB).
          try {
            final copy = await _serverCopy(pair, target, native);
            if (copy != null) {
              final candidate = await LexiconPack.openSqlite(copy);
              LexiconPack.instance.replaceWith(candidate);
              await repo.linkLexiconInBatches(LexiconPack.instance);
              opened = true;
              if (_cache?.containsKey(pair) ?? false) {
                await _cache?.delete(pair);
              }
            }
          } catch (e) {
            debugPrint('DictionarySync: downloaded pack unusable: $e');
          }
        }
        if (!opened) saved = await _cache?.get(pair);
        if (opened) {
          // ready
        } else if (saved != null) {
          try {
            final candidate = LexiconPack()
              ..loadJson(await compute(_decodeBody, utf8.encode(saved)));
            if (candidate.target != target || candidate.native != native) {
              throw const FormatException('Wrong cached dictionary language');
            }
            LexiconPack.instance.replaceWith(candidate);
            await repo.linkLexiconInBatches(LexiconPack.instance);
          } catch (_) {
            await _cache?.delete(pair);
            await LexiconPack.instance.load(target: target, native: native);
            if (current()) {
              await repo.linkLexiconInBatches(LexiconPack.instance);
            }
          }
        } else if (!kIsWeb) {
          await LexiconPack.instance.load(target: target, native: native);
          if (current()) await repo.linkLexiconInBatches(LexiconPack.instance);
        }
        // The web page skips the 30 MB bundled pack and goes online; the
        // bundled one is only the offline fallback (catch below, #357).
        if (!kIsWeb || saved != null) _activePair = pair;
      }
      final cachedVersion = LexiconPack.instance.version;
      final samePair = cachedVersion != null &&
          LexiconPack.instance.target == target &&
          LexiconPack.instance.native == native;
      // Only a flag here: reading the cached pack (~60 MB of text) on every
      // 30 s tick allocated a huge string each time, even on a 304 (#419).
      final hasSaved = _cache?.containsKey(pair) ?? false;
      // A SQLite pack (downloaded or bundled) can take a delta too: the
      // bundled file is copied beside the downloads first.
      final sqliteBase = useSqlite && LexiconPack.instance.fromSqlite;
      final canReuse =
          !_forceFull.contains(pair) && samePair && (hasSaved || sqliteBase);
      final uri = endpoint(target, native);
      final request = http.Request(
          'GET',
          uri.replace(queryParameters: {
            ...uri.queryParameters,
            if (useSqlite) 'format': 'sqlite',
            if (canReuse) 'since': cachedVersion,
          }))
        ..headers.addAll({
          ..._keyHeader,
          if (canReuse) 'If-None-Match': '"$cachedVersion"',
        });
      final response =
          await client.send(request).timeout(const Duration(seconds: 60));
      if (!current()) {
        unawaited(response.stream.drain<void>().catchError((_) {}));
        return;
      }
      if (response.statusCode == 304 && canReuse) {
        unawaited(response.stream.drain<void>().catchError((_) {}));
        _succeeded();
        await _sendMissingQuietly();
        return;
      }
      if (response.statusCode != 200) {
        unawaited(response.stream.drain<void>().catchError((_) {}));
        throw StateError('Dictionary unavailable');
      }
      final contentType = response.headers['content-type'] ?? '';
      final body = trackDownload(response.stream, response.contentLength);
      if (useSqlite && contentType.contains('sqlite')) {
        // The whole pack as a file: streamed to disk, never held in memory.
        await _installSqliteDownload(
            body, pair, target, native, repo, current);
        _forceFull.remove(pair);
        _succeeded();
        await _sendMissingQuietly();
        return;
      }
      final bodyBytes = await http.ByteStream(body)
          .toBytes()
          .timeout(const Duration(minutes: 5));
      if (!current()) return;
      // Decode off the UI thread and keep only one big copy alive at a time:
      // body bytes + string + tree + a second pack hit iOS's 2 GB limit
      // right after launch (問題回報 #424).
      String? raw;
      var json = await compute(_decodeBody, bodyBytes);
      if (json.containsKey('delta_version')) {
        try {
          if (!canReuse) throw const FormatException('No base for delta');
          if (sqliteBase) {
            // The isolate decodes its own copy; this tree can go.
            json = const {};
            await _applySqliteDelta(bodyBytes, pair, repo);
            _forceFull.remove(pair);
            _succeeded();
            await _sendMissingQuietly();
            return;
          }
          final base = await _cache?.get(pair);
          if (base == null) throw const FormatException('No base for delta');
          final merged = await compute(_mergeDelta, (base, json));
          json = merged.$1;
          raw = merged.$2;
        } catch (_) {
          // Recover with a full request next time, preserving the last good data.
          _forceFull.add(pair);
          rethrow;
        }
      }
      // Parse fully before replacing the last good pack/cache.
      final candidate = LexiconPack()..loadJson(json);
      if (candidate.target != target ||
          candidate.native != native ||
          json['lexemes'] is! List) {
        throw const FormatException('Wrong dictionary language');
      }
      // The same version means the same pack, so the cache is not re-read
      // and compared (another ~60 MB string) just to skip the write.
      if (LexiconPack.instance.version != candidate.version || !hasSaved) {
        LexiconPack.instance.replaceWith(candidate);
        await repo.linkLexiconInBatches(LexiconPack.instance);
        await _cache?.put(pair, raw ?? utf8.decode(bodyBytes));
        await _cache?.compact();
      }
      _forceFull.remove(pair);
      _succeeded();
      await _sendMissingQuietly();
    } catch (e) {
      debugPrint('DictionarySync: refresh failed: $e');
      if (kIsWeb && _activePair != pair && current()) {
        try {
          await LexiconPack.instance.load(target: target, native: native);
          if (current()) {
            await repo.linkLexiconInBatches(LexiconPack.instance);
            _activePair = pair;
          }
        } catch (_) {}
      }
      if (current()) {
        status = '暫時無法連線 · 使用已儲存的詞庫，稍後自動重試';
        hasError = true;
        BackgroundErrors.instance.report(this, status, retry: refresh);
      }
    } finally {
      _running = false;
      downloading = false;
      if (!_disposed) notifyListeners();
      // A language switch during a request must not apply the old response.
      if (!_disposed && !current()) unawaited(refresh());
    }
  }

  /// Counts [body]'s bytes into [downloadedBytes] (問題回報 #856), telling
  /// listeners about every ~1 MB so the progress line moves without
  /// rebuilding the page for each chunk.
  @visibleForTesting
  Stream<List<int>> trackDownload(Stream<List<int>> body, int? total) {
    downloading = true;
    downloadedBytes = 0;
    downloadTotalBytes = total != null && total > 0 ? total : null;
    if (!_disposed) notifyListeners();
    var told = 0;
    return body.map((chunk) {
      downloadedBytes += chunk.length;
      if (downloadedBytes - told >= 1000000 && !_disposed) {
        told = downloadedBytes;
        notifyListeners();
      }
      return chunk;
    });
  }

  /// Writes a `format=sqlite` response to a new `{pair}.server.*.sqlite`
  /// file, checks it, opens it and drops the older downloads. A bad file
  /// is deleted and the current pack stays.
  Future<void> _installSqliteDownload(
      Stream<List<int>> body,
      String pair,
      String target,
      String native,
      WordDatabaseRepository repo,
      bool Function() current) async {
    final dir = await LexiconPack.storageDirectory();
    await dir.create(recursive: true);
    final path = _newServerCopyPath(dir, pair);
    final part = File('$path.part');
    final LexiconPack candidate;
    try {
      final sink = part.openWrite();
      try {
        await body.pipe(sink).timeout(const Duration(minutes: 10));
      } catch (_) {
        await sink.close().catchError((_) {});
        rethrow;
      }
      // Checked, indexed and renamed off the UI thread (M-PERF2).
      candidate = await LexiconPack.openSqlite(part.path,
          target: target, native: native, renameTo: path);
    } catch (_) {
      try {
        if (await part.exists()) await part.delete();
      } catch (_) {}
      rethrow;
    }
    if (!current()) {
      candidate.clear();
      return;
    }
    LexiconPack.instance.replaceWith(candidate);
    await repo.linkLexiconInBatches(LexiconPack.instance);
    if (_cache?.containsKey(pair) ?? false) await _cache?.delete(pair);
    await _pruneServerCopies(pair, path);
    unawaited(LexiconPack.instance.warmMeanings());
  }

  /// Applies a server delta to a copy of the open SQLite pack (a new
  /// `{pair}.server.*.sqlite`), so the pack on screen keeps reading its own
  /// file until the patched one replaces it; the bundled pack is never
  /// patched (its version must keep matching the asset). Copy, patch and
  /// index run off the UI thread (M-PERF2); a failed patch leaves no file.
  Future<void> _applySqliteDelta(
      Uint8List deltaJson, String pair, WordDatabaseRepository repo) async {
    final active = LexiconPack.instance.sqlitePath;
    if (active == null) throw const FormatException('No base for delta');
    final dir = await LexiconPack.storageDirectory();
    await dir.create(recursive: true);
    final path = _newServerCopyPath(dir, pair);
    final candidate = await LexiconPack.openSqlite(path,
        copyFrom: active, deltaJson: deltaJson);
    LexiconPack.instance.replaceWith(candidate);
    await repo.linkLexiconInBatches(LexiconPack.instance);
    await _pruneServerCopies(pair, path);
    unawaited(LexiconPack.instance.warmMeanings());
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    _settings?.removeListener(_kick);
    client.close();
    BackgroundErrors.instance.clear(this);
    super.dispose();
  }
}

Map<String, dynamic> _decodeBody(List<int> bytes) =>
    jsonDecode(utf8.decode(bytes)) as Map<String, dynamic>;

(Map<String, dynamic>, String) _mergeDelta((String, Map<String, dynamic>) a) {
  final merged =
      applyDictionaryDelta(jsonDecode(a.$1) as Map<String, dynamic>, a.$2);
  return (merged, jsonEncode(merged));
}
