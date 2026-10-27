// 問題回報 #856: a fresh install fetches the pack (~62 MB) in its first
// minutes. Until it is in, the 資料庫 pages say it is downloading (with
// progress) instead of a count, 「沒有符合」 or an empty grid; a failed
// download shows the retry card; the pages fill in when the pack arrives.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/screens/word_deck_photos_screen.dart';
import 'package:photo_english_app/services/deck_library.dart';
import 'package:photo_english_app/services/dictionary_sync.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import 'helpers.dart';

Map<String, dynamic> pack() => {
      'schema_version': 3,
      'catalog_version': 1,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'ought',
          'normalized': 'ought',
          'pos': 'verb',
          'status': 'full',
          'senses': [
            {'id': 11, 'native': '應該', 'definition': 'should'}
          ]
        },
        {
          'id': 2,
          'lemma': 'peak',
          'normalized': 'peak',
          'pos': 'noun',
          'status': 'full',
          'senses': [
            {'id': 21, 'native': '山峰', 'definition': 'top'}
          ]
        },
      ],
      'catalog_images': [
        for (final (id, lex) in [(1, 1), (2, 2)])
          {
            'id': id,
            'url': 'assets/sample/photo_kitchen.jpg',
            'width': 100,
            'height': 100,
            'tags': [
              {'lexeme_id': lex, 'sense_id': 1, 'review_status': 'approved'}
            ],
            'labels': const [],
          },
      ],
    };

