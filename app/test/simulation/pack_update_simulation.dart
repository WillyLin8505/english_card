// Dictionary update simulation (not part of the regular suite).
//
// While a learner studies, the admin keeps publishing new dictionary versions:
// meanings change, translations arrive, some entries disappear. After each
// update (DictionarySync → linkLexicon) the learner's data must hold: card
// ids, FSRS state and review logs never change; meanings the learner edited
// stay; other meanings follow the new version (AUTO_SYNC.md; spec section 7:
// 使用者修改值優先於後續自動更新).
//
//   flutter test test/simulation/pack_update_simulation.dart  (SIM_PACK, SIM_SEED)

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'learner_simulation.dart' show Findings, allCards, answer;

void main() {
  test('learner data survives dictionary updates', () {
    final env = Platform.environment;
    final rnd = Random(int.parse(env['SIM_SEED'] ?? '1'));
    final json = jsonDecode(File(env['SIM_PACK'] ?? 'assets/lexicon/en-zh-TW.json')
        .readAsStringSync()) as Map<String, dynamic>;
    final pack = LexiconPack.instance..loadJson(json);
    var now = DateTime(2026, 10, 1, 20);
    final repo = WordDatabaseRepository(
        clock: () => now, profile: UserVocabularyProfile.start('A2', now: now));
    final f = Findings();
    final full = pack.catalogWords.where((w) => w.full && !w.rareUsage).toList()..shuffle(rnd);
    for (final w in full.take(80)) {
      try {
        repo.addWord(word: w.lemma, pos: shortPos(w.pos), meaning: w.learnerMeaning ?? '', level: w.cefr);
      } on DuplicateWordException {
        continue; // one card per spelling
      }
    }
    repo.linkLexicon(pack);
    final edited = <String, String>{};
    for (var version = 1; version <= 12; version++) {
      // Study a little.
      final s = FlashcardSession(repo, random: rnd);
      var n = 0;
      while (!s.finished && n < 40) {
        final c = s.card!;
        s.showAnswer();
        s.rate(answer(repo, c, repo.entry(c.wordEntryId)!, rnd, now));
        n++;
      }
      // The learner edits a meaning.
      final e = repo.entries[rnd.nextInt(repo.entries.length)];
      final mine = '我寫的意思$version';
      repo.editEntry(e.copyWith(meaning: mine), {WordField.meaning});
      edited[e.id] = mine;

      // A new dictionary version: changed meanings, and one entry gone.
      final lexemes = [for (final l in json['lexemes'] as List) Map<String, dynamic>.from(l as Map)];
      final changed = <String, String>{};
      for (final l in lexemes) {
        if (l['status'] != 'full' || rnd.nextDouble() > 0.15) continue;
        final senses = [for (final x in (l['senses'] as List? ?? [])) Map<String, dynamic>.from(x as Map)];
        if (senses.isEmpty) continue;
        senses[0]['native'] = '新版$version-${l['lemma']}';
        l['senses'] = senses;
        changed['${l['normalized']}|${l['pos']}'] = senses[0]['native'] as String;
      }
      final gone = lexemes.where((l) => l['status'] == 'full').toList()[rnd.nextInt(50)];
      final goneWord = gone['normalized'];
      lexemes.remove(gone);
      final next = {...json, 'lexemes': lexemes, 'created_at': 'v$version'};

      final before = {for (final c in allCards(repo)) c.id: jsonEncode(c.toJson())};
      final logs = {for (final c in allCards(repo)) c.id: repo.logsOf(c.id).length};
      pack.loadJson(next);
      final shown = {
        for (final w in pack.catalogWords) '${w.lemma}|${w.pos}': w.learnerMeaning,
      };
      repo.linkLexicon(pack);
      for (final c in allCards(repo)) {
        if (before[c.id] != jsonEncode(c.toJson())) f.add('詞庫更新改動了卡片或 FSRS', '${c.id} v$version');
        if (logs[c.id] != repo.logsOf(c.id).length) f.add('詞庫更新改動了複習紀錄', '${c.id} v$version');
      }
      if (before.length != allCards(repo).length) f.add('詞庫更新後卡片數量變了', '${before.length} → ${allCards(repo).length}');
      for (final x in edited.entries) {
        final e = repo.entry(x.key);
        if (e == null) {
          f.add('詞庫更新後詞條不見了', x.key);
        } else if (e.meaning != x.value) {
          f.add('詞庫更新蓋掉使用者改的意思', '${e.word}：${x.value} → ${e.meaning}');
        }
      }
      for (final e in repo.entries) {
        if (edited.containsKey(e.id) || e.word == goneWord) continue;
        final want = changed['${e.word}|${LexiconPack.packPos(e.pos)}'];
        // Only when the changed sense is one the front uses (rare and
        // other-etymology senses are skipped, #18/#76).
        final front = shown['${e.word}|${LexiconPack.packPos(e.pos)}'] ?? '';
        if (want != null && front.contains(want) && !e.meaning.contains(want)) {
          f.add('沒改過的字沒有拿到新版意思', '${e.word}：${e.meaning}（新版 $want）');
        }
        if (e.word == goneWord && e.meaning.isEmpty) {
          f.add('詞庫刪掉的字，學習中的卡失去中文意思', e.word);
        }
      }
      now = now.add(const Duration(days: 2));
    }
    final report = {'findings': f.toJson()};
    File(env['SIM_OUT'] ?? 'build/pack_update_simulation.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert({'counts': f.counts}));
  });
}
