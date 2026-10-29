import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

void main() {
  testWidgets('first frame with 8,680 words stays fast (card #791)',
      (tester) async {
    final entries = [
      for (var i = 0; i < 8680; i++)
        WordEntry.fromUserInput(
            id: 'w$i',
            word: 'word$i',
            pos: 'noun',
            meaning: '意思$i',
            level: 'A2',
            now: testNow),
    ];
    final repo = WordDatabaseRepository(
        entries: entries, cards: const [], clock: () => testNow);
    final sw = Stopwatch()..start();
    await pumpApp(tester, repository: repo, initialTab: AppTab.camera);
    // ignore: avoid_print
    print('first pump: ${sw.elapsedMilliseconds} ms');
    expect(find.byType(Navigator), findsNWidgets(2),
        reason: 'only the first tab is built (plus the app root)');
    expect(sw.elapsedMilliseconds, lessThan(3000),
        reason: "loaded suites run in parallel; the Navigator count above is the real guard");
  });
}
