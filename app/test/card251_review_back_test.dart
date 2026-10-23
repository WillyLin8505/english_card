// Card #251: the review card back (owner, 2026-10-18, nine items).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/speaker.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

import 'helpers.dart';

class AccentSpeaker extends SilentSpeaker {
  final accents = <String>[];
  @override
  Future<bool> say(String text,
      {required String language,
      String? audioUrl,
      String accent = 'en-GB'}) async {
    accents.add(accent);
    return super.say(text, language: language, audioUrl: audioUrl, accent: accent);
  }
}

WordEntry _entry(String id, String word, String meaning,
        {String pos = 'noun',
        String? level,
        int? lexemeId,
        List<WordExample> examples = const [],
        String? definition}) =>
    WordEntry(
      id: id,
      word: word,
      pos: pos,
      meaning: meaning,
      level: level,
      lexemeId: lexemeId,
      examples: examples,
      definition: definition,
      createdAt: testNow,
      updatedAt: testNow,
    );

Photo _photo(String id) => Photo(
      id: id,
      title: '',
      takenAt: testNow,
      createdAt: testNow,
      placeholderColors: const [0xFFB8C4D6, 0xFFDDE4EE],
    );

void main() {
  setUp(() {
    LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'sunlight',
          'normalized': 'sunlight',
          'pos': 'noun',
          'cefr': 'A2',
          'forms': [
            {
              'field': 'form',
              'form': 'sunlights',
              'normalized': 'sunlights',
              'label': 'plural'
            },
          ],
          'morphemes': [
            {'part': 'sun', 'kind': 'root', 'free': true, 'native': '太陽'},
            {
              'part': 'light',
              'kind': 'root',
              'free': true,
              'native': '光',
              'native_ai': true
            },
          ],
          'relations': [
            {'relation': 'synonyms', 'word': 'sunshine', 'native': '陽光', 'cefr': 'B1'},
            {'relation': 'related', 'word': 'daylight', 'native': '日光', 'cefr': 'B2'},
            // Card #226: also a synonym, so the 相關詞 block must skip it.
            {'relation': 'related', 'word': 'Sunshine', 'native': '陽光', 'cefr': 'B1'},
            {'relation': 'near_homophones', 'word': 'sunlit', 'native': '陽光照耀的'},
            {'relation': 'similar_spelling', 'word': 'sunlike'},
            {
              'relation': 'similar_spelling',
              'word': 'obscurity',
              'hide_by_default': true
            },
          ],
        },
      ],
    });
  });
  tearDown(() => LexiconPack.instance.clear());

  late WordDatabaseRepository repo;
  late WordEntry sunlight;

  WordDatabaseRepository makeRepo() {
    sunlight = _entry('w-sunlight', 'sunlight', '陽光',
        level: 'A2',
        lexemeId: 1,
        definition: 'light from the sun',
        examples: const [
          WordExample(
              text: 'The sunlight warms the sea.', translation: '陽光曬暖了海。'),
          WordExample(text: 'Soft sunlight.', translation: '柔和的陽光。'),
        ]);
    return WordDatabaseRepository(clock: () => testNow, entries: [
      sunlight,
      _entry('w-sea', 'sea', '海'),
      _entry('w-sun', 'sun', '太陽'),
      _entry('w-sunshine', 'sunshine', '陽光'),
    ]);
  }

  Future<void> pumpBack(WidgetTester tester,
      {List<CardPhoto> photos = const [],
      ValueChanged<int>? onPhotoSelected,
      ValueChanged<String>? onOpenWord}) async {
    repo = makeRepo();
    await pumpApp(tester,
        repository: repo,
        size: const Size(402, 2000),
        home: Scaffold(
            body: SingleChildScrollView(
                child: FlashcardBack(
          entry: sunlight,
          card: const LearningCard(
              id: 'card', wordEntryId: 'w-sunlight', templateId: 't'),
          photo: photos.isEmpty ? null : photos.first.$1,
          anchor: photos.isEmpty ? null : photos.first.$2,
          photos: photos,
          onPhotoSelected: onPhotoSelected,
          template: repo.template,
          learnerLevel: 'A2',
          onPlay: () {},
          onOpen: () {},
          onOpenWord: onOpenWord,
        ))));
    await tester.pumpAndSettle();
  }

  testWidgets('item 2: part of speech stays, the CEFR level chip goes',
      (tester) async {
    await pumpBack(tester);
    expect(find.text('名詞'), findsOneWidget);
    expect(find.textContaining('基礎'), findsNothing);
    expect(find.textContaining('A2'), findsNothing);
  });

  testWidgets('item 3: no 照片情境 title; the word label is on by default (#406)',
      (tester) async {
    await pumpBack(tester,
        photos: [(_photo('p1'), const LabelPoint(0.3, 0.4), null)]);
    expect(find.text('照片情境'), findsNothing);
    final view = tester.widget<PinnedPhoto>(find.byType(PinnedPhoto));
    expect(view.pins.map((p) => p.word.toLowerCase()), ['sunlight']);
  });

  testWidgets('item 5: every form is listed with its label', (tester) async {
    await pumpBack(tester);
    expect(find.text('詞形變化'), findsOneWidget);
    expect(find.textContaining('sunlights'), findsOneWidget);
    expect(find.textContaining('複數'), findsOneWidget);
  });

  testWidgets(
      'item 6: 同義詞／相關詞／近音字／拼字相近 blocks; empty ones and hidden words left out',
      (tester) async {
    await pumpBack(tester);
    for (final label in ['同義詞', '相關詞', '容易混淆的字']) {
      expect(find.text(label), findsOneWidget, reason: label);
    }
    expect(find.text('反義詞'), findsNothing);
    expect(find.text('相關字'), findsNothing);
    for (final word in ['sunshine', 'daylight', 'sunlit']) {
      expect(find.textContaining(word), findsOneWidget, reason: word);
    }
    // No Chinese meaning, so it stays off the back (card #437).
    expect(find.textContaining('sunlike'), findsNothing);
    // A word already under 同義詞 is not repeated under 相關詞 (card #226).
    expect(find.textContaining('Sunshine'), findsNothing);
    expect(find.textContaining('陽光照耀的'), findsOneWidget);
    expect(find.textContaining('obscurity'), findsNothing);
    // The chips sit in a Wrap, so they fill the row instead of one per line.
    final wrap = tester.widget<Wrap>(find
        .ancestor(of: find.textContaining('sunshine'), matching: find.byType(Wrap))
        .first);
    expect(wrap.children, isNotEmpty);
  });

  testWidgets('item 7: 構詞拆解 boxes joined by +, with kind and AI mark',
      (tester) async {
    await pumpBack(tester);
    expect(find.text('構詞拆解'), findsOneWidget);
    expect(find.text('構詞與詞源'), findsNothing);
    expect(find.text('sun'), findsOneWidget);
    expect(find.text('light'), findsOneWidget);
    expect(find.text('單字'), findsNWidgets(2));
    expect(find.text('+'), findsOneWidget);
    expect(find.text('太陽'), findsOneWidget);
    expect(find.text('光'), findsOneWidget);
    expect(find.text('AI'), findsOneWidget);
  });

  testWidgets('item 8: several photos swipe left and right and report the pick',
      (tester) async {
    final picked = <int>[];
    await pumpBack(tester, photos: [
      (_photo('p1'), null, null),
      (_photo('p2'), null, 'Author A'),
      (_photo('p3'), null, null),
    ], onPhotoSelected: picked.add);
    expect(find.byType(PageView), findsOneWidget);
    await tester.drag(find.byType(PageView), const Offset(-300, 0));
    await tester.pumpAndSettle();
    expect(picked, [1]);
    expect(find.bySemanticsLabel(RegExp('第 2 張，共 3 張')), findsOneWidget);
  });

  testWidgets('item 8: one photo shows without a pager', (tester) async {
    await pumpBack(tester, photos: [(_photo('p1'), null, null)]);
    expect(find.byType(PageView), findsNothing);
    expect(find.byType(PinnedPhoto), findsOneWidget);
  });

  testWidgets('card #308: many photos show a counter instead of dots',
      (tester) async {
    await pumpBack(tester, photos: [
      for (var i = 0; i < 29; i++) (_photo('p$i'), null, null),
    ]);
    expect(find.text('第 1 / 29 張　·　左右滑動換照片'), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('第 1 張，共 29 張')), findsOneWidget);
  });

  test('item 9: only words in the database become links (phrases first)',
      () {
    final repo = WordDatabaseRepository(clock: () => testNow, entries: [
      _entry('w-sea', 'sea', '海'),
      _entry('w-look-after', 'look after', '照顧', pos: 'phrase'),
      _entry('w-go', 'go', '去', pos: 'verb', lexemeId: 40),
    ]);
    LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 40,
          'lemma': 'go',
          'normalized': 'go',
          'pos': 'verb',
          'forms': [
            {'field': 'form', 'form': 'went', 'normalized': 'went', 'label': 'past'}
          ],
        }
      ],
    });
    final links = WordLinks.of(repo);
    final segs = links.segments('We went to look after the Sea, not the sky.');
    expect(
        [for (final s in segs) if (s.id != null) (s.text, s.id)],
        [('went', 'w-go'), ('look after', 'w-look-after'), ('Sea', 'w-sea')]);
    expect(segs.map((s) => s.text).join(), 'We went to look after the Sea, not the sky.');
    expect(links.idFor('sky'), isNull);
  });

  testWidgets('item 9: tapping a linked word in an example opens that word',
      (tester) async {
    final opened = <String>[];
    await pumpBack(tester, onOpenWord: opened.add);
    final sentence = find.textContaining('The sunlight warms the sea.');
    expect(sentence, findsOneWidget);
    final text = tester.widget<RichText>(find
        .descendant(of: sentence, matching: find.byType(RichText))
        .first);
    final spans = <String, TextSpan>{};
    (text.text as TextSpan).visitChildren((s) {
      if (s is TextSpan && s.text != null) spans[s.text!] = s;
      return true;
    });
    // Words in the database read as links; "warms" is plain text.
    expect(spans['sea']?.recognizer, isNotNull);
    expect(spans['sea']?.style?.decoration, TextDecoration.underline);
    expect(spans['sunlight']?.recognizer, isNotNull);
    expect(spans.keys.where((t) => t.contains('warms')).single, ' warms the ');
    (spans['sea']!.recognizer as dynamic).onTap();
    await tester.pumpAndSettle();
    expect(opened, ['w-sea']);
    // The related-word chip of a database word links too.
    await tester.tap(find.textContaining('sunshine'));
    await tester.pumpAndSettle();
    expect(opened, ['w-sea', 'w-sunshine']);
  });

  testWidgets('item 1: turning the card plays British then American',
      (tester) async {
    final repo = testRepository();
    for (final entry in repo.entries.where((e) => e.word != 'apple')) {
      repo.archiveWord(entry.id);
    }
    final speaker = AccentSpeaker();
    await pumpApp(tester,
        initialTab: AppTab.review,
        repository: repo,
        speaker: speaker,
        size: const Size(402, 1400));
    await tester.tap(find.text('綜合'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('顯示答案'));
    await tester.pumpAndSettle();
    expect(find.byType(FlashcardBack), findsOneWidget);
    // Both accents (#649); recorded ones would go first — see
    // flip_pronunciation_test.dart.
    expect(speaker.accents, ['en-GB', 'en-US']);
  });
}
