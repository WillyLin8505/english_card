// 問題回報 #533 (複習開始畫面：時間估計算進忘記重來的卡、複習中上方細進度條)
// and #534 (複習結束畫面：「記得 N 張・再練 N 次」與這次忘記的字).

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

WordDatabaseRepository withWords(List<(String, String)> words) {
  final repo = WordDatabaseRepository(clock: () => testNow);
  for (final (w, zh) in words) {
    final word = repo.addWord(word: w, pos: 'n.', meaning: zh, level: 'A1');
    repo.applyWordData(word.id,
        newExamples: [
          WordExample(text: 'I ate a $w.', translation: '我吃了一個$zh。')
        ],
        status: WordDataStatus.complete);
  }
  return repo;
}

const fruit = [('banana', '香蕉'), ('cherry', '櫻桃'), ('grape', '葡萄')];

void main() {
  test('the estimate is a range that adds the expected returns', () {
    // 40 cards × 25 s = 16.7 min; with p = 0.3 a card comes back
    // 0.3 + 0.09 times → × 1.39 = 23.2 min.
    expect(reviewMinutes(40, secondsPerCard: 25, againRate: 0.3),
        (low: 17, high: 23));
    // Nobody forgets: one number.
    expect(reviewMinutes(40, secondsPerCard: 25, againRate: 0),
        (low: 17, high: 17));
    // Never below a minute.
    expect(reviewMinutes(1, secondsPerCard: 25, againRate: 0.3).low, 1);
  });

  test('the pace comes from the learner’s own grades once there are enough',
      () {
    final repo = withWords(fruit);
    expect(reviewPace(repo), (secondsPerCard: 25.0, againRate: 0.3));
    final card = repo.cardOf(repo.entries.first.id)!.id;
    for (var i = 0; i < 20; i++) {
      repo.review(card, i < 5 ? Rating.again : Rating.good,
          duration: const Duration(seconds: 40));
    }
    final pace = reviewPace(repo);
    expect(pace.againRate, 0.25);
    expect(pace.secondsPerCard, 40);
  });

  test('progress counts today’s cards and the forgotten ones that come back',
      () {
    final repo = withWords(fruit);
    final s = FlashcardSession(repo, continuous: true);
    expect((s.progressDone, s.progressTotal), (0, 3));
    final forgotten = s.card!.wordEntryId;
    s.showAnswer();
    s.rate(Rating.again);
    expect((s.progressDone, s.progressTotal), (1, 4));
    for (var i = 0; i < 20 && s.progressDone < s.progressTotal; i++) {
      s.showAnswer();
      s.rate(Rating.good);
    }
    expect((s.progressDone, s.progressTotal), (4, 4));
    final run = s.summary;
    expect(run.remembered, 2);
    expect(run.repractised, 1);
    expect(run.forgottenWordIds, [forgotten]);
    // Extra practice after today's share does not move the bar.
    s.showAnswer();
    s.rate(Rating.good);
    expect((s.progressDone, s.progressTotal), (4, 4));
    s.dispose();
  });

  testWidgets('the review grid and intro show the estimate as a range',
      (tester) async {
    final repo = withWords(fruit);
    await pumpApp(tester,
        initialTab: AppTab.review,
        repository: repo,
        size: const Size(375, 812));
    await tester.pumpAndSettle();
    // 3 cards × 25 s = 1.25 → 1; × 1.39 = 1.7 → 2.
    expect(find.text('約 1–2 分鐘'), findsWidgets);
    expect(tester.takeException(), isNull);
    expect(translateUi('今天 3 張，約 1–2 分鐘。做完還可以繼續練習，想休息時按左上角結束。', 'fr'),
        startsWith('3 cartes aujourd’hui, env. 1–2 min.'));
    expect(translateUi('約 19–27 分鐘', 'en'), 'About 19–27 min');
  });

  Future<void> grade(WidgetTester tester, LogicalKeyboardKey key) async {
    await tester.sendKeyEvent(LogicalKeyboardKey.space); // 顯示答案
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(key);
    await tester.pumpAndSettle();
  }

  for (final language in ['zh-TW', 'fr']) {
    testWidgets(
        'progress bar, then the end screen lists the forgotten word '
        '($language, 375 pt)', (tester) async {
      final repo = withWords(fruit);
      await pumpApp(tester,
          initialTab: AppTab.review,
          repository: repo,
          settings: AppSettings.inMemory(nativeLanguage: language),
          size: const Size(375, 812));
      await tester.pumpAndSettle();
      await tester.tap(find.text(language == 'fr' ? 'Tout' : '綜合'));
      await tester.pumpAndSettle();

      ReviewProgressBar bar() =>
          tester.widget<ReviewProgressBar>(find.byType(ReviewProgressBar));
      expect((bar().done, bar().total), (0, 3));
      final word =
          tester.widget<FlashcardFront>(find.byType(FlashcardFront)).entry;
      await grade(tester, LogicalKeyboardKey.digit1); // Again
      expect((bar().done, bar().total), (1, 4));
      for (var i = 0; i < 10 && bar().done < bar().total; i++) {
        await grade(tester, LogicalKeyboardKey.digit3); // Good
      }
      expect((bar().done, bar().total), (4, 4));
      expect(tester.takeException(), isNull);

      await tester
          .tap(find.bySemanticsLabel(language == 'fr' ? 'Retour' : '返回'));
      await tester.pumpAndSettle();
      expect(
          find.text(
              language == 'fr' ? 'Retenues : 2 · 1 reprises' : '記得 2 張・再練 1 次'),
          findsOneWidget);
      expect(find.text(language == 'fr' ? 'Oubliés cette fois' : '這次忘記的字'),
          findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.tap(find.byKey(ValueKey('forgotten:${word.id}')));
      await tester.pumpAndSettle();
      expect(find.byType(WordDetailScreen), findsOneWidget);
    });
  }
}
