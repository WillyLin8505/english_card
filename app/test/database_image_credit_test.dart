import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import 'helpers.dart';

void loadImage(Map<String, dynamic> image) {
  LexiconPack.instance.loadJson({
    'catalog_version': 1,
    'target_language': 'en',
    'native_language': 'zh-TW',
    'lexemes': const [],
    'catalog_images': [image],
  });
}

Map<String, dynamic> creditImage({
  String source = 'wikimedia_commons',
  String? author = 'Ada Lovelace',
  String? license = 'CC BY-SA 4.0',
  String? attribution = 'Ada Lovelace, CC BY-SA 4.0, via Wikimedia Commons',
}) =>
    {
      'id': 9,
      'url': 'http://127.0.0.1/api/image?id=9',
      'source': source,
      if (author != null) 'author': author,
      if (license != null) 'license': license,
      if (attribution != null) 'attribution': attribution,
      'tags': const [],
    };

void main() {
  tearDown(() => LexiconPack.instance.clear());

  Future<void> open(WidgetTester tester) => pumpApp(tester,
      size: const Size(402, 1400),
      home: const DatabaseImageScreen(imageId: 9));

  testWidgets('credit stays inside collapsed 圖片資訊 until opened',
      (tester) async {
    loadImage(creditImage());
    await open(tester);
    expect(find.text('圖片標籤'), findsOneWidget);
    expect(find.text('圖片資訊'), findsOneWidget);
    expect(find.textContaining('維基共享資源'), findsNothing);
    expect(find.textContaining('Ada Lovelace'), findsNothing);
    expect(find.textContaining('CC BY-SA'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('image-info')));
    await tester.pumpAndSettle();
    expect(find.text('圖片來源：維基共享資源'), findsOneWidget);
    expect(find.text('作者：Ada Lovelace'), findsOneWidget);
    expect(find.text('授權：CC BY-SA 4.0'), findsOneWidget);
    expect(
        find.text('Ada Lovelace, CC BY-SA 4.0, via Wikimedia Commons'),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('internal source codes stay off the learner page',
      (tester) async {
    loadImage(creditImage(
        source: 'openverse',
        author: 'Sam',
        license: 'CC0',
        attribution: 'Sam / Openverse'));
    await open(tester);
    expect(find.text('圖片資訊'), findsOneWidget);
    expect(find.textContaining('openverse'), findsNothing);
    await tester.tap(find.text('圖片資訊'));
    await tester.pumpAndSettle();
    expect(find.textContaining('openverse'), findsNothing);
    expect(find.text('作者：Sam'), findsOneWidget);
    expect(find.text('授權：CC0'), findsOneWidget);
    expect(find.text('Sam / Openverse'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a source code alone does not add an image-info section',
      (tester) async {
    loadImage(creditImage(
        source: 'smithsonian', author: null, license: null, attribution: null));
    await open(tester);
    expect(find.text('圖片資訊'), findsNothing);
    expect(find.textContaining('smithsonian'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('numeric-only credit is omitted', (tester) async {
    loadImage(creditImage(
        source: 'open_images', author: '12', license: null, attribution: '#123'));
    await open(tester);
    expect(find.text('圖片資訊'), findsNothing);
    expect(find.textContaining('open_images'), findsNothing);
    expect(find.textContaining('#123'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
