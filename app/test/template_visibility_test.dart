import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/card_template.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';

import 'helpers.dart';

void main() {
  testWidgets('fields switched off in 卡片背面順序 leave the card back', (tester) async {
    final repo = testRepository();
    final t = repo.template;
    repo.updateTemplate(t.copyWith(backFields: [
      for (final f in t.backFields)
        f.field == CardBackField.pronunciation || f.field == CardBackField.example
            ? f.copyWith(visible: false)
            : f
    ]));
    await pumpApp(tester, initialTab: AppTab.review, repository: repo, size: const Size(402, 1400));
    await tester.tap(find.text('開始複習'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('顯示答案'));
    await tester.pumpAndSettle();
    final back = tester.widget<FlashcardBack>(find.byType(FlashcardBack));
    expect(back.entry.ipa, isNotNull);
    expect(find.text(back.entry.ipa!), findsNothing);
    expect(find.bySemanticsLabel('播放發音'), findsNothing);
    expect(find.byType(ExampleText), findsNothing);
  });
}
