import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

void main() {
  testWidgets('an answered exercise shows correctness and both answers',
      (tester) async {
    final entry = WordEntry.fromUserInput(
      id: 'cup',
      word: 'cup',
      pos: 'noun',
      meaning: '杯子',
      level: 'A1',
      now: testNow,
    ).copyWith(examples: const [
      WordExample(text: 'This is a cup.', translation: '這是一個杯子。'),
    ]);
    final repo = WordDatabaseRepository(
      clock: () => testNow,
      entries: [entry],
      cards: [
        LearningCard(
          id: LearningCard.idFor(entry.id),
          wordEntryId: entry.id,
          templateId: 'test',
        ),
      ],
    );

    await pumpApp(tester, repository: repo, initialTab: AppTab.review);
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    expect(find.text('句子填空'), findsNothing);
    expect(find.text('送出答案'), findsNothing);
    expect(
        tester.widget<TextField>(find.byType(TextField)).decoration?.hintText,
        isNull);
    await tester.enterText(find.byType(TextField), 'mug');
    await tester.tap(find.byTooltip('送出答案'));
    await tester.pumpAndSettle();

    expect(find.text('答錯了'), findsOneWidget);
    // 問題回報 #606: both lines, compared letter by letter.
    expect(find.byType(AnswerComparison), findsOneWidget);
    final cmp = tester.widget<AnswerComparison>(find.byType(AnswerComparison));
    expect(cmp.submitted.toLowerCase(), 'mug');
    expect(cmp.answer.toLowerCase(), 'cup');
    expect(find.text('你的答案'), findsOneWidget);
    expect(find.text('正確答案'), findsOneWidget);
  });
}
