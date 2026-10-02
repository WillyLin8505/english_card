// Learner simulation (not part of the regular suite: no _test suffix).
//
// A new learner keeps drawing words from the 資料庫 tab (「加入我的收藏與
// 複習」) and studies them in the 複習 flow for many simulated days. Each
// card's front and back, the rating buttons and the FSRS schedule are
// checked against spec sections 4 and 7; the 複習 screen itself is also
// rendered for every drawn word to catch layout errors.
//
//   flutter test test/simulation/learner_simulation.dart
//
// Environment (all optional):
//   SIM_PACK   a /api/lexicon JSON (default assets/lexicon/en-zh-TW.json)
//   SIM_DAYS   simulated days (30)      SIM_NEW    new words a day (8)
//   SIM_LEVEL  learner CEFR (A2)        SIM_SEED   random seed (1)
//   SIM_SKIP   chance to skip a day (0.2)
//   SIM_OUT    report JSON path (build/learner_simulation.json)

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/learning_content.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import '../helpers.dart';

final _env = Platform.environment;
String _opt(String k, String d) => _env[k] ?? d;

/// Problems, grouped by kind, with a few examples each.
class Findings {
  final Map<String, List<String>> byKind = {};
  final Map<String, int> counts = {};

  void add(String kind, String example) {
    counts[kind] = (counts[kind] ?? 0) + 1;
    final list = byKind.putIfAbsent(kind, () => []);
    if (list.length < 12 && !list.contains(example)) list.add(example);
  }

  Map<String, dynamic> toJson() => {
        for (final k in counts.keys)
          k: {'count': counts[k], 'examples': byKind[k]},
      };
}

final _letter = RegExp(r'\p{L}', unicode: true);
final _cjk = RegExp(r'[一-鿿]');

void checkFront(WordEntry e, Findings f) {
  final hint = firstLetterHint(e.word);
  final letters = _letter.allMatches(e.word).length;
  if ('_'.allMatches(hint).length != letters - 1) {
    f.add('正面底線數和字母數不符', '${e.word} → $hint');
  }
  if (e.meaning.trim().isEmpty) {
    f.add('正面沒有中文意思，無法回想', e.word);
  } else {
    if (!_cjk.hasMatch(e.meaning)) f.add('正面意思不是中文', '${e.word}：${e.meaning}');
    if (e.meaning.toLowerCase().contains(e.word.toLowerCase())) {
      f.add('正面意思洩漏答案', '${e.word}：${e.meaning}');
    }
  }
  if (posLabel(e.pos) == '其他詞性') f.add('正面詞性顯示「其他詞性」', '${e.word}（${e.pos}）');
  if (e.meaning.contains('null')) f.add('正面出現 null', e.word);
}

void checkBack(WordEntry e, String level, Findings f) {
  final xs = learningExamples(e, level);
  if (xs.isEmpty) {
    f.add('背面沒有可顯示的例句（需有翻譯且不超過程度+1）', '${e.word}（${e.level}）');
  }
  final all =
      e.examples.where((x) => (x.translation ?? '').isNotEmpty).toList();
  final same = all.where((x) => x.difficulty == level).toList();
  if (xs.isNotEmpty && same.isNotEmpty && xs.first.difficulty != level) {
    f.add('背面第一句例句不是使用者程度（規格：先顯示同級）',
        '${e.word}：程度 $level，顯示 ${xs.first.difficulty}「${xs.first.text}」');
  }
  final forms = {
    e.word.toLowerCase(),
    for (final x in e.forms) x.form.toLowerCase()
  };
  for (final x in xs.take(1)) {
    final low = x.text.toLowerCase();
    if (!forms.any((w) => RegExp('\\b${RegExp.escape(w)}\\b').hasMatch(low))) {
      f.add('背面例句不含這個單字或詞形', '${e.word}：${x.text}');
    }
    if (x.text.split(' ').length > 20) {
      f.add('背面例句超過 20 字', '${e.word}：${x.text}');
    }
  }
  if (e.ipa == null) f.add('背面沒有 IPA', e.word);
  if (e.ipa != null && e.ipa!.startsWith('[')) {
    f.add('背面 IPA 是窄式音標', '${e.word} ${e.ipa}');
  }
  if (e.audioUrl == null) f.add('沒有真人發音（翻面只能用 TTS）', e.word);
}

