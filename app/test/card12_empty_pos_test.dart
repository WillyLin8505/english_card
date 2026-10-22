import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

// 卡 #12 第 131 輪: a part of speech with no meaning yet (secret 動詞, imply 名詞)
// showed a bare POS chip in 詞性與意思; it is now left out, as in the database view.
void main() {
  testWidgets('a part of speech without meaning gets no chip', (tester) async {
    final entry = WordEntry(
        id: 'secret',
        word: 'secret',
        pos: 'adj',
        meaning: '秘密的',
        createdAt: testNow,
        updatedAt: testNow,
        usages: const [
          LexemeUsage(id: 'a', pos: 'adj', senses: [
            WordSense(id: 'a1', meaning: '秘密的'),
          ]),
          LexemeUsage(id: 'n', pos: 'noun', senses: [
            WordSense(id: 'n1', meaning: '秘密'),
          ]),
          LexemeUsage(id: 'v', pos: 'verb', rare: true, senses: [
            WordSense(id: 'v1', meaning: ''),
          ]),
        ]);
    final repo =
        WordDatabaseRepository(entries: [entry], clock: () => testNow);
    await pumpApp(tester,
        repository: repo, home: const WordDetailScreen(wordEntryId: 'secret'));
    expect(find.text('詞性與意思'), findsOneWidget);
    expect(find.text('形容詞'), findsOneWidget);
    expect(find.text('名詞'), findsOneWidget);
    expect(find.text('動詞'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
