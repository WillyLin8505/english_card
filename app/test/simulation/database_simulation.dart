// Database browsing simulation (not part of the regular suite).
//
// A learner opens 單字詳情 in the 資料庫 for a sample of the pack on a
// phone-sized screen and adds each word to 我的單字本與複習. SIM_SEED picks
// the sample: half full words with a meaning across every CEFR level, half
// still waiting (stubs with pos=unknown or a part of speech, full words with
// no Chinese yet). Checked: no layout errors or "null" on screen (the page is
// scrolled to the bottom), no section title without content, the add message
// matches what happens (a word without Chinese waits — 問題回報 #44, #100),
// and a review run afterwards shows every added word that has a meaning. Any
// finding fails the test.
//
//   flutter test test/simulation/database_simulation.dart   (SIM_PACK, SIM_LIMIT, SIM_SEED, SIM_OUT)

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import '../helpers.dart';
import 'detail_simulation.dart'
    show SampleWord, groupCounts, sampleWords, showsNull, stratifiedSample, sweepPage;
import 'learner_simulation.dart' show Findings;

void main() {
  testWidgets('learner browses the database and adds words', (tester) async {
    final env = Platform.environment;
    final json = jsonDecode(File(env['SIM_PACK'] ?? 'assets/lexicon/en-zh-TW.json')
        .readAsStringSync()) as Map<String, dynamic>;
    final pack = LexiconPack.instance..loadJson(json);
    final limit = int.parse(env['SIM_LIMIT'] ?? '250');
    final seed = int.parse(env['SIM_SEED'] ?? '1');
    final rnd = Random(seed);
    var now = testNow;
    final repo = WordDatabaseRepository(
        clock: () => now, profile: UserVocabularyProfile.start('B1', now: testNow));
    final f = Findings();
    var current = '';
    final original = FlutterError.onError;
    FlutterError.onError = (d) => f.add('版面錯誤', '$current：${d.exceptionAsString().split('\n').first}');
    addTearDown(() => FlutterError.onError = original);
    await pumpApp(tester, initialTab: AppTab.words, repository: repo, size: const Size(390, 844));

    // Full words first, then some still waiting for a meaning: stubs, and
    // full entries with no Chinese yet (the live pack's stubs are all form
    // pointers, so without these the waiting path went untested — round 68).
    bool noMeaning(SampleWord w) => (w.meaning ?? '').trim().isEmpty;
    bool stub(SampleWord w) => w.group.startsWith('stub');
    final all = sampleWords(pack, json);
    final words = [
      ...stratifiedSample(all.where((w) => !stub(w) && !noMeaning(w)), limit ~/ 2, rnd,
          group: (w) => w.group),
      // Waiting: stubs (pos=unknown form pointers open their lemma's page)
      // and full words with no Chinese yet.
      ...stratifiedSample(all.where((w) => stub(w) || noMeaning(w)), limit ~/ 2, rnd,
          group: (w) => stub(w) ? w.group : 'full-no-meaning'),
    ];
    var added = 0, waiting = 0, opened = 0;
    for (final w in words) {
      current = '${w.lemma} (${w.pos})';
      tester.state<NavigatorState>(find.byType(Navigator).last)
          .push(MaterialPageRoute(builder: (_) => DatabaseWordScreen(wordId: w.id)));
      await tester.pumpAndSettle();
      opened++;
      final page = await sweepPage(tester);
      for (final s in page.texts) {
        if (showsNull(s)) f.add('畫面出現 null', '$current：$s');
      }
      for (final h in page.blank) {
        f.add('空白標題（標題下沒有內容）', '$current：$h');
      }
      final button = find.byKey(const ValueKey('database-add'));
      if (button.evaluate().isEmpty) {
        f.add('沒有加入按鈕', current);
      } else if (tester.widget<FilledButton>(button).onPressed == null) {
        // 「已在我的單字本 ✓」: one card per spelling, another part of
        // speech (or the base word of this form) was added already.
      } else {
        await tester.ensureVisible(button);
        final before = {for (final e in repo.entries) e.id};
        await tester.tap(button);
        await tester.pump();
        // Judge the card, not the lexeme: one card per spelling, so a part
        // of speech with no Chinese (top intj) gets another one's, and a
        // form folds into its base word's card (potted → pot, 問題回報 #51)
        // — rounds 76–77 false alarms.
        final card = repo.entryByWord(w.lemma) ??
            repo.entries.where((e) => !before.contains(e.id)).firstOrNull;
        final folded = card == null;
        final hasMeaning = card?.meaning.trim().isNotEmpty ?? false;
        final saysWaiting = find.text('已加入我的單字本；中文意思補齊後會自動排進複習').evaluate().isNotEmpty;
        final saysAdded = find.text('已加入我的單字本與複習').evaluate().isNotEmpty;
        final saysDup = find.textContaining('已在我的單字本').evaluate().isNotEmpty ||
            find.textContaining('放回複習').evaluate().isNotEmpty;
        if (saysDup || folded) {
          // one card per spelling: another part of speech was added already
        } else if (hasMeaning && !saysAdded) {
          f.add('有中文的字沒有說已加入複習', current);
        } else if (!hasMeaning && !saysWaiting) {
          f.add('沒有中文的字說已加入複習（其實要等詞庫補齊）', current);
        }
        if (saysAdded) added++;
        if (saysWaiting) waiting++;
      }
      tester.state<NavigatorState>(find.byType(Navigator).last).pop();
      await tester.pumpAndSettle();
      now = now.add(const Duration(seconds: 20));
    }

    // Review: every added word with a meaning comes up once.
    final withMeaning = {
      for (final e in repo.entries)
        if (e.meaning.trim().isNotEmpty) e.word
    };
    final s = FlashcardSession(repo);
    final seen = <String>{};
    var n = 0;
    while (!s.finished && n < 2000) {
      final e = repo.entry(s.card!.wordEntryId)!;
      if (e.meaning.trim().isEmpty) f.add('沒有中文意思的卡出現在複習', e.word);
      seen.add(e.word);
      s.showAnswer();
      s.rate(Rating.good);
      now = now.add(const Duration(seconds: 8));
      n++;
    }
    for (final w in withMeaning.difference(seen)) {
      f.add('加入的字第一輪沒有出現', w);
    }
    final report = {
      'seed': seed, 'sampled': groupCounts(words, (w) => stub(w) ? w.group : noMeaning(w) ? 'full-no-meaning' : w.group),
      'opened': opened, 'added': added, 'waiting': waiting,
      'entries': repo.entries.length, 'reviewed': seen.length,
      'findings': f.toJson(),
    };
    File(env['SIM_OUT'] ?? 'build/database_simulation.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert(report));
    // Restored before expect: a failing expect with the override still in
    // place trips the binding's assertion and the test hangs to its timeout.
    FlutterError.onError = original;
    expect(f.counts, isEmpty,
        reason: const JsonEncoder.withIndent(' ').convert(f.toJson()));
  }, timeout: const Timeout(Duration(minutes: 20)));
}
