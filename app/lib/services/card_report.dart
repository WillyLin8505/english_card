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

  /// The 問題回報 status the server last reported (`open`, `in_progress`,
  /// `fixed`, …), null until the server has said (問題回報 #728).
  final String? status;

  const FeedbackRecord({
    required this.id,
    required this.title,
    required this.createdAt,
    this.queued = true,
    this.issueNo,
    this.screenshot,
    this.status,
  });

  /// Statuses that mean the report has been dealt with (問題回報 #728).
  static const doneStatuses = {
    'fixed',
    'done',
    'resolved',
    'closed',
    'wontfix',
    'rejected',
    'duplicate',
  };

  /// True once handled, false while being handled, null when unknown.
  bool? get handled => status == null
      ? null
      : doneStatuses.contains(status!.trim().toLowerCase());

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
      screenshot: screenshot,
      status: status);

  FeedbackRecord withStatus(String? s) => FeedbackRecord(
      id: id,
      title: title,
      createdAt: createdAt,
      queued: queued,
      issueNo: issueNo,
      screenshot: screenshot,
      status: s);

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'createdAt': createdAt.toIso8601String(),
        'queued': queued,
        if (issueNo != null) 'issueNo': issueNo,
        if (screenshot != null) 'screenshot': screenshot,
        if (status != null) 'status': status,
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
      status: json['status'] is String ? json['status'] as String : null,
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

  /// Deletes a sent record's 問題回報 on the server too (問題回報 #716:
  /// `DELETE /api/issues/{id}` with the same X-API-Key reports are sent
  /// with), then removes it here; a queued one is just not sent any more.
  /// Returns false, keeping the record, when the server didn't delete it —
  /// [localOnly] removes it from this phone anyway. A 404 counts as deleted
  /// (it is already gone there).
  Future<bool> delete(String id,
      {String apiKey = '', bool localOnly = false}) async {
    await _load();
    final record = _history.where((r) => r.id == id).firstOrNull;
    final no = record?.issueNo;
    final queued = _memory.any((e) => e.$1 == id);
    if (!localOnly && !queued && no != null) {
      if (!remote) return false;
      try {
        final response = await client
            .delete(endpoint.replace(path: '/api/issues/$no'), headers: {
          if (apiKey.trim().isNotEmpty) 'X-API-Key': apiKey.trim(),
        }).timeout(const Duration(seconds: 20));
        final ok = (response.statusCode >= 200 && response.statusCode < 300) ||
            response.statusCode == 404;
        if (!ok) return false;
      } catch (e) {
        debugPrint('CardReportService: delete failed: $e');
        return false;
      }
    }
    await _removeLocal(id);
    return true;
  }

  Future<void> _removeLocal(String id) async {
    final before = _memory.length;
    _memory.removeWhere((e) => e.$1 == id);
    _history.removeWhere((r) => r.id == id);
    if (_memory.length != before) await _save();
    await _saveHistory();
    notifyListeners();
  }

  /// Asks the server whether each sent 問題回報 is being handled or done
  /// (問題回報 #728): `GET /api/issues/status?ids=724,725` answering
  /// `[{"id": 724, "status": "fixed"}, …]` (or `{"items": [...]}`). Until
  /// the server offers it (or offline, or refused) nothing changes and the
  /// list keeps 已送出 · #number. Returns whether any status changed.
  Future<bool> refreshStatus({String apiKey = ''}) async {
    await _load();
    if (!remote) return false;
    final ids = {
      for (final r in _history)
        if (!r.queued && r.issueNo != null) r.issueNo!
    };
    if (ids.isEmpty) return false;
    final Object? json;
    try {
      final response = await client.get(
          endpoint.replace(
              path: '/api/issues/status',
              queryParameters: {'ids': ids.join(',')}),
          headers: {
            if (apiKey.trim().isNotEmpty) 'X-API-Key': apiKey.trim(),
          }).timeout(const Duration(seconds: 15));
      if (response.statusCode != 200) return false;
      json = _tryDecode(response.body);
    } catch (e) {
      debugPrint('CardReportService: status failed: $e');
      return false;
    }
    final items = json is Map ? json['items'] : json;
    if (items is! List) return false;
    final statuses = <int, String>{
      for (final item in items)
        if (item is Map && item['id'] is num && item['status'] is String)
          (item['id'] as num).toInt(): item['status'] as String
    };
    var changed = false;
    for (var i = 0; i < _history.length; i++) {
      final r = _history[i];
      final s = statuses[r.issueNo];
      if (r.queued || s == null || s == r.status) continue;
      _history[i] = r.withStatus(s);
      changed = true;
    }
    if (changed) {
      await _saveHistory();
      notifyListeners();
    }
    return changed;
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
