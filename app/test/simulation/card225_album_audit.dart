// Card 225: cross-level search hint (#302) plus a photo-to-word flow.
// Run manually: flutter test test/simulation/card225_album_audit.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import '../album_level_test.dart' show leveledCatalog, level;
import '../helpers.dart';

void main() {
  setUp(() => LexiconPack.instance.loadJson(leveledCatalog()));
  tearDown(() => LexiconPack.instance.clear());

  testWidgets('observe cross-level search then add a word from its photo',
      (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.album,
        databaseLibrary: true,
        size: const Size(360, 740));
    await tester.pumpAndSettle();
    await tester.tap(level('A1'));
    await tester.enterText(find.byType(TextField), 'cluster');
    await tester.pumpAndSettle();

    // Round 87 (#302 fixed by #307): a B1 hit at A1 is named on the tile and
    // in the detail, whose 「切到 B1」 reveals the word without leaving it.
    expect(find.byType(DatabaseImageTile), findsOneWidget);
    expect(find.text('入門（A1）：apple · 蘋果'), findsOneWidget);
    expect(find.text('搜尋的字 cluster 在 中階（B1）'), findsOneWidget);
    await tester.tap(find.byType(DatabaseImageTile));
    await tester.pumpAndSettle();
    expect(find.text('搜尋的字 cluster 在 中階（B1）'), findsOneWidget);
    expect(find.text('已確認'), findsNothing);
    expect(find.text('圖片與單字的配對待確認'), findsNothing);
    await tester.tap(find.text('切到 B1'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('cluster · 串'));
    await tester.tap(find.text('cluster · 串'));
    await tester.pumpAndSettle();
    expect(find.byType(DatabaseWordScreen), findsOneWidget);
    expect(app.repository.entryByWord('cluster'), isNull);
    await tester.ensureVisible(find.text('加入我的單字本與複習'));
    await tester.tap(find.text('加入我的單字本與複習'));
    await tester.pumpAndSettle();
    final entry = app.repository.entryByWord('cluster');
    expect(entry, isNotNull);
    expect(entry!.meaning, '串');
    expect(app.repository.isArchived(entry.id), isFalse);
    expect(find.text('已加入我的單字本與複習'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
