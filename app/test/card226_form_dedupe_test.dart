// Card #226 round 105: the pack's Chinese form labels (名詞複數、形容詞比較級…)
// name the same kinds as its fields, so the 複習 back shows each form once.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/learning_content.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

Map<String, dynamic> _form(String field, String form, String label) =>
    {'field': field, 'form': form, 'normalized': form, 'label': label};

void main() {
  test('the pack\'s Chinese labels map to the short kinds', () {
    expect(formLabel('名詞複數'), '複數');
    expect(formLabel('形容詞比較級'), '比較級');
    expect(formLabel('形容詞最高級'), '最高級');
  });

  setUp(() {
    LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'happy',
          'normalized': 'happy',
          'pos': 'adj',
          'zipf': 5,
          'forms': [
            _form('adj_comparative', 'happier', '形容詞比較級'),
            _form('adj_superlative', 'happiest', '形容詞最高級'),
          ],
        },
      ],
    });
  });
  tearDown(() => LexiconPack.instance.clear());

  testWidgets('pack forms and the entry\'s own copies show once',
      (tester) async {
    final entry = WordEntry(
      id: 'w-happy',
      word: 'happy',
      pos: 'adj',
      meaning: '快樂的',
      lexemeId: 1,
      forms: const [
        WordForm('happier', '形容詞比較級'),
        WordForm('happiest', '形容詞最高級'),
      ],
      examples: const [
        WordExample(text: 'I am happy.', translation: '我很快樂。')
      ],
      createdAt: testNow,
      updatedAt: testNow,
    );
    final repo = WordDatabaseRepository(clock: () => testNow, entries: [entry]);
    await pumpApp(tester,
        repository: repo,
        size: const Size(402, 2000),
        home: Scaffold(
            body: SingleChildScrollView(
                child: FlashcardBack(
          entry: entry,
          card: const LearningCard(
              id: 'card', wordEntryId: 'w-happy', templateId: 't'),
          template: repo.template,
          learnerLevel: 'A2',
          onPlay: () {},
          onOpen: () {},
        ))));
    await tester.pumpAndSettle();
    expect(find.text('happier'), findsOneWidget);
    expect(find.text('happiest'), findsOneWidget);
    expect(find.text('形容詞比較級'), findsNothing);
  });
}
