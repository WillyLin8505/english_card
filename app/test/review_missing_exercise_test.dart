import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'helpers.dart';

WordEntry leakyApple() => WordEntry.fromUserInput(
            id: 'apple',
            word: 'apple',
            pos: 'noun',
            meaning: '蘋果',
            level: 'A1',
            now: testNow)
        .copyWith(examples: const [
      WordExample(text: 'An applecart holds apple.', translation: '蘋果車放蘋果。')
    ]);

WordDatabaseRepository singleWordRepo(WordEntry entry) =>
    WordDatabaseRepository(clock: () => testNow, entries: [
      entry
    ], cards: [
      LearningCard(
          id: LearningCard.idFor(entry.id),
          wordEntryId: entry.id,
          templateId: 'test')
    ]);

void main() {
  testWidgets(
      'a card with no safe interactive exercise falls back to the flip '
      'card instead of being skipped (問題回報 #207 decision A)', (tester) async {
    final repo = singleWordRepo(leakyApple());
    if (Platform.environment['SIM_SCREENSHOT'] != null) {
      await tester.runAsync(() async {
        final bytes = await File('C:/Windows/Fonts/msjh.ttc').readAsBytes();
        for (final family in ['Manrope', 'Inter']) {
          final loader = FontLoader(family)
            ..addFont(Future.value(ByteData.sublistView(bytes)));
          await loader.load();
        }
      });
    }
    await pumpApp(tester, repository: repo, initialTab: AppTab.review);
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    // The only example leaks the answer (applecart contains apple), so no
    // interactive exercise can be built. The card still shows, as the
    // traditional flip front, rather than being silently skipped.
    expect(find.byType(TextField), findsNothing);
    expect(find.text('蘋果'), findsOneWidget);
    expect(find.text('先在心裡想出這個字，再按「顯示答案」。'), findsOneWidget);
    await tester.tap(find.text('顯示答案'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('記得'));
    await tester.pumpAndSettle();
    expect(repo.logsOf(LearningCard.idFor('apple')), hasLength(1));
    // Review has no artificial end: after the due card is scheduled, it
    // remains available for another practice round until the learner leaves.
    expect(find.text('完成'), findsNothing);
    expect(find.text('顯示答案'), findsOneWidget);
  });

  test(
      'fixing the example upgrades the same card to a real cloze exercise '
      'on its next session', () {
    final before = FlashcardSession(singleWordRepo(leakyApple()));
    addTearDown(before.dispose);
    expect(before.exercise, isNull);
    expect(before.finished, isFalse);

    final repo = singleWordRepo(leakyApple());
    repo.applyWordData('apple',
        newExamples: const [
          WordExample(text: 'She eats an apple.', translation: '她吃蘋果。')
        ],
        status: WordDataStatus.complete);
    final after = FlashcardSession(repo);
    addTearDown(after.dispose);
    expect(after.exercise?.prompt, 'She eats an _ _ _ _ _.');
  });

  testWidgets('Again continues without inflating failure records',
      (tester) async {
    final repo = singleWordRepo(WordEntry.fromUserInput(
            id: 'cup',
            word: 'cup',
            pos: 'noun',
            meaning: '杯子',
            level: 'A1',
            now: testNow)
        .copyWith(examples: const [
      WordExample(text: 'This is a cup.', translation: '這是一個杯子。')
    ]));
    await pumpApp(tester, repository: repo, initialTab: AppTab.review);
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    for (var i = 0; i < 3; i++) {
      await tester.enterText(find.byType(TextField), 'wrong');
      await tester.tap(find.byTooltip('送出答案'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('忘記'));
      await tester.pumpAndSettle();
    }
    expect(find.text('自由加練，不更動下次複習時間'), findsNothing);
    expect(find.bySemanticsLabel('返回'), findsOneWidget);
    expect(find.textContaining('目前沒有其他需要複習'), findsNothing);
    expect(repo.logsOf(LearningCard.idFor('cup')), hasLength(1));
    expect(
        repo
            .logsOf(LearningCard.idFor('cup'))
            .every((log) => log.rating == Rating.again),
        isTrue);
    expect(repo.cardOf('cup')!.fsrs.reps, 1);
  });
}
