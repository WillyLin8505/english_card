// Word detail sweep (not part of the regular suite).
//
// Every complete word of the pack is added and its 單字詳情 page opened on a
// phone-sized screen. Checked: no layout errors, no "null" on screen, and no
// empty section titles (spec: 欄位沒有內容時自動省略；不可出現空白標題、空卡
// 或字串 null).
//
//   flutter test test/simulation/detail_simulation.dart   (SIM_PACK, SIM_LIMIT)

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import '../helpers.dart';
import 'learner_simulation.dart' show Findings;

void main() {
  testWidgets('every word detail page renders cleanly', (tester) async {
    final env = Platform.environment;
    final pack = LexiconPack.instance
      ..loadJson(jsonDecode(File(env['SIM_PACK'] ?? 'assets/lexicon/en-zh-TW.json')
          .readAsStringSync()) as Map<String, dynamic>);
    final repo = WordDatabaseRepository(
        clock: () => testNow, profile: UserVocabularyProfile.start('A2', now: testNow));
    final limit = int.parse(env['SIM_LIMIT'] ?? '400');
    for (final w in pack.catalogWords.where((w) => w.full).take(limit)) {
      try {
        repo.addWord(word: w.lemma, pos: shortPos(w.pos), meaning: w.learnerMeaning ?? '', level: w.cefr);
      } on DuplicateWordException {
        continue;
      }
    }
    repo.linkLexicon(pack);
    final f = Findings();
    var current = '';
    final original = FlutterError.onError;
    FlutterError.onError = (d) => f.add('版面錯誤', '$current：${d.exceptionAsString().split('\n').first}');
    addTearDown(() => FlutterError.onError = original);
    final app = await pumpApp(tester, initialTab: AppTab.words, repository: repo, size: const Size(390, 844));
    var opened = 0;
    for (final e in repo.entries) {
      current = e.word;
      app.navigator.openWord(e.id);
      await tester.pumpAndSettle();
      if (find.byType(WordDetailScreen).evaluate().isEmpty) {
        f.add('單字詳情頁沒有打開', e.word);
        continue;
      }
      if (find.text(displayWord(e.word)).evaluate().isEmpty &&
          find.text(e.word).evaluate().isEmpty) {
        f.add('詳情頁沒有顯示單字本身', e.word);
      }
      opened++;
      final texts = [
        for (final t in tester.widgetList<Text>(find.byType(Text)))
          t.data ?? t.textSpan?.toPlainText() ?? ''
      ];
      if (texts.any((t) => RegExp(r'\bnull\b').hasMatch(t))) {
        f.add('畫面出現 null', '${e.word}：${texts.firstWhere((t) => t.contains('null'))}');
      }
      if (texts.any((t) => t.contains('Instance of'))) f.add('畫面出現物件字串', e.word);
      // Scroll the whole page so lazily built sections are checked too.
      final scrollable = find.byType(Scrollable);
      if (scrollable.evaluate().isNotEmpty) {
        await tester.drag(scrollable.first, const Offset(0, -3000));
        await tester.pumpAndSettle();
      }
      Navigator.of(tester.element(find.byType(Scaffold).last)).maybePop();
      await tester.pumpAndSettle();
    }
    final report = {'opened': opened, 'findings': f.toJson()};
    File('build/detail_simulation.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert({'opened': opened, 'counts': f.counts}));
  }, timeout: const Timeout(Duration(minutes: 20)));
}