void checkPreview(Map<Rating, dynamic> p, String word, Findings f) {
  final d = [for (final r in Rating.values) p[r].scheduledDays as int];
  for (var i = 1; i < d.length; i++) {
    if (d[i] <= d[i - 1]) f.add('評分按鈕的間隔沒有遞增', '$word：$d');
  }
}

/// A learner who remembers with FSRS's own probability (a slightly
/// forgetful one), and finds new words harder above their level.
Rating answer(WordDatabaseRepository repo, LearningCard c, WordEntry e,
    Random rnd, DateTime now) {
  final r = repo.scheduler.retrievability(c.fsrs, now);
  // New-card recall follows the same continuous ability curve as production.
  // A fixed 70% probability for every word at or below the learner's band made
  // a B2 learner implausibly fail A1 words and polluted the calibration test.
  final p = (r ??
          UserVocabularyProfile.expected(
              repo.profile.ability, e.level ?? 'B1')) *
      0.95;
  if (rnd.nextDouble() > p) return Rating.again;
  final x = rnd.nextDouble();
  return x < 0.15
      ? Rating.hard
      : x < 0.85
          ? Rating.good
          : Rating.easy;
}

List<LearningCard> allCards(WordDatabaseRepository repo) => [
      for (final e in repo.entries)
        if (repo.cardOf(e.id) case final c?) c,
    ];

Map<String, dynamic> loadPack() {
  final path = _opt('SIM_PACK', 'assets/lexicon/en-zh-TW.json');
  return jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
}

