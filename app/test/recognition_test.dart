import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/cefr_lexicon.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_selector.dart';

import 'helpers.dart';

WordCandidate c(
  String word, {
  String pos = 'noun',
  String level = 'A1',
  String meaning = '',
  double vc = 0.9,
  double use = 0.8,
  bool inferred = false,
}) =>
    WordCandidate(
      word: word,
      pos: pos,
      meaning: meaning.isEmpty ? word : meaning,
      level: level,
      levelSource: 'cefr-j',
      point: const LabelPoint(0.5, 0.5),
      visualConfidence: vc,
      usefulness: use,
      inferred: inferred,
    );

void main() {
  group('CefrLexicon (本機詞彙資料庫校正)', () {
    final lex = testLexicon();

    test('list level wins over the model; POS-specific; plurals', () {
      final mug = lex.resolve('mug', 'noun', modelLevel: 'A1');
      expect((mug.level, mug.source, mug.ipa), ('A2', 'cefr-j', '/mʌɡ/'));
      expect(lex.resolve('slice', 'verb').level, 'B2');
      expect(lex.resolve('slice', 'noun').level, 'A2');
      final slices = lex.resolve('slices', 'noun');
      expect((slices.level, slices.lemma), ('A2', 'slice'));
    });

    test('phrases take their hardest listed word', () {
      expect(lex.resolve('pour coffee', 'phrase').level, 'A2');
      expect(lex.resolve('on the table', 'phrase').level, 'A1');
    });

    test('unlisted words: frequency blended with the model, else the model', () {
      final r = lex.resolve('sourdough', 'noun', modelLevel: 'B1', zipf: 2.78);
      expect((r.level, r.source), ('C1', 'frequency'));
      expect(lex.resolve('zzword', 'noun', modelLevel: 'B2').source, 'ai');
      expect(lex.resolve('zzword', 'noun').level, 'B1');
      expect(CefrLexicon.levelFromZipf(5.5), 'A1');
      expect(CefrLexicon.levelFromZipf(2.0), 'C2');
    });

    test('IPA from CMUdict, phrases joined; quick-check samples', () {
      expect(lex.ipaOf('balcony'), '/ˈbælkəni/');
      expect(lex.ipaOf('ice cream'), '/aɪs krim/');
      final a1 = lex.sample('A1', 3);
      expect(a1, hasLength(3));
      expect(a1.every((w) => lex.resolve(w, 'noun').level == 'A1'), isTrue);
      expect(lex.sample('A1', 3), a1, reason: 'same words every time');
    });
  });

  group('parseCandidates', () {
    test('server shape → candidates with corrected levels', () {
      final list = parseCandidates({
        'candidates': [
          {
            'word': 'Mug',
            'pos': 'noun',
            'meaning': '馬克杯',
            'cefr': 'A1',
            'evidence': 'white mug',
            'point': [0.64, 0.41],
            'visualConfidence': 0.95,
            'usefulness': 0.8,
            'inferred': false,
          },
          {
            'word': 'steaming',
            'pos': 'adjective',
            'zh': '冒熱氣的',
            'point': [640, 410]
          },
          {'word': 'mug', 'pos': 'noun'},
        ],
      }, lexicon: testLexicon(), focus: 'harder');
      expect(list.map((c) => c.word), ['mug', 'steaming']);
      expect((list[0].level, list[0].levelSource, list[0].modelLevel), ('A2', 'cefr-j', 'A1'));
      expect(list[0].focus, 'harder');
      expect((list[1].pos, list[1].meaning), ('adj.', '冒熱氣的'));
      expect((list[1].point.x, list[1].point.y), (0.64, 0.41)); // 0–1000 grid
    });
  });

  group('WordSelector (第二階段 · 選擇學習詞)', () {
    const selector = WordSelector();
    final profile = UserVocabularyProfile.start('A1', now: testNow);

    Selection pick(
      List<WordCandidate> pool, {
      int target = 0,
      UserVocabularyProfile? p,
      Set<String> studying = const {},
      Set<String> removed = const {},
      List<String> current = const [],
      Set<String> locked = const {},
      PosBias bias = PosBias.none,
    }) =>
        selector.select(
          pool: pool,
          target: target,
          profile: p ?? profile,
          studying: studying,
          removed: removed,
          current: current,
          locked: locked,
          bias: bias,
          now: testNow,
        );

    final breakfast = [
      c('apple'),
      c('bread'),
      c('coffee'),
      c('plate'),
      c('spoon'),
      c('table'),
      c('mug', level: 'A2'),
      c('warm', pos: 'adj.'),
      c('fresh', pos: 'adj.', level: 'A2'),
      c('pour coffee', pos: 'phrase', level: 'A2'),
      c('saucer', level: 'B2'),
      c('rustic', pos: 'adj.', level: 'C1'),
      c('steaming', pos: 'adj.', level: 'B1', inferred: true),
    ];

    test('at most five words, at most three nouns, mixed parts of speech', () {
      final sel = pick(breakfast);
      expect(sel.words, hasLength(5));
      expect(sel.words.where((w) => w.isNoun).length, lessThanOrEqualTo(3));
      expect(sel.words.map((w) => w.pos).toSet().length, greaterThanOrEqualTo(2));
      expect(sel.scored, hasLength(breakfast.length));
    });

    test('one challenge word above the target level', () {
      final sel = pick(breakfast);
      expect(sel.words.any((w) => w.level != 'A1'), isTrue);
    });

    test('learned, studied-elsewhere and removed words are not offered, with reasons', () {
      final p = profile.withFamiliarity('apple', Familiarity.mastered, testNow);
      final sel = pick(breakfast, p: p, studying: {'bread'}, removed: {'coffee'});
      final words = sel.words.map((w) => w.word);
      expect(words, isNot(contains('apple')));
      expect(words, isNot(contains('bread')));
      expect(words, isNot(contains('coffee')));
      String? reason(String w) => sel.scored.firstWhere((s) => s.word == w).rejected;
      expect(reason('apple'), '已學會');
      expect(reason('bread'), '已在學習（其他照片）');
      expect(reason('coffee'), '本次已移除');
    });

    test('synonyms and one word family keep one member', () {
      expect(WordSelector.related(c('cup', meaning: '杯子'), c('mug', meaning: '杯子')), isTrue);
      expect(WordSelector.related(c('bake'), c('baking')), isTrue);
      expect(WordSelector.related(c('fresh'), c('freshly')), isTrue);
      expect(WordSelector.related(c('plate'), c('plant')), isFalse);
      final sel = pick([c('bake', pos: 'verb'), c('baking', pos: 'verb'), c('bread')]);
      expect(sel.words.where((w) => w.word.startsWith('bak')), hasLength(1));
    });

    test('changing level keeps fitting and starred words, replaces the rest', () {
      final first = pick(breakfast);
      final current = [for (final w in first.words) w.word];
      final starred =
          current.firstWhere((w) => breakfast.firstWhere((c) => c.word == w).level == 'A1');
      final harder = pick(breakfast, target: 3, current: current, locked: {starred});
      expect(harder.words.map((w) => w.word), contains(starred));
      // An A1 word two levels below B2 doesn't fit any more.
      final dropped = current
          .where((w) => w != starred)
          .where((w) => breakfast.firstWhere((c) => c.word == w).level == 'A1');
      for (final w in dropped) {
        expect(harder.words.map((x) => x.word), isNot(contains(w)));
      }
      // Kept words stay in their places (no jumping around).
      final again = pick(breakfast, current: current);
      expect(again.words.map((w) => w.word), current);
    });

    test('更多動作 favours verbs and verb phrases', () {
      final pool = [
        ...breakfast,
        c('sip', pos: 'verb', level: 'B1'),
        c('stir', pos: 'verb', level: 'B1'),
      ];
      final plain = pick(pool).words.where((w) => w.isAction).length;
      final actions = pick(pool, bias: PosBias.actions).words.where((w) => w.isAction).length;
      expect(actions, greaterThan(plain));
    });

    test('too few words for a level → ask the model for more (候選不足才重新呼叫模型)', () {
      expect(pick(breakfast).topUp, isNull);
      expect(pick(breakfast, target: 5).topUp, 'harder');
      expect(pick([c('apple'), c('bread')]).topUp, isNotNull);
      final sel = pick([c('apple', vc: 0.1), c('bread')]);
      expect(sel.words.map((w) => w.word), ['bread']);
      expect(sel.scored.first.explain(), contains('程度適配'));
    });

    test('all-noun vision pool asks for another part of speech', () {
      final nouns = [
        c('laptop'), c('notebook'), c('cup'), c('mouse'),
        c('plant'), c('phone'), c('desk'), c('shelf'),
      ];
      final first = pick(nouns, target: 1);
      expect(first.words, hasLength(WordSelector.maxNouns));
      expect(first.words.every((word) => word.isNoun), isTrue);
      expect(first.topUp, 'actions');

      final mixed = pick([
        ...nouns,
        c('type', pos: 'verb', level: 'A2'),
        c('write', pos: 'verb', level: 'A2'),
      ], target: 1);
      expect(mixed.words, hasLength(WordSelector.maxWords));
      expect(mixed.words.where((word) => word.isNoun), hasLength(3));
      expect(mixed.topUp, isNull);
    });
  });

  group('UserVocabularyProfile (Elo 能力模型)', () {
    test('starts mid-band; signals move ability by K × (實際 − 預期)', () {
      final p = UserVocabularyProfile.start('B1', now: testNow);
      expect((p.ability, p.level, p.cefr), (2.5, 2, 'B1'));
      final known = p.update(const KnownWordSignal('C1'), testNow);
      expect(known.ability, greaterThan(p.ability));
      final forgot = p.update(const RecallSignal('A1', 0), testNow);
      expect(forgot.ability, lessThan(p.ability));
      // Dial moves are a weaker signal than active recall.
      final dial = p.update(const DialSignal(1), testNow).ability - p.ability;
      final recall = p.update(const RecallSignal('C2', 1), testNow).ability - p.ability;
      expect(dial, greaterThan(0));
      expect(recall, greaterThan(dial));
    });

    test('scheduled reviews use the FSRS recall expectation', () {
      final p = UserVocabularyProfile.start('A1', now: testNow);
      final routine = p.update(
          const RecallSignal('C2', .9, expectedRecall: .9), testNow);
      final surprise = p.update(
          const RecallSignal('C2', .9, expectedRecall: .3), testNow);
      expect(routine.ability, closeTo(p.ability, 1e-12));
      expect(surprise.ability, greaterThan(routine.ability));
    });

    test('the level changes only after 20 signals, past a 0.2 buffer, one step at a time', () {
      var p = UserVocabularyProfile.start('A1', now: testNow);
      for (var i = 0; i < 19; i++) {
        p = p.update(const RecallSignal('C2', 1), testNow);
      }
      expect(p.level, 0, reason: 'fewer than 20 signals');
      expect(p.smoothed, greaterThan(1.2));
      p = p.update(const RecallSignal('C2', 1), testNow);
      expect(p.level, 1, reason: 'one level at a time');
      expect(p.source, 'elo');
      for (var i = 0; i < 200; i++) {
        p = p.update(const RecallSignal('A1', 0), testNow);
      }
      expect(p.level, 0);
    });

    test('suggests a new default level when the dial keeps going one way', () {
      var p = UserVocabularyProfile.start('A2', now: testNow);
      for (final o in [1, 0, 1, 1, 2]) {
        p = p.dialled(o, testNow);
      }
      expect(p.suggestedShift, 0);
      p = p.dialled(1, testNow);
      expect(p.suggestedShift, 1);
    });

    test('unknown probability, learned list and JSON round trip', () {
      var p = UserVocabularyProfile.start('B1', now: testNow);
      expect(p.unknownProbability('cat', 'A1'), lessThan(0.2));
      expect(p.unknownProbability('ubiquitous', 'C2'), greaterThan(0.9));
      p = p
          .withFamiliarity('cat', Familiarity.mastered, testNow)
          .exposed(['cat', 'dog'], testNow).keptPos(['noun'], testNow).dialled(-1, testNow);
      expect(p.unknownProbability('cat', 'A1'), 0);
      expect(p.learned, {'cat'});
      final back = UserVocabularyProfile.fromJson(p.toJson());
      expect(back.learned, {'cat'});
      expect(back.exposure['dog']!.count, 1);
      expect(back.posPreference, {'noun': 1});
      expect(back.dialHistory, [-1]);
      expect(back.ability, p.ability);
    });
  });
}
