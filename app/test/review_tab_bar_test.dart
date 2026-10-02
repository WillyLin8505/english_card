import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/widgets/mobile/tab_bar.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

void main() {
  testWidgets('the tab bar hides during a review run and comes back after (問題回報 #101)',
      (tester) async {
    final app = await pumpApp(tester, initialTab: AppTab.review,
        repository: WordDatabaseRepository(clock: () => testNow));
    app.repository.addWord(word: 'banana', pos: 'n.', meaning: '香蕉', level: 'A1');
    await tester.pumpAndSettle();
    expect(find.byType(MobileTabBar), findsOneWidget);
    await tester.tap(find.text('開始複習'));
    await tester.pumpAndSettle();
    expect(find.byType(MobileTabBar), findsNothing);
    await tester.tap(find.bySemanticsLabel('結束複習'));
    await tester.pumpAndSettle();
    expect(find.byType(MobileTabBar), findsOneWidget);
    // A run that finishes by itself brings it back too.
    await tester.tap(find.text('開始複習'));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.space); // 顯示答案
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.digit4); // Easy
    await tester.pumpAndSettle();
    expect(find.text('今天先到這裡'), findsOneWidget);
    expect(find.byType(MobileTabBar), findsOneWidget);
  });
}