void main() {
  final days = int.parse(_opt('SIM_DAYS', '30'));
  final perDay = int.parse(_opt('SIM_NEW', '8'));
  final level = _opt('SIM_LEVEL', 'A2');
  final seed = int.parse(_opt('SIM_SEED', '1'));
  final skip = double.parse(_opt('SIM_SKIP', '0.2'));
  final out = _opt('SIM_OUT', 'build/learner_simulation.json');

  test('learner draws and studies cards for $days days', () {
    final json = loadPack();
    final pack = LexiconPack.instance..loadJson(json);
    final rnd = Random(seed);
    var now = DateTime(2026, 10, 1, 20);
    final repo = WordDatabaseRepository(
        clock: () => now,
        profile: UserVocabularyProfile.start(level, now: now));
    final f = Findings();
    final pool = pack.catalogWords.where((w) => w.full).toList()..shuffle(rnd);
    var next = 0;
    final daysLog = <Map<String, dynamic>>[];
    var reviews = 0, again = 0, maxSession = 0;
    final levelHistory = <String>[];

    for (var day = 0; day < days; day++) {
      final skipped = day > 0 && rnd.nextDouble() < skip;
      var added = 0;
      if (!skipped) {
        // 抽卡: open database words and add them.
        while (added < perDay && next < pool.length) {
          final w = pool[next++];
          try {
            repo.addWord(
                word: w.lemma,
                pos: shortPos(w.pos),
                meaning: w.learnerMeaning ?? '',
                level: w.cefr);
            repo.linkLexicon(pack);
            added++;
          } on DuplicateWordException {
            // Another part of speech of a word already added: one card per
            // spelling (spec section 7), so this is expected.
          }
        }
      }
      final dueBefore = repo.eligibleCards().length;
      var shown = 0, sessionAgain = 0;
      if (!skipped && dueBefore > 0) {
        final s = FlashcardSession(repo, random: rnd);
        final seen = <String, int>{};
        final againAt = <String, int>{};
        final againCounts = <String, int>{};
        var step = 0;
        while (!s.finished && step < 1000) {
          final c = s.card!;
          final e = repo.entry(c.wordEntryId)!;
          if (seen.containsKey(c.id) && !againAt.containsKey(c.id)) {
            f.add('同一次複習中沒按忘記的卡又出現', e.word);
          }
          if (againAt.containsKey(c.id)) {
            final gap = step - againAt.remove(c.id)!;
            final others = repo.eligibleCards().length;
            if (gap < FlashcardSession.againGap &&
                others > FlashcardSession.againGap) {
              f.add('按忘記的卡太快又出現', '${e.word}：隔 ${gap - 1} 張');
            }
          }
          seen[c.id] = step;
          if (c.fsrs.reps == 0 || rnd.nextDouble() < 0.1) checkFront(e, f);
          s.showAnswer();
          if (c.fsrs.reps == 0 || rnd.nextDouble() < 0.1) {
            checkBack(e, repo.profile.cefr, f);
            checkPreview(repo.previewReview(c.id), e.word, f);
          }
          final r = answer(repo, c, e, rnd, now);
          s.rate(r);
          reviews++;
          shown++;
          if (r == Rating.again) {
            again++;
            sessionAgain++;
            final count = (againCounts[c.id] ?? 0) + 1;
            againCounts[c.id] = count;
            if (count <= FlashcardSession.maxAgainRepeats) {
              againAt[c.id] = step;
            }
          } else {
            final after = repo.card(c.id)!;
            if (!after.fsrs.due!.isAfter(now)) {
              f.add('評分後到期日沒有往後', '${e.word}：$r');
            }
          }
          step++;
          now = now.add(const Duration(seconds: 12));
        }
        if (step >= 1000) f.add('複習一直沒結束（超過 1000 張）', 'day $day');
        if (againAt.isNotEmpty) {
          f.add('按忘記的卡在同一次複習中沒有再出現', againAt.keys.join(','));
        }
        final left = repo.eligibleCards().where((c) => !seen.containsKey(c.id));
        if (left.isNotEmpty) {
          f.add('複習結束時還有到期卡片沒出現', '${left.length} 張');
        }
        maxSession = max(maxSession, shown);
      }
      levelHistory.add(repo.profile.cefr);
      daysLog.add({
        'day': day,
        'skipped': skipped,
        'added': added,
        'due_before': dueBefore,
        'shown': shown,
        'again': sessionAgain,
        'level': repo.profile.cefr,
        'cards': allCards(repo).length,
      });
      now = DateTime(now.year, now.month, now.day + 1, 20);
    }

    final byState = <String, int>{};
    for (final c in allCards(repo)) {
      byState[c.fsrs.state.name] = (byState[c.fsrs.state.name] ?? 0) + 1;
    }
    final report = {
      'config': {
        'days': days,
        'per_day': perDay,
        'level': level,
        'seed': seed,
        'skip': skip,
        'pack_words': pool.length
      },
      'totals': {
        'cards': allCards(repo).length,
        'reviews': reviews,
        'again_rate': reviews == 0 ? 0 : again / reviews,
        'max_session': maxSession,
        'states': byState,
        'level_history': levelHistory,
      },
      'findings': f.toJson(),
      'days': daysLog,
    };
    File(out)
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ')
        .convert({'totals': report['totals'], 'findings': f.counts}));
  });

  testWidgets('every drawn word renders on the 複習 screen', (tester) async {
    final json = loadPack();
    final pack = LexiconPack.instance..loadJson(json);
    final rnd = Random(seed);
    final repo = WordDatabaseRepository(
        clock: () => testNow,
        profile: UserVocabularyProfile.start(level, now: testNow));
    final limit = int.parse(_opt('SIM_RENDER', '60'));
    final words = pack.catalogWords.where((w) => w.full).toList()..shuffle(rnd);
    for (final w in words.take(limit)) {
      try {
        repo.addWord(
            word: w.lemma,
            pos: shortPos(w.pos),
            meaning: w.learnerMeaning ?? '',
            level: w.cefr);
      } on DuplicateWordException {
        continue;
      }
    }
    repo.linkLexicon(pack);
    final errors = <String>[];
    final original = FlutterError.onError;
    String current = '';
    FlutterError.onError = (d) =>
        errors.add('$current：${d.exceptionAsString().split('\n').first}');
    addTearDown(() => FlutterError.onError = original);

    await pumpApp(tester,
        initialTab: AppTab.review,
        repository: repo,
        size: const Size(390, 844));
    await tester.tap(find.text('開始複習'));
    await tester.pumpAndSettle();
    var n = 0;
    while (find.byType(FlashcardFront).evaluate().isNotEmpty && n < limit * 3) {
      final front = tester.widget<FlashcardFront>(find.byType(FlashcardFront));
      current = '${front.entry.word} 正面';
      await tester.tap(find.text('顯示答案'));
      await tester.pumpAndSettle();
      current = '${front.entry.word} 背面';
      await tester.drag(
          find.byType(SingleChildScrollView).first, const Offset(0, -600));
      await tester.pumpAndSettle();
      await tester.tap(find.text(n % 5 == 0 ? '忘記' : '記得'));
      await tester.pumpAndSettle();
      n++;
    }
    final report = {'rendered': n, 'errors': errors.toSet().toList()};
    File(out.replaceAll('.json', '_render.json'))
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print('rendered $n cards, ${errors.length} layout errors');
  });
}
