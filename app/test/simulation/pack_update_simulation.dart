// Dictionary update simulation (not part of the regular suite).
//
// While a learner studies, the admin keeps publishing new dictionary versions:
// meanings change, translations arrive, some entries disappear. After each
// update the learner's data must hold: card ids, FSRS state and review logs
// never change; meanings the learner edited stay; other meanings follow the
// new version (AUTO_SYNC.md; spec section 7: 使用者修改值優先於後續自動更新).
//
// Two paths, as the app takes them:
// - JSON: pack.loadJson + repo.linkLexicon (synchronous; desktop / web).
// - SQLite: each version written as a pack file, opened with
//   LexiconPack.openSqlite (background isolate) and linked with
//   linkLexiconInBatches (DictionarySync on a phone, #428 / M-PERF2). While
//   the batches pause, the learner edits a meaning, rates a card and
//   archives a word; afterwards all three must be as the learner left them.
//   Any finding of this path fails the test.
//
//   flutter test test/simulation/pack_update_simulation.dart  (SIM_PACK, SIM_SEED, SIM_OUT, SIM_SQLITE_VERSIONS)

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'learner_simulation.dart' show Findings, allCards, answer;

Map<String, dynamic> _loadPack() => jsonDecode(File(
        Platform.environment['SIM_PACK'] ?? 'assets/lexicon/en-zh-TW.json')
    .readAsStringSync()) as Map<String, dynamic>;

/// A learner with 80 random everyday words of [pack].
WordDatabaseRepository _learner(LexiconPack pack, Random rnd, DateTime Function() clock) {
  final repo = WordDatabaseRepository(
      clock: clock, profile: UserVocabularyProfile.start('A2', now: clock()));
  final full = pack.catalogWords.where((w) => w.full && !w.rareUsage).toList()..shuffle(rnd);
  for (final w in full.take(80)) {
    try {
      repo.addWord(word: w.lemma, pos: shortPos(w.pos), meaning: w.learnerMeaning ?? '', level: w.cefr);
    } on DuplicateWordException {
      continue; // one card per spelling
    }
  }
  return repo;
}

/// Studies up to 40 cards.
void _study(WordDatabaseRepository repo, Random rnd, DateTime now) {
  final s = FlashcardSession(repo, random: rnd);
  var n = 0;
  while (!s.finished && n < 40) {
    final c = s.card!;
    s.showAnswer();
    s.rate(answer(repo, c, repo.entry(c.wordEntryId)!, rnd, now));
    n++;
  }
}

/// A new dictionary version made from [json]: changed meanings, and one of
/// the learner's own words gone (so the checks have a card to look at).
({Map<String, dynamic> next, Map<String, String> changed, Object? goneWord}) _newVersion(
    Map<String, dynamic> json, int version, Random rnd, WordDatabaseRepository repo) {
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
  final saved = {for (final e in repo.entries) e.word};
  final owned = lexemes.where((l) => l['status'] == 'full' && saved.contains(l['normalized'])).toList();
  final gone = owned.isNotEmpty
      ? owned[rnd.nextInt(owned.length)]
      : lexemes.where((l) => l['status'] == 'full').toList()[rnd.nextInt(50)];
  lexemes.remove(gone);
  return (
    next: {...json, 'lexemes': lexemes, 'created_at': 'v$version'},
    changed: changed,
    goneWord: gone['normalized'],
  );
}

