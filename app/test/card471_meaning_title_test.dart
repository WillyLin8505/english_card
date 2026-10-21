import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

// 問題回報 #469 (card #471): a word with one part of speech titled its
// meaning with the native language's name (「繁體中文」); it now uses the same
// 詞性與意思 title and POS chip as a word with several.
void main() {
  testWidgets('one part of speech: 詞性與意思 with the POS chip', (tester) async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final id = repo.addWord(word: 'nebula', pos: 'noun', meaning: '星雲').id;
    await pumpApp(tester,
        repository: repo, home: WordDetailScreen(wordEntryId: id));
    expect(find.text('詞性與意思'), findsOneWidget);
    expect(find.text('繁體中文'), findsNothing);
    // The chip sits beside the meaning, not also in the header.
    expect(find.text('名詞'), findsOneWidget);
    expect(find.text('星雲'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('no meaning yet: the header keeps the POS chip', (tester) async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final id = repo.addWord(word: 'nebula', pos: 'noun', meaning: '').id;
    await pumpApp(tester,
        repository: repo, home: WordDetailScreen(wordEntryId: id));
    expect(find.text('詞性與意思'), findsNothing);
    expect(find.text('名詞'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
