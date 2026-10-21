// Card #227 round 109: a card saved as one part of speech but reviewed as
// another (sweep saved as the noun, tested as the verb) shows the tested
// part of speech's forms on the 複習 back, not 複數 sweeps under 動詞.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

Map<String, dynamic> _form(String field, String form, String label) =>
    {'field': field, 'form': form, 'normalized': form, 'label': label};

void main() {
  setUp(() {
    LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'sweep',
          'normalized': 'sweep',
          'pos': 'verb',
          'zipf': 4,
          'forms': [
            _form('verb_past', 'swept', '過去式'),
            _form('verb_present_participle', 'sweeping', '現在分詞'),
          ],
        },
        {
          'id': 2,
          'lemma': 'sweep',
          'normalized': 'sweep',
          'pos': 'noun',
          'zipf': 4,
          'forms': [_form('noun_plural', 'sweeps', '名詞複數')],
        },
      ],
    });
  });
  tearDown(() => LexiconPack.instance.clear());

  Future<void> pumpBack(WidgetTester tester, {String? activePos}) async {
    final entry = WordEntry(
      id: 'w-sweep',
      word: 'sweep',
      pos: 'noun',
      meaning: '掃',
      lexemeId: 2,
      forms: const [WordForm('sweeps', '複數')],
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
          activePos: activePos,
          card: const LearningCard(
              id: 'card', wordEntryId: 'w-sweep', templateId: 't'),
          photo: null,
          anchor: null,
          template: repo.template,
          learnerLevel: 'B1',
          onPlay: () {},
          onOpen: () {},
        ))));
    await tester.pumpAndSettle();
  }

  testWidgets('the tested verb usage shows the verb forms', (tester) async {
    await pumpBack(tester, activePos: 'verb');
    expect(find.text('swept'), findsOneWidget);
    expect(find.text('sweeps'), findsNothing);
  });

  testWidgets('without an active usage the saved noun still wins',
      (tester) async {
    await pumpBack(tester);
    expect(find.text('sweeps'), findsOneWidget);
    expect(find.text('swept'), findsNothing);
  });
}
