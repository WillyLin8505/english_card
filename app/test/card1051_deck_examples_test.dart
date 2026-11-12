// Card #1051 (問題回報 #1571): a situation deck carries Tatoeba sentences per
// word; reviewing that deck shows them first, with the author named.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/deck_library.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

Map<String, dynamic> _json({bool withExamples = true}) => {
      'slug': 'fr-situation-restaurant',
      'kind': 'words',
      'title': 'Au restaurant',
      'count': 1,
      'items': [
        {
          'word': 'addition',
          'pos': 'noun',
          'cefr': 'A2',
          if (withExamples)
            'examples': [
              {
                'text': "L'addition, s'il vous plaît.",
                'translation': 'The bill, please.',
                'tatoeba_id': 42,
                'author': 'sacredceltic',
                'license': 'CC BY 2.0 FR',
              }
            ],
        },
      ],
    };

void main() {
  test('the deck JSON keeps the examples with their credit', () {
    final c = DeckContent.fromJson(_json());
    final x = c.examples['addition']!.single;
    expect(x.text, "L'addition, s'il vous plaît.");
    expect(x.translation, 'The bill, please.');
    expect(x.credit, contains('sacredceltic'));
    expect(x.credit, contains('CC BY 2.0 FR'));
    expect(DeckContent.fromJson(_json(withExamples: false)).examples, isEmpty);
  });

  test('card #1061: English albums read zh and show the AI flag', () {
    final j = _json();
    j['items'][0]['examples'] = [
      {'text': 'The bill, please.', 'zh': '請給我帳單。', 'zh_ai': true},
      {'text': 'Hi', 'translation': '嗨', 'aiTranslated': true},
      {'text': 'Plain', 'translation': 'X'},
    ];
    final xs = DeckContent.fromJson(j).examples['addition']!;
    expect(xs[0].translation, '請給我帳單。');
    expect(xs[0].aiTranslated, isTrue);
    expect(xs[1].aiTranslated, isTrue);
    expect(xs[2].aiTranslated, isFalse);
  });

  test('installed decks remember them; only their own scope sees them',
      () async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final lib = DeckLibrary(remote: false, persist: false);
    await lib.install(DeckContent.fromJson(_json()),
        repository: repo,
        intake: PhotoIntake(
            repository: () => repo, photoStore: PhotoStore.inMemory()));
    final deck = lib.installedDeck('fr-situation-restaurant')!;
    final back = InstalledDeck.fromJson(
        jsonDecode(jsonEncode(deck.toJson())) as Map<String, dynamic>);
    expect(back.examples['addition']!.single.credit, contains('sacredceltic'));
    expect(lib.contextExamples('deck:fr-situation-restaurant', 'Addition'),
        hasLength(1));
    expect(lib.contextExamples('all', 'addition'), isEmpty);
    expect(lib.contextExamples('deck:other', 'addition'), isEmpty);
  });

  testWidgets('the back shows the deck sentence, translation and author first',
      (tester) async {
    final entry = WordEntry(
      id: 'w-addition',
      word: 'addition',
      pos: 'noun',
      meaning: 'bill',
      examples: const [
        WordExample(text: 'Une addition simple.', translation: 'A sum.')
      ],
      createdAt: testNow,
      updatedAt: testNow,
    );
    final repo = WordDatabaseRepository(clock: () => testNow, entries: [entry]);
    final x = DeckContent.fromJson(_json()).examples['addition']!;
    await pumpApp(tester,
        repository: repo,
        size: const Size(402, 2000),
        home: Scaffold(
            body: SingleChildScrollView(
                child: FlashcardBack(
          entry: entry,
          card: const LearningCard(
              id: 'card', wordEntryId: 'w-addition', templateId: 't'),
          photo: null,
          anchor: null,
          template: repo.template,
          learnerLevel: 'A2',
          contextExamples: x,
          onPlay: () {},
          onOpen: () {},
        ))));
    await tester.pumpAndSettle();
    expect(find.textContaining("L'addition"), findsOneWidget);
    expect(find.text('The bill, please.'), findsOneWidget);
    expect(find.textContaining('sacredceltic'), findsOneWidget);
    expect(find.textContaining('Une addition simple'), findsOneWidget);
  });
}
