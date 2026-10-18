import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;

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
      patch['metadata'] is! Map || patch['order'] is! List ||
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
  DictionarySync({http.Client? client}) : client = client ?? http.Client();
  Timer? _timer;
  Box<String>? _cache;
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
  String? _activePair;
  final _forceFull = <String>{};

  Uri endpoint(String target, String native) {
    const base = String.fromEnvironment('DICTIONARY_URL');
    final uri = base.isNotEmpty
        ? Uri.parse(base)
        : kIsWeb
            ? Uri.base.resolve('/api/lexicon')
            : Uri.parse('http://127.0.0.1:8123/api/lexicon');
    return uri.replace(queryParameters: {'target': target, 'native': native});
  }

  /// Where 缺詞條 go (spec section 7): the same local server, which saves
  /// them in the admin's missing_lexeme / missing_localization requests.
  Uri get missingEndpoint =>
      endpoint('en', 'zh-TW').replace(path: '/api/missing', queryParameters: {});

  final _sentMissing = <String>{};

  /// Sends the words the pack lacked since the last call. Returns how many
  /// were sent; failures are retried on the next refresh.
  Future<int> sendMissing() async {
    final pending = {
      for (final e in LexiconPack.instance.requests.entries)
        if (!_sentMissing.contains(e.key)) e.key: e.value,
    };
    if (pending.isEmpty) return 0;
    final response = await client
        .post(missingEndpoint,
            headers: {'Content-Type': 'application/json'},
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
    _cache = await Hive.openBox<String>('dictionary_cache_v1');
    if (_disposed) return;
    settings.addListener(_kick);
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => refresh());
    await refresh();
  }

  void _kick() {
    unawaited(refresh());
  }

  void _succeeded() {
    lastSuccess = DateTime.now();
    status = '已連接詞庫 · 每 30 秒自動更新';
    hasError = false;
    BackgroundErrors.instance.clear(this);
  }

  Future<void> refresh() async {
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
        final saved = _cache?.get(pair);
        if (saved != null) {
          try {
            final candidate = LexiconPack()
              ..loadJson(jsonDecode(saved) as Map<String, dynamic>);
            if (candidate.target != target || candidate.native != native) {
              throw const FormatException('Wrong cached dictionary language');
            }
            LexiconPack.instance.replaceWith(candidate);
            repo.linkLexicon(LexiconPack.instance);
          } catch (_) {
            await _cache?.delete(pair);
            await LexiconPack.instance.load(target: target, native: native);
            if (current()) repo.linkLexicon(LexiconPack.instance);
          }
        } else {
          await LexiconPack.instance.load(target: target, native: native);
          if (current()) repo.linkLexicon(LexiconPack.instance);
        }
        _activePair = pair;
      }
      final cachedVersion = LexiconPack.instance.version;
      final saved = _cache?.get(pair);
      final canReuse = !_forceFull.contains(pair) && saved != null &&
          cachedVersion != null && LexiconPack.instance.target == target &&
          LexiconPack.instance.native == native;
      final uri = endpoint(target, native);
      final response = await client
          .get(uri.replace(queryParameters: {
            ...uri.queryParameters,
            if (canReuse) 'since': cachedVersion,
          }), headers: {
            if (canReuse)
              'If-None-Match': '"$cachedVersion"',
          })
          .timeout(const Duration(seconds: 60));
      if (!current()) return;
      if (response.statusCode == 304 && canReuse) {
        _succeeded();
        await _sendMissingQuietly();
        return;
      }
      if (response.statusCode != 200) {
        throw StateError('Dictionary unavailable');
      }
      var raw = utf8.decode(response.bodyBytes);
      var json = jsonDecode(raw) as Map<String, dynamic>;
      if (json.containsKey('delta_version')) {
        try {
          if (!canReuse) throw const FormatException('No base for delta');
          json = applyDictionaryDelta(
              jsonDecode(saved) as Map<String, dynamic>, json);
          raw = jsonEncode(json);
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
      if (LexiconPack.instance.version != candidate.version ||
          _cache?.get(pair) != raw) {
        LexiconPack.instance.replaceWith(candidate);
        repo.linkLexicon(LexiconPack.instance);
        await _cache?.put(pair, raw);
      }
      _forceFull.remove(pair);
      _succeeded();
      await _sendMissingQuietly();
    } catch (e) {
      debugPrint('DictionarySync: refresh failed: $e');
      if (current()) {
        status = '暫時無法連線 · 使用已儲存的詞庫，稍後自動重試';
        hasError = true;
        BackgroundErrors.instance.report(this, status, retry: refresh);
      }
    } finally {
      _running = false;
      if (!_disposed) notifyListeners();
      // A language switch during a request must not apply the old response.
      if (!_disposed && !current()) unawaited(refresh());
    }
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
