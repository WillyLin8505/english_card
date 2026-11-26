import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/analytics.dart';
import 'package:photo_english_app/services/dictionary_sync.dart';
import 'package:photo_english_app/services/tagging_queue.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';

/// Runs before every test file: tests never download fonts.
/// With SIM_EVENTS set (run_round.py), the app's analytics events are
/// written there as JSON lines, for upload to PostHog as simulated users.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  MFont.useGoogleFonts = false;
  // The app polls the public dictionary by default; tests must not.
  DictionarySync.defaultRemote = false;
  // Owner 11/25: the background harder-words pass is tested on its own
  // (card_harder_levels_test.dart); other fake servers answer fixed requests.
  TaggingQueue.autoHarderLevels = false;
  final path = Platform.environment['SIM_EVENTS'];
  if (path != null && path.isNotEmpty) {
    final events = <Map<String, Object?>>[];
    Analytics.instance.recorder = events.add;
    tearDownAll(() => File(path)
        .writeAsStringSync(events.map(jsonEncode).map((l) => '$l\n').join()));
  }
  // The stock sample photos are no longer bundled (#1732); tests still show
  // them from test/fixtures/photos, served from disk.
  // Inside setUpAll: initialising the binding at load time would install the
  // test HttpOverrides outside a test zone.
  setUpAll(() {
    TestWidgetsFlutterBinding.ensureInitialized();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMessageHandler('flutter/assets', (message) async {
      final key = utf8.decode(message!.buffer
          .asUint8List(message.offsetInBytes, message.lengthInBytes));
      // Everything else is what `flutter test` built from pubspec.yaml.
      final f = key.startsWith('test/fixtures/photos/')
          ? File(key)
          : File('build/unit_test_assets/$key');
      return f.existsSync() ? ByteData.sublistView(f.readAsBytesSync()) : null;
    });
  });
  await testMain();
}
