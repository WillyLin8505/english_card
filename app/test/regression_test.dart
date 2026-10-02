import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_enricher.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

import 'helpers.dart';

void main() {
  test('every asset the app loads is declared in pubspec.yaml', () {
    final pubspec = File('pubspec.yaml').readAsStringSync();
    for (final asset in ['assets/word_db.json', 'assets/cefr_en.json']) {
      expect(pubspec, contains('- $asset'),
          reason: '$asset must be bundled (web 404 otherwise)');
      expect(File(asset).existsSync(), isTrue);
    }
  });

  group('WordEnricher and existing words', () {
    testWidgets(
        'complete dictionary words never call the photo tagging model for enrichment',
        (tester) async {
      final repo = testRepository();
      var calls = 0;
      final intake = PhotoIntake(
        repository: () => repo,
        photoStore: PhotoStore.inMemory(),
        createTagger: (uri, key) => TaggingService(
          endpoint: uri,
          apiKey: key,
          client: MockClient((r) async {
            calls++;
            return jsonResponse({
              'examples': [
                {
                  'text': 'One more sentence with the word.',
                  'translation': '再一句。'
                },
              ],
            });
          }),
        ),
      );
      final enricher = WordEnricher(
        repository: () => repo,
        settings: AppSettings.inMemory(taggingUrl: 'http://x/tag', apiKey: 'k'),
        intake: intake,
        lexicon: testLexicon,
      );
      await tester.runAsync(enricher.process);
      final bread = repo.entryByWord('bread')!;
      expect(bread.examples, hasLength(1));
      expect(calls, 0);
      await tester.runAsync(enricher.process);
      expect(calls, 0);
    });

    testWidgets('without the AI service, complete words are left alone',
        (tester) async {
      final repo = testRepository();
      final enricher = WordEnricher(
        repository: () => repo,
        settings: AppSettings.inMemory(),
        intake: PhotoIntake(
            repository: () => repo, photoStore: PhotoStore.inMemory()),
        lexicon: testLexicon,
      );
      await tester.runAsync(enricher.process);
      expect(repo.entries.every((e) => e.dataStatus == WordDataStatus.complete),
          isTrue);
    });
  });

  testWidgets('labels stay inside the photo, apart, and off every object dot',
      (tester) async {
    final photo = Photo(
      id: 'p',
      title: 'p',
      takenAt: testNow,
      placeholderColors: const [0xFF000000, 0xFF333333],
      createdAt: testNow,
    );
    await tester.pumpWidget(MaterialApp(
      theme: MobileTheme.light(),
      home: Center(
        child: SizedBox(
          width: 300,
          height: 200,
          child: PinnedPhoto(photo: photo, pins: const [
            PinData(
                id: 'top',
                anchor: LabelPoint(0.5, 0.03),
                word: 'Plant',
                zh: '植物'),
            PinData(
                id: 'mid', anchor: LabelPoint(0.5, 0.6), word: 'Cup', zh: '杯子'),
            PinData(
                id: 'near',
                anchor: LabelPoint(0.53, 0.63),
                word: 'Saucer',
                zh: '碟子'),
            PinData(
                id: 'new',
                anchor: LabelPoint(0.45, 0.58),
                word: 'Spoon',
                zh: '',
                linked: false),
          ]),
        ),
      ),
    ));
    final photoBox = tester.getRect(find.byType(PinnedPhoto));
    final badges = [
      for (final w in ['Plant', 'Cup', 'Saucer', 'Spoon'])
        tester.getRect(
            find.ancestor(of: find.text(w), matching: find.byType(WordPin)))
    ];
    for (final b in badges) {
      expect(
          photoBox.contains(b.topLeft) &&
              photoBox.contains(b.bottomRight - const Offset(1, 1)),
          isTrue);
      for (final o in badges) {
        if (o != b) expect(b.overlaps(o), isFalse);
      }
      for (final a in const [
        Offset(0.5, 0.03),
        Offset(0.5, 0.6),
        Offset(0.53, 0.63),
        Offset(0.45, 0.58)
      ]) {
        final dot = photoBox.topLeft +
            Offset(a.dx * photoBox.width, a.dy * photoBox.height);
        expect(b.contains(dot), isFalse);
      }
    }
    expect(find.text('未收錄'), findsOneWidget,
        reason: 'a word the pack lacks says so');
  });
}
