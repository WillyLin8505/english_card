// Database browsing simulation (not part of the regular suite).
//
// A learner opens 單字詳情 in the 資料庫 for every word of the pack (full and
// still-missing ones) on a phone-sized screen and adds it to 我的收藏與複習.
// Checked: no layout errors or "null" on screen, the add message matches
// what happens (a word without Chinese waits — 問題回報 #44, #100), and a
// review run afterwards shows every added word that has a meaning.
//
//   flutter test test/simulation/database_simulation.dart   (SIM_PACK, SIM_LIMIT, SIM_OUT)

import 'dart:convert';
import 'dart:io';

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
import 'learner_simulation.dart' show Findings;

void main() {
  testWidgets('learner browses the database and adds words', (tester) async {
    final env = Platform.environment;
    final pack = LexiconPack.instance
      ..loadJson(jsonDecode(File(env['SIM_PACK'] ?? 'assets/lexicon/en-zh-TW.json')
          .readAsStringSync()) as Map<String, dynamic>);
    final limit = int.parse(env['SIM_LIMIT'] ?? '250');
    var now = testNow;
    final repo = WordDatabaseRepository(
        clock: () => now, profile: UserVocabularyProfile.start('B1', now: testNow));
    final f = Findings();
    var current = '';
    final original = FlutterError.onError;
    FlutterError.onError = (d) => f.add('版面錯誤', '$current：${d.exceptionAsString().split('\n').first}');
    addTearDown(() => FlutterError.onError = original);
    await pumpApp(tester, initialTab: AppTab.words, repository: repo, size: const Size(390, 844));

    // Full words first, then some still-missing (stub) ones.
    final words = [
      ...pack.catalogWords.where((w) => w.full).take(limit ~/ 2),
      ...pack.catalogWords.where((w) => !w.full).take(limit ~/ 2),
    ];
    var added = 0, waiting = 0, opened = 0;
    for (final w in words) {
      current = '${w.lemma} (${w.pos})';
      tester.state<NavigatorState>(find.byType(Navigator).last)
          .push(MaterialPageRoute(builder: (_) => DatabaseWordScreen(wordId: w.id)));
      await tester.pumpAndSettle();
      opened++;
      for (final t in tester.widgetList<Text>(find.byType(Text))) {
        final s = t.data ?? t.textSpan?.toPlainText() ?? '';
        if (RegExp(r'\bnull\b').hasMatch(s)) f.add('畫面出現 null', '$current：$s');
      }
      final button = find.text('加入我的收藏與複習');
      if (button.evaluate().isEmpty) {
        f.add('沒有加入按鈕', current);
      } else {
        await tester.ensureVisible(button);
        await tester.tap(button);
        await tester.pump();
        final hasMeaning = (w.learnerMeaning ?? '').trim().isNotEmpty;
        final saysWaiting = find.text('已加入我的收藏；中文意思補齊後會自動排進複習').evaluate().isNotEmpty;
        final saysAdded = find.text('已加入我的收藏與複習字卡').evaluate().isNotEmpty;
        final saysDup = find.textContaining('已在我的收藏').evaluate().isNotEmpty ||
            find.textContaining('放回複習').evaluate().isNotEmpty;
        if (saysDup) {
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
      'opened': opened, 'added': added, 'waiting': waiting,
      'entries': repo.entries.length, 'reviewed': seen.length,
      'findings': f.toJson(),
    };
    File(env['SIM_OUT'] ?? 'build/database_simulation.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert({...report, 'findings': f.counts}));
  }, timeout: const Timeout(Duration(minutes: 20)));
}
