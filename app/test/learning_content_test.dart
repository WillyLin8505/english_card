import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/fsrs_scheduler.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/learning_content.dart';
import 'package:photo_english_app/services/word_database_query.dart';

import 'helpers.dart';

void main() {
  test('the lexicon pack\'s short POS codes have labels', () {
    expect(posLabel('adj'), '形容詞');
    expect(posLabel('adv'), '副詞');
    expect(posLabel('intj'), '感嘆詞');
    expect(posLabel('det'), '限定詞');
    expect(posLabel('num'), '數詞');
    expect(posLabel(shortPos('adj')), '形容詞');
  });

  test('examples: learner level first, then the easier neighbour, then the harder one', () {
    final e = WordEntry.fromUserInput(
      id: 'w1',
      word: 'bench',
      pos: 'noun',
      language: 'en',
      meaning: '長椅',
      now: testNow,
    ).copyWith(examples: const [
      WordExample(text: 'A bench.', translation: '一張長椅', difficulty: 'A1'),
      WordExample(text: 'The park bench was wet after the rain.', translation: '雨後公園長椅是濕的', difficulty: 'B1'),
      WordExample(text: 'She sat on the bench.', translation: '她坐在長椅上', difficulty: 'A2'),
      WordExample(text: 'The judge took the bench after a long career.', translation: '法官任職', difficulty: 'B2'),
      WordExample(text: 'No translation here.', difficulty: 'A2'),
    ]);
    expect([for (final x in learningExamples(e, 'A2')) x.difficulty], ['A2', 'A1', 'B1']);
    expect(learningExamples(e, 'B2').first.difficulty, 'B2');
  });

  testWidgets('Again says it comes back in this run; the others show days', (tester) async {
    final previews = const FsrsScheduler().preview(FsrsState.initial, testNow);
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: RatingBar(previews: previews, onRate: (_) {}))));
    expect(find.text('稍後再出現'), findsOneWidget);
    expect(find.textContaining('天後複習'), findsNWidgets(3));
  });

  test('a rarer part of speech is read from the pack (問題回報 #16)', () {
    Map<String, dynamic> j(String pos, bool rare, String cefr) => {
          'id': rare ? 2 : 1, 'lemma': 'tea', 'normalized': 'tea', 'pos': pos,
          'status': 'full', 'cefr': cefr, 'rare_usage': rare,
        };
    expect(LexEntry.fromJson(j('noun', false, 'A1')).rareUsage, isFalse);
    final adj = LexEntry.fromJson(j('adj', true, 'C1'));
    expect(adj.rareUsage, isTrue);
    expect(adj.cefr, 'C1');
  });

  test('the card meaning is the first two common senses (問題回報 #18)', () {
    LexEntry tea(List<Map<String, dynamic>> senses) => LexEntry.fromJson({
          'id': 1, 'lemma': 'tea', 'normalized': 'tea', 'pos': 'noun',
          'status': 'full', 'senses': senses,
        });
    Map<String, dynamic> s(int id, String? native, [List<String> labels = const []]) =>
        {'id': id, 'definition': 'd', 'native': native, 'labels': labels};
    expect(tea([s(1, '茶樹'), s(2, '茶葉、茶、茶水'), s(3, '茶飲')]).learnerMeaning,
        '茶樹；茶葉、茶、茶水');
    expect(tea([s(1, '番茄、柿子'), s(2, '番茄'), s(3, '紅色')]).learnerMeaning, '番茄、柿子',
        reason: 'a second sense that repeats the first adds nothing');
    expect(tea([s(1, '棒球', ['obsolete', 'slang']), s(2, '蘋果')]).learnerMeaning, '蘋果');
    expect(tea([s(1, null), s(2, '茶')]).learnerMeaning, '茶');
    expect(tea([s(1, '舊', ['obsolete'])]).learnerMeaning, '舊', reason: 'only rare senses: still something');
    // Another etymology is a different word (sofa: 馬利帝國奴隸兵).
    expect(tea([s(1, '沙發'), s(2, '馬利帝國奴隸兵', ['etymology-2'])]).learnerMeaning, '沙發');
    // 問題回報 #118: a meaning spelling the answer is left out.
    expect(tea([s(1, '茶'), s(2, '喝 tea、午茶')]).learnerMeaning, '茶；午茶');
    expect(tea([s(1, 'T恤')]).learnerMeaning, 'T恤');
    // 問題回報 #84: dictionary translations before AI descriptions.
    Map<String, dynamic> ai(int id, String native) => {...s(id, native), 'native_ai': true};
    expect(tea([s(1, '門、戶'), ai(2, '有門的建築物')]).learnerMeaning, '門、戶');
    expect(tea([ai(1, '物件之外圍'), s(2, '表面')]).learnerMeaning, '表面');
    expect(tea([ai(1, '廚房用寬平容器'), ai(2, '容器內之物')]).learnerMeaning,
        '廚房用寬平容器；容器內之物', reason: 'only AI senses: still something');
  });

  test('a word origin comes from the pack, in the native language only', () {
    Map<String, dynamic> lex(String word, Map<String, dynamic>? ety) => {
          'id': word.length, 'lemma': word, 'normalized': word, 'pos': 'noun',
          'status': 'full', 'etymology': ety,
        };
    LexiconPack.instance.loadJson({
      'target_language': 'en', 'native_language': 'zh-TW',
      'lexemes': [
        lex('cup', {'text': 'From Old English cuppe.', 'native': '源自古英語 cuppe。'}),
        lex('green', {'text': 'From Middle English grene.', 'native': null}),
        {...lex('grass', {'text': 'From Old English græs.'}), 'missing': {'etymology_native': 'missing'}},
        lex('sofa', null),
      ],
    });
    addTearDown(LexiconPack.instance.clear);
    WordEntry w(String word) => WordEntry.fromUserInput(
        id: word, word: word, pos: 'noun', language: 'en', meaning: '意思', now: testNow);
    expect(learningEtymology(w('cup')), '源自古英語 cuppe。');
    expect(learningEtymology(w('green')), isNull,
        reason: 'spec 08: no untranslated etymology text');
    expect(learningEtymology(w('sofa')), isNull);
    expect(missingFieldNames(w('grass')), contains('詞源'),
        reason: '單字集必須指出詞源等具體缺漏欄位');
    expect(LexiconPack.instance.lookup('cup')!.entry.etymology!.text, 'From Old English cuppe.');
    expect(missingFieldNames(w('green')), isNot(contains('詞源')));
  });

  test('related words follow the learner level, not only the most frequent (問題回報 #96)', () {
    Map<String, dynamic> rel(String w, String cefr, String rarity, {bool hide = false}) => {
          'relation': 'derived_terms', 'word': w, 'native': '意思', 'cefr': cefr,
          'rarity': rarity, 'hide_by_default': hide,
        };
    LexiconPack.instance.loadJson({
      'target_language': 'en', 'native_language': 'zh-TW',
      'lexemes': [
        {'id': 1, 'lemma': 'happy', 'normalized': 'happy', 'pos': 'adj', 'status': 'full',
         'relations': [rel('happiness', 'B1', 'less_common'), rel('happily', 'B1', 'less_common'),
                       rel('happyish', 'C2', 'very_rare', hide: true)]},
      ],
    });
    addTearDown(LexiconPack.instance.clear);
    final e = WordEntry.fromUserInput(
        id: 'h', word: 'happy', pos: 'adj', language: 'en', meaning: '快樂', now: testNow);
    expect([for (final r in learningRelations(e, 'B1', 'derived_terms')) r.word],
        ['happiness', 'happily']);
    expect(learningRelations(e, 'A2', 'derived_terms'), isEmpty);
    expect([for (final r in learningRelations(e, 'C2', 'derived_terms')) r.word],
        isNot(contains('happyish')));
  });

  test('構詞 shows each part with its Chinese, and nothing for a one-part word', () {
    Map<String, dynamic> m(String part, String kind, String? native) =>
        {'part': part, 'kind': kind, 'meaning': null, 'native': native};
    LexiconPack.instance.loadJson({
      'target_language': 'en', 'native_language': 'zh-TW',
      'lexemes': [
        {'id': 1, 'lemma': 'unhappy', 'normalized': 'unhappy', 'pos': 'adj', 'status': 'full',
         'morphemes': [m('un-', 'prefix', '不'), m('happy', 'root', '高興、快樂')]},
        {'id': 2, 'lemma': 'leaf', 'normalized': 'leaf', 'pos': 'noun', 'status': 'full',
         'morphemes': [m('leaf', 'root', '葉')]},
      ],
    });
    addTearDown(LexiconPack.instance.clear);
    WordEntry w(String word, String pos) => WordEntry.fromUserInput(
        id: word, word: word, pos: pos, language: 'en', meaning: '意思', now: testNow);
    expect(learningMorphology(w('unhappy', 'adj')), 'un-（不） ＋ happy（高興）');
    expect(learningMorphology(w('leaf', 'noun')), isNull);
  });
}

