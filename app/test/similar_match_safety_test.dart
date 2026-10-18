import 'dart:math';
import 'package:flutter/material.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'helpers.dart';

WordDatabaseRepository matchRepo(
    List<(String, String)> words, List<RelatedWord> relations) {
  final entries = [
    for (final (word, meaning) in words)
      WordEntry.fromUserInput(
          id: word,
          word: word,
          pos: 'adj',
          meaning: meaning,
          level: 'A1',
          now: testNow)
  ];
  entries[0] = entries[0].copyWith(related: relations);
  return WordDatabaseRepository(clock: () => testNow, entries: entries, cards: [
    LearningCard(
        id: LearningCard.idFor(entries[0].id),
        wordEntryId: entries[0].id,
        templateId: 'test')
  ]);
}

void main() {
  setUp(() {
    final previous = WidgetController.hitTestWarningShouldBeFatal;
    WidgetController.hitTestWarningShouldBeFatal = true;
    addTearDown(() => WidgetController.hitTestWarningShouldBeFatal = previous);
  });
  test(
      'overlapping native glosses cannot form a uniquely graded matching question',
      () {
    final repo = matchRepo([
      ('big', '大、大型'),
      ('large', '大'),
      ('small', '小')
    ], [
      const RelatedWord('large', RelationType.synonym),
      const RelatedWord('small', RelationType.associated)
    ]);
    final s = FlashcardSession(repo, random: Random(1));
    // No safe exercise falls back to the traditional flip card rather than
    // skipping the card (問題回報 #207 decision A).
    expect(s.finished, isFalse);
    expect(s.exercise, isNull);
    expect(repo.logsOf(repo.cardOf('big')!.id), isEmpty);
    expect(repo.cardOf('big')!.fsrs.reps, 0);
    s.dispose();
  });
  test('self relation cannot duplicate the target pair', () {
    final repo = matchRepo([
      ('big', '大'),
      ('small', '小')
    ], [
      const RelatedWord('big', RelationType.synonym),
      const RelatedWord('small', RelationType.associated)
    ]);
    final s = FlashcardSession(repo, random: Random(1));
    expect(s.finished, isFalse);
    expect(s.exercise, isNull);
    s.dispose();
  });
  test(
      'skip rare and overlapping meanings and retain three usable distinct pairs',
      () {
    final repo = matchRepo([
      ('big', '大、大型'),
      ('large', '大（尺寸）'),
      ('colossal', '巨大的'),
      ('small', '小'),
      ('tiny', '微小')
    ], [
      const RelatedWord('large', RelationType.synonym),
      const RelatedWord('colossal', RelationType.synonym, hideByDefault: true),
      const RelatedWord('small', RelationType.associated),
      const RelatedWord('tiny', RelationType.associated)
    ]);
    final s = FlashcardSession(repo, random: Random(1));
    expect(s.exercise!.type, ReviewExerciseType.similarMatch);
    expect(s.exercise!.pairs.map((p) => p.word), ['big', 'small', 'tiny']);
    s.completeInteraction(correct: false, attempts: 4);
    s.rate(Rating.good);
    final log = repo.logsOf(repo.cardOf('big')!.id).single;
    expect(log.correct, isFalse);
    expect(log.attempts, 4);
    expect(log.rating, Rating.good);
    expect(log.requestedRating, Rating.good);
    s.dispose();
  });
  for (final wrongFirst in [false, true]) {
    testWidgets('complete real matching UI after wrong attempt=$wrongFirst',
        (tester) async {
      final repo = matchRepo([
        ('hot', '熱'),
        ('cold', '冷'),
        ('warm', '溫暖')
      ], [
        const RelatedWord('cold', RelationType.associated),
        const RelatedWord('warm', RelationType.associated)
      ]);
      await pumpApp(tester, repository: repo, initialTab: AppTab.review);
      await tester.tap(find.text('開始複習'));
      await tester.pumpAndSettle();
      expect(find.text('相似詞配對'), findsNothing);
      if (wrongFirst) {
        await tester.tap(find.widgetWithText(ChoiceChip, '熱'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Cold'));
        await tester.pumpAndSettle();
        expect(find.text('這一組不相符，再試一次。'), findsOneWidget);
        expect(repo.logsOf(repo.cardOf('hot')!.id), isEmpty);
      }
      for (final (meaning, word) in [
        ('熱', 'Hot'),
        ('冷', 'Cold'),
        ('溫暖', 'Warm')
      ]) {
        await tester.tap(find.widgetWithText(ChoiceChip, meaning));
        await tester.pumpAndSettle();
        await tester.tap(find.text(word));
        await tester.pumpAndSettle();
      }
      expect(find.text(wrongFirst ? '答錯了' : '答對了'), findsOneWidget);
      await tester.tap(find.text('記得'));
      await tester.pumpAndSettle();
      final log = repo.logsOf(repo.cardOf('hot')!.id).single;
      expect(log.correct, !wrongFirst);
      expect(log.attempts, wrongFirst ? 4 : 3);
      expect(log.requestedRating, Rating.good);
      expect(log.rating, wrongFirst ? Rating.good : Rating.hard);
      expect(find.text('自由加練，不更動下次複習時間'), findsNothing);
    expect(find.bySemanticsLabel('返回'), findsOneWidget);
    });
  }
}
