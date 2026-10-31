import 'dart:convert';
import 'dart:math';

import 'package:http/http.dart' as http;

import 'app_settings.dart';
import 'cloud_backup.dart';

/// 匿名使用事件 (card #914): install, onboarded, first_photo, first_review and one
/// `open` per day, tied to a random install id. No account, no content. Switched off in
/// 設定 → 隱私 means nothing is stored or sent. Failures are ignored; unsent events
/// stay queued (max [maxQueue]) and go out with the next event or start.
class EventReport {
  static final instance = EventReport._();
  EventReport._();

  static const maxQueue = 40;
  static const batch = 20;

  AppSettings? _settings;
  http.Client? _client;
  String _baseUrl = CloudBackup.accountUrl;
  DateTime Function() _now = DateTime.now;
  bool _sending = false;

  /// Called once at start-up. [client]/[baseUrl]/[now] are for tests.
  void attach(AppSettings settings,
      {http.Client? client, String? baseUrl, DateTime Function()? now}) {
    _settings = settings;
    _client = client;
    _baseUrl = baseUrl ?? CloudBackup.accountUrl;
    _now = now ?? DateTime.now;
  }

  String _day() {
    final n = _now();
    String two(int v) => v.toString().padLeft(2, '0');
    return '${n.year}-${two(n.month)}-${two(n.day)}';
  }

  String installId(AppSettings s) {
    var id = s.usageValue('installId');
    if (id == null || id.length < 16) {
      final r = Random.secure();
      id = List.generate(32, (_) => r.nextInt(16).toRadixString(16)).join();
      s.setUsageValue('installId', id);
    }
    return id;
  }

  /// First start: `install`. Later starts: one `open` per local day.
  void appStarted() {
    final s = _settings;
    if (s == null) return;
    if (s.usageValue('evt_install') == null) once('install');
    final today = _day();
    if (s.usageValue('evt_open_day') != today) {
      if (s.anonymousEvents) s.setUsageValue('evt_open_day', today);
      _add('open');
    }
    flush();
  }

  /// A "first time" event (install, onboarded, first_photo, first_review): sent once per install.
  void once(String event) {
    final s = _settings;
    if (s == null || !s.anonymousEvents || s.usageValue('evt_$event') != null) {
      return;
    }
    s.setUsageValue('evt_$event', _day());
    _add(event);
    flush();
  }

  void _add(String event) {
    final s = _settings;
    if (s == null || !s.anonymousEvents) return;
    final q = _queue(s)..add({'event': event, 'day': _day()});
    while (q.length > maxQueue) {
      q.removeAt(0);
    }
    s.setUsageValue('evt_queue', jsonEncode(q));
  }

  List<Map<String, Object?>> _queue(AppSettings s) {
    try {
      return [
        for (final e in jsonDecode(s.usageValue('evt_queue') ?? '[]') as List)
          Map<String, Object?>.from(e as Map)
      ];
    } catch (_) {
      return [];
    }
  }

  /// Sends the queue. Returns whether the server took it (or nothing was due).
  Future<bool> flush() async {
    final s = _settings;
    if (s == null || !s.anonymousEvents || _sending || _baseUrl.trim().isEmpty) {
      return false;
    }
    final q = _queue(s);
    if (q.isEmpty) return true;
    _sending = true;
    try {
      final sent = q.take(batch).toList();
      final r = await (_client ??= http.Client())
          .post(Uri.parse(_baseUrl).resolve('/api/events'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'install_id': installId(s), 'events': sent}))
          .timeout(const Duration(seconds: 10));
      if (r.statusCode != 200) return false;
      final rest = _queue(s)..removeRange(0, min(sent.length, _queue(s).length));
      s.setUsageValue('evt_queue', jsonEncode(rest));
      return true;
    } catch (_) {
      return false;
    } finally {
      _sending = false;
    }
  }
}
