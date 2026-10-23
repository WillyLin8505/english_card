// 問題回報 #641 (回到正面、上一張卡片) and #642 #643 (意思、例句列 1 2 3).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';

import 'helpers.dart';

String currentWord(WidgetTester tester) {
  final front = find.byType(FlashcardFront);
  if (front.evaluate().isNotEmpty) {
    return tester.widget<FlashcardFront>(front).entry.word;
  }
  return tester.widget<FlashcardBack>(find.byType(FlashcardBack)).entry.word;
}

void main() {
  test('meanings split into senses on ；', () {
    expect(FlashcardBack.meaningParts('國民、民族、人民；人們、人'), ['國民、民族、人民', '人們、人']);
    expect(FlashcardBack.meaningParts('蘋果'), ['蘋果']);
    expect(FlashcardBack.meaningParts(' a ; b；；c '), ['a', 'b', 'c']);
  });

  testWidgets('回到正面, 上一張卡片 and back to the current card', (tester) async {
    await pumpApp(tester,
        initialTab: AppTab.review, size: const Size(402, 1400));
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();

    final prev = find.byKey(const ValueKey('previous-card'));
    final front = find.byKey(const ValueKey('flip-to-front'));
    expect(tester.widget<NavIconButton>(prev).onTap, isNull,
        reason: 'nothing graded yet');
    expect(front, findsNothing, reason: 'already on the front');

    final first = currentWord(tester);
    await tester.tap(find.text('顯示答案'));
    await tester.pumpAndSettle();
    expect(find.byType(FlashcardBack), findsOneWidget);

    // 回到正面: the question again, same card.
    await tester.tap(front);
    await tester.pumpAndSettle();
    expect(find.byType(FlashcardFront), findsOneWidget);
    expect(currentWord(tester), first);

    await tester.tap(find.text('顯示答案'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('記得'));
    await tester.pumpAndSettle();
    final second = currentWord(tester);
    expect(tester.widget<NavIconButton>(prev).onTap, isNotNull);

    // 上一張卡片: the graded card's back, no rating buttons.
    await tester.tap(prev);
    await tester.pumpAndSettle();
    expect(currentWord(tester), first);
    expect(find.byType(FlashcardBack), findsOneWidget);
    expect(find.text('記得'), findsNothing);
    expect(find.text('這是上一張卡片，已經評分過'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('return-to-current')));
    await tester.pumpAndSettle();
    expect(currentWord(tester), second);

    // 問題回報 #652: 上一張 goes back more than one card.
    await tester.tap(find.text('顯示答案'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('記得'));
    await tester.pumpAndSettle();
    final third = currentWord(tester);
    await tester.tap(prev);
    await tester.pumpAndSettle();
    expect(currentWord(tester), second);
    await tester.tap(prev);
    await tester.pumpAndSettle();
    expect(currentWord(tester), first);
    expect(find.text('往前第 2 張，已經評分過'), findsOneWidget);
    expect(tester.widget<NavIconButton>(prev).onTap, isNull,
        reason: 'the first card of the run');
    await tester.tap(find.byKey(const ValueKey('return-to-current')));
    await tester.pumpAndSettle();
    expect(currentWord(tester), third);
    expect(find.byType(FlashcardFront), findsOneWidget);
  });

  testWidgets('examples on the back are numbered, three at first',
      (tester) async {
    await pumpApp(tester,
        initialTab: AppTab.review, size: const Size(402, 2400));
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    var checked = false;
    for (var i = 0; i < 12 && !checked; i++) {
      final fronts = find.byType(FlashcardFront);
      if (fronts.evaluate().isEmpty) break;
      // A photo exercise waits for its picture; the test has none to load.
      final session = tester.widget<FlashcardFront>(fronts).session;
      if (session != null && !session.canAnswer) {
        session.reportPhotoState(session.photoAttempt, true);
      }
      session?.showAnswer();
      await tester.pumpAndSettle();
      if (find
          .byKey(const ValueKey('numbered-example-1'))
          .evaluate()
          .isNotEmpty) {
        expect(find.byKey(const ValueKey('numbered-example-4')), findsNothing,
            reason: 'only three before 顯示更多');
        checked = true;
      }
      if (find.text('記得').evaluate().isEmpty) break;
      await tester.tap(find.text('記得'));
      await tester.pumpAndSettle();
    }
    expect(checked, isTrue, reason: 'a card with examples');
  });
}
