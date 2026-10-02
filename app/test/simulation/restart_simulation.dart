// Restart simulation (not part of the regular suite: no _test suffix).
//
// A learner studies with the real Hive store; every few days the app is
// closed and opened again. Everything — words, learner edits, cards, FSRS,
// review logs, the ability profile, archived words — must come back exactly,
// and a dictionary refresh after the restart must not undo learner edits.
//
//   flutter test test/simulation/restart_simulation.dart
//
// Environment: SIM_PACK, SIM_DAYS (40), SIM_NEW (6), SIM_SEED (1),
// SIM_OUT (build/restart_simulation.json)

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_database_store.dart';

import 'learner_simulation.dart' show Findings, allCards, answer;

final _env = Platform.environment;
String _opt(String k, String d) => _env[k] ?? d;

Map<String, String> snapshot(WordDatabaseRepository r) => {
      for (final e in r.entries) 'entry:${e.id}': jsonEncode(e.toJson()),
      for (final c in allCards(r)) 'card:${c.id}': jsonEncode(c.toJson()),
      for (final c in allCards(r)) 'logs:${c.id}': '${r.logsOf(c.id).length}',
      'profile': jsonEncode(r.profile.toJson()),
      for (final p in r.photos) 'photo:${p.id}': jsonEncode(p.toJson()),
    };

void main() {
  final days = int.parse(_opt('SIM_DAYS', '40'));
  final perDay = int.parse(_opt('SIM_NEW', '6'));
  final seed = int.parse(_opt('SIM_SEED', '1'));

  test('everything survives restarts', () async {
    final pack = LexiconPack.instance
      ..loadJson(jsonDecode(File(_opt('SIM_PACK', 'assets/lexicon/en-zh-TW.json'))
          .readAsStringSync()) as Map<String, dynamic>);
    final dir = await Directory.systemTemp.createTemp('restart_sim');
    addTearDown(() async {
      await Hive.close();
      await dir.delete(recursive: true);
    });
    Hive.init(dir.path);
    final rnd = Random(seed);
    var now = DateTime(2026, 10, 1, 20);
    var store = await HiveWordDatabaseStore.open();
    await store.seed(WordDatabaseData(profile: UserVocabularyProfile.start('A2', now: now)));
    var repo = WordDatabaseRepository.fromData(store.load(), store: store, clock: () => now);
    final f = Findings();
    final pool = pack.catalogWords.where((w) => w.full && !w.rareUsage).toList()..shuffle(rnd);
    var next = 0, restarts = 0, reviews = 0;
    final edited = <String, String>{};

    for (var day = 0; day < days; day++) {
      for (var i = 0; i < perDay && next < pool.length; i++) {
        final w = pool[next++];
        try {
          repo.addWord(word: w.lemma, pos: shortPos(w.pos),
              meaning: w.learnerMeaning ?? '', level: w.cefr);
        } on DuplicateWordException {
          continue;
        }
      }
      repo.linkLexicon(pack);
      // The learner corrects a meaning now and then (使用者修改值優先).
      if (rnd.nextDouble() < 0.3 && repo.entries.isNotEmpty) {
        final e = repo.entries[rnd.nextInt(repo.entries.length)];
        final mine = '我的意思${edited.length}';
        repo.editEntry(e.copyWith(meaning: mine), {WordField.meaning});
        edited[e.id] = mine;
      }
      // …and archives or restores a word.
      if (rnd.nextDouble() < 0.2 && repo.entries.length > 3) {
        final e = repo.entries[rnd.nextInt(repo.entries.length)];
        if (repo.isArchived(e.id)) {
          repo.restoreWord(e.word);
        } else {
          repo.archiveWord(e.id);
        }
      }
      final s = FlashcardSession(repo, random: rnd);
      var step = 0;
      while (!s.finished && step < 400) {
        final c = s.card!;
        final e = repo.entry(c.wordEntryId)!;
        s.showAnswer();
        s.rate(answer(repo, c, e, rnd, now));
        reviews++;
        step++;
        now = now.add(const Duration(seconds: 15));
      }

      if (day % 3 == 2) {
        final before = snapshot(repo);
        await repo.flush();
        await Hive.close();
        Hive.init(dir.path);
        store = await HiveWordDatabaseStore.open();
        if (store.needsSeed) f.add('重開後要求重新初始化（資料會被清掉）', 'day $day');
        repo = WordDatabaseRepository.fromData(store.load(), store: store, clock: () => now);
        restarts++;
        final after = snapshot(repo);
        for (final k in {...before.keys, ...after.keys}) {
          if (before[k] != after[k]) {
            f.add('重開後資料不同：${k.split(':').first}',
                '$k day $day\n前 ${before[k]?.substring(0, min(160, before[k]!.length))}\n後 ${after[k]?.substring(0, min(160, after[k]!.length))}');
          }
        }
        // A dictionary refresh right after starting must keep learner edits.
        repo.linkLexicon(pack);
        for (final e in edited.entries) {
          final now = repo.entry(e.key);
          if (now != null && now.meaning != e.value) {
            f.add('詞庫更新蓋掉使用者改的中文意思', '${now.word}：${e.value} → ${now.meaning}');
          }
        }
      }
      now = DateTime(now.year, now.month, now.day + 1, 20);
    }
    await repo.flush();
    final report = {
      'totals': {'days': days, 'restarts': restarts, 'reviews': reviews,
        'cards': allCards(repo).length, 'edited': edited.length},
      'findings': f.toJson(),
    };
    File(_opt('SIM_OUT', 'build/restart_simulation.json'))
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert(report));
  }, timeout: const Timeout(Duration(minutes: 30)));
}
