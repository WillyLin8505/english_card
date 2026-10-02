import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/onboarding_screen.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'helpers.dart';

void main() {
  testWidgets('a complete beginner starts without the vocabulary exam',
      (tester) async {
    tester.view.physicalSize = const Size(360, 740);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    OnboardingResult? result;
    await tester.pumpWidget(MaterialApp(
        home: OnboardingScreen(
            lexicon: testLexicon(), onDone: (r) => result = r)));
    expect(find.text('英文（English）'), findsOneWidget);
    await tester.tap(find.text('下一步'));
    await tester.pumpAndSettle();
    expect(find.text('上一步'), findsOneWidget);
    await tester.tap(find.text('從未接觸'));
    await tester.pump();
    await tester.tap(find.text('從基礎開始'));
    expect(result!.level, 'A1');
    expect(result!.source, 'self');
    expect(find.text('jurisdiction'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'small screen photo word opens directly and exposes a management button',
      (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.album, size: const Size(360, 740));
    app.navigator.openPhoto('photo-breakfast');
    await tester.pumpAndSettle();
    final row = find.byKey(const ValueKey('word:apple'));
    await tester.ensureVisible(row);
    await tester.tap(row);
    await tester.pumpAndSettle();
    expect(find.text('單字詳情'), findsOneWidget);
    expect(find.text('查看單字'), findsNothing);
    expect(find.text('名詞'), findsOneWidget);
    expect(find.text('Pome'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('learning filter includes new cards and review answer is compact',
      (tester) async {
    final repo = testRepository();
    for (final entry in repo.entries.where((entry) => entry.word != 'apple')) {
      repo.archiveWord(entry.id);
    }
    await pumpApp(tester,
        initialTab: AppTab.words, repository: repo, size: const Size(360, 740));
    expect(find.text('缺漏欄位'), findsNothing);
    await tester.tap(find.text('還在學'));
    await tester.pumpAndSettle();
    expect(find.text('apple'), findsOneWidget);
    await tester.tap(find.text('開始複習'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('開始複習'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('顯示答案'));
    await tester.pumpAndSettle();
    expect(find.byType(FlashcardBack), findsOneWidget);
    // Owner decision 2026-09-30 (問題回報 #15): the back follows the spec —
    // 3–5 examples and every section with data, the longer ones collapsed.
    expect(find.byType(ExampleText).evaluate().length, inInclusiveRange(1, 5));
    expect(find.byIcon(Icons.expand_more), findsWidgets);
    expect(find.byIcon(Icons.expand_less), findsNothing,
        reason: 'long sections start collapsed');
    await tester.ensureVisible(find.byIcon(Icons.expand_more).first);
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.expand_more).first);
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.expand_less), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
