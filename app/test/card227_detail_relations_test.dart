import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

// Card #227 round 90: the detail page listed nightclub/clubhouse under both
// 近義詞 and 衍生詞 (the review back was fixed in issue #399).
Map<String, dynamic> relation(String kind, String word, String native) =>
    {'relation': kind, 'word': word, 'native': native, 'cefr': 'B1'};

Map<String, dynamic> dictionary(List<Map<String, dynamic>> relations) => {
      'target_language': 'en',
      'native_language': 'zh-TW',
      'created_at': '1',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'club',
          'normalized': 'club',
          'pos': 'noun',
          'status': 'full',
          'cefr': 'B1',
          'senses': [
            {'id': 1, 'definition': 'association', 'native': '俱樂部'}
          ],
          'relations': relations,
        }
      ],
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  tearDown(() => LexiconPack.instance.clear());

  Future<void> open(
      WidgetTester tester, List<Map<String, dynamic>> relations) async {
    LexiconPack.instance.loadJson(dictionary(relations));
    final repo = WordDatabaseRepository(clock: () => testNow);
    final id = repo.addWord(word: 'club', pos: 'noun', meaning: '').id;
    repo.linkLexicon(LexiconPack.instance);
    await pumpApp(tester,
        repository: repo, home: WordDetailScreen(wordEntryId: id));
  }

  testWidgets('a word in 近義詞 is not repeated under 衍生詞', (tester) async {
    await open(tester, [
      relation('synonyms', 'nightclub', '夜總會'),
      relation('derived_terms', 'nightclub', '夜總會'),
      relation('derived_terms', 'clubhouse', '俱樂部會所'),
    ]);
    expect(find.textContaining('nightclub'), findsOneWidget);
    expect(find.textContaining('clubhouse'), findsOneWidget);
    expect(find.text('衍生詞'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a section left empty by duplicates is hidden', (tester) async {
    await open(tester, [
      relation('synonyms', 'nightclub', '夜總會'),
      relation('derived_terms', 'nightclub', '夜總會'),
    ]);
    expect(find.textContaining('nightclub'), findsOneWidget);
    expect(find.text('衍生詞'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
