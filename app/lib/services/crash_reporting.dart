import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

/// Crash and unhandled-exception reports sent to Sentry (卡 #913). Best
/// effort only: with no DSN compiled in, nothing is initialised and no
/// network or native code runs. While 設定 → 分享使用統計 is off, events that
/// do occur are dropped before sending (same consent as [Analytics]).
///
/// Build with the DSN:
/// `flutter build ipa --dart-define=SENTRY_DSN=https://xxx@oXXX.ingest.sentry.io/YYY`
/// Optional `--dart-define=SENTRY_ENVIRONMENT=testflight`.
/// The release (app version + build number) is read from the bundle by the
/// SDK. A report carries the stack trace, the exception type, OS and device
/// model, release and build number; it never carries photos, words, email,
/// user, request data, breadcrumbs or screenshots.
class CrashReporting {
  CrashReporting._();
  static final instance = CrashReporting._();

  static const dsn = String.fromEnvironment('SENTRY_DSN');
  static const environment = String.fromEnvironment('SENTRY_ENVIRONMENT',
      defaultValue: 'production');

  bool _sharing = false;
  bool _debugTreatAsEnabled = false;

  /// True only when a DSN was compiled in. Tests can pretend.
  bool get enabled => dsn.isNotEmpty || _debugTreatAsEnabled;

  /// Mirrors 設定 → 分享使用統計. Off until the learner turns it on.
  bool get sharing => _sharing;
  set sharing(bool value) => _sharing = value;

  @visibleForTesting
  set debugTreatAsEnabled(bool value) => _debugTreatAsEnabled = value;

  /// Runs [appRunner]. With a DSN it runs inside Sentry's error handlers;
  /// without one it just calls [appRunner] (no SDK touched).
  Future<void> run(FutureOr<void> Function() appRunner) async {
    if (dsn.isEmpty) return appRunner();
    await SentryFlutter.init(configure, appRunner: appRunner);
  }

  /// Applies the privacy settings to Sentry's options.
  @visibleForTesting
  void configure(SentryFlutterOptions options) {
    options
      ..dsn = dsn
      ..environment = environment
      ..sendDefaultPii = false
      ..maxBreadcrumbs = 0
      ..attachScreenshot = false
      ..attachViewHierarchy = false
      ..enableUserInteractionBreadcrumbs = false
      ..enableAutoNativeBreadcrumbs = false
      ..tracesSampleRate = null
      ..beforeSend = beforeSend;
  }

  /// Drops the event unless sharing is on; otherwise strips everything that
  /// could hold learner content.
  @visibleForTesting
  SentryEvent? beforeSend(SentryEvent event, Hint hint) {
    if (!_sharing) return null;
    return scrub(event);
  }

  /// Keeps type, stack and release; removes user, request, free text,
  /// breadcrumbs, extra data and contexts that could identify content.
  static SentryEvent scrub(SentryEvent event) {
    event
      ..user = null
      ..request = null
      ..breadcrumbs = const []
      ..extra = null
      ..message = null
      ..serverName = null
      ..tags = {
        for (final e in (event.tags ?? const <String, String>{}).entries)
          if (e.key.startsWith('app.') || e.key == 'handled') e.key: e.value,
      };
    // The message of an exception can quote a word or a file path.
    for (final x in event.exceptions ?? const <SentryException>[]) {
      x.value = null;
    }
    return event;
  }
}
