// Photo page UI simulation (not part of the regular suite).
//
// Real tagger replies (from tagger/cache) become photos; each photo page is
// opened on a phone screen and used the way a learner would: read the list,
// turn the difficulty dial, swipe a word away as known, show the learned
// words, and leave (which saves). Layout errors, lists over five words and
// pages that don't save are reported.
//
//   flutter test test/simulation/photo_ui_simulation.dart   (SIM_PACK, SIM_PHOTOS, SIM_SEED)

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import '../helpers.dart';
import 'learner_simulation.dart' show Findings;

void main() {
  testWidgets('learner uses the photo page on real tagger replies', (tester) async {
    final env = Platform.environment;
    final rnd = Random(int.parse(env['SIM_SEED'] ?? '1'));
    final pack = LexiconPack.instance
      ..loadJson(jsonDecode(File(env['SIM_PACK'] ?? 'assets/lexicon/en-zh-TW.json')
          .readAsStringSync()) as Map<String, dynamic>);
    final replies = Directory('../tagger/cache')
        .listSync()
        .whereType<File>()
        .where((f) => !f.uri.pathSegments.last.startsWith('score-'))
        .toList()
      ..sort((a, b) => a.path.compareTo(b.path))
      ..shuffle(rnd);
    final repo = WordDatabaseRepository(
        clock: () => testNow, profile: UserVocabularyProfile.start('A2', now: testNow));
    final f = Findings();
    var current = '';
    final original = FlutterError.onError;
    FlutterError.onError = (d) =>
        f.add('版面錯誤', '$current：${d.exceptionAsString().split('\n').first}');
    addTearDown(() => FlutterError.onError = original);

    final photos = <String>[];
    for (final file in replies) {
      if (photos.length >= int.parse(env['SIM_PHOTOS'] ?? '25')) break;
      final Object? raw;
      try {
        raw = jsonDecode(file.readAsStringSync());
      } catch (_) {
        continue;
      }
      final cands = pack.linkAll(parseCandidates(raw, lexicon: testLexicon()));
      if (cands.length < 3) continue;
      final id = 'sim-${photos.length}';
      repo.addPhoto(Photo(
          id: id, title: id, takenAt: testNow, createdAt: testNow,
          placeholderColors: const [0xFF8899AA, 0xFF334455],
          width: 1200, height: rnd.nextBool() ? 900 : 1600,
          taggingStatus: TaggingStatus.done, candidates: cands));
      photos.add(id);
    }

    final app = await pumpApp(tester, initialTab: AppTab.album, repository: repo,
        size: const Size(390, 844));
    var opened = 0;
    for (final id in photos) {
      current = id;
      app.navigator.openPhoto(id);
      await tester.pumpAndSettle();
      opened++;
      final cards = find.byWidgetPredicate(
          (w) => w.key is ValueKey<String> && (w.key as ValueKey<String>).value.startsWith('word:'));
      final listed = cards.evaluate().length;
      if (listed > 5) f.add('照片頁列出超過 5 個詞', '$id：$listed');
      // A photo with no new words keeps its list blank (spec: 照片中沒有新詞時
      // 列表保持空白): only a photo with a word not studied yet counts.
      final fresh = repo.photo(id)!.candidates.where((c) {
        final e = repo.entryByWord(c.word);
        return e == null || repo.cardOf(e.id) == null;
      });
      if (listed == 0 && fresh.isNotEmpty) f.add('照片頁沒有列出任何詞', id);
      // Dial: one step harder when it is there.
      final dial = find.bySemanticsLabel(RegExp('^單字難度 .*點一下'));
      if (dial.evaluate().isNotEmpty && rnd.nextBool()) {
        await tester.ensureVisible(dial.first);
        await tester.pumpAndSettle();
        await tester.tap(dial.first);
        await tester.pumpAndSettle();
        final harder = find.bySemanticsLabel(RegExp('^難度 B[12]'));
        if (harder.evaluate().isNotEmpty) {
          await tester.ensureVisible(harder.first);
          await tester.pumpAndSettle();
          await tester.tap(harder.first);
          await tester.pumpAndSettle();
        } else {
          final texts = [
            for (final t in tester.widgetList<Text>(find.byType(Text)))
              if ((t.data ?? '').contains('難度') || (t.data ?? '').contains('A1') || (t.data ?? '').contains('B1')) t.data
          ];
          f.add('輪盤展開後找不到難度刻度', '$id 畫面文字：$texts '
              '收起：${find.bySemanticsLabel('收起難度選單').evaluate().length} '
              '轉盤：${find.bySemanticsLabel(RegExp('^單字難度 ')).evaluate().length}');
        }
      }
      // Swipe the first word away as known.
      if (cards.evaluate().isNotEmpty && rnd.nextDouble() < 0.5) {
        final key = (cards.evaluate().first.widget.key as ValueKey<String>).value;
        await tester.ensureVisible(find.byKey(ValueKey(key)));
        await tester.pumpAndSettle();
        await tester.drag(find.byKey(ValueKey(key)), const Offset(-500, 0));
        await tester.pumpAndSettle();
        final word = key.substring(5);
        final e = repo.entryByWord(word);
        if (!(repo.profile.learned.contains(word) || (e != null && repo.isArchived(e.id)))) {
          f.add('左滑後沒有進入已學會', '$id $word');
        }
        final sw = find.byType(Switch);
        if (sw.evaluate().isNotEmpty) {
          await tester.tap(sw.first);
          await tester.pumpAndSettle();
        }
      }
      final back = find.bySemanticsLabel('返回');
      if (back.evaluate().isEmpty) {
        f.add('照片頁沒有返回按鈕', id);
        continue;
      }
      await tester.tap(back.first);
      await tester.pumpAndSettle();
      final p = repo.photo(id);
      if (p != null && p.wordsSavedAt == null && repo.occurrencesInPhoto(id).isEmpty) {
        f.add('離開照片頁沒有保存', id);
      }
    }
    final report = {'opened': opened, 'findings': f.toJson()};
    File('build/photo_ui_simulation.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(const JsonEncoder.withIndent(' ').convert(report));
    // ignore: avoid_print
    print(const JsonEncoder.withIndent(' ').convert({'opened': opened, 'counts': f.counts}));
  }, timeout: const Timeout(Duration(minutes: 20)));
}
