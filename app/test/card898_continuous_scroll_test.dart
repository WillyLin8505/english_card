import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';

import 'helpers.dart';

void main() {
  testWidgets('單字本 loads more rows as it scrolls, no page buttons (card #898)',
      (tester) async {
    final app = await pumpApp(tester, initialTab: AppTab.words);
    for (var i = 0; i < 150; i++) {
      app.repository.addWord(word: 'zword${i.toString().padLeft(3, '0')}', pos: 'noun', meaning: '字');
    }
    await tester.pump();
    expect(find.text('›'), findsNothing);
    expect(find.textContaining('第 '), findsNothing);
    final list = find.byType(Scrollable).first;
    for (var i = 0; i < 40; i++) {
      await tester.drag(list, const Offset(0, -1500));
      await tester.pump();
      await tester.pump();
    }
    expect(find.textContaining('zword149', skipOffstage: false), findsOneWidget);
  });
}
