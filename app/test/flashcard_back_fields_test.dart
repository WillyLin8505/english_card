import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/card_template.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/speaker.dart';
import 'helpers.dart';

class RecordingSpeaker extends SilentSpeaker {
  final calls = <({String accent, String? url})>[];
  @override
  Future<bool> say(String text,
      {required String language,
      String? audioUrl,
      String accent = 'en-GB'}) async {
    calls.add((accent: accent, url: audioUrl));
    return true;
  }
}

void main() {
  setUp(() {
    LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'media_base': 'http://localhost/media',
      'lexemes': [
        {
          'id': 40,
          'lemma': 'go',
          'normalized': 'go',
          'pos': 'verb',
          'forms': [
            // The pack's real fields: one grid cell per kind of form.
            for (final (field, form) in const [
              ('verb_third_person', 'goes'),
              ('verb_present_participle', 'going'),
              ('verb_past', 'went'),
              ('verb_past_participle', 'gone'),
            ])
              {
                'field': field,
                'form': form,
                'normalized': form,
              },
          ],
          'pronunciations': [
            {'kind': 'ipa', 'value': '/ɡəʊ/'},
            {'kind': 'ipa', 'value': '/ɡoʊ/'},
            {
              'kind': 'audio',
              'audio': 'us.mp3',
              'accent': 'US',
              'default': true
            },
            {'kind': 'audio', 'audio': 'uk.mp3', 'accent': 'UK'},
          ],
          'relations': [
            for (final kind in [
              'homophones',
              'near_homophones',
              'similar_spelling'
            ])
              {'relation': kind, 'word': 'hidden-$kind', 'native': '相似字', 'cefr': 'A1'},
          ],
        },
      ],
    });
  });
  tearDown(() => LexiconPack.instance.clear());

  Future<void> pumpBack(WidgetTester tester, RecordingSpeaker speaker,
      {bool pronunciation = true, bool linked = false}) async {
    final entry = WordEntry(
      id: 'private-id',
      word: 'went',
      pos: 'verb',
      meaning: '去',
      createdAt: testNow,
      updatedAt: testNow,
      ipa: '/ɡəʊ/',
      ipaSource: 'cmudict',
      levelSource: 'cefr-j',
      frequency: 6.123,
      lexemeId: linked ? 40 : null,
    );
    await pumpApp(tester,
        speaker: speaker,
        home: Scaffold(
            body: SingleChildScrollView(
                child: FlashcardBack(
          entry: entry,
          card: const LearningCard(
              id: 'card-id', wordEntryId: 'private-id', templateId: 'test'),
          photo: null,
          anchor: null,
          learnerLevel: 'A1',
          onPlay: () {},
          onOpen: () {},
          template: CardTemplate(id: 'test', name: 'test', backFields: [
            TemplateField(CardBackField.pronunciation, visible: pronunciation),
            const TemplateField(CardBackField.formsAndDerivations,
                limit: 1, expandAll: false, collapsed: true),
            const TemplateField(CardBackField.related, collapsed: false),
            const TemplateField(CardBackField.source, collapsed: false),
          ]),
        ))));
  }

  testWidgets(
      'lemma forms are complete despite template limits; metadata omitted; lookalikes shown (card #251)',
      (tester) async {
    await pumpBack(tester, RecordingSpeaker());
    for (final form in ['goes', 'going', 'went', 'gone']) {
      expect(find.textContaining(form), findsOneWidget);
    }
    for (final text in [
      '來源',
      'CMUdict',
      'CEFR-J 詞表',
      'private-id',
      '6.123',
    ]) {
      expect(find.textContaining(RegExp(RegExp.escape(text), caseSensitive: false)), findsNothing);
    }
    // Card #251 item 6: 近音字 and 拼字相近 are shown when the pack has them.
    expect(find.text('近音字'), findsOneWidget);
    expect(find.text('容易混淆的字'), findsOneWidget);
    for (final text in [
      'hidden-homophones',
      'hidden-near_homophones',
      'hidden-similar_spelling'
    ]) {
      expect(find.textContaining(text), findsOneWidget);
    }
    expect(find.text('/ɡəʊ/'), findsOneWidget);
    expect(find.text('/ɡoʊ/'), findsNothing);
  });

  testWidgets('two controls play their corresponding recordings',
      (tester) async {
    final speaker = RecordingSpeaker();
    await pumpBack(tester, speaker, linked: true);
    await tester.tap(find.byTooltip('播放英式發音'));
    await tester.tap(find.byTooltip('播放美式發音'));
    expect(speaker.calls, [
      (accent: 'en-GB', url: 'http://localhost/media?path=uk.mp3'),
      (accent: 'en-US', url: 'http://localhost/media?path=us.mp3'),
    ]);
  });

  testWidgets('hidden pronunciation hides IPA and both controls',
      (tester) async {
    await pumpBack(tester, RecordingSpeaker(), pronunciation: false);
    expect(find.text('/ɡəʊ/'), findsNothing);
    expect(find.byType(IconButton), findsNothing);
  });

  testWidgets('missing recordings use distinct accent fallbacks',
      (tester) async {
    LexiconPack.instance.clear();
    final speaker = RecordingSpeaker();
    await pumpBack(tester, speaker);
    await tester.tap(find.byTooltip('播放英式發音'));
    await tester.tap(find.byTooltip('播放美式發音'));
    expect(speaker.calls, [
      (accent: 'en-GB', url: null),
      (accent: 'en-US', url: null),
    ]);
  });

  testWidgets(
      '問題回報 #224: learning info shows learner-facing counts, not raw FSRS stability/difficulty',
      (tester) async {
    LexiconPack.instance.clear();
    final entry = WordEntry(
      id: 'private-id',
      word: 'went',
      pos: 'verb',
      meaning: '去',
      createdAt: testNow,
      updatedAt: testNow,
    );
    const card = LearningCard(
      id: 'card-id',
      wordEntryId: 'private-id',
      templateId: 'test',
      fsrs: FsrsState(
        state: FsrsCardState.review,
        stability: 12.3,
        difficulty: 6.8,
        reps: 4,
        lapses: 1,
      ),
    );
    await pumpApp(tester,
        speaker: RecordingSpeaker(),
        home: Scaffold(
            body: SingleChildScrollView(
                child: FlashcardBack(
          entry: entry,
          card: card,
          photo: null,
          anchor: null,
          learnerLevel: 'A1',
          onPlay: () {},
          onOpen: () {},
          template: const CardTemplate(id: 'test', name: 'test', backFields: [
            TemplateField(CardBackField.learningInfo),
          ]),
        ))));
    expect(find.text('學習資訊'), findsNothing);
    expect(find.textContaining('穩定度'), findsNothing);
    expect(find.textContaining('難度'), findsNothing);
    expect(find.text('已複習 4 次 · 忘記 1 次'), findsNothing);
  });
}
