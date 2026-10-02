import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

/// Spec section 7: 使用者修改值優先於後續自動更新，不得被覆寫 — for every
/// field the edit dialog offers, not only the meaning.
void main() {
  test('every edited field survives a dictionary update', () {
    final pack = LexiconPack()
      ..loadJson(jsonDecode(File('assets/lexicon/en-zh-TW.json').readAsStringSync())
          as Map<String, dynamic>);
    final w = pack.catalogWords.firstWhere((w) => w.full && w.examples.isNotEmpty && w.ipa != null);
    final repo = WordDatabaseRepository(clock: () => testNow);
    final e = repo.addWord(word: w.lemma, pos: shortPos(w.pos), meaning: w.learnerMeaning ?? '', level: w.cefr);
    repo.linkLexicon(pack);
    final linked = repo.entry(e.id)!;
    expect(linked.examples, isNotEmpty);
    repo.editEntry(
        linked.copyWith(
          meaning: '我的意思',
          definition: () => 'my definition',
          ipa: () => '/maɪ/',
          level: () => 'C2',
          examples: const [WordExample(text: 'My own sentence.', translation: '我的句子')],
        ),
        {WordField.meaning, WordField.definition, WordField.ipa, WordField.level, WordField.examples});
    repo.linkLexicon(pack);
    final after = repo.entry(e.id)!;
    expect(after.meaning, '我的意思');
    expect(after.definition, 'my definition');
    expect(after.ipa, '/maɪ/');
    expect(after.level, 'C2');
    expect(after.examples.map((x) => x.text), ['My own sentence.']);
  });
}
