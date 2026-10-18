// What a learner actually sees (not part of the regular suite).
//
// A learner at SIM_LEVEL adds SIM_WORDS words from the 資料庫 (complete
// words around their level), reviews each one — front, then the back
// scrolled to the end — and opens its 單字詳情 page. Every text on each
// screen is written to SIM_OUT, in reading order, so a reviewer can judge
// the screens as a learner would (convenient, necessary, clear, no noise)
// without screenshots. Checked here only: no layout errors, no "null".
//
//   flutter test test/simulation/learner_view_simulation.dart
//   SIM_PACK (a /api/lexicon JSON)  SIM_WORDS (60)  SIM_LEVEL (B1)
//   SIM_SEED (1)  SIM_OUT (build/learner_view.json)
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import '../helpers.dart';

String _opt(String k, String d) => Platform.environment[k] ?? d;

const _levels = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];

/// Every text on screen, top to bottom, left to right (offstage too: a
/// scrolled page builds what the learner scrolls to).
List<String> screenTexts(WidgetTester tester) {
  final rows = <(double, double, String)>[];
  for (final el in find.byType(Text).evaluate()) {
    final t = el.widget as Text;
    final s = (t.data ?? t.textSpan?.toPlainText() ?? '').trim();
    if (s.isEmpty) continue;
    final box = el.renderObject;
    var y = 0.0, x = 0.0;
    if (box is RenderBox && box.hasSize && box.attached) {
      final o = box.localToGlobal(Offset.zero);
      y = o.dy;
      x = o.dx;
    }
    rows.add((y, x, s));
  }
  rows.sort((a, b) => a.$1 != b.$1 ? a.$1.compareTo(b.$1) : a.$2.compareTo(b.$2));
  final out = <String>[];
  for (final r in rows) {
    if (out.isEmpty || out.last != r.$3) out.add(r.$3);
  }
  return out;
}

void main() {
  testWidgets('a learner reviews and opens every added word', (tester) async {
    final pack = LexiconPack.instance
      ..loadJson(jsonDecode(File(_opt('SIM_PACK', 'assets/lexicon/en-zh-TW.json'))
          .readAsStringSync()) as Map<String, dynamic>);
    final level = _opt('SIM_LEVEL', 'B1');
    final want = int.parse(_opt('SIM_WORDS', '60'));
    final rnd = Random(int.parse(_opt('SIM_SEED', '1')));
    final li = _levels.indexOf(level);
    // Words a learner at this level would pick: their level and one either side.
    final near = pack.catalogWords
        .where((w) => w.full && w.cefr != null &&
            (_levels.indexOf(w.cefr!) - li).abs() <= 1)
        .toList()
      ..shuffle(rnd);
    final repo = WordDatabaseRepository(
        clock: () => testNow, profile: UserVocabularyProfile.start(level, now: testNow));
    final added = <String>[];
    for (final w in near) {
      if (added.length >= want) break;
      try {
        repo.addWord(word: w.lemma, pos: shortPos(w.pos), meaning: w.learnerMeaning ?? '', level: w.cefr);
        added.add(w.lemma);
      } on DuplicateWordException {
        continue;
      }
    }
    repo.linkLexicon(pack);

    final errors = <String>[];
    var current = '';
    final original = FlutterError.onError;
    FlutterError.onError = (d) => errors.add('$current：${d.exceptionAsString().split('\n').first}');
    addTearDown(() => FlutterError.onError = original);

    final words = <String, Map<String, dynamic>>{};
    final app = await pumpApp(tester,
        initialTab: AppTab.review, repository: repo, size: const Size(390, 844));
    await tester.tap(find.text('開始複習'));
    await tester.pumpAndSettle();
    var n = 0;
    while (find.byType(FlashcardFront).evaluate().isNotEmpty && n < want * 2) {
      final front = tester.widget<FlashcardFront>(find.byType(FlashcardFront));
      final word = front.entry.word;
      try {
        current = '$word 正面';
        final w = words.putIfAbsent(word, () => {'word': word, 'level': front.entry.level});
        w['exercise'] = front.session?.exercise?.type.name;
        w['front'] = screenTexts(tester);
        // A photo question waits for pixels the test never decodes.
        final s = front.session;
        if (s != null && !s.canAnswer) {
          s.reportPhotoState(s.photoAttempt, true);
          s.showAnswer();
        } else {
          await tester.tap(find.text('顯示答案'));
        }
        await tester.pumpAndSettle(const Duration(milliseconds: 100),
            EnginePhase.sendSemanticsUpdate, const Duration(seconds: 10));
        current = '$word 背面';
        final scroll = find.byType(SingleChildScrollView);
        if (scroll.evaluate().isNotEmpty) {
          await tester.drag(scroll.first, const Offset(0, -4000));
          await tester.pumpAndSettle(const Duration(milliseconds: 100),
              EnginePhase.sendSemanticsUpdate, const Duration(seconds: 10));
        }
        w['back'] = screenTexts(tester);
        await tester.tap(find.text('記得'));
        await tester.pumpAndSettle(const Duration(milliseconds: 100),
            EnginePhase.sendSemanticsUpdate, const Duration(seconds: 10));
      } catch (e) {
        errors.add('$current：${e.toString().split('\n').first}');
        break;
      }
      n++;
    }

    // Then each word's 單字詳情 page, scrolled through.
    for (final e in repo.entries) {
      current = '${e.word} 詳情';
      app.navigator.openWord(e.id);
      await tester.pumpAndSettle();
      if (find.byType(WordDetailScreen).evaluate().isEmpty) {
        errors.add('$current：沒有打開');
        continue;
      }
      final scrollable = find.byType(Scrollable);
      final seen = <String>[];
      for (var k = 0; k < 6; k++) {
        for (final t in screenTexts(tester)) {
          if (!seen.contains(t)) seen.add(t);
        }
        if (scrollable.evaluate().isEmpty) break;
        await tester.drag(scrollable.first, const Offset(0, -700));
        await tester.pumpAndSettle();
      }
      words.putIfAbsent(e.word, () => {'word': e.word, 'level': e.level})['detail'] = seen;
      Navigator.of(tester.element(find.byType(Scaffold).last)).maybePop();
      await tester.pumpAndSettle();
    }

    final nulls = [
      for (final w in words.values)
        for (final part in ['front', 'back', 'detail'])
          for (final t in (w[part] as List<String>? ?? const <String>[]))
            if (RegExp(r'\bnull\b').hasMatch(t)) '${w['word']} $part：$t'
    ];
    final report = {
      'level': level, 'added': added.length, 'reviewed': n,
      'errors': errors.toSet().toList(), 'nulls': nulls, 'words': words.values.toList(),
    };
    File(_opt('SIM_OUT', 'build/learner_view.json'))
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print('added ${added.length}, reviewed $n, opened ${words.length}, '
        '${errors.length} errors, ${nulls.length} nulls');
    expect(errors, isEmpty);
    expect(nulls, isEmpty);
  }, timeout: const Timeout(Duration(minutes: 20)));
}
