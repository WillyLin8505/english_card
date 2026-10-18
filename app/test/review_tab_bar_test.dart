import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/widgets/mobile/tab_bar.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

void main() {
  testWidgets('the tab bar hides during a review run and comes back after (問題回報 #101)',
      (tester) async {
    final app = await pumpApp(tester, initialTab: AppTab.review,
        repository: WordDatabaseRepository(clock: () => testNow));
    final word = app.repository.addWord(
        word: 'banana', pos: 'n.', meaning: '香蕉', level: 'A1');
    app.repository.applyWordData(word.id,
        newExamples: const [
          WordExample(text: 'I ate a banana.', translation: '我吃了一根香蕉。')
        ],
        status: WordDataStatus.complete);
    await tester.pumpAndSettle();
    expect(find.byType(MobileTabBar), findsOneWidget);
    await tester.tap(find.text('開始複習'));
    await tester.pumpAndSettle();
    expect(find.byType(MobileTabBar), findsNothing);
    await tester.tap(find.bySemanticsLabel('返回'));
    await tester.pumpAndSettle();
    expect(find.byType(MobileTabBar), findsOneWidget);
    // Finishing due cards keeps reviewing until the learner exits.
    await tester.tap(find.text('開始複習'));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.space); // 顯示答案
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.digit4); // Easy
    await tester.pumpAndSettle();
    expect(find.text('自由加練，不更動下次複習時間'), findsNothing);
    expect(find.bySemanticsLabel('返回'), findsOneWidget);
    expect(find.byType(MobileTabBar), findsNothing);
    await tester.tap(find.bySemanticsLabel('返回'));
    await tester.pumpAndSettle();
    expect(find.byType(MobileTabBar), findsOneWidget);
  });
}
