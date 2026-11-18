// Card #1218 (問題回報 #1670): every word opens — the learner's word book, then
// the lexicon pack, then the compact offline dictionary; French letters,
// elisions and hyphens are split right.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/compact_dictionary.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

void main() {
  CompactDictionary.instance
    ..openFile('en', 'zh-TW', 'assets/compact/compact_en_zh-TW.sqlite')
    ..openFile('fr', 'en', 'assets/compact/compact_fr_en.sqlite');
  setUp(() => LexiconPack.instance.clear());

  WordLinks links(String lang) => WordLinks.of(WordDatabaseRepository(
      clock: () => testNow, entries: const [], language: lang));

  List<String> linked(WordLinks l, String text) => [
        for (final s in l.segments(text))
          if (s.id != null) s.text
      ];

  test('English: a word only the compact dictionary has opens it', () {
    final l = links('en');
    expect(l.idFor('serendipity'), 'compact:serendipity');
    expect(l.idFor('went'), 'compact:went');
    expect(l.idFor('qqzzxx'), isNull);
    expect(linked(l, 'A serendipity, qqzzxx.'), ['A', 'serendipity']);
  });

  test('French: accents and elision', () {
    final l = links('fr');
    expect(l.idFor('arbre'), startsWith('compact:'));
    final segs = l.segments("Voir l'arbre, l’arbre.");
    expect([for (final s in segs) if (s.id != null) s.text],
        contains('arbre'));
    // The elided l' stays plain text.
    expect(segs.where((s) => s.id != null).every((s) => !s.text.contains("'")),
        isTrue);
    expect(linked(l, 'Un été très chaud'), contains('été'));
  });

  test('nothing known stays plain', () {
    final l = links('fr');
    expect(l.segments('qqzzxx').single.id, isNull);
  });

  test('long text is quick and cached', () {
    final l = links('en');
    final text = List.filled(400, 'The serendipity of went and bus.').join(' ');
    final sw = Stopwatch()..start();
    l.segments(text);
    final first = sw.elapsedMilliseconds;
    sw.reset();
    l.segments(text);
    expect(sw.elapsedMilliseconds, lessThanOrEqualTo(first));
    expect(first, lessThan(500));
  });
}