/// The checks after an update: cards and logs as in [before] / [logs]
/// (which already hold what the learner did meanwhile), edited meanings
/// kept, other meanings following the new version.
void _checkUpdate(WordDatabaseRepository repo, Findings f, String tag,
    {required Map<String, String> before,
    required Map<String, int> logs,
    required Map<String, String> edited,
    required Map<String, String> changed,
    required Map<String, String?> shown,
    required Map<String, String> meaningBefore,
    required Object? goneWord}) {
  for (final c in allCards(repo)) {
    if (before[c.id] != jsonEncode(c.toJson())) f.add('詞庫更新改動了卡片或 FSRS', '${c.id} $tag');
    if (logs[c.id] != repo.logsOf(c.id).length) f.add('詞庫更新改動了複習紀錄', '${c.id} $tag');
  }
  if (before.length != allCards(repo).length) {
    f.add('詞庫更新後卡片數量變了', '${before.length} → ${allCards(repo).length} $tag');
  }
  for (final x in edited.entries) {
    final e = repo.entry(x.key);
    if (e == null) {
      f.add('詞庫更新後詞條不見了', '${x.key} $tag');
    } else if (e.meaning != x.value) {
      f.add('詞庫更新蓋掉使用者改的意思', '${e.word}：${x.value} → ${e.meaning} $tag');
    }
  }
  for (final e in repo.entries) {
    // Only a meaning the card had before the update can be lost (card #752,
    // 問題回報 #896: "annum" has no 中文 in the pack, so its card was empty
    // before the word was deleted too).
    if (e.word == goneWord &&
        e.meaning.isEmpty &&
        (meaningBefore[e.id] ?? '').isNotEmpty) {
      f.add('詞庫刪掉的字，學習中的卡失去中文意思', '${e.word} $tag');
    }
    if (edited.containsKey(e.id) || e.word == goneWord) continue;
    final want = changed['${e.word}|${LexiconPack.packPos(e.pos)}'];
    // Only when the changed sense is one the front uses (rare and
    // other-etymology senses are skipped, #18/#76).
    final front = shown['${e.word}|${LexiconPack.packPos(e.pos)}'] ?? '';
    if (want != null && front.contains(want) && !e.meaning.contains(want)) {
      f.add('沒改過的字沒有拿到新版意思', '${e.word}：${e.meaning}（新版 $want） $tag');
    }
  }
}

Map<String, String?> _shown(LexiconPack pack) =>
    {for (final w in pack.catalogWords) '${w.lemma}|${w.pos}': w.learnerMeaning};

