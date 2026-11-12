import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/compact_dictionary.dart';

// Card #1075 (問題回報 #1598): the compact offline dictionary built by
// lexicon/tools/card1075_build_compact.py answers words the full pack lacks.
void main() {
  final d = CompactDictionary.instance
    ..openFile('en', 'zh-TW', 'assets/compact/compact_en_zh-TW.sqlite')
    ..openFile('fr', 'en', 'assets/compact/compact_fr_en.sqlite');

  test('rare English words: meaning, part of speech, IPA', () {
    for (final w in ['serendipity', 'pernicious', 'ephemeral']) {
      final h = d.lookup(w, 'en', 'zh-TW')!;
      expect(h.meaning, isNotEmpty);
      expect(h.ipa, isNotNull);
      expect(h.viaForm, isFalse);
    }
    expect(d.lookup('Serendipity', 'en', 'zh-TW')!.pos, 'noun');
    expect(d.lookup('pernicious', 'en', 'zh-TW')!.pos, 'adj');
  });

  test('Chinese is Taiwan usage, not Simplified', () {
    final m = d.lookup('pernicious', 'en', 'zh-TW')!.meaning;
    expect(m, contains('險惡'));
    expect(m, isNot(contains('险')));
  });

  // Card #1098 (問題回報 #1605): mainland terms → Taiwan terms; POS as App values.
  test('bus says 公車 (Taiwan), not 公共汽車', () {
    final h = d.lookup('bus', 'en', 'zh-TW')!;
    expect(h.meaning, contains('公車'));
    expect(h.meaning, isNot(contains('公共汽車')));
    expect(d.lookup('taxi', 'en', 'zh-TW')!.meaning, contains('計程車'));
  });

  test('pos is the App value, not the ECDICT code', () {
    expect(d.lookup('bus', 'en', 'zh-TW')!.pos, 'noun');
    expect(d.lookup('mass', 'en', 'zh-TW')!.pos, 'noun');
    expect(d.lookup('software', 'en', 'zh-TW')!.pos, 'noun');
  });

  test('definitions carry each line\'s pos and no ECDICT prefix', () {
    final det = d.lookup('mass', 'en', 'zh-TW')!.toDetail('精簡字典');
    final poss = det.definitions.map((x) => x.pos).toSet();
    expect(poss, containsAll(['noun', 'adj', 'verb']));
    for (final x in det.definitions) {
      expect(x.gloss, isNot(matches(RegExp(r'^[a-z]{1,6}\.\s'))));
      expect(x.gloss, isNot(contains('：')));
    }
  });

  test('inflected forms resolve to the base word (went → go)', () {
    final h = d.lookup('went', 'en', 'zh-TW')!;
    expect(h.word, 'go');
    expect(h.viaForm, isTrue);
    expect(d.lookup('running', 'en', 'zh-TW')!.word, 'run');
  });

  test('French → English', () {
    expect(d.lookup('flâner', 'fr', 'en')!.meaning, contains('wander'));
    expect(d.lookup('mangeons', 'fr', 'en')!.word, 'manger');
  });

  test('unknown word and unopened pair give null; toDetail carries the source',
      () {
    expect(d.lookup('qqzzxx', 'en', 'zh-TW'), isNull);
    expect(d.lookup('serendipity', 'de', 'en'), isNull);
    final det = d.lookup('serendipity', 'en', 'zh-TW')!.toDetail('精簡字典');
    expect(det.definitionsSource, '精簡字典');
    expect(det.definitions, isNotEmpty);
  });

  test('basic flag survives JSON and defaults to false', () {
    final e = WordEntry.fromUserInput(
        id: 'w1',
        word: 'serendipity',
        meaning: 'x',
        basic: true,
        now: DateTime(2026));
    expect(WordEntry.fromJson(e.toJson()).basic, isTrue);
    final j = e.toJson()..remove('basic');
    expect(WordEntry.fromJson(j).basic, isFalse);
  });
}
