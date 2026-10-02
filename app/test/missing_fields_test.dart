import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/word_database_query.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

void main() {
  testWidgets('a word whose data failed names the missing fields (spec 7)', (tester) async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final e = repo.addWord(word: 'nebula', pos: 'noun', meaning: '', level: 'B1');
    repo.editEntry(e.copyWith(dataStatus: WordDataStatus.failed), {});
    expect(missingFieldNames(repo.entry(e.id)!), ['中文意思', '音標', '真人發音', '例句']);
    await pumpApp(tester, initialTab: AppTab.words, repository: repo, size: const Size(402, 1200));
    await tester.pumpAndSettle();
    expect(find.text('待補：中文意思、音標、真人發音、例句'), findsOneWidget);
  });
}
