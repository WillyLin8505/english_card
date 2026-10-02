// Random-action simulation (not part of the regular suite).
//
// Thousands of learner actions in random order — photos arriving from the
// tagger, the photo page (dial, swipe, star, correct, restore, leave), words
// added from the database, meanings edited, photos removed, review runs,
// level changes, days passing — with the data checked after every step and
// the whole state saved and reloaded through Hive at the end.
//
//   flutter test test/simulation/fuzz_simulation.dart  (SIM_PACK, SIM_STEPS, SIM_SEED)

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_database_store.dart';
import 'package:photo_english_app/services/word_selector.dart';

import '../helpers.dart';
import 'learner_simulation.dart' show Findings, allCards, answer;
import 'restart_simulation.dart' show snapshot;

void check(WordDatabaseRepository r, Findings f, String step, {String? openPhoto}) {
  final words = <String, int>{};
  for (final e in r.entries) {
    words[e.word] = (words[e.word] ?? 0) + 1;
  }
  for (final w in words.entries) {
    if (w.value > 1) f.add('同一個拼字有兩個以上的詞條（規格：一個拼字一張卡）', '${w.key} ×${w.value} @$step');
  }
  final cardsPerEntry = <String, int>{};
  for (final c in allCards(r)) {
    cardsPerEntry[c.wordEntryId] = (cardsPerEntry[c.wordEntryId] ?? 0) + 1;
    if (r.entry(c.wordEntryId) == null) f.add('卡片指向不存在的詞條', '${c.id} @$step');
  }
  for (final p in r.photos) {
    for (final o in r.occurrencesInPhoto(p.id)) {
      if (r.entry(o.wordEntryId) == null) f.add('照片情境指向不存在的詞條', '${o.id} @$step');
      if (o.anchor.x < 0 || o.anchor.x > 1 || o.anchor.y < 0 || o.anchor.y > 1) {
        f.add('標籤位置超出照片', '${o.id} (${o.anchor.x},${o.anchor.y}) @$step');
      }
    }
    // A photo page still open saves its list when it is left.
    if (p.id == openPhoto) continue;
    final listed = r.activeLabels(p.id).where((l) => !l.occ.contextOnly).length;
    if (listed > WordSelector.maxWords) f.add('照片的列表字超過 5 個', '${p.id} $listed @$step');
  }
  final now = r.clock();
  for (final c in r.eligibleCards()) {
    if (c.archived) f.add('已學會的卡出現在複習', '${c.id} @$step');
    if (!r.isEligible(c, now)) f.add('eligibleCards 與 isEligible 不一致', '${c.id} @$step');
  }
  final lv = r.profile.level;
  if (lv < 0 || lv > 5) f.add('程度超出範圍', '$lv @$step');
}

