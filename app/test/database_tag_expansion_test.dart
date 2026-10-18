import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import 'helpers.dart';

Map<String, dynamic> imageTags({int id = 9, int count = 5}) => {
      'id': id,
      'url': 'http://127.0.0.1/api/image?id=$id',
      'tags': [
        for (final level in ['A1', 'B1'])
          for (var i = 1; i <= count; i++)
            {
              'lexeme_id': (level == 'A1' ? 0 : 10) + i,
              'cefr': level,
              'review_status': 'approved',
            },
      ],
    };

void main() {
  setUp(() => LexiconPack.instance.loadJson({
        'catalog_version': 1,
        'target_language': 'en',
        'native_language': 'zh-TW',
        'lexemes': [
          for (final level in ['A1', 'B1'])
            for (var i = 1; i <= 5; i++)
              {
                'id': (level == 'A1' ? 0 : 10) + i,
                'lemma': '$level-word$i',
                'normalized': '$level-word$i'.toLowerCase(),
                'pos': 'noun',
                'status': 'full',
                'senses': [
                  {'id': i, 'native': '意思$i'}
                ],
              },
        ],
        'catalog_images': [imageTags()],
      }));
  tearDown(() => LexiconPack.instance.clear());

  Future<void> pumpTags(WidgetTester tester,
          {int id = 9, int count = 5, String? level}) =>
      pumpApp(tester,
          size: const Size(402, 1200),
          home: Scaffold(
            body: SingleChildScrollView(
              child: DatabaseTagSections(
                image: imageTags(id: id, count: count),
                pack: LexiconPack.instance,
                level: level,
              ),
            ),
          ));

  testWidgets('each level starts with three and expands independently',
      (tester) async {
    await pumpTags(tester);
    for (final level in ['A1', 'B1']) {
      expect(find.text('$level-word3 · 意思3'), findsOneWidget);
      expect(find.text('$level-word4 · 意思4'), findsNothing);
    }
    await tester.tap(find.byKey(const ValueKey('toggle-A1')));
    await tester.pump();
    expect(find.text('A1-word5 · 意思5'), findsOneWidget);
    expect(find.text('B1-word4 · 意思4'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('toggle-A1')));
    await tester.pump();
    expect(find.text('A1-word4 · 意思4'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('zero through three tags need no expansion control',
      (tester) async {
    for (var count = 0; count <= 3; count++) {
      await pumpTags(tester, count: count);
      expect(find.byType(TextButton), findsNothing);
      if (count > 0) {
        expect(find.text('A1-word$count · 意思$count'), findsOneWidget);
      }
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('changing image or level does not inherit expanded state',
      (tester) async {
    await pumpTags(tester, level: 'A1');
    await tester.tap(find.byKey(const ValueKey('toggle-A1')));
    await tester.pump();
    await pumpTags(tester, level: 'B1');
    expect(find.text('B1-word4 · 意思4'), findsNothing);
    await pumpTags(tester, level: 'A1', id: 10);
    expect(find.text('A1-word4 · 意思4'), findsNothing);
  });

  testWidgets('expanded labels still open their word detail', (tester) async {
    await pumpTags(tester, level: 'A1');
    await tester.tap(find.byKey(const ValueKey('toggle-A1')));
    await tester.pump();
    await tester.tap(find.text('A1-word5 · 意思5'));
    await tester.pumpAndSettle();
    expect(find.byType(DatabaseWordScreen), findsOneWidget);
    expect(find.text('A1-word5'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('image detail uses collapsed level sections', (tester) async {
    await pumpApp(tester,
        size: const Size(402, 1400),
        home: const DatabaseImageScreen(imageId: 9, initialLevel: 'A1'));
    await tester.pumpAndSettle();
    expect(find.text('A1-word3 · 意思3'), findsOneWidget);
    expect(find.text('A1-word4 · 意思4'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('toggle-A1')));
    await tester.pump();
    expect(find.text('A1-word5 · 意思5'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('compact image tile keeps each level on its own line',
      (tester) async {
    await pumpApp(tester,
        home: Scaffold(
            body: SizedBox(
                width: 175,
                height: 280,
                child: DatabaseImageTile(image: imageTags(count: 2)))));
    await tester.pumpAndSettle();
    expect(find.textContaining('A1-word1'), findsOneWidget);
    expect(find.textContaining('B1-word1'), findsOneWidget);
    final joined = find.textContaining('A1-word1').evaluate().any((element) {
      final widget = element.widget;
      return widget is Text &&
          widget.data != null &&
          widget.data!.contains('B1');
    });
    expect(joined, isFalse);
    expect(tester.takeException(), isNull);
  });

  testWidgets('compact image tile expands without overflow or navigation',
      (tester) async {
    await pumpApp(tester,
        home: Scaffold(
            body: SizedBox(
                width: 175,
                height: 230,
                child: DatabaseImageTile(image: imageTags(), level: 'A1'))));
    await tester.pumpAndSettle();
    expect(find.textContaining('A1-word4'), findsNothing);
    final toggle = find.byKey(const ValueKey('toggle-A1'));
    await tester.ensureVisible(toggle);
    await tester.tap(toggle);
    await tester.pumpAndSettle();
    expect(find.textContaining('A1-word5'), findsOneWidget);
    expect(find.byType(DatabaseImageScreen), findsNothing);
    await tester.ensureVisible(toggle);
    await tester.tap(toggle);
    await tester.pump();
    expect(find.textContaining('A1-word4'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
