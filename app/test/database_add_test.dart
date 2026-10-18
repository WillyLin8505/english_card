import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import 'helpers.dart';

void main() {
  setUp(() => LexiconPack.instance.loadJson({
        'target_language': 'en',
        'native_language': 'zh-TW',
        'lexemes': [
          {'id': 7, 'lemma': 'banana', 'normalized': 'banana', 'pos': 'noun', 'status': 'full',
           'senses': [{'id': 70, 'definition': 'A fruit.', 'native': '香蕉'}]},
          {'id': 8, 'lemma': 'kettle', 'normalized': 'kettle', 'pos': 'noun', 'status': 'full',
           'senses': [{'id': 80, 'definition': 'A pot.', 'native': null}]},
          {'id': 9, 'lemma': 'pot', 'normalized': 'pot', 'pos': 'verb', 'status': 'full',
           'forms': [{'field': 'verb_past', 'form': 'potted', 'normalized': 'potted'}],
           'senses': [{'id': 90, 'definition': 'To plant in a pot.', 'native': '種植'}]},
          {'id': 10, 'lemma': 'potted', 'normalized': 'potted', 'pos': 'adj', 'status': 'full',
           'card': 'pot',
           'senses': [{'id': 100, 'definition': 'Grown in a pot.', 'native': '盆栽的'}]},
        ],
      }));
  tearDown(LexiconPack.instance.clear);

  Future<void> open(WidgetTester tester, int id) async {
    tester.state<NavigatorState>(find.byType(Navigator).last)
        .push(MaterialPageRoute(builder: (_) => DatabaseWordScreen(wordId: id)));
    await tester.pumpAndSettle();
  }

  testWidgets('a word without Chinese yet says it waits (問題回報 #100)', (tester) async {
    await pumpApp(tester);
    await open(tester, 8);
    await tester.ensureVisible(find.text('加入我的單字本與複習'));
    await tester.tap(find.text('加入我的單字本與複習'));
    await tester.pump();
    expect(find.text('已加入我的單字本；中文意思補齊後會自動排進複習'), findsOneWidget);
  });

  testWidgets('adding a word learned earlier puts it back into review (問題回報 #99)', (tester) async {
    final app = await pumpApp(tester);
    await open(tester, 7);
    await tester.ensureVisible(find.text('加入我的單字本與複習'));
    await tester.tap(find.text('加入我的單字本與複習'));
    await tester.pump();
    expect(find.text('已加入我的單字本與複習'), findsOneWidget);
    final e = app.repository.entryByWord('banana')!;
    app.repository.archiveWord(e.id);
    await tester.pump();
    await tester.ensureVisible(find.text('加入我的單字本與複習'));
    await tester.tap(find.text('加入我的單字本與複習'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('已從「已學會」放回複習'), findsOneWidget);
    expect(app.repository.isArchived(e.id), isFalse);
  });

  testWidgets(
      'adding a form that folds into an already-added word still says it was added',
      (tester) async {
    final app = await pumpApp(tester);
    await open(tester, 9);
    await tester.ensureVisible(find.text('加入我的單字本與複習'));
    await tester.tap(find.text('加入我的單字本與複習'));
    await tester.pump();
    expect(find.text('已加入我的單字本與複習'), findsOneWidget);
    tester.state<NavigatorState>(find.byType(Navigator).last).pop();
    await tester.pumpAndSettle();
    await open(tester, 10);
    await tester.ensureVisible(find.text('加入我的單字本與複習'));
    await tester.tap(find.text('加入我的單字本與複習'));
    await tester.pump();
    expect(find.text('已加入我的單字本與複習'), findsOneWidget);
    expect(app.repository.entryByWord('pot')?.meaning, isNotEmpty);
  });

  testWidgets('a message from the database page does not cover the grade buttons (問題回報 #97)',
      (tester) async {
    final app = await pumpApp(tester, initialTab: AppTab.review);
    app.repository.addWord(word: 'banana', pos: 'n.', meaning: '香蕉', level: 'A1');
    await tester.pumpAndSettle();
    tester.state<ScaffoldMessengerState>(find.byType(ScaffoldMessenger).first)
        .showSnackBar(const SnackBar(content: Text('已加入我的單字本與複習')));
    await tester.pump();
    expect(find.text('已加入我的單字本與複習'), findsOneWidget);
    await tester.tap(find.text('開始複習'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('已加入我的單字本與複習'), findsNothing);
  });
}
