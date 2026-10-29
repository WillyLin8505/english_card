// Word detail sweep (not part of the regular suite).
//
// A sample of the pack (SIM_SEED picks it: every CEFR level, words without a
// level, and stubs — form pointers with pos=unknown and stubs with a part of
// speech) is added and each word's 單字詳情 page opened on a phone-sized
// screen and scrolled to the bottom, its text collected section by section.
// Checked: no layout errors, no "null" on screen, and no empty section titles
// (spec: 欄位沒有內容時自動省略；不可出現空白標題、空卡或字串 null). Any
// finding fails the test.
//
//   flutter test test/simulation/detail_simulation.dart   (SIM_PACK, SIM_LIMIT, SIM_SEED, SIM_OUT)

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/l10n/ui_text.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/word_detail_screen.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';

import '../helpers.dart';
import 'learner_simulation.dart' show Findings;

/// Which sampling group a pack word belongs to: its CEFR level, `none` for
/// a full word without one, or the kind of stub.
String sampleGroup(LexEntry w) => !w.full
    ? (w.pos == 'unknown' ? 'stub-unknown' : 'stub-pos')
    : (w.cefr ?? 'none');

/// [n] words drawn round-robin from the shuffled groups of [words] (by
/// [group]), so a small sample still covers every level and the stubs.
List<T> stratifiedSample<T>(Iterable<T> words, int n, Random rnd,
    {required String Function(T) group}) {
  final groups = <String, List<T>>{};
  for (final w in words) {
    groups.putIfAbsent(group(w), () => []).add(w);
  }
  final keys = groups.keys.toList()..sort();
  final queues = [for (final k in keys) (groups[k]!..shuffle(rnd)).iterator];
  final out = <T>[];
  var progressed = true;
  while (out.length < n && progressed) {
    progressed = false;
    for (final q in queues) {
      if (out.length >= n) break;
      if (q.moveNext()) {
        out.add(q.current);
        progressed = true;
      }
    }
  }
  return out;
}

/// How many of [words] fall in each group.
Map<String, int> groupCounts<T>(Iterable<T> words, String Function(T) group) {
  final out = <String, int>{};
  for (final w in words) {
    out[group(w)] = (out[group(w)] ?? 0) + 1;
  }
  return out;
}

/// A word of the pack to sample: a [LexEntry] of [LexiconPack.catalogWords],
/// or a form pointer (a stub with pos=unknown and redirect_to), which the
/// pack keeps only as an id → lemma redirect.
typedef SampleWord = ({int id, String lemma, String pos, String? meaning, String? cefr, String group});

List<SampleWord> sampleWords(LexiconPack pack, Map<String, dynamic> json) => [
      for (final w in pack.catalogWords)
        (id: w.id, lemma: w.lemma, pos: w.pos, meaning: w.learnerMeaning, cefr: w.cefr, group: sampleGroup(w)),
      for (final raw in json['lexemes'] as List)
        if (raw is Map && raw['redirect_to'] is num)
          (
            id: (raw['id'] as num).toInt(),
            lemma: '${raw['lemma']}',
            pos: '${raw['pos'] ?? 'unknown'}',
            meaning: null,
            cefr: null,
            group: raw['pos'] == 'unknown' ? 'stub-unknown' : 'stub-pos',
          ),
    ];

/// A "null" on screen that is not the English word null (shown as a related
/// word of none / nowhere: 「null　空值」).
bool showsNull(String text) =>
    RegExp(r'\bnull\b').hasMatch(text.replaceAll(RegExp(r'(^|\n)null\u3000'), ''));

/// The heading of a section: 單字詳情's [SectionLabel] or the 資料庫 detail's
/// titleSm [UiText].
bool _isHeading(Widget w) =>
    w is SectionLabel || (w is UiText && w.style == MFont.titleSm);

String _headingText(Widget w) => w is SectionLabel ? w.text : (w as UiText).data;

