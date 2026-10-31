import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'helpers.dart';

WordDatabaseRepository smallRepo(int count) {
  final repo = WordDatabaseRepository(clock: () => testNow);
  for (final word in ['apple', 'cup', 'book'].take(count)) {
    final entry = repo.addWord(
        word: word, pos: 'noun', meaning: '測試意思', level: 'A1');
    repo.applyWordData(entry.id,
        newExamples: [
          WordExample(
              text: 'This is a $word.', translation: '這是一個測試例句。')
        ],
        status: WordDataStatus.complete);
  }
  return repo;
}

void main() {
  test('archiving the current card advances without writing a review', () {
    final repo = smallRepo(2), s = FlashcardSession(repo, random: Random(1));
    addTearDown(s.dispose);
    final old = s.card!;
    s.showAnswer();
    repo.archiveWord(old.wordEntryId);
    expect(s.card!.id, isNot(old.id));
    expect(s.showingBack, false);
    expect(repo.logsOf(old.id), isEmpty);
    expect(s.reviewed, 0);
  });

  test('archived Again card is removed even when it is the last queued card',
      () {
    final repo = smallRepo(2), s = FlashcardSession(repo, random: Random(1));
    addTearDown(s.dispose);
    final again = s.card!;
    s.showAnswer();
    s.rate(Rating.again);
    repo.archiveWord(again.wordEntryId);
    s.showAnswer();
    s.rate(Rating.good);
    expect(s.finished, true);
    expect(repo.logsOf(again.id), hasLength(1));
    repo.restoreWord(repo.entry(again.wordEntryId)!.word);
    expect(repo.card(again.id)!.fsrs.reps, 1);
  });

  test('archiving the only card finishes and disposed session removes listener',
      () {
    final repo = smallRepo(1), s = FlashcardSession(repo);
    repo.archiveWord(s.card!.wordEntryId);
    expect(s.finished, true);
    s.dispose();
    repo.restoreWord('apple');
    expect(repo.cardOf(repo.entryByWord('apple')!.id)!.archived, false);
  });

  testWidgets('delete button advances without grading the removed card',
      (tester) async {
    final repo = smallRepo(2);
    await pumpApp(tester,
        repository: repo,
        initialTab: AppTab.review,
        size: const Size(402, 1400));
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    final first =
        tester.widget<FlashcardFront>(find.byType(FlashcardFront)).entry;
    final card = repo.cardOf(first.id)!;
    expect(find.bySemanticsLabel('標為已學會'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('標為已學會'));
    await tester.pumpAndSettle();
    // 問題回報 #262: 一顆確認對話框先擋下誤觸.
    expect(find.text('移除'), findsOneWidget);
    expect(repo.card(card.id)!.archived, false);
    await tester.tap(find.text('移除'));
    await tester.pumpAndSettle();
    expect(find.byType(FlashcardFront), findsOneWidget);
    expect(tester.widget<FlashcardFront>(find.byType(FlashcardFront)).entry.id,
        isNot(first.id));
    expect(repo.logsOf(card.id), isEmpty);
    expect(repo.card(card.id)!.archived, true);
    expect(repo.entry(first.id), isNotNull,
        reason: 'only the review card is removed; dictionary data stays');
    // 問題回報 #262: 封存後給 SnackBar + 復原 action 當立即回饋.
    expect(find.text('復原'), findsOneWidget);
    await tester.tap(find.text('復原'));
    await tester.pumpAndSettle();
    expect(repo.card(card.id)!.archived, false);
  });

  testWidgets('delete button cancel keeps the card in review', (tester) async {
    final repo = smallRepo(2);
    await pumpApp(tester,
        repository: repo,
        initialTab: AppTab.review,
        size: const Size(402, 1400));
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    final first =
        tester.widget<FlashcardFront>(find.byType(FlashcardFront)).entry;
    final card = repo.cardOf(first.id)!;
    await tester.tap(find.bySemanticsLabel('標為已學會'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('取消'));
    await tester.pumpAndSettle();
    expect(repo.card(card.id)!.archived, false);
    expect(tester.widget<FlashcardFront>(find.byType(FlashcardFront)).entry.id,
        first.id);
  });
}
