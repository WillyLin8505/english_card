import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'helpers.dart';

void main() {
  testWidgets('卡 #896: 複習卡用「已學會」圖示加文字，不再是紅色 ✕', (tester) async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final entry =
        repo.addWord(word: 'apple', pos: 'noun', meaning: '測試意思', level: 'A1');
    repo.applyWordData(entry.id,
        newExamples: [WordExample(text: 'This is an apple.', translation: '例句')],
        status: WordDataStatus.complete);
    await pumpApp(tester,
        repository: repo,
        initialTab: AppTab.review,
        size: const Size(375, 667));
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('mark-learned')), findsOneWidget);
    expect(find.text('已學會'), findsOneWidget);
    expect(find.byIcon(Icons.check_circle_outline), findsOneWidget);
    expect(find.byIcon(Icons.close), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
