// 問題回報 #845、#848、#850、#851、#852（owner，照片詳情）:
// - #845 「旁邊的字都截到了 簡單跟困難」: 難度條兩端的「簡單」「難」不能被螢幕切掉。
// - #848 「下面單字不要縮起來 要完整呈現單字和一個簡短說明」.
// - #850 「給我一個儲存的按鈕…單字一個個跳到單字庫裡面，圖片跳到相片冊，然後畫面會到拍照的地方」.
// - #851 「還在打標籤的動畫在清楚一點」.
// - #852 來回滑動難度條時標籤要固定，C1 的字不該出現在最簡單的位置。

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/screens/photo_detail_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_selector.dart';
import 'package:photo_english_app/widgets/mobile/tab_bar.dart';

import 'helpers.dart';

WordCandidate _c(String word,
        {String pos = 'noun',
        String level = 'A1',
        String? meaning,
        double x = 0.5}) =>
    WordCandidate(
      word: word,
      pos: pos,
      meaning: meaning ?? '$word 義',
      level: level,
      levelSource: 'cefr-j',
      evidence: 'seen',
      point: LabelPoint(x, 0.5),
      visualConfidence: 0.9,
      usefulness: 0.8,
    );

/// A photo just taken and tagged, not saved yet.
Photo _fresh(String id, List<WordCandidate> candidates) => Photo(
      id: id,
      title: id,
      takenAt: testNow,
      createdAt: testNow,
      placeholderColors: const [0xFF8899AA, 0xFF334455],
      width: 1200,
      height: 900,
      taggingStatus: TaggingStatus.done,
      candidates: candidates,
    );

