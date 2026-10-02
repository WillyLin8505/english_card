// Photo learner simulation (not part of the regular suite: no _test suffix).
//
// A learner adds real photos, the real tagging service (Ollama + Qwen3-VL on
// 127.0.0.1:8765) proposes candidates, the photo page picks at most five,
// the learner sometimes swipes a word away as known or turns the dial,
// leaves the page (cards are created), and reviews every evening. Checks
// follow spec sections 3, 4 and 7.
//
//   flutter test test/simulation/photo_simulation.dart
//
// Environment (all optional):
//   SIM_PACK    a /api/lexicon JSON (default assets/lexicon/en-zh-TW.json)
//   SIM_IMAGES  folder of photos (default ../lexicon/media/images/wikimedia_commons)
//   SIM_PHOTOS  photos to add (12)       SIM_LEVEL  learner CEFR (A2)
//   SIM_SEED    random seed (1)          SIM_TAGGER tagging URL
//   SIM_OUT     report JSON (build/photo_simulation.json)

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/dictionary_sync.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/tagging_queue.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_selector.dart';

import '../helpers.dart';
import 'learner_simulation.dart' show Findings, answer, checkBack, checkFront;

final _env = Platform.environment;
String _opt(String k, String d) => _env[k] ?? d;

void main() {
  final photosWanted = int.parse(_opt('SIM_PHOTOS', '12'));
  final level = _opt('SIM_LEVEL', 'A2');
  final seed = int.parse(_opt('SIM_SEED', '1'));
  final out = _opt('SIM_OUT', 'build/photo_simulation.json');

  test('learner studies from $photosWanted photos', () async {
    // flutter_test answers every HTTP request with 400; this run talks to
    // the real tagger.
    HttpOverrides.global = null;
    LexiconPack.instance.loadJson(
        jsonDecode(File(_opt('SIM_PACK', 'assets/lexicon/en-zh-TW.json'))
            .readAsStringSync()) as Map<String, dynamic>);
    final rnd = Random(seed);
    var now = DateTime(2026, 10, 1, 19);
    final repo = WordDatabaseRepository(
        clock: () => now, profile: UserVocabularyProfile.start(level, now: now));
    final key = File('../tagger/.api_key').readAsStringSync().trim();
    final settings = AppSettings.inMemory(
        taggingUrl: _opt('SIM_TAGGER', 'http://127.0.0.1:8765/tag'), apiKey: key);
    final store = PhotoStore.inMemory();
    final intake = PhotoIntake(repository: () => repo, photoStore: store);
    final queue = TaggingQueue(
        repository: () => repo, settings: settings, intake: intake, lexicon: testLexicon);
    final f = Findings();
    final images = Directory(_opt('SIM_IMAGES', '../lexicon/media/images/wikimedia_commons'))
        .listSync()
        .whereType<File>()
        .where((x) => x.path.endsWith('.jpg'))
        .toList()
      ..sort((a, b) => a.path.compareTo(b.path))
      ..shuffle(rnd);
    final photosLog = <Map<String, dynamic>>[];
    var reviews = 0;

    for (final file in images.take(photosWanted)) {
      final id = 'photo-${photosLog.length}';
      final saved = await store.save(id, file.readAsBytesSync());
      repo.addPhoto(Photo(
          id: id,
          title: file.uri.pathSegments.last.substring(0, 12),
          takenAt: now,
          storedKey: saved.storedKey,
          createdAt: now,
          taggingStatus: TaggingStatus.pending));
      final started = DateTime.now();
      await queue.process();
      final secs = DateTime.now().difference(started).inMilliseconds / 1000;
      final photo = repo.photo(id)!;
      final log = <String, dynamic>{'photo': id, 'file': file.uri.pathSegments.last,
        'status': photo.taggingStatus.name, 'seconds': secs};
      photosLog.add(log);
      if (photo.taggingStatus != TaggingStatus.done) {
        f.add('照片辨識沒有完成', '${file.uri.pathSegments.last}：${photo.taggingError}');
        continue;
      }
      final pool = photo.candidates;
      log['pool'] = [for (final c in pool) '${c.word}/${c.pos}/${c.level}'];
      if (pool.length < 6) f.add('候選詞少於 6 個（規格：6–8 個以上）', '$id：${pool.length}');
      for (final c in pool) {
        if (c.point.x < 0 || c.point.x > 1 || c.point.y < 0 || c.point.y > 1) {
          f.add('候選詞標記位置超出照片', '$id ${c.word} (${c.point.x},${c.point.y})');
        }
        if (c.evidence.trim().isEmpty) f.add('候選詞沒有圖片證據', '$id ${c.word}');
        if (RegExp(r'^[A-Z]').hasMatch(c.word)) f.add('候選詞是大寫（可能是專有名詞）', '$id ${c.word}');
      }

      // Match PhotoDetailScreen: the real screen passes the queue so a pool
      // that is numerous but all nouns can request actions/descriptions.
      final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
      await Future<void>.delayed(Duration.zero); // let _maybeTopUp start
      final topUpDeadline = DateTime.now().add(const Duration(minutes: 3));
      while (queue.isToppingUp(id) && DateTime.now().isBefore(topUpDeadline)) {
        await Future<void>.delayed(const Duration(milliseconds: 50));
      }
      if (queue.isToppingUp(id)) {
        f.add('候選補抓逾時', id);
      }
      final words = s.words;
      log['top_up'] = [
        for (final c in repo.photo(id)!.candidates)
          if (c.focus != null) '${c.word}/${c.focus}'
      ];
      log['listed'] = [for (final w in words) '${w.word}/${w.candidate.pos}/${w.candidate.level}'];
      if (words.length > WordSelector.maxWords) f.add('照片列出超過 5 個詞', '$id：${words.length}');
      final nouns = words.where((w) => w.candidate.isNoun).length;
      if (nouns > WordSelector.maxNouns) f.add('照片列出超過 3 個名詞', '$id：$nouns');
      if (words.map((w) => w.word).toSet().length != words.length) f.add('照片列出重複的詞', id);
      for (final w in words) {
        if (w.candidate.meaning.trim().isEmpty) {
          f.add('照片列出的詞沒有中文意思', '$id ${w.word}');
        }
        if (repo.studyingWords.contains(w.word)) {
          f.add('照片列出已在學的詞（規格：只新增情境）', '$id ${w.word}');
        }
        final gap = levelIndex(w.candidate.level) - s.target;
        if (gap.abs() >= 3) f.add('照片列出的詞難度離程度三級以上', '$id ${w.word} ${w.candidate.level}（目標 ${s.targetLevel}）');
      }
      // The learner: sometimes turns the dial, sometimes knows a word.
      if (rnd.nextDouble() < 0.3) {
        s.setTarget(s.target + 1, live: true);
        s.setTarget(s.target);
        log['dial'] = s.targetLevel;
        if (s.words.length > WordSelector.maxWords) f.add('轉輪盤後超過 5 個詞', id);
      }
      String? swiped;
      if (s.words.length > 1 && rnd.nextDouble() < 0.4) {
        final w = s.words[rnd.nextInt(s.words.length)];
        swiped = w.word;
        s.swipe(w);
        if (s.words.any((x) => x.word == swiped)) f.add('左滑後詞還在列表', '$id $swiped');
      }
      final listedBefore = [for (final w in s.words) w.word];
      final result = s.save();
      s.dispose();
      log['saved'] = listedBefore;
      for (final w in listedBefore) {
        final e = repo.entryByWord(w);
        if (e == null || repo.cardOf(e.id) == null) {
          f.add('離開照片後沒有建立卡片', '$id $w');
        }
      }
      if (swiped != null) {
        final e = repo.entryByWord(swiped);
        if (e != null && repo.cardOf(e.id) != null && !repo.isArchived(e.id)) {
          f.add('左滑已學會的詞仍有可複習的卡片', '$id $swiped');
        }
        if (!repo.profile.learned.contains(swiped) && (e == null || !repo.isArchived(e.id))) {
          f.add('左滑的詞沒有進入已學會', '$id $swiped');
        }
      }
      if (result.photoRemoved) log['removed'] = true;
      // Re-opening the photo shows the saved list, not a new pick.
      final again = PhotoWordSession(repo: repo, photoId: id);
      final reopened = [for (final w in again.words) w.word]..sort();
      again.dispose();
      if (!result.photoRemoved && reopened.join(',') != ([...listedBefore]..sort()).join(',')) {
        f.add('重新打開照片時列表變了', '$id：$listedBefore → $reopened');
      }

      // Evening review.
      final fs = FlashcardSession(repo, random: rnd);
      var step = 0;
      while (!fs.finished && step < 300) {
        final c = fs.card!;
        final e = repo.entry(c.wordEntryId)!;
        if (c.fsrs.reps == 0) checkFront(e, f);
        fs.showAnswer();
        if (c.fsrs.reps == 0) {
          checkBack(e, repo.profile.cefr, f);
          if (fs.photo == null) f.add('照片來的卡背面沒有照片', e.word);
        }
        fs.rate(answer(repo, c, e, rnd, now));
        reviews++;
        step++;
      }
      now = DateTime(now.year, now.month, now.day + 1, 19);
    }

    // The app sends what the pack lacked (spec: 缺詞條) to the local server.
    final missing = LexiconPack.instance.requests.length;
    var sent = 0;
    try {
      sent = await DictionarySync().sendMissing();
    } catch (e) {
      f.add('缺詞條送不出去', '$e');
    }
    if (missing > 0 && sent == 0) f.add('缺詞條送不出去', '$missing 筆');

    final report = {
      'config': {'photos': photosWanted, 'level': level, 'seed': seed},
      'totals': {
        'cards': repo.entries.where((e) => repo.cardOf(e.id) != null).length,
        'archived': repo.entries.where((e) => repo.isArchived(e.id)).length,
        'reviews': reviews,
        'missing_requests': missing,
        'missing_sent': sent,
        'level': repo.profile.cefr,
        'avg_tag_seconds': photosLog.isEmpty
            ? 0
            : photosLog.map((p) => p['seconds'] as double).reduce((a, b) => a + b) /
                photosLog.length,
      },
      'findings': f.toJson(),
      'photos': photosLog,
    };
    File(out)
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ')
        .convert({'totals': report['totals'], 'findings': f.counts}));
  }, timeout: const Timeout(Duration(minutes: 60)));
}
