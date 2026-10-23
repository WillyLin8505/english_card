// 問題回報 #683: 複習 always lists the books; one with nothing to review says
// why instead of hiding every other book.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';

import 'helpers.dart';

void main() {
  testWidgets('the grid shows even when the last pick has nothing',
      (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.words, size: const Size(402, 1400));
    // Last pick: 弱項單字, which has no cards in the sample data.
    app.settings.reviewScope = 'weak';
    app.navigator.selectTab(AppTab.review);
    await tester.pumpAndSettle();
    expect(find.text('想複習哪一本？'), findsOneWidget);
    expect(find.text('等待詞庫補齊'), findsNothing);

    await tester.tap(find.text('弱項單字'));
    await tester.pump();
    expect(find.text('這一本現在沒有可以複習的卡'), findsOneWidget);
    // Still on the grid; another book starts.
    await tester.pumpAndSettle(const Duration(seconds: 5));
    expect(find.text('想複習哪一本？'), findsOneWidget);
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    expect(find.text('想複習哪一本？'), findsNothing);
  });
}
