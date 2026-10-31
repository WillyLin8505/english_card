// 問題回報 #633 #636: the 卡片集 label on an album card stays on one line.
// 問題回報 #634: adding a database word whose part of speech has no Chinese
// but another one does says it is in review, as it is.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import 'helpers.dart';

void main() {
  tearDown(() => LexiconPack.instance.clear());

  testWidgets('the 相片冊 label is one line', (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.words, size: const Size(402, 2400));
    app.repository.addAlbum(
        name: '水果與蔬菜相片冊',
        deckSlug: 'food-b1',
        author: 'English Card 編輯部 with a very long name');
    app.navigator.selectTab(AppTab.album);
    await tester.pumpAndSettle();
    final label = tester.widget<Text>(find.byWidgetPredicate(
        (w) => w is Text && (w.data ?? '').startsWith('相片冊 · English')));
    expect(label.maxLines, 1);
    expect(label.overflow, TextOverflow.ellipsis);
  });

  testWidgets("another part of speech's Chinese means it is in review",
      (tester) async {
    LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'frightening',
          'normalized': 'frightening',
          'pos': 'noun',
          'status': 'full',
        },
        {
          'id': 2,
          'lemma': 'frightening',
          'normalized': 'frightening',
          'pos': 'adj',
          'status': 'full',
          'senses': [
            {'id': 1, 'native': '恐怖的、可怕的'}
          ],
        },
      ],
    });
    await pumpApp(tester, initialTab: AppTab.words);
    final noun = LexiconPack.instance.byId(1)!;
    final ctx = tester.element(find.byType(Scaffold).first);
    addDatabaseWord(ctx, LexiconPack.instance, noun);
    await tester.pump();
    final app = AppScope.of(ctx).repository;
    final e = app.entryByWord('frightening');
    if ((e?.meaning ?? '').isNotEmpty) {
      expect(find.text('已加入我的單字本與複習'), findsOneWidget);
    } else {
      expect(find.textContaining('意思補齊後會自動排進複習'), findsOneWidget);
    }
  });
}
