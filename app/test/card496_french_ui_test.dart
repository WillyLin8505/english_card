// 卡 #496 (M156–M162, 問題回報 #494): a French learner on an English (or
// French) phone sees no Chinese UI copy in 設定, 單字本, 複習 and 照片詳情.
// Learner content (titles they typed) is out of scope; the sample words here
// carry English meanings, so any Chinese on screen is UI copy.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';
import 'simulation/learner_view_simulation.dart' show screenTexts;

final _cjk = RegExp(r'[一-鿿]');

WordCandidate _cand(String word, String pos, String meaning) => WordCandidate(
      word: word,
      pos: pos,
      meaning: meaning,
      level: 'A1',
      levelSource: 'cefr-j',
      evidence: '$word in the photo',
      point: const LabelPoint(0.3, 0.4),
      visualConfidence: 0.9,
    );

WordDatabaseRepository _frenchRepo() {
  final repo = WordDatabaseRepository(language: 'fr', clock: () => testNow);
  repo.addWord(word: 'manger', pos: 'verb', meaning: 'to eat', level: 'A1');
  repo.addWord(word: 'petit', pos: 'adj.', meaning: 'small', level: 'A1');
  final at = DateTime(2026, 10, 21);
  repo.addDeckPhoto(
      Photo(id: 'p1', title: 'cuisine', takenAt: at, createdAt: at),
      [_cand('table', 'noun', 'table'), _cand('chaise', 'noun', 'chair')]);
  return repo;
}

Future<Set<String>> _scan(WidgetTester tester) async {
  final seen = <String>{};
  final scrollable = find.byType(Scrollable);
  for (var k = 0; k < 6; k++) {
    seen.addAll(screenTexts(tester).where(_cjk.hasMatch));
    if (scrollable.evaluate().isEmpty) break;
    await tester.drag(scrollable.first, const Offset(0, -600),
        warnIfMissed: false);
    await tester.pumpAndSettle();
  }
  return seen;
}

void main() {
  test('photo-detail and settings copy translate whole', () {
    expect(translateUi('入門（A1） · 剛好', 'en'), 'Beginner（A1） · At your level');
    expect(translateUi('辨識單字列表 (2)', 'fr'), 'Mots reconnus (2)');
    // Not the generic 「{0} 張」 (→ "每天最多複習 100 photos").
    expect(translateUi('每天最多複習 100 張', 'en'), 'Up to 100 reviews a day');
    expect(translateUi('已把「chat」移到已學會', 'en'), 'Moved “chat” to Learned');
    expect(
        translateUi(
            '來源：{0}。新照片的單字會以這個程度為中心挑選；照片詳情的難度轉盤只影響那一張照片。'
                .replaceFirst('{0}', 'X'),
            'en'),
        startsWith('Source: X. New photos'));
  });

  for (final native in ['en', 'fr']) {
    testWidgets('French learner, $native phone: no Chinese UI copy',
        (tester) async {
      // The test font draws every glyph 1em wide, so longer French copy
      // overflows rows that fit on a phone; only the words are checked here.
      final original = FlutterError.onError;
      FlutterError.onError = (d) {
        if (!d.exceptionAsString().contains('overflowed')) original?.call(d);
      };
      addTearDown(() => FlutterError.onError = original);
      final repo = _frenchRepo();
      final settings =
          AppSettings.inMemory(learningLanguage: 'fr', nativeLanguage: native);
      final found = <String, Set<String>>{};
      for (final tab in [AppTab.settings, AppTab.words, AppTab.album]) {
        await tester.pumpWidget(const SizedBox());
        await pumpApp(tester,
            initialTab: tab,
            repository: repo,
            settings: settings,
            size: const Size(390, 844));
        await tester.pumpAndSettle();
        found[tab.name] = await _scan(tester);
        if (tab == AppTab.settings) {
          // 進階設定 is collapsed: open it and read it too.
          final advanced = find.text(translateUi('進階設定', native));
          await tester.ensureVisible(advanced);
          await tester.pumpAndSettle();
          await tester.tap(advanced, warnIfMissed: false);
          await tester.pumpAndSettle();
          expect(find.byType(Slider), findsWidgets);
          found[tab.name]!.addAll(await _scan(tester));
        }
      }
      // 照片詳情.
      final app = await pumpApp(tester,
          initialTab: AppTab.album,
          repository: repo,
          settings: settings,
          size: const Size(390, 844));
      await tester.pumpAndSettle();
      app.navigator.openPhoto('p1');
      await tester.pumpAndSettle();
      found['photo'] = await _scan(tester);
      // 單字詳情.
      await tester.pumpWidget(const SizedBox());
      final app2 = await pumpApp(tester,
          initialTab: AppTab.words,
          repository: repo,
          settings: settings,
          size: const Size(390, 844));
      await tester.pumpAndSettle();
      app2.navigator.openWord(repo.entryByWord('table')!.id);
      await tester.pumpAndSettle();
      found['word'] = await _scan(tester);
      // 複習: start, front, back.
      await tester.pumpWidget(const SizedBox());
      await pumpApp(tester,
          initialTab: AppTab.review,
          repository: repo,
          settings: settings,
          size: const Size(390, 844));
      await tester.pumpAndSettle();
      found['review'] = screenTexts(tester).where(_cjk.hasMatch).toSet();
      if (await startReview(tester, label: (s) => translateUi(s, native))) {
        await tester.pumpAndSettle();
        found['front'] = screenTexts(tester).where(_cjk.hasMatch).toSet();
        final show = find.text(translateUi('顯示答案', native));
        if (show.evaluate().isNotEmpty) {
          await tester.tap(show.first);
          await tester.pumpAndSettle();
          found['back'] = await _scan(tester);
        }
      }
      expect(found.keys,
          containsAll(['settings', 'words', 'photo', 'word', 'front', 'back']));
      found.removeWhere((_, v) => v.isEmpty);
      expect(found, isEmpty);
    });
  }
}
