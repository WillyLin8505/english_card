// Replay live French catalog labels and the live deck list without calling AI.
// Camera hardware/new-photo recognition are explicitly outside this replay.
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/screens/deck_browser_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/deck_library.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import '../helpers.dart';
import 'learner_view_simulation.dart' show screenTexts;

void main() {
  testWidgets('French picture labels and deck browser', (tester) async {
    final env = Platform.environment;
    final pack = LexiconPack.instance
      ..loadJson(jsonDecode(File(env['SIM_PACK']!).readAsStringSync())
          as Map<String, dynamic>);
    final repo = WordDatabaseRepository(language: 'fr', clock: () => testNow);
    final settings =
        AppSettings.inMemory(learningLanguage: 'fr', nativeLanguage: 'en');
    final photos = pack.catalogImages
        .where((p) => databasePins(p, pack).isNotEmpty)
        .toList()
      ..shuffle(Random(int.parse(env['SIM_SEED'] ?? '1')));
    final screens = <Map<String, Object?>>[];
    final errors = <String>[];
    final original = FlutterError.onError;
    FlutterError.onError = (d) {
      // Card #496 round 7: keep the error-causing widget so a failure names
      // the screen (e.g. "Duplicate keys found. @ DatabaseImageScreen …").
      final lines = d.toString().split('\n');
      final at = lines.indexWhere((l) => l.contains('error-causing widget'));
      final where =
          at >= 0 && at + 1 < lines.length ? ' @ ${lines[at + 1].trim()}' : '';
      errors.add('${d.exceptionAsString().split('\n').first}$where');
      File('${env['SIM_OUT']!}.errors.txt')
          .writeAsStringSync('${d.toString()}\n\n', mode: FileMode.append);
    };
    addTearDown(() => FlutterError.onError = original);
    var checked = 0;
    final wrong = <String>[];
    // Every rendered pin must resolve to the French lexeme, not its English label.
    for (final photo in photos) {
      for (final pin in databasePins(photo, pack)) {
        checked++;
        if (pack.entriesFor(pin.word).isEmpty) {
          wrong.add('${photo['id']}: ${pin.word}');
        }
      }
    }
    for (final photo in photos.take(25)) {
      await tester.pumpWidget(const SizedBox());
      await pumpApp(tester,
          repository: repo,
          settings: settings,
          size: const Size(390, 844),
          home: DatabaseImageScreen(imageId: (photo['id'] as num).toInt()));
      await tester.pumpAndSettle();
      final texts = screenTexts(tester);
      final scroll = find.byType(Scrollable);
      if (scroll.evaluate().isNotEmpty) {
        await tester.drag(scroll.first, const Offset(0, -650));
        await tester.pumpAndSettle();
        texts.addAll(screenTexts(tester).where((t) => !texts.contains(t)));
      }
      screens.add({
        'image_id': photo['id'],
        'texts': texts,
        'pins': databasePins(photo, pack)
            .map((p) => {'word': p.word, 'meaning': p.zh})
            .toList()
      });
    }
    final requests = <String>[];
    final deckJson = jsonDecode(File(env['SIM_DECKS']!).readAsStringSync());
    final library = DeckLibrary(
        remote: true,
        persist: false,
        client: MockClient((r) async {
          requests.add(r.url.path + (r.url.hasQuery ? '?${r.url.query}' : ''));
          return jsonResponse(deckJson);
        }));
    await tester.pumpWidget(const SizedBox());
    await pumpApp(tester,
        repository: repo,
        settings: settings,
        size: const Size(390, 844),
        home: DeckBrowserScreen(library: library));
    await settle(tester);
    final deckTexts = <String>[];
    for (var i = 0; i < 8; i++) {
      for (final t in screenTexts(tester)) {
        if (!deckTexts.contains(t)) deckTexts.add(t);
      }
      final scroll = find.byType(Scrollable);
      if (scroll.evaluate().isEmpty) break;
      await tester.drag(scroll.first, const Offset(0, -600));
      await tester.pumpAndSettle();
    }
    File(env['SIM_OUT']!)
        .writeAsStringSync(const JsonEncoder.withIndent(' ').convert({
      'language': 'fr',
      'native': 'en',
      'photos_opened': screens.length,
      'catalog_photos_with_pins': photos.length,
      'pins_checked': checked,
      'wrong_language_pins': wrong,
      'photos': screens,
      'deck_requests': requests,
      'deck_texts': deckTexts,
      'deck_count': (deckJson['decks'] as List).length,
      'errors': errors,
      'limitations': [
        'Camera hardware, newly captured images and audio playback are not exercised.',
        'Network image bytes are not decoded in widget tests; image error text is not a live-server finding.',
        'Deck list replay only; do not install an unfiltered English deck into a French profile.'
      ],
    }));
    FlutterError.onError = original;
    expect(screens.length, 25);
    expect(checked, greaterThan(0));
    expect(wrong, isEmpty);
    expect(requests, isNotEmpty);
    expect(errors, isEmpty);
  }, timeout: const Timeout(Duration(minutes: 8)));
}
