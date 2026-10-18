import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;

/// Usage analytics sent to PostHog (使用者習慣). Best effort only: with no
/// key it does nothing, and a failed send never throws or blocks the UI.
///
/// Build with the key:
/// `flutter run --dart-define=POSTHOG_API_KEY=phc_xxx`
/// (optional `--dart-define=POSTHOG_HOST=https://eu.i.posthog.com`).
/// Event names follow the shared taxonomy so dashboards line up:
/// app_opened, $screen, onboarding_completed, photo_added, word_added,
/// card_reviewed, review_started, review_finished.
class Analytics {
  Analytics._();
  static final instance = Analytics._();

  static const apiKey = String.fromEnvironment('POSTHOG_API_KEY');
  static const host = String.fromEnvironment('POSTHOG_HOST',
      defaultValue: 'https://us.i.posthog.com');
  static const site = 'photo-english-app';

  /// Sends at most this many events per request; flushes on this period.
  static const _batchSize = 20;
  static const _flushEvery = Duration(seconds: 30);

  final _queue = <Map<String, Object?>>[];
  String _distinctId = 'anonymous';
  Timer? _timer;
  AppLifecycleListener? _lifecycle;
  http.Client? _client;
  bool _sending = false;

  bool get enabled => apiKey.isNotEmpty;

  /// Simulations (test/flutter_test_config.dart) collect events here
  /// instead of sending them; run_round.py uploads them marked simulated.
  void Function(Map<String, Object?> event)? recorder;

  /// Loads (or creates) this install's anonymous id. Safe to call without
  /// a key; then it only returns.
  Future<void> start() async {
    if (!enabled) return;
    try {
      final box = await Hive.openBox<String>('analytics');
      _distinctId = box.get('distinctId') ?? _newId();
      if (box.get('distinctId') == null) await box.put('distinctId', _distinctId);
    } catch (_) {
      _distinctId = _newId();
    }
    _client ??= http.Client();
    _timer ??= Timer.periodic(_flushEvery, (_) => unawaited(flush()));
    // Send what is queued when the app goes to the background.
    _lifecycle ??= AppLifecycleListener(onHide: () => unawaited(flush()));
    capture('app_opened');
  }

  /// Records [event], at [at] (the app's clock) or now. Never throws.
  void capture(String event,
      [Map<String, Object?> properties = const {}, DateTime? at]) {
    if (!enabled && recorder == null) return;
    try {
      final e = {
        'event': event,
        'distinct_id': _distinctId,
        'timestamp': (at ?? DateTime.now()).toUtc().toIso8601String(),
        'properties': {
          'site': site,
          'platform': kIsWeb ? 'web' : defaultTargetPlatform.name,
          r'$lib': 'photo-english-app-dart',
          ...properties,
        },
      };
      final rec = recorder;
      if (rec != null) return rec(e);
      _queue.add(e);
      if (_queue.length >= _batchSize) unawaited(flush());
    } catch (_) {}
  }

  /// A screen or tab became visible.
  void screen(String name, [Map<String, Object?> properties = const {}]) =>
      capture(r'$screen', {r'$screen_name': name, ...properties});

  /// Sends the queued events to PostHog's batch endpoint.
  Future<void> flush() async {
    if (!enabled || _sending || _queue.isEmpty) return;
    _sending = true;
    final batch = List.of(_queue.take(_batchSize));
    try {
      final r = await (_client ??= http.Client())
          .post(Uri.parse('$host/batch/'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'api_key': apiKey, 'batch': batch}))
          .timeout(const Duration(seconds: 10));
      // Drop on success or a client error (bad payload won't improve);
      // keep for the next try on a server or network error.
      if (r.statusCode < 500) _queue.removeRange(0, batch.length);
    } catch (_) {
      // Offline: keep, but never let the queue grow without bound.
      if (_queue.length > 500) _queue.removeRange(0, _queue.length - 500);
    } finally {
      _sending = false;
    }
  }

  static String _newId() {
    final r = Random.secure();
    return List.generate(16, (_) => r.nextInt(256).toRadixString(16).padLeft(2, '0'))
        .join();
  }
}
