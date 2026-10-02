import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;

import 'app_settings.dart';
import 'lexicon_pack.dart';
import 'word_database_repository.dart';

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
  String? _activePair;

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
    } catch (_) {
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
          final candidate = LexiconPack()
            ..loadJson(jsonDecode(saved) as Map<String, dynamic>);
          if (candidate.target == target && candidate.native == native) {
            LexiconPack.instance
                .loadJson(jsonDecode(saved) as Map<String, dynamic>);
            repo.linkLexicon(LexiconPack.instance);
          }
        } else {
          await LexiconPack.instance.load(target: target, native: native);
          if (current()) repo.linkLexicon(LexiconPack.instance);
        }
        _activePair = pair;
      }
      final cachedVersion = LexiconPack.instance.version;
      final response = await client
          .get(endpoint(target, native), headers: {
            if (cachedVersion != null && _cache?.get(pair) != null)
              'If-None-Match': '"$cachedVersion"',
          })
          .timeout(const Duration(seconds: 60));
      if (!current()) return;
      if (response.statusCode == 304 && _cache?.get(pair) != null) {
        lastSuccess = DateTime.now();
        status = '已連接詞庫 · 每 30 秒自動更新';
        await _sendMissingQuietly();
        return;
      }
      if (response.statusCode != 200) {
        throw StateError('Dictionary unavailable');
      }
      final raw = utf8.decode(response.bodyBytes);
      final json = jsonDecode(raw) as Map<String, dynamic>;
      // Parse fully before replacing the last good pack/cache.
      final candidate = LexiconPack()..loadJson(json);
      if (candidate.target != target ||
          candidate.native != native ||
          json['lexemes'] is! List) {
        throw const FormatException('Wrong dictionary language');
      }
      if (LexiconPack.instance.version != candidate.version ||
          _cache?.get(pair) != raw) {
        LexiconPack.instance.loadJson(json);
        repo.linkLexicon(LexiconPack.instance);
        await _cache?.put(pair, raw);
      }
      lastSuccess = DateTime.now();
      status = '已連接詞庫 · 每 30 秒自動更新';
      await _sendMissingQuietly();
    } catch (_) {
      if (current()) status = '暫時無法連線 · 使用已儲存的詞庫，稍後自動重試';
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
    super.dispose();
  }
}
