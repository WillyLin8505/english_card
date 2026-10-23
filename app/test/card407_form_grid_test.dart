// Card #407 (問題回報 #406): label on the photo by default, the forms as an
// even grid, and every English word on the card opens.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

import 'helpers.dart';

Map<String, dynamic> _lex(int id, String lemma, String pos,
        {List<Map<String, dynamic>> forms = const [],
        List<Map<String, dynamic>> relations = const [],
        double zipf = 4}) =>
    {
      'id': id,
      'lemma': lemma,
      'normalized': lemma,
      'pos': pos,
      'zipf': zipf,
      'forms': forms,
      'relations': relations,
    };

Map<String, dynamic> _form(String field, String form, String label) =>
    {'field': field, 'form': form, 'normalized': form, 'label': label};

void main() {
  setUp(() {
    LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        _lex(1, 'decide', 'verb', forms: [
          _form('verb_base', 'decide', '動詞原形'),
          _form('verb_third_person', 'decides', '第三人稱單數'),
          _form('verb_past', 'decided', '過去式'),
          _form('verb_past_participle', 'decided', '過去分詞'),
          _form('verb_present_participle', 'deciding', '現在分詞'),
        ], relations: [
          {'relation': 'derived_terms', 'word': 'decision'},
          {'relation': 'derived_terms', 'word': 'decisive'},
          {'relation': 'derived_terms', 'word': 'decisively'},
        ]),
        _lex(2, 'decision', 'noun'),
        _lex(3, 'decisive', 'adj'),
        _lex(4, 'decisively', 'adv'),
        _lex(5, 'decided', 'adj'),
      ],
    });
  });
  tearDown(() => LexiconPack.instance.clear());

  WordEntry decide() => WordEntry(
        id: 'w-decide',
        word: 'decide',
        pos: 'verb',
        meaning: '決定',
        lexemeId: 1,
        examples: const [
          WordExample(text: 'I decide to go.', translation: '我決定去。')
        ],
        createdAt: testNow,
        updatedAt: testNow,
      );

  Future<WordDatabaseRepository> pumpBack(WidgetTester tester,
      {AppSettings? settings,
      Size size = const Size(402, 2000),
      ValueChanged<String>? onOpenWord,
      List<CardPhoto> photos = const []}) async {
    final entry = decide();
    final repo = WordDatabaseRepository(clock: () => testNow, entries: [entry]);
    await pumpApp(tester,
        repository: repo,
        settings: settings,
        size: size,
        home: Scaffold(
            body: SingleChildScrollView(
                child: FlashcardBack(
          entry: entry,
          card: const LearningCard(
              id: 'card', wordEntryId: 'w-decide', templateId: 't'),
          photo: photos.isEmpty ? null : photos.first.$1,
          anchor: photos.isEmpty ? null : photos.first.$2,
          photos: photos,
          template: repo.template,
          learnerLevel: 'A2',
          onPlay: () {},
          onOpen: () {},
          onOpenWord: onOpenWord,
        ))));
    // M-PERF2: the sections under the photo come one frame each.
    await tester.pumpAndSettle();
    return repo;
  }

  final photo = Photo(
    id: 'p1',
    title: '',
    takenAt: testNow,
    createdAt: testNow,
    placeholderColors: const [0xFFB8C4D6, 0xFFDDE4EE],
  );

  testWidgets('photo labels are on by default and can be switched off',
      (tester) async {
    await pumpBack(tester, photos: [(photo, const LabelPoint(0.3, 0.4), null)]);
    expect(
        tester.widget<PinnedPhoto>(find.byType(PinnedPhoto)).pins, isNotEmpty);
    await pumpBack(tester,
        settings: AppSettings.inMemory(showPhotoLabels: false),
        photos: [(photo, const LabelPoint(0.3, 0.4), null)]);
    expect(tester.widget<PinnedPhoto>(find.byType(PinnedPhoto)).pins, isEmpty);
  });

  testWidgets('forms: one cell per kind, equal width, nothing overflows',
      (tester) async {
    for (final size in const [
      Size(320, 2000),
      Size(402, 2000),
      Size(900, 2000)
    ]) {
      await pumpBack(tester, size: size);
      const kinds = [
        '第三人稱單數',
        '過去式',
        '過去分詞',
        '現在分詞',
        '名詞',
        '形容詞',
        '副詞',
      ];
      for (final k in kinds) {
        expect(find.byKey(ValueKey('form-cell-$k')), findsOneWidget, reason: k);
      }
      // 動詞原形 is the headword itself: no cell.
      expect(find.byKey(const ValueKey('form-cell-動詞原形')), findsNothing);
      final widths = {
        for (final k in kinds)
          tester.getSize(find.byKey(ValueKey('form-cell-$k'))).width
      };
      expect(widths.length, 1, reason: 'cells are equal width at $size');
      expect(tester.takeException(), isNull);
    }
    // decided is both the past tense and the past participle: two cells.
    expect(find.text('decided'), findsNWidgets(2));
    expect(find.text('decision'), findsWidgets);
  });

  testWidgets('tapping a word in the forms opens it, in my words or not',
      (tester) async {
    final opened = <String>[];
    await pumpBack(tester, onOpenWord: opened.add);
    await tester.tap(find.text('decisive').first);
    await tester.pumpAndSettle();
    expect(opened, ['pack:3']);
  });

  test('WordLinks: a dictionary-only word gets a pack target', () {
    final repo =
        WordDatabaseRepository(clock: () => testNow, entries: [decide()]);
    final links = WordLinks.of(repo);
    expect(links.idFor('decide'), 'w-decide');
    expect(links.idFor('decision'), 'pack:2');
    expect(links.idFor('zzzz'), isNull);
    final segs = links.segments('A decisive decision.');
    expect([
      for (final s in segs)
        if (s.id != null) s.id
    ], [
      'pack:3',
      'pack:2'
    ]);
  });
}