/// Adds the texts built on screen right now to [texts], and the section
/// headings with nothing under them to [blank].
void collectBuilt(Set<String> texts, Set<String> blank) {
  for (final el in find.byType(RichText).evaluate()) {
    texts.add((el.widget as RichText).text.toPlainText());
  }
  for (final h in find.byWidgetPredicate(_isHeading).evaluate()) {
    Element? section;
    h.visitAncestorElements((a) {
      if (a.widget is Flex) {
        section = a;
        return false;
      }
      return true;
    });
    if (section == null) continue;
    var content = false;
    void visit(Element e) {
      if (content || identical(e, h)) return;
      final w = e.widget;
      if ((w is RichText && w.text.toPlainText().trim().isNotEmpty) ||
          w is Image ||
          w is Scrollable) {
        content = true;
        return;
      }
      e.visitChildren(visit);
    }

    section!.visitChildren(visit);
    if (!content) blank.add(_headingText(h.widget));
  }
}

/// Scrolls the page's main (vertical) list from top to bottom, collecting
/// the text and blank headings of each stretch as it is built, then back to
/// the top.
Future<({Set<String> texts, Set<String> blank})> sweepPage(WidgetTester tester) async {
  final texts = <String>{}, blank = <String>{};
  collectBuilt(texts, blank);
  final vertical = find.byWidgetPredicate(
      (w) => w is Scrollable && axisDirectionToAxis(w.axisDirection) == Axis.vertical);
  ScrollableState? main;
  for (final el in vertical.evaluate()) {
    final s = (el as StatefulElement).state as ScrollableState;
    if (main == null || s.position.viewportDimension > main.position.viewportDimension) main = s;
  }
  if (main == null) return (texts: texts, blank: blank);
  final p = main.position;
  for (var i = 0; i < 80 && p.pixels < p.maxScrollExtent; i++) {
    p.jumpTo(min(p.pixels + p.viewportDimension * 0.7, p.maxScrollExtent));
    await tester.pump();
    collectBuilt(texts, blank);
  }
  // Back to the top, where the page's buttons are (a lazy list drops what
  // scrolled away).
  p.jumpTo(0);
  await tester.pump();
  return (texts: texts, blank: blank);
}

void main() {
  testWidgets('every word detail page renders cleanly', (tester) async {
    final env = Platform.environment;
    final json = jsonDecode(File(env['SIM_PACK'] ?? 'assets/lexicon/en-zh-TW.json')
        .readAsStringSync()) as Map<String, dynamic>;
    final pack = LexiconPack.instance..loadJson(json);
    final repo = WordDatabaseRepository(
        clock: () => testNow, profile: UserVocabularyProfile.start('A2', now: testNow));
    final seed = int.parse(env['SIM_SEED'] ?? '1');
    final sample = sampleWords(pack, json).where((w) => ['can', 'tip', 'dwarf'].contains(w.lemma)).toList();
    for (final w in sample) {
      try {
        repo.addWord(word: w.lemma, pos: shortPos(w.pos), meaning: w.meaning ?? '', level: w.cefr);
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
    final learnerViews = <String, dynamic>{};
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
      final page = await sweepPage(tester);
      learnerViews[e.word] = page.texts.toList();
      for (final t in page.texts) {
        if (showsNull(t)) f.add('畫面出現 null', '${e.word}：$t');
        if (t.contains('Instance of')) f.add('畫面出現物件字串', '${e.word}：$t');
      }
      for (final h in page.blank) {
        f.add('空白標題（標題下沒有內容）', '${e.word} (${e.pos})：$h');
      }
      Navigator.of(tester.element(find.byType(Scaffold).last)).maybePop();
      await tester.pumpAndSettle();
    }
    final report = {
      'seed': seed, 'sampled': groupCounts(sample, (w) => w.group), 'entries': repo.entries.length,
      'opened': opened, 'findings': f.toJson(), 'learner_views': learnerViews,
    };
    File(env['SIM_OUT'] ?? 'build/detail_simulation.json')
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