void main() {
  final sync = DictionarySync.instance;
  late (String, bool, bool, int, int?) saved;
  setUp(() {
    saved = (
      sync.status,
      sync.hasError,
      sync.downloading,
      sync.downloadedBytes,
      sync.downloadTotalBytes
    );
    LexiconPack.instance.clear();
    sync
      ..hasError = false
      ..downloading = true
      ..downloadedBytes = 12000000
      ..downloadTotalBytes = 62000000;
  });
  tearDown(() {
    sync
      ..status = saved.$1
      ..hasError = saved.$2
      ..downloading = saved.$3
      ..downloadedBytes = saved.$4
      ..downloadTotalBytes = saved.$5;
    LexiconPack.instance.clear();
  });

  Iterable<String> texts(WidgetTester tester) => tester
      .widgetList<Text>(find.byType(Text))
      .map((t) => t.data ?? t.textSpan?.toPlainText() ?? '');

  testWidgets('單字本 資料庫: downloading with progress, then the count',
      (tester) async {
    await pumpApp(tester, initialTab: AppTab.words, databaseLibrary: true);
    await tester.pump();
    expect(find.text('詞庫下載中（約 62 MB）'), findsOneWidget);
    expect(find.text('已下載 12 / 62 MB（19%）'), findsOneWidget);
    final progress = tester.widget<LinearProgressIndicator>(
        find.byKey(const ValueKey('lexicon-download-progress')));
    expect(progress.value, closeTo(12 / 62, 0.001));
    expect(texts(tester).where((t) => t.contains('null')), isEmpty);
    expect(find.textContaining('筆正式單字'), findsNothing);

    // Search says the pack is coming, not 「沒有符合」.
    await tester.enterText(find.byType(TextField), 'ought');
    await tester.pump();
    expect(find.text('詞庫還在下載，下載完成後就能搜尋'), findsOneWidget);
    expect(find.text('沒有符合的單字'), findsNothing);

    // Progress moves on its own.
    sync.downloadedBytes = 31000000;
    sync.notifyListeners();
    await tester.pump();
    expect(find.text('已下載 31 / 62 MB（50%）'), findsOneWidget);

    // The pack arrives: the same search finds the word, the count shows.
    sync.downloading = false;
    LexiconPack.instance.loadJson(pack());
    await tester.pumpAndSettle();
    expect(find.text('詞庫還在下載，下載完成後就能搜尋'), findsNothing);
    expect(find.text('ought'), findsNWidgets(2), reason: 'field + row');
    await tester.enterText(find.byType(TextField), '');
    await tester.pumpAndSettle();
    expect(find.text('2 筆正式單字 · 與資料庫同步'), findsOneWidget);
    expect(find.text('peak'), findsOneWidget);
  });

  testWidgets('相片冊 資料庫: placeholders while downloading, then pictures',
      (tester) async {
    await pumpApp(tester,
        initialTab: AppTab.album,
        databaseLibrary: true,
        size: const Size(402, 1200));
    await tester.pumpAndSettle();
    expect(find.text('詞庫下載中（約 62 MB）'), findsOneWidget);
    expect(find.text('已下載 12 / 62 MB（19%）'), findsOneWidget);
    expect(find.byKey(const ValueKey('lexicon-picture-placeholders')),
        findsOneWidget);
    expect(find.text('圖片會隨詞庫一起下載'), findsWidgets);
    expect(find.textContaining('共 0 張'), findsNothing);
    expect(find.text('沒有符合的圖片'), findsNothing);

    sync.downloading = false;
    LexiconPack.instance.loadJson(pack());
    await tester.pumpAndSettle();
    expect(find.text('圖片會隨詞庫一起下載'), findsNothing);
    expect(find.text('共 2 張圖片 · 每張都有單字標籤'), findsOneWidget);
    expect(find.byType(DatabaseImageTile), findsNWidgets(2));
  });

  testWidgets('a failed download shows the retry card', (tester) async {
    sync
      ..downloading = false
      ..hasError = true
      ..status = '暫時無法連線 · 使用已儲存的詞庫，稍後自動重試';
    await pumpApp(tester, initialTab: AppTab.words, databaseLibrary: true);
    await tester.pumpAndSettle();
    expect(find.text('重新連線'), findsOneWidget);
    expect(find.text(sync.status), findsOneWidget);
    expect(
        find.byKey(const ValueKey('lexicon-download-progress')), findsNothing);
    expect(find.textContaining('筆正式單字'), findsNothing);

    // A retry that succeeds replaces the card with the list.
    sync.hasError = false;
    LexiconPack.instance.loadJson(pack());
    await tester.pumpAndSettle();
    expect(find.text('重新連線'), findsNothing);
    expect(find.text('2 筆正式單字 · 與資料庫同步'), findsOneWidget);
  });

  testWidgets('a word set opened before the pack fills in when it arrives',
      (tester) async {
    final previous = DeckLibrary.instance;
    addTearDown(() => DeckLibrary.instance = previous);
    final lib = DeckLibrary(remote: false, persist: false);
    DeckLibrary.instance = lib;
    final app = await pumpApp(tester,
        initialTab: AppTab.album, size: const Size(402, 1400));
    await lib.install(
        const DeckContent(
            DeckInfo(slug: 'b1', kind: 'words', title: '單字集・B1', count: 2),
            words: [
              (word: 'ought', pos: 'verb', level: 'B1'),
              (word: 'peak', pos: 'noun', level: 'B1'),
            ]),
        repository: app.repository,
        intake:
            AppScope.of(tester.element(find.byType(Scaffold).first)).intake);
    await tester.pumpAndSettle();
    await tester.tap(find.text('單字集・B1'));
    await tester.pumpAndSettle();
    expect(find.byType(WordDeckPhotosScreen), findsOneWidget);
    expect(find.text('詞庫下載中（約 62 MB）'), findsOneWidget);
    expect(find.text('已下載 12 / 62 MB（19%）'), findsOneWidget);
    expect(find.text('圖片會隨詞庫一起下載'), findsWidgets);
    expect(find.textContaining('還沒有圖片'), findsNothing);

    sync.downloading = false;
    LexiconPack.instance.loadJson(pack());
    await tester.pumpAndSettle();
    expect(find.text('單字集 · 2 個單字 · 2 張詞庫圖片'), findsOneWidget);
    expect(find.byType(DatabaseImageTile), findsNWidgets(2));
  });

  test('download progress counts bytes and the strings translate', () async {
    final s = DictionarySync(remote: false);
    addTearDown(s.dispose);
    final out = await s
        .trackDownload(
            Stream.fromIterable(
                [List.filled(600000, 0), List.filled(600000, 0)]),
            2400000)
        .toList();
    expect(out, hasLength(2));
    expect(s.downloading, isTrue);
    expect(s.downloadedBytes, 1200000);
    expect(s.downloadTotalBytes, 2400000);

    expect(translateUi('已下載 12 / 62 MB（19%）', 'en'),
        '12 / 62 MB downloaded (19%)');
    expect(translateUi('已下載 12 MB', 'fr'), '12 Mo téléchargés');
    for (final zh in ['詞庫下載中（約 62 MB）', '詞庫還在下載，下載完成後就能搜尋', '圖片會隨詞庫一起下載']) {
      expect(translateUi(zh, 'en'), isNot(zh));
      expect(translateUi(zh, 'fr'), isNot(zh));
    }
  });
}
