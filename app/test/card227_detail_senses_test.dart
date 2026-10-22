import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

// Card #227 round 124: a word with one part of speech showed only its main
// meaning (pupil 「學生」, never 「瞳孔」), and slang/obsolete senses took the
// visible top three of a part of speech (bank 動詞「藏在直腸內」).
Map<String, dynamic> sense(int id, String native, [List<String>? labels]) =>
    {'id': id, 'definition': 'd$id', 'native': native, 'labels': labels ?? []};

Map<String, dynamic> lexeme(int id, String lemma, String pos,
        List<Map<String, dynamic>> senses) =>
    {
      'id': id,
      'lemma': lemma,
      'normalized': lemma,
      'pos': pos,
      'status': 'full',
      'cefr': 'B1',
      'senses': senses,
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  tearDown(() => LexiconPack.instance.clear());

  Future<void> open(WidgetTester tester, String word, String pos,
      List<Map<String, dynamic>> lexemes) async {
    LexiconPack.instance.loadJson({
      'target_language': 'en',
      'native_language': 'zh-TW',
      'created_at': '1',
      'lexemes': lexemes,
    });
    final repo = WordDatabaseRepository(clock: () => testNow);
    final id = repo.addWord(word: word, pos: pos, meaning: '').id;
    repo.linkLexicon(LexiconPack.instance);
    await pumpApp(tester,
        repository: repo, home: WordDetailScreen(wordEntryId: id));
  }

  testWidgets('one part of speech also lists its other senses',
      (tester) async {
    await open(tester, 'pupil', 'noun', [
      lexeme(1, 'pupil', 'noun', [
        sense(1, '學生'),
        sense(2, '瞳孔', ['etymology-2', 'low_priority']),
        sense(3, '學生', ['low_priority']),
        sense(4, '國定孤兒', ['obsolete', 'low_priority']),
      ]),
    ]);
    expect(find.text('學生'), findsOneWidget);
    expect(find.text('瞳孔'), findsOneWidget);
    // The repeat of the main meaning is not listed again; the obsolete one
    // is there, after the rest.
    expect(find.text('國定孤兒'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('slang senses go after common ones, behind 顯示更多',
      (tester) async {
    await open(tester, 'bank', 'noun', [
      lexeme(1, 'bank', 'noun', [sense(1, '銀行')]),
      lexeme(2, 'bank', 'verb', [
        sense(10, '存入銀行'),
        sense(11, '提供銀行服務'),
        sense(12, '藏在直腸內', ['slang', 'low_priority']),
        sense(13, '傾斜轉彎', ['etymology-2', 'low_priority']),
      ]),
    ]);
    expect(find.text('傾斜轉彎'), findsOneWidget);
    expect(find.text('藏在直腸內'), findsNothing);
    expect(find.text('顯示更多（1）'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