void main() {
  final env = Platform.environment;
  final seed = int.parse(env['SIM_SEED'] ?? '1');
  final report = <String, dynamic>{'seed': seed};
  tearDownAll(() {
    File(env['SIM_OUT'] ?? 'build/pack_update_simulation.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
  });

  test('learner data survives dictionary updates', () {
    final rnd = Random(seed);
    final json = _loadPack();
    final pack = LexiconPack.instance..loadJson(json);
    var now = DateTime(2026, 10, 1, 20);
    final repo = _learner(pack, rnd, () => now);
    final f = Findings();
    repo.linkLexicon(pack);
    final edited = <String, String>{};
    for (var version = 1; version <= 12; version++) {
      _study(repo, rnd, now);
      // The learner edits a meaning.
      final e = repo.entries[rnd.nextInt(repo.entries.length)];
      final mine = '我寫的意思$version';
      repo.editEntry(e.copyWith(meaning: mine), {WordField.meaning});
      edited[e.id] = mine;

      final v = _newVersion(json, version, rnd, repo);
      final before = {for (final c in allCards(repo)) c.id: jsonEncode(c.toJson())};
      final logs = {for (final c in allCards(repo)) c.id: repo.logsOf(c.id).length};
      final meaningBefore = {for (final e in repo.entries) e.id: e.meaning};
      pack.loadJson(v.next);
      final shown = _shown(pack);
      repo.linkLexicon(pack);
      _checkUpdate(repo, f, 'v$version',
          before: before, logs: logs, edited: edited, changed: v.changed,
          shown: shown, meaningBefore: meaningBefore, goneWord: v.goneWord);
      now = now.add(const Duration(days: 2));
    }
    report['findings'] = f.toJson();
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert({'json counts': f.counts}));
  });

  test('SQLite updates linked in batches keep what the learner does meanwhile', () async {
    final rnd = Random(seed + 1);
    final json = _loadPack();
    final versions = int.parse(env['SIM_SQLITE_VERSIONS'] ?? '4');
    final dir = await Directory.systemTemp.createTemp('pack_update_sqlite');
    final pack = LexiconPack.instance..clear();
    addTearDown(() async {
      pack.clear();
      try {
        await dir.delete(recursive: true);
      } on FileSystemException {
        // Windows may still hold the last pack file for a moment.
      }
    });
    Future<void> install(Map<String, dynamic> p, String name) async {
      final path = '${dir.path}/$name.sqlite';
      LexiconSqlite.build(p, path);
      pack.replaceWith(await LexiconPack.openSqlite(path));
    }

    await install({...json, 'created_at': 'v0'}, 'v0');
    if (!pack.fromSqlite) fail('the pack did not open from SQLite');
    var now = DateTime(2026, 10, 1, 20);
    final repo = _learner(pack, rnd, () => now);
    await repo.linkLexiconInBatches(pack);
    final f = Findings();
    final edited = <String, String>{};
    final midway = <String, int>{'edit': 0, 'rate': 0, 'archive': 0, 'after the link': 0};
    final timings = <int>[];
    for (var version = 1; version <= versions; version++) {
      _study(repo, rnd, now);
      final v = _newVersion(json, version, rnd, repo);
      final before = {for (final c in allCards(repo)) c.id: jsonEncode(c.toJson())};
      final logs = {for (final c in allCards(repo)) c.id: repo.logsOf(c.id).length};
      final meaningBefore = {for (final e in repo.entries) e.id: e.meaning};
      final watch = Stopwatch()..start();
      await install(v.next, 'v$version');
      final shown = _shown(pack);
      // Zero budget: a pause after every word, so the learner's actions
      // below land between the steps (first loop: forms folding into their
      // word; second: meanings and details merged).
      var done = false;
      final link = repo.linkLexiconInBatches(pack, budget: Duration.zero)
          .whenComplete(() => done = true);
      final steps = repo.entries.length;
      Future<void> pauses(int n) async {
        for (var i = 0; i < n && !done; i++) {
          await Future<void>.delayed(Duration.zero);
        }
      }

      // 1. Edit a meaning while the forms are folded.
      await pauses(3);
      if (done) midway['after the link'] = midway['after the link']! + 1;
      final e = repo.entries[rnd.nextInt(repo.entries.length)];
      final mine = '暫停中改的意思$version';
      repo.editEntry(e.copyWith(meaning: mine), {WordField.meaning});
      edited[e.id] = mine;
      if (!done) midway['edit'] = midway['edit']! + 1;

      // 2. Rate a card while the meanings are merged.
      await pauses(steps ~/ 3);
      final active = allCards(repo).where((c) => !c.archived).toList();
      if (active.isNotEmpty) {
        final c = active[rnd.nextInt(active.length)];
        repo.review(c.id, Rating.good);
        before[c.id] = jsonEncode(repo.cardOf(c.wordEntryId)!.toJson());
        logs[c.id] = (logs[c.id] ?? 0) + 1;
        if (!done) midway['rate'] = midway['rate']! + 1;
      }

      // 3. Archive a word a little later.
      await pauses(steps ~/ 3);
      final keep = allCards(repo).where((c) => !c.archived).toList();
      String? archivedEntry;
      if (keep.isNotEmpty) {
        final c = keep[rnd.nextInt(keep.length)];
        repo.archiveWord(c.wordEntryId);
        archivedEntry = c.wordEntryId;
        before[c.id] = jsonEncode(repo.cardOf(c.wordEntryId)!.toJson());
        if (!done) midway['archive'] = midway['archive']! + 1;
      }
      await link;
      timings.add(watch.elapsedMilliseconds);

      _checkUpdate(repo, f, 'sqlite v$version',
          before: before, logs: logs, edited: edited, changed: v.changed,
          shown: shown, meaningBefore: meaningBefore, goneWord: v.goneWord);
      if (archivedEntry != null && !repo.isArchived(archivedEntry)) {
        f.add('暫停中封存的字，連結詞庫後沒有封存', '$archivedEntry sqlite v$version');
      }
      if (pack.version != 'v$version' || !pack.fromSqlite) {
        f.add('SQLite 詞庫沒有換成新版', '${pack.version} sqlite v$version');
      }
      now = now.add(const Duration(days: 2));
    }
    report['sqlite'] = {
      'versions': versions,
      'actions during the link pauses': midway,
      'open + link ms per version': timings,
      'findings': f.toJson(),
    };
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert(report['sqlite']));
    expect(midway['after the link'], 0,
        reason: 'the learner actions must land while the batches pause');
    expect(f.counts, isEmpty, reason: const JsonEncoder.withIndent(' ').convert(f.toJson()));
  }, timeout: const Timeout(Duration(minutes: 10)));
}