void main() {
  test('random learner actions keep the data consistent', () async {
    final env = Platform.environment;
    final seed = int.parse(env['SIM_SEED'] ?? '1');
    final steps = int.parse(env['SIM_STEPS'] ?? '1500');
    final rnd = Random(seed);
    final pack = LexiconPack.instance
      ..loadJson(jsonDecode(File(env['SIM_PACK'] ?? 'assets/lexicon/en-zh-TW.json')
          .readAsStringSync()) as Map<String, dynamic>);
    final replies = [
      for (final file in Directory('../tagger/cache').listSync().whereType<File>())
        if (!file.uri.pathSegments.last.startsWith('score-')) file
    ]..sort((a, b) => a.path.compareTo(b.path));
    final dir = await Directory.systemTemp.createTemp('fuzz_sim');
    addTearDown(() async {
      await Hive.close();
      await dir.delete(recursive: true);
    });
    Hive.init(dir.path);
    var now = DateTime(2026, 10, 1, 9);
    final store = await HiveWordDatabaseStore.open();
    await store.seed(WordDatabaseData(profile: UserVocabularyProfile.start('A2', now: now)));
    final repo = WordDatabaseRepository.fromData(store.load(), store: store, clock: () => now);
    final f = Findings();
    final pool = pack.catalogWords.where((w) => w.full).toList();
    var photoN = 0;
    final counts = <String, int>{};
    PhotoWordSession? open;

    for (var i = 0; i < steps; i++) {
      final action = rnd.nextInt(100);
      String name;
      try {
        if (open != null && action < 45) {
          final s = open;
          final r = rnd.nextInt(8);
          if (r == 0 && s.words.isNotEmpty) {
            name = 'swipe';
            s.swipe(s.words[rnd.nextInt(s.words.length)]);
          } else if (r == 1) {
            name = 'dial';
            s.setTarget(rnd.nextInt(6));
          } else if (r == 2 && s.words.isNotEmpty) {
            name = 'star';
            s.toggleStar(s.words[rnd.nextInt(s.words.length)]);
          } else if (r == 3 && s.words.isNotEmpty) {
            name = 'correct';
            final w = s.words[rnd.nextInt(s.words.length)];
            final other = pool[rnd.nextInt(pool.length)];
            s.correct(w, word: other.lemma, meaning: other.learnerMeaning ?? '改過');
          } else if (r == 4 && s.words.isNotEmpty) {
            name = 'move';
            s.move(s.words[rnd.nextInt(s.words.length)],
                LabelPoint(rnd.nextDouble(), rnd.nextDouble()));
          } else if (r == 5 && s.oldWords.isNotEmpty) {
            name = 'restore';
            s.restore(s.oldWords[rnd.nextInt(s.oldWords.length)]);
          } else {
            name = 'leave';
            s.save();
            s.dispose();
            open = null;
          }
          if (open != null && open.words.length > WordSelector.maxWords) {
            f.add('照片頁列出超過 5 個詞', '$name @$i');
          }
        } else if (action < 60 && replies.isNotEmpty) {
          name = 'new photo';
          final Object? raw = jsonDecode(replies[rnd.nextInt(replies.length)].readAsStringSync());
          final id = 'f${photoN++}';
          repo.addPhoto(Photo(
              id: id, title: id, takenAt: now, createdAt: now, storedKey: id,
              taggingStatus: TaggingStatus.done,
              candidates: pack.linkAll(parseCandidates(raw, lexicon: testLexicon()))));
          open?.save();
          open?.dispose();
          open = PhotoWordSession(repo: repo, photoId: id);
        } else if (action < 66 && repo.photos.isNotEmpty) {
          name = 'reopen photo';
          open?.save();
          open?.dispose();
          open = PhotoWordSession(repo: repo, photoId: repo.photos[rnd.nextInt(repo.photos.length)].id);
        } else if (action < 72) {
          name = 'add from database';
          final w = pool[rnd.nextInt(pool.length)];
          try {
            repo.addWord(word: w.lemma, pos: shortPos(w.pos), meaning: w.learnerMeaning ?? '', level: w.cefr);
            repo.linkLexicon(pack);
          } on DuplicateWordException {
            name = 'add duplicate';
          }
        } else if (action < 77 && repo.entries.isNotEmpty) {
          name = 'edit meaning';
          final e = repo.entries[rnd.nextInt(repo.entries.length)];
          repo.editEntry(e.copyWith(meaning: '自己的意思$i'), {WordField.meaning});
        } else if (action < 81 && repo.entries.isNotEmpty) {
          final e = repo.entries[rnd.nextInt(repo.entries.length)];
          if (repo.isArchived(e.id)) {
            name = 'restore word';
            repo.restoreWord(e.word);
          } else {
            name = 'archive word';
            repo.archiveWord(e.id);
          }
        } else if (action < 84 && repo.photos.isNotEmpty && open == null) {
          name = 'remove photo';
          repo.removePhoto(repo.photos[rnd.nextInt(repo.photos.length)].id);
        } else if (action < 94) {
          name = 'review';
          open?.save();
          open?.dispose();
          open = null;
          final s = FlashcardSession(repo, random: rnd);
          var n = 0;
          while (!s.finished && n < 60) {
            final c = s.card!;
            final e = repo.entry(c.wordEntryId);
            if (e == null) {
              f.add('複習中的卡找不到詞條', c.id);
              break;
            }
            if (e.meaning.trim().isEmpty) f.add('沒有中文意思的卡出現在複習', e.word);
            s.showAnswer();
            s.rate(answer(repo, c, e, rnd, now));
            n++;
          }
          s.dispose();
        } else if (action < 97) {
          name = 'set level';
          repo.setLevel(['A1', 'A2', 'B1', 'B2', 'C1', 'C2'][rnd.nextInt(6)]);
        } else {
          name = 'next day';
          now = now.add(Duration(days: 1 + rnd.nextInt(3)));
        }
      } catch (e, st) {
        name = 'crash';
        f.add('操作時拋出例外', '$e\n${st.toString().split('\n').take(4).join('\n')}');
      }
      counts[name] = (counts[name] ?? 0) + 1;
      now = now.add(const Duration(minutes: 3));
      check(repo, f, '$i:$name', openPhoto: open?.photoId);
    }
    open?.save();
    open?.dispose();
    // Everything comes back after a restart.
    final before = snapshot(repo);
    await repo.flush();
    await Hive.close();
    Hive.init(dir.path);
    final again = WordDatabaseRepository.fromData(
        (await HiveWordDatabaseStore.open()).load(), clock: () => now);
    final after = snapshot(again);
    for (final k in {...before.keys, ...after.keys}) {
      if (before[k] != after[k]) f.add('重開後資料不同：${k.split(':').first}', k);
    }
    final report = {
      'steps': steps, 'seed': seed, 'actions': counts,
      'final': {'entries': repo.entries.length, 'photos': repo.photos.length,
        'cards': allCards(repo).length},
      'findings': f.toJson(),
    };
    File(env['SIM_OUT'] ?? 'build/fuzz_simulation.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert({...report, 'findings': f.counts}));
  }, timeout: const Timeout(Duration(minutes: 30)));
}
