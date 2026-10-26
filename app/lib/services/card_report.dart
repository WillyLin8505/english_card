import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;

import 'dictionary_sync.dart';
import 'screen_capture.dart';

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

  /// The screen when the learner reported it (問題回報 #669: every report).
  final Uint8List? screenshot;

  const CardReport({
    required this.kind,
    required this.note,
    required this.word,
    required this.pos,
    this.meaning,
    this.photoId,
    this.cardType = '',
    this.screenshot,
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
          if (screenshot != null) '截圖：有（screenshot 欄位）',
        ].join('\n'),
        'lemma': word,
        'reporter': 'App 使用者',
        if (screenshot != null) 'screenshot': screenshotField(screenshot!),
      };

  Map<String, dynamic> toJson() => toIssue();
}

/// One report or 意見回饋 sent from this phone, for 設定 → 我的意見回饋
/// (問題回報 #701). [issueNo] is the 問題回報 number the server gave it;
/// a record that is still [queued] has none yet.
class FeedbackRecord {
  final String id;
  final String title;
  final DateTime createdAt;
  final bool queued;
  final int? issueNo;

  /// The screenshot as sent (`data:image/png;base64,…`), when there was one.
  final String? screenshot;

  const FeedbackRecord({
    required this.id,
    required this.title,
    required this.createdAt,
    this.queued = true,
    this.issueNo,
    this.screenshot,
  });

  Uint8List? get screenshotBytes {
    final s = screenshot;
    if (s == null) return null;
    final comma = s.indexOf(',');
    try {
      return base64Decode(comma < 0 ? s : s.substring(comma + 1));
    } catch (_) {
      return null;
    }
  }

  FeedbackRecord sent(int? no) => FeedbackRecord(
      id: id,
      title: title,
      createdAt: createdAt,
      queued: false,
      issueNo: no ?? issueNo,
      screenshot: screenshot);

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'createdAt': createdAt.toIso8601String(),
        'queued': queued,
        if (issueNo != null) 'issueNo': issueNo,
        if (screenshot != null) 'screenshot': screenshot,
      };

  static FeedbackRecord? fromJson(Object? json) {
    if (json is! Map) return null;
    final created = DateTime.tryParse('${json['createdAt']}');
    if (json['id'] is! String || created == null) return null;
    return FeedbackRecord(
      id: json['id'] as String,
      title: '${json['title'] ?? ''}',
      createdAt: created,
      queued: json['queued'] != false,
      issueNo: (json['issueNo'] as num?)?.toInt(),
      screenshot: json['screenshot'] as String?,
    );
  }
}

/// Sends [CardReport]s; a report that cannot be sent (no key from the
/// internet, offline) is kept on the device and retried on the next send.
/// Every report is also listed in [history] until the learner deletes it
/// (問題回報 #701).
class CardReportService extends ChangeNotifier {
  static final instance = CardReportService();

  /// The newest reports kept in [history]; older ones drop off.
  static const historyLimit = 100;

  final http.Client client;
  final bool? _remoteOverride;
  final DateTime Function() _now;
  Box<String>? _box;
  Box<String>? _historyBox;
  bool _loaded = false;

  /// Queued issues as (record id, issue JSON).
  final _memory = <(String, String)>[];
  final _history = <FeedbackRecord>[];
  int _seq = 0;

  CardReportService(
      {http.Client? client,
      bool? remote,
      bool? persist,
      DateTime Function()? now})
      : client = client ?? http.Client(),
        _remoteOverride = remote,
        _persistOverride = persist,
        _now = now ?? DateTime.now;

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

  String _newId() =>
      '${_now().microsecondsSinceEpoch.toRadixString(36)}-${_seq++}';

