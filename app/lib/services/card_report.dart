import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;

import 'dictionary_sync.dart';

/// 問題回報 #316: the learner reports a card that looks wrong. The report
/// goes to the owner's 問題回報 page through the dictionary server's
/// /api/issues route, titled "[卡片回報] …" and reported by "App 使用者",
/// which dispatches a fix automatically.
class CardReport {
  /// Why the card is reported; [label] is what the learner picks.
  static const kinds = <(String, String)>[
    ('translation', '翻譯錯'),
    ('example', '例句不好'),
    ('image', '圖片不對'),
    ('audio', '發音'),
    ('layout', '版面'),
    ('other', '其他'),
  ];

  static const appVersion =
      String.fromEnvironment('APP_VERSION', defaultValue: '1.0.0+1');

  final String kind;
  final String note;
  final String word;
  final String pos;
  final String? meaning;
  final String? photoId;

  /// Which side/exercise the learner was looking at ("recall 正面" etc.).
  final String cardType;

  const CardReport({
    required this.kind,
    required this.note,
    required this.word,
    required this.pos,
    this.meaning,
    this.photoId,
    this.cardType = '',
  });

  String get kindLabel =>
      kinds.firstWhere((k) => k.$1 == kind, orElse: () => kinds.last).$2;

  Map<String, dynamic> toIssue() => {
        'kind': 'bug',
        'severity': 'medium',
        'area': 'app',
        'title': '[卡片回報] $word（$pos）$kindLabel',
        'detail': [
          '問題類型：$kindLabel',
          if (note.trim().isNotEmpty) '說明：${note.trim()}',
          '單字：$word',
          '詞性：$pos',
          if ((meaning ?? '').isNotEmpty) '義項：$meaning',
          if ((photoId ?? '').isNotEmpty) '照片 id：$photoId',
          if (cardType.isNotEmpty) '卡片題型：$cardType',
          'App 版本：$appVersion',
        ].join('\n'),
        'lemma': word,
        'reporter': 'App 使用者',
      };

  Map<String, dynamic> toJson() => toIssue();
}

/// Sends [CardReport]s; a report that cannot be sent (no key from the
/// internet, offline) is kept on the device and retried on the next send.
class CardReportService {
  static final instance = CardReportService();

  final http.Client client;
  final bool? _remoteOverride;
  Box<String>? _box;
  final _memory = <String>[];

  CardReportService({http.Client? client, bool? remote, bool? persist})
      : client = client ?? http.Client(),
        _remoteOverride = remote,
        _persistOverride = persist;

  /// Tests use [DictionarySync.defaultRemote] = false, so nothing here
  /// reaches the network either.
  bool get remote => _remoteOverride ?? DictionarySync.defaultRemote;

  @visibleForTesting
  int get pendingCount => _memory.length;

  Uri get endpoint => DictionarySync.instance
      .endpoint('en', 'zh-TW')
      .replace(path: '/api/issues', queryParameters: {});

  /// Tests have no Hive; with no server either, keep the queue in memory.
  bool get _persist => _persistOverride ?? remote;
  final bool? _persistOverride;

  Future<void> _load() async {
    if (_box != null || !_persist) return;
    try {
      _box = await Hive.openBox<String>('card_reports');
      _memory
        ..clear()
        ..addAll(_box!.values);
    } catch (_) {}
  }

  Future<void> _save() async {
    try {
      await _box?.clear();
      await _box?.addAll(_memory);
    } catch (_) {}
  }

  /// Queues [report] and tries to send everything queued. Returns true when
  /// the report reached the server, false when it stays queued on the device.
  Future<bool> submit(CardReport report, {String apiKey = ''}) async {
    await _load();
    _memory.add(jsonEncode(report.toJson()));
    await _save();
    return await flush(apiKey: apiKey) == 0;
  }

  /// Sends the queued reports in order; returns how many are still queued.
  Future<int> flush({String apiKey = ''}) async {
    await _load();
    if (!remote) return _memory.length;
    final headers = {
      'Content-Type': 'application/json',
      if (apiKey.trim().isNotEmpty) 'X-API-Key': apiKey.trim(),
    };
    while (_memory.isNotEmpty) {
      try {
        final response = await client
            .post(endpoint, headers: headers, body: _memory.first)
            .timeout(const Duration(seconds: 20));
        if (response.statusCode < 200 || response.statusCode >= 300) break;
      } catch (e) {
        debugPrint('CardReportService: send failed: $e');
        break;
      }
      _memory.removeAt(0);
      await _save();
    }
    return _memory.length;
  }
}
