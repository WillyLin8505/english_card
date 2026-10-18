import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/analytics.dart';
import 'package:photo_english_app/services/dictionary_sync.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';

/// Runs before every test file: tests never download fonts.
/// With SIM_EVENTS set (run_round.py), the app's analytics events are
/// written there as JSON lines, for upload to PostHog as simulated users.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  MFont.useGoogleFonts = false;
  // The app polls the public dictionary by default; tests must not.
  DictionarySync.defaultRemote = false;
  final path = Platform.environment['SIM_EVENTS'];
  if (path != null && path.isNotEmpty) {
    final events = <Map<String, Object?>>[];
    Analytics.instance.recorder = events.add;
    tearDownAll(() => File(path)
        .writeAsStringSync(events.map(jsonEncode).map((l) => '$l\n').join()));
  }
  await testMain();
}
