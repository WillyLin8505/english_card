// 問題回報 #580 (關係詞中文只取第一個「；」「：」之前、最多 10 字，可點開看全文)
// and #558 (A1–B1 複習背面英文定義預設收起，點中文意思展開).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/card_template.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';

import 'helpers.dart';

const _long = '身材矮小的人，尤指神話中的小矮人族群成員';

Map<String, dynamic> _pack() => {
      'catalog_version': 1,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'giant',
          'normalized': 'giant',
          'pos': 'noun',
          'status': 'full',
          'cefr': 'B1',
          'senses': [
            {'id': 11, 'native': '巨人', 'definition': 'a very big person'},
          ],
          'relations': [
            {'relation': 'synonyms', 'word': 'dwarf', 'native': '小人：身材矮小的人'},
            {'relation': 'related', 'word': 'titan', 'native': _long},
            {'relation': 'related', 'word': 'ogre', 'native': '食人魔'},
          ],
        },
        {
          'id': 2,
          'lemma': 'dwarf',
          'normalized': 'dwarf',
          'pos': 'noun',
          'status': 'full',
          'senses': [
            {'id': 21, 'native': '侏儒'},
          ],
        },
      ],
    };

Widget _back(String level, {String language = 'en'}) => Scaffold(
        body: SingleChildScrollView(
            child: FlashcardBack(
      entry: WordEntry(
        id: 'giant-id',
        word: language == 'fr' ? 'géant' : 'giant',
        language: language,
        pos: 'noun',
        meaning: '巨人',
        definition:
            language == 'fr' ? 'une personne très grande' : 'a very big person',
        createdAt: testNow,
        updatedAt: testNow,
      ),
      card: const LearningCard(
          id: 'card-id', wordEntryId: 'giant-id', templateId: 'test'),
      photo: null,
      anchor: null,
      learnerLevel: level,
      onPlay: () {},
      onOpen: () {},
      template: const CardTemplate(id: 'test', name: 'test', backFields: [
        TemplateField(CardBackField.posAndMeaning),
      ]),
    )));

void main() {
  tearDown(() => LexiconPack.instance.clear());

  test('#580 short meaning: before the first ；：;:, at most 10 characters', () {
    expect(shortRelationMeaning('小人：身材矮小的人'), '小人');
    expect(shortRelationMeaning('通過；經過'), '通過');
    expect(shortRelationMeaning('pass; go by'), 'pass');
    expect(shortRelationMeaning('a: b'), 'a');
    expect(shortRelationMeaning('食人魔'), '食人魔');
    expect(shortRelationMeaning(_long), '身材矮小的人，尤指神…');
    expect(shortRelationMeaning('一二三四五六七八九十'), '一二三四五六七八九十');
    expect(shortRelationMeaning(''), '');
  });

  testWidgets('#580 word detail relation chips: short, long press shows all',
      (tester) async {
    LexiconPack.instance.loadJson(_pack());
    await pumpApp(tester,
        home: const DatabaseWordScreen(wordId: 1), size: const Size(375, 2400));
    await tester.pumpAndSettle();

    expect(find.text('dwarf　小人'), findsOneWidget);
    expect(find.textContaining('小人：'), findsNothing);
    expect(find.text('titan　身材矮小的人，尤指神…'), findsOneWidget);
    expect(find.text('ogre　食人魔'), findsOneWidget);

    // titan is not in the pack: its tap opens the full text, and folds it.
    await tester.tap(find.byKey(const ValueKey('relation-titan')));
    await tester.pump();
    expect(find.text('titan　$_long'), findsOneWidget);
    expect(tester.takeException(), isNull, reason: 'no overflow at 375pt');
    await tester.tap(find.byKey(const ValueKey('relation-titan')));
    await tester.pump();
    expect(find.text('titan　身材矮小的人，尤指神…'), findsOneWidget);

    // dwarf opens its own page on tap; a long press shows the full text.
    await tester.longPress(find.byKey(const ValueKey('relation-dwarf')));
    await tester.pump();
    expect(find.text('dwarf　小人：身材矮小的人'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('relation-dwarf')));
    await tester.pumpAndSettle();
    expect(find.text('侏儒'), findsOneWidget);
  });

  for (final level in ['A1', 'A2', 'B1']) {
    testWidgets('#558 $level: the definition folds under the meaning',
        (tester) async {
      await pumpApp(tester, home: _back(level), size: const Size(375, 900));
      await tester.pumpAndSettle();
      expect(find.text('巨人'), findsOneWidget);
      expect(find.text('a very big person'), findsNothing);

      await tester.tap(find.text('巨人'));
      await tester.pumpAndSettle();
      expect(find.text('a very big person'), findsOneWidget);

      await tester.tap(find.text('巨人'));
      await tester.pumpAndSettle();
      expect(find.text('a very big person'), findsNothing);
    });
  }

  for (final level in ['B2', 'C1', 'C2']) {
    testWidgets('#558 $level: the definition shows as before', (tester) async {
      await pumpApp(tester, home: _back(level), size: const Size(375, 900));
      await tester.pumpAndSettle();
      expect(find.text('a very big person'), findsOneWidget);
      expect(find.byKey(const ValueKey('toggle-definition')), findsNothing);
    });
  }

  testWidgets('#558 French learner: the French definition folds the same way',
      (tester) async {
    await pumpApp(tester,
        home: _back('A2', language: 'fr'), size: const Size(375, 900));
    await tester.pumpAndSettle();
    expect(find.text('une personne très grande'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('toggle-definition')));
    await tester.pumpAndSettle();
    expect(find.text('une personne très grande'), findsOneWidget);
  });
}
