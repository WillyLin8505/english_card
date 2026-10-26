// 問題回報 #692 (回到正面 上下各一), #694 (英文說明列 1 2 3),
// #698 #699 (單字詳情的意思列 1 2 3), #704 (相關詞、詞形變化可點開),
// #705 (單字詳情的等級只標一次).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/card_template.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';

import 'helpers.dart';

Map<String, dynamic> _pack() => {
      'catalog_version': 1,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'flow',
          'normalized': 'flow',
          'pos': 'noun',
          'status': 'full',
          'cefr': 'B1',
          'senses': [
            {'id': 11, 'native': '流', 'definition': 'a flowing'},
            {'id': 12, 'native': '流量', 'definition': 'rate'},
            {'id': 13, 'native': '潮汐上升', 'definition': 'tide'},
          ],
          'forms': [
            {'field': 'noun_plural', 'form': 'flows', 'normalized': 'flows'},
          ],
          'relations': [
            {'relation': 'related', 'word': 'stream', 'native': '溪流'},
            {'relation': 'synonyms', 'word': 'nowhere', 'native': '沒有'},
          ],
        },
        {
          'id': 2,
          'lemma': 'stream',
          'normalized': 'stream',
          'pos': 'noun',
          'status': 'full',
          'senses': [
            {'id': 21, 'native': '小溪'},
          ],
        },
        {
          'id': 3,
          'lemma': 'flows',
          'normalized': 'flows',
          'pos': 'verb',
          'status': 'full',
          'senses': [
            {'id': 31, 'native': '流動'},
          ],
        },
      ],
    };

void main() {
  tearDown(() => LexiconPack.instance.clear());

  testWidgets('#692 回到正面 above the word and above the ratings', (tester) async {
    await pumpApp(tester,
        initialTab: AppTab.review, size: const Size(402, 1400));
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    final top = find.byKey(const ValueKey('flip-to-front-top'));
    final bottom = find.byKey(const ValueKey('flip-to-front'));
    expect(top, findsNothing, reason: 'already on the front');

    final s =
        tester.widget<FlashcardFront>(find.byType(FlashcardFront)).session;
    if (s != null && !s.canAnswer) s.reportPhotoState(s.photoAttempt, true);
    s?.showAnswer();
    await tester.pumpAndSettle();
    expect(top, findsOneWidget);
    expect(bottom, findsOneWidget);
    expect(tester.getTopLeft(top).dy,
        lessThan(tester.getTopLeft(find.byType(FlashcardBack)).dy),
        reason: 'above the word');

    await tester.tap(top);
    await tester.pumpAndSettle();
    expect(find.byType(FlashcardFront), findsOneWidget);
    expect(top, findsNothing);
  });

  testWidgets('#694 the English definition is numbered on the back',
      (tester) async {
    final entry = WordEntry(
      id: 'yellow-id',
      word: 'yellow',
      pos: 'noun',
      meaning: '黃色',
      definition: 'The color of lemons; the color of gold; a primary color',
      createdAt: testNow,
      updatedAt: testNow,
    );
    await pumpApp(tester,
        home: Scaffold(
            body: SingleChildScrollView(
                child: FlashcardBack(
          entry: entry,
          card: const LearningCard(
              id: 'card-id', wordEntryId: 'yellow-id', templateId: 'test'),
          photo: null,
          anchor: null,
          learnerLevel: 'A1',
          onPlay: () {},
          onOpen: () {},
          template: CardTemplate(id: 'test', name: 'test', backFields: const [
            TemplateField(CardBackField.posAndMeaning),
          ]),
        ))));
    await tester.pumpAndSettle();
    for (final n in [1, 2, 3]) {
      expect(find.byKey(ValueKey('numbered-definition-$n')), findsOneWidget);
      expect(
          find.descendant(
              of: find.byKey(ValueKey('numbered-definition-$n')),
              matching: find.text('$n.')),
          findsOneWidget);
    }
    expect(find.textContaining('the color of gold'), findsOneWidget);
  });

  testWidgets(
      '#698 #699 #704 #705 word detail: numbered senses, linked words, one level',
      (tester) async {
    LexiconPack.instance.loadJson(_pack());
    await pumpApp(tester,
        home: const DatabaseWordScreen(wordId: 1), size: const Size(402, 2400));
    await tester.pumpAndSettle();

    // #698 #699: 1 2 3 before each meaning, one per line (not side by side).
    final rows = [
      for (final n in [1, 2, 3]) find.byKey(ValueKey('sense-1-$n')),
    ];
    for (final (i, row) in rows.indexed) {
      expect(row, findsOneWidget);
      expect(find.descendant(of: row, matching: find.text('${i + 1}.')),
          findsOneWidget);
    }
    expect(tester.getTopLeft(rows[0]).dx, tester.getTopLeft(rows[1]).dx);
    expect(tester.getTopLeft(rows[1]).dy,
        greaterThan(tester.getTopLeft(rows[0]).dy));

    // #705: the level is the badge only, not also in the line beside it.
    expect(find.text('名詞'), findsNWidgets(2), reason: 'header line + pos chip');
    expect(find.text('名詞 · 中階（B1）'), findsNothing);
    expect(find.textContaining('中階（B1）'), findsOneWidget);

    // #704: a word the pack has opens its own detail; one it lacks does not.
    final missing =
        tester.widget<TagChip>(find.byKey(const ValueKey('relation-nowhere')));
    expect(missing.onTap, isNull);
    final form =
        tester.widget<TagChip>(find.byKey(const ValueKey('form-flows')));
    expect(form.onTap, isNotNull);

    await tester.tap(find.byKey(const ValueKey('relation-stream')));
    await tester.pumpAndSettle();
    expect(find.text('stream'), findsOneWidget);
    expect(find.text('小溪'), findsOneWidget);
  });
}