  Future<void> _load() async {
    if (_loaded) return;
    _loaded = true;
    if (!_persist) return;
    try {
      _box = await Hive.openBox<String>('card_reports');
      _historyBox = await Hive.openBox<String>('card_report_history');
      _memory.clear();
      final legacy = <FeedbackRecord>[];
      for (final v in _box!.values) {
        // Queued before #701: the bare issue, with no record id.
        final wrapped = _tryDecode(v);
        if (wrapped is Map &&
            wrapped['issue'] is Map &&
            wrapped['id'] is String) {
          _memory.add((wrapped['id'] as String, jsonEncode(wrapped['issue'])));
        } else {
          final id = _newId();
          _memory.add((id, v));
          legacy.add(FeedbackRecord(
              id: id,
              title: wrapped is Map ? '${wrapped['title'] ?? ''}' : '',
              createdAt: _now()));
        }
      }
      _history
        ..clear()
        ..addAll(_historyBox!.values
            .map((v) => FeedbackRecord.fromJson(_tryDecode(v)))
            .whereType<FeedbackRecord>())
        ..addAll(legacy);
      if (legacy.isNotEmpty) {
        await _save();
        await _saveHistory();
      }
    } catch (_) {}
  }

  static Object? _tryDecode(String v) {
    try {
      return jsonDecode(v);
    } catch (_) {
      return null;
    }
  }

  Future<void> _save() async {
    try {
      await _box?.clear();
      await _box?.addAll([
        for (final (id, issue) in _memory)
          jsonEncode({'id': id, 'issue': jsonDecode(issue)})
      ]);
    } catch (_) {}
  }

  Future<void> _saveHistory() async {
    try {
      await _historyBox?.clear();
      await _historyBox
          ?.addAll([for (final r in _history) jsonEncode(r.toJson())]);
    } catch (_) {}
  }

  /// What this phone has sent or still has queued, newest first.
  Future<List<FeedbackRecord>> history() async {
    await _load();
    final queued = {for (final (id, _) in _memory) id};
    return [
      for (final r in _history.reversed)
        r.queued && !queued.contains(r.id) ? r.sent(null) : r
    ];
  }

  /// Removes the record from this phone; a queued one is not sent any more.
  /// The 問題回報 on the server stays (deleting it there needs the admin
  /// API, 問題回報 #701).
  Future<void> delete(String id) async {
    await _load();
    final before = _memory.length;
    _memory.removeWhere((e) => e.$1 == id);
    _history.removeWhere((r) => r.id == id);
    if (_memory.length != before) await _save();
    await _saveHistory();
    notifyListeners();
  }

  /// Queues [report] and tries to send everything queued. Returns true when
  /// the report reached the server, false when it stays queued on the device.
  Future<bool> submit(CardReport report, {String apiKey = ''}) =>
      submitIssue(report.toJson(), apiKey: apiKey);

  /// Same queue for any issue the App may send (卡片回報, 意見回饋).
  Future<bool> submitIssue(Map<String, dynamic> issue,
      {String apiKey = ''}) async {
    await _load();
    final id = _newId();
    _memory.add((id, jsonEncode(issue)));
    _history.add(FeedbackRecord(
        id: id,
        title: '${issue['title'] ?? ''}',
        createdAt: _now(),
        screenshot: issue['screenshot'] as String?));
    while (_history.length > historyLimit) {
      _history.removeAt(0);
    }
    await _save();
    await _saveHistory();
    notifyListeners();
    final left = await flush(apiKey: apiKey);
    return left == 0 || !_memory.any((e) => e.$1 == id);
  }

  /// Sends the queued reports in order; returns how many are still queued.
  Future<int> flush({String apiKey = ''}) async {
    await _load();
    if (!remote) return _memory.length;
    final headers = {
      'Content-Type': 'application/json',
      if (apiKey.trim().isNotEmpty) 'X-API-Key': apiKey.trim(),
    };
    var changed = false;
    while (_memory.isNotEmpty) {
      final (id, body) = _memory.first;
      int? no;
      try {
        final response = await client
            .post(endpoint, headers: headers, body: body)
            .timeout(const Duration(seconds: 20));
        if (response.statusCode < 200 || response.statusCode >= 300) break;
        no = _issueNo(response.body);
      } catch (e) {
        debugPrint('CardReportService: send failed: $e');
        break;
      }
      _memory.removeAt(0);
      final i = _history.indexWhere((r) => r.id == id);
      if (i >= 0) _history[i] = _history[i].sent(no);
      changed = true;
      await _save();
    }
    if (changed) {
      await _saveHistory();
      notifyListeners();
    }
    return _memory.length;
  }

  /// The 問題回報 number in the server's reply (`{"id": 701, …}`).
  static int? _issueNo(String body) {
    final json = _tryDecode(body);
    return json is Map && json['id'] is num
        ? (json['id'] as num).toInt()
        : null;
  }
}
