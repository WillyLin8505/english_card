import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

/// 測驗結束畫面 (spec §7 deferred item, card #217): leaving a run after
/// grading shows how many cards were graded — and nothing else.
void main() {
  Future<void> pump(WidgetTester tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.review,
        repository: WordDatabaseRepository(clock: () => testNow));
    for (final (w, zh) in [('banana', '香蕉'), ('cherry', '櫻桃')]) {
      final word =
          app.repository.addWord(word: w, pos: 'n.', meaning: zh, level: 'A1');
      app.repository.applyWordData(word.id,
          newExamples: [
            WordExample(text: 'I ate a $w.', translation: '我吃了一個$zh。')
          ],
          status: WordDataStatus.complete);
    }
    await tester.pumpAndSettle();
  }

  testWidgets('leaving without grading goes straight back to the intro',
      (tester) async {
    await pump(tester);
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('返回'));
    await tester.pumpAndSettle();
    expect(find.text('綜合'), findsOneWidget);
    expect(find.textContaining('這次複習了'), findsNothing);
  });

  testWidgets('leaving after grading shows the count, then 完成 → intro',
      (tester) async {
    await pump(tester);
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    for (var i = 0; i < 2; i++) {
      await tester.sendKeyEvent(LogicalKeyboardKey.space); // 顯示答案
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.digit3); // Good
      await tester.pumpAndSettle();
    }
    await tester.tap(find.bySemanticsLabel('返回'));
    await tester.pumpAndSettle();

    expect(find.text('這次複習了 2 張卡'), findsOneWidget);
    expect(find.text('完成'), findsOneWidget);
    // Nothing that nags: no due count, streak or score wording.
    expect(find.textContaining('到期'), findsNothing);
    expect(find.textContaining('連續'), findsNothing);
    expect(find.text('綜合'), findsNothing);

    await tester.tap(find.text('完成'));
    await tester.pumpAndSettle();
    expect(find.text('綜合'), findsOneWidget);
    expect(find.textContaining('這次複習了'), findsNothing);
  });
}
