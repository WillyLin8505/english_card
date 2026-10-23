// 問題回報 #619: a verb lists every tense (現在式、過去式、未來式、分詞);
// a form that does not belong to the part of speech is not shown.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

Map<String, dynamic> _form(String field, String form) =>
    {'field': field, 'form': form, 'normalized': form, 'label': field};

void main() {
  setUp(() => LexiconPack.instance.loadJson({
        'schema_version': 3,
        'target_language': 'en',
        'native_language': 'zh-TW',
        'lexemes': [
          {
            'id': 1,
            'lemma': 'decide',
            'normalized': 'decide',
            'pos': 'verb',
            'forms': [
              _form('verb_third_person', 'decides'),
              _form('verb_past', 'decided'),
              _form('verb_past_participle', 'decided'),
              _form('verb_present_participle', 'deciding'),
            ],
          },
          {
            // Bad data: an adjective carrying verb forms (happy, M87).
            'id': 2, 'lemma': 'happy', 'normalized': 'happy', 'pos': 'adj',
            'forms': [
              _form('adj_comparative', 'happier'),
              _form('adj_superlative', 'happiest'),
              _form('verb_past', 'happied'),
              _form('verb_present_participle', 'happying'),
              _form('verb_third_person', 'happies'),
            ],
          },
        ],
      }));
  tearDown(() => LexiconPack.instance.clear());

  Future<void> pumpBack(
      WidgetTester tester, String word, String pos, int id) async {
    final entry = WordEntry(
        id: 'w-$word',
        word: word,
        pos: pos,
        meaning: '意思',
        lexemeId: id,
        createdAt: testNow,
        updatedAt: testNow);
    final repo = WordDatabaseRepository(clock: () => testNow, entries: [entry]);
    await pumpApp(tester,
        repository: repo,
        size: const Size(402, 2400),
        home: Scaffold(
            body: SingleChildScrollView(
                child: FlashcardBack(
          entry: entry,
          card: LearningCard(id: 'c', wordEntryId: entry.id, templateId: 't'),
          photo: null,
          anchor: null,
          template: repo.template,
          learnerLevel: 'A2',
          onPlay: () {},
          onOpen: () {},
        ))));
    await tester.pumpAndSettle();
  }

  testWidgets('a verb shows 現在式 and 未來式 with the other tenses', (tester) async {
    await pumpBack(tester, 'decide', 'verb', 1);
    for (final kind in ['現在式', '第三人稱單數', '過去式', '未來式', '現在分詞', '過去分詞']) {
      expect(find.text(kind), findsOneWidget, reason: kind);
    }
    expect(find.text('will decide'), findsOneWidget);
    // In time order: 現在式 before 過去式 before 未來式.
    final x = [
      for (final k in ['現在式', '過去式', '未來式']) tester.getTopLeft(find.text(k))
    ];
    expect(x[0].dy < x[1].dy || x[0].dx < x[1].dx, isTrue);
  });

  testWidgets('an adjective keeps 比較級／最高級, never verb forms', (tester) async {
    await pumpBack(tester, 'happy', 'adj.', 2);
    expect(find.text('比較級'), findsOneWidget);
    expect(find.text('最高級'), findsOneWidget);
    for (final kind in ['過去式', '現在分詞', '第三人稱單數', '未來式', '現在式']) {
      expect(find.text(kind), findsNothing, reason: kind);
    }
    expect(find.text('happied'), findsNothing);
  });
}
