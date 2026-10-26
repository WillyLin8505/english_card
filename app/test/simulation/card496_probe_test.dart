import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

void main() {
  test('card496 read-only link diagnostics', () {
    final pack = LexiconPack.instance..loadJson(jsonDecode(File('build/rounds_fr/23/pack.json').readAsStringSync()));
    const levels = ['A1','A2','B1','B2','C1','C2'];
    String pos(String p) => p == 'adj' ? 'adj.' : p == 'adv' ? 'adv.' : p;
    final near = pack.catalogWords.where((w) => w.full && w.cefr != null && levels.indexOf(w.cefr!).abs() <= 1).toList()..shuffle(Random(23));
    final repo = WordDatabaseRepository(language: 'fr');
    for (final w in near) {
      if (repo.entries.length >= 40) break;
      try { repo.addWord(word:w.lemma, pos:pos(w.pos), meaning:w.learnerMeaning ?? '', level:w.cefr); } on DuplicateWordException { continue; }
    }
    final before = repo.entries.map((e)=>e.word).toList();
    final mappings = [for(final e in repo.entries) if(pack.lookup(e.word,pos:e.pos)?.entry.normalized != e.word) {'word':e.word,'to':pack.lookup(e.word,pos:e.pos)?.entry.normalized}];
    final all = [for(final w in pack.catalogWords) if(w.full && pack.lookup(w.lemma,pos:pos(w.pos))?.entry.normalized != w.normalized) {'word':w.lemma,'pos':w.pos,'to':pack.lookup(w.lemma,pos:pos(w.pos))?.entry.normalized}];
    repo.linkLexicon(pack);
    final result={'before':before,'after':repo.entries.map((e)=>e.word).toList(),'mappings':mappings,'all_redirects':all};
    File('build/rounds_fr/23/card496_link_probe.json').writeAsStringSync(jsonEncode(result));
    print('before=${before.length} after=${repo.entries.length} mappings=$mappings all_redirects=${all.length}');
    expect(before.length,40);
  });
}