void main() {
  group('#845 the difficulty bar ends', () {
    for (final width in [375.0, 1024.0]) {
      testWidgets('簡單 and 難 are inside the screen at $width pt',
          (tester) async {
        final app = await pumpApp(tester,
            initialTab: AppTab.album, size: Size(width, 1400));
        app.navigator.openPhoto('photo-breakfast');
        await tester.pumpAndSettle();

        for (final key in ['difficulty-easy', 'difficulty-hard']) {
          final r = tester.getRect(find.byKey(ValueKey(key)));
          expect(r.left, greaterThanOrEqualTo(8), reason: key);
          expect(r.right, lessThanOrEqualTo(width - 8), reason: key);
        }
        // The thumb still reaches both ends of the track.
        final track =
            tester.getRect(find.byKey(const ValueKey('difficulty-track')));
        for (final (dx, end) in [
          (track.left + 2, track.left),
          (track.right - 2, track.right),
        ]) {
          await tester.tapAt(Offset(dx, track.center.dy));
          await tester.pumpAndSettle();
          final thumb =
              tester.getRect(find.byKey(const ValueKey('difficulty-thumb')));
          expect((thumb.center.dx - end).abs(), lessThan(14));
          expect(thumb.left, greaterThanOrEqualTo(0));
          expect(thumb.right, lessThanOrEqualTo(width));
        }
      });
    }
  });

  group('#848 the word rows', () {
    test('a short meaning: the first sense, two synonyms at most', () {
      expect(briefMeaning('不清楚、陰暗的、模糊的；不顯眼的'), '不清楚、陰暗的');
      expect(briefMeaning('顯眼的；引人注目的'), '顯眼的');
      expect(briefMeaning('集會：教會會眾'), '集會');
      expect(briefMeaning('集合'), '集合');
      expect(briefMeaning('[片語] 收起來、存放'), '[片語] 收起來、存放');
    });

    testWidgets('long words show in full at 375 pt, with a short meaning',
        (tester) async {
      final app = await pumpApp(tester,
          initialTab: AppTab.album, size: const Size(375, 1600));
      app.repository.addPhoto(_fresh('p848', [
        _c('conspicuous',
            pos: 'adj.', level: 'B2', meaning: '顯眼的、引人注目的、明顯的；突出的', x: 0.2),
        _c('congregation', level: 'B2', meaning: '集會、會眾、聚集；教會', x: 0.5),
      ]));
      app.navigator.openPhoto('p848');
      await tester.pumpAndSettle();

      for (final word in ['Conspicuous', 'Congregation']) {
        final f = find.byKey(ValueKey('word-card-word-$word'));
        expect(f, findsOneWidget, reason: word);
        final text = tester.widget<Text>(f);
        expect(text.data, word);
        expect(text.overflow, isNot(TextOverflow.ellipsis));
        final para = tester.renderObject<RenderParagraph>(f);
        expect(para.didExceedMaxLines, isFalse);
        // On screen, left of the row's buttons.
        final r = tester.getRect(f);
        expect(r.left, greaterThanOrEqualTo(0));
        expect(r.right, lessThan(375));
      }
      expect(find.text('顯眼的、引人注目的'), findsOneWidget);
      expect(find.text('集會、會眾'), findsOneWidget);
      // The row's buttons are all on screen.
      for (final b in find.byTooltip('管理這個單字').evaluate()) {
        expect(tester.getRect(find.byWidget(b.widget)).right,
            lessThanOrEqualTo(375));
      }
    });
  });

  group('#850 儲存', () {
    final pool = [
      _c('cup', x: 0.1),
      _c('run', pos: 'verb', x: 0.3),
      _c('red', pos: 'adj.', x: 0.5),
      _c('table', x: 0.7),
      _c('sit', pos: 'verb', x: 0.9),
    ];

    Future<TestApp> open(WidgetTester tester) async {
      final app = await pumpApp(tester,
          initialTab: AppTab.album, size: const Size(402, 1600));
      app.repository.addPhoto(_fresh('p850', pool));
      app.navigator.openPhoto('p850');
      await tester.pumpAndSettle();
      return app;
    }

    AppTab tab(WidgetTester tester) =>
        tester.widget<MobileTabBar>(find.byType(MobileTabBar)).current;

    int labels(TestApp app) => app.repository.occurrencesInPhoto('p850').length;

    testWidgets('saves once, flies, then opens 拍照', (tester) async {
      final app = await open(tester);
      final button = find.byKey(const ValueKey('photo-save'));
      expect(button, findsOneWidget);
      expect(app.repository.photo('p850')!.wordsSavedAt, isNull);

      await tester.ensureVisible(button);
      await tester.tap(button);
      await tester.pump();
      expect(app.repository.photo('p850')!.wordsSavedAt, isNotNull);
      final saved = labels(app);
      expect(saved, greaterThan(0));
      expect(find.byKey(const ValueKey('save-flight')), findsOneWidget);
      expect(tab(tester), AppTab.album, reason: 'still flying');

      await tester.pump(const Duration(milliseconds: 1900));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('save-flight')), findsNothing);
      expect(tab(tester), AppTab.camera);
      expect(find.byType(PhotoDetailScreen), findsNothing,
          reason: 'the album tab is back on the album');
      expect(labels(app), saved, reason: 'leaving did not save again');
    });

    testWidgets('a tap skips the animation', (tester) async {
      await open(tester);
      final button = find.byKey(const ValueKey('photo-save'));
      await tester.ensureVisible(button);
      await tester.tap(button);
      await tester.pump(const Duration(milliseconds: 200));
      await tester.tap(find.byKey(const ValueKey('save-flight')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('save-flight')), findsNothing);
      expect(tab(tester), AppTab.camera);
    });

    testWidgets('reduced motion: no flying, a toast', (tester) async {
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(disableAnimations: true);
      addTearDown(
          tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
      final app = await open(tester);
      final button = find.byKey(const ValueKey('photo-save'));
      await tester.ensureVisible(button);
      await tester.tap(button);
      await tester.pump();
      expect(find.byKey(const ValueKey('save-flight')), findsNothing);
      expect(find.text('已儲存到單字本和相片冊'), findsOneWidget);
      await tester.pumpAndSettle();
      expect(tab(tester), AppTab.camera);
      expect(app.repository.photo('p850')!.wordsSavedAt, isNotNull);
    });

    testWidgets('a saved photo has no 儲存 button', (tester) async {
      final app = await pumpApp(tester,
          initialTab: AppTab.album, size: const Size(402, 1600));
      app.navigator.openPhoto('photo-breakfast');
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('photo-save')), findsNothing);
    });
  });

  testWidgets('#851 a note on the photo while it is rescanned', (tester) async {
    final settings = AppSettings.inMemory(
        taggingUrl: 'http://predator:8765/tag', apiKey: 'k');
    final app = await pumpApp(
      tester,
      initialTab: AppTab.album,
      settings: settings,
      size: const Size(402, 1400),
      createTagger: (uri, key) => TaggingService(
        endpoint: uri,
        apiKey: key,
        client: MockClient((http.Request request) async {
          await Future<void>.delayed(const Duration(milliseconds: 200));
          return jsonResponse({'candidates': <Object>[]});
        }),
      ),
    );
    app.navigator.openPhoto('photo-breakfast');
    await tester.pumpAndSettle();
    final label = find.byKey(const ValueKey('photo-scanning-label'));
    expect(label, findsNothing);

    await tester.tap(find.byKey(const ValueKey('rescan-tags')));
    await tester.pump();
    expect(label, findsOneWidget);
    expect(find.text('AI 正在找單字…'), findsOneWidget);
    expect(find.byKey(const ValueKey('photo-scan-band')), findsOneWidget);

    for (var i = 0; i < 40 && label.evaluate().isNotEmpty; i++) {
      await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 50)));
      await tester.pump(const Duration(milliseconds: 50));
    }
    expect(label, findsNothing);
    expect(find.byKey(const ValueKey('photo-scan-band')), findsNothing);
  });

  group('#852 the dial shows the same labels at each position', () {
    final profile = UserVocabularyProfile.start('A1', now: testNow);
    final pool = [
      for (final (i, w)
          in ['cup', 'bowl', 'spoon', 'plate', 'fork', 'table'].indexed)
        _c(w, level: i.isEven ? 'A1' : 'A2', x: 0.1 + i * 0.12),
      _c('eat', pos: 'verb', x: 0.2),
      _c('hot', pos: 'adj.', level: 'A2', x: 0.4),
      _c('utensil', level: 'B2', x: 0.6),
      _c('ladle', level: 'B1', x: 0.7),
      _c('obscure', pos: 'adj.', level: 'C1', x: 0.8),
      _c('conspicuous', pos: 'adj.', level: 'C1', x: 0.85),
      _c('congregate', pos: 'verb', level: 'C2', x: 0.9),
      _c('amass', pos: 'verb', level: 'C2', x: 0.95),
    ];

    PhotoWordSession session() {
      final repo =
          WordDatabaseRepository(clock: () => testNow, profile: profile);
      repo.addPhoto(_fresh('p852', pool));
      final s = PhotoWordSession(repo: repo, photoId: 'p852');
      addTearDown(s.dispose);
      return s;
    }

    List<String> shown(PhotoWordSession s) => [for (final w in s.words) w.word];

    test('0 → 4 → 0, step by step and back, shows the same words', () {
      final s = session();
      s.setTarget(0);
      final first = shown(s);
      expect(first, hasLength(WordSelector.maxWords));
      for (var i = 1; i <= 4; i++) {
        s.setTarget(i, live: true);
      }
      final atFour = shown(s);
      for (var i = 3; i >= 0; i--) {
        s.setTarget(i, live: true);
      }
      expect(shown(s), first);
      s.setTarget(4, live: true);
      expect(shown(s), atFour);
    });

    test('a position reached directly or by sliding shows the same words', () {
      final a = session()..setTarget(2, live: true);
      final b = session();
      for (final i in [0, 1, 4, 3, 2]) {
        b.setTarget(i, live: true);
      }
      expect(shown(b).toSet(), shown(a).toSet());
    });

    test('the easiest position shows no C1/C2 word', () {
      final s = session();
      for (final i in [4, 5, 3, 1, 0]) {
        s.setTarget(i, live: true);
      }
      final levels = [for (final w in s.words) w.candidate.level];
      expect(levels, hasLength(WordSelector.maxWords));
      expect(levels.where((l) => l == 'C1' || l == 'C2'), isEmpty,
          reason: '$levels');
    });

    test('a starred word stays at every position', () {
      final s = session()..setTarget(0);
      final w = s.words.first;
      s.toggleStar(w);
      for (final i in [3, 5, 0]) {
        s.setTarget(i, live: true);
        expect(shown(s), contains(w.word));
      }
    });
  });
}
