import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/screens/onboarding_screen.dart';
import 'package:photo_english_app/screens/photo_picker_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/dictionary_sync.dart';
import 'package:photo_english_app/services/speaker.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';

import 'helpers.dart';

/// Two words due for review, one with a photo, for flashcard tests.
WordDatabaseRepository tinyRepository() {
  final full = testRepository();
  final keep = {'railing', 'coffee'};
  final entries = [
    for (final e in full.entries)
      if (keep.contains(e.word)) e,
  ];
  final kitchen = full.photo('photo-kitchen')!;
  return WordDatabaseRepository(
    entries: entries,
    photos: [kitchen],
    occurrences: [
      for (final o in full.occurrencesInPhoto(kitchen.id))
        if (full.entry(o.wordEntryId)?.word == 'coffee') o,
    ],
    cards: [for (final e in entries) full.cardOf(e.id)!],
    clock: () => testNow,
  );
}

void main() {
  group('我的單字本 · Mobile', () {
    testWidgets('alphabetical, one row per word; a row opens 單字詳情',
        (tester) async {
      final app = await pumpApp(tester, initialTab: AppTab.words);
      expect(find.text('我的單字本'), findsOneWidget);
      expect(find.text('apple'), findsOneWidget);
      expect(find.text('第 1-8 個，共 21 個'), findsOneWidget);

      // A failed background fetch is marked in the list.
      app.repository.applyWordData(app.repository.entryByWord('apple')!.id,
          status: WordDataStatus.failed, error: '連不到');
      await tester.pump();
      expect(find.byTooltip('資料取得失敗，稍後自動重試'), findsOneWidget);

      await tester.tap(find.text('balcony'));
      await tester.pumpAndSettle();
      expect(find.text('單字詳情'), findsOneWidget);
      expect(find.text('Balcony'), findsOneWidget);
    });

    testWidgets('開始複習 goes to the 複習 tab', (tester) async {
      await pumpApp(tester, initialTab: AppTab.words);
      await tester.tap(find.text('開始複習'));
      await tester.pumpAndSettle();
      expect(find.text('想複習哪一本？'), findsOneWidget);
    });
  });

  group('相片冊', () {
    testWidgets('albums with word counts; hourglass on waiting photos',
        (tester) async {
      final app = await pumpApp(tester, initialTab: AppTab.album);
      expect(find.text('早餐時光'), findsOneWidget);
      expect(find.text('5 個單字'), findsWidgets);
      expect(find.bySemanticsLabel(RegExp('等待 AI 辨識')), findsNothing);

      app.repository.addPhoto(Photo(
        id: 'p-wait',
        albumId: 'album-breakfast',
        title: '排隊中',
        takenAt: testNow,
        storedKey: 'p-wait',
        createdAt: testNow,
        taggingStatus: TaggingStatus.pending,
      ));
      await tester.pump();
      expect(find.bySemanticsLabel(RegExp('等待 AI 辨識')), findsOneWidget);

      await tester.tap(find.text('早餐時光'));
      await tester.pumpAndSettle();
      expect(find.text('排隊中'), findsOneWidget);
      expect(find.bySemanticsLabel(RegExp('等待 AI 辨識')), findsOneWidget);
    });
  });

  group('照片詳情', () {
    Future<TestApp> openBreakfast(WidgetTester tester) async {
      final app = await pumpApp(tester,
          initialTab: AppTab.album, size: const Size(402, 1400));
      app.navigator.openPhoto('photo-breakfast');
      await tester.pumpAndSettle();
      return app;
    }

    testWidgets('saved words, the dial re-picks, ☆ keeps, leaving saves',
        (tester) async {
      final app = await openBreakfast(tester);
      expect(find.text('辨識單字列表 (5)'), findsOneWidget);
      expect(find.text('Coffee'), findsNWidgets(2)); // pin + card
      expect(find.text('入門（A1） · 剛好'), findsOneWidget);

      // ☆ Apple, then turn the dial to B2.
      await tester.tap(find.bySemanticsLabel('鎖定（調整難度時保留）').at(1));
      await tester.pump();
      // The difficulty bar under the photo (問題回報 #442): tap the B2 tick.
      await tester.tap(find.text('B2'));
      await tester.pumpAndSettle();
      expect(find.text('中高階（B2） · 挑戰'), findsOneWidget);
      expect(find.text('Apple'), findsNWidgets(2), reason: 'starred');
      expect(find.text('Coffee'), findsNothing,
          reason: 'A1 is too far from B2');

      // Nothing is written until the page is left.
      final apple = app.repository.entryByWord('apple')!;
      expect(app.repository.photo('photo-breakfast')!.difficultyOffset, 0);
      await tester.tap(find.bySemanticsLabel('返回'));
      await tester.pumpAndSettle();
      final photo = app.repository.photo('photo-breakfast')!;
      expect(photo.difficultyOffset, 3);
      final words = {
        for (final l in app.repository.activeLabels(photo.id)) l.entry.word,
      };
      expect(words, contains('apple'));
      expect(words, isNot(contains('coffee')));
      expect(app.repository.cardOf(apple.id), isNotNull);
    });

    testWidgets('自動保存提示在列表標題旁，不在所有單字之後（問題回報 #276）',
        (tester) async {
      await openBreakfast(tester);
      final hint = find.text('返回時自動保存，不用再按建立。');
      expect(hint, findsOneWidget);
      final titleY = tester.getTopLeft(find.text('辨識單字列表 (5)')).dy;
      final hintY = tester.getTopLeft(hint).dy;
      final firstWordY = tester.getTopLeft(find.byType(Dismissible).first).dy;
      expect(hintY, greaterThan(titleY));
      expect(hintY, lessThan(firstWordY), reason: 'visible before any word');
      expect(find.textContaining('離開這一頁時會自動保存'), findsNothing,
          reason: 'the bottom hint no longer repeats the save rule');
    });

    testWidgets('swipe left → 已學會; 顯示已學會單字 shows 復原', (tester) async {
      final app = await openBreakfast(tester);
      await tester.drag(
          find.byKey(const ValueKey('word:bread')), const Offset(-500, 0));
      await tester.pumpAndSettle();
      expect(find.text('已把「Bread」移到已學會'), findsOneWidget);
      expect(app.repository.isArchived(app.repository.entryByWord('bread')!.id),
          isTrue);
      expect(find.text('辨識單字列表 (5)'), findsOneWidget, reason: 'refilled');

      await tester.tap(find.byType(Switch));
      await tester.pumpAndSettle();
      expect(find.text('已學會與學習中的舊詞'), findsOneWidget);
      // Scroll it clear of the bottom edge first (the list's height changed in #444).
      await tester.ensureVisible(find.bySemanticsLabel(RegExp('^復原 Bread')));
      await tester.pumpAndSettle();
      await tester.tap(find.bySemanticsLabel(RegExp('^復原 Bread')));
      await tester.pumpAndSettle();
      expect(app.repository.isArchived(app.repository.entryByWord('bread')!.id),
          isFalse);
    });

    testWidgets('為什麼是這些字？ explains the picks', (tester) async {
      await openBreakfast(tester);
      await tester.tap(find.text('難一點'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('為什麼是這些字？'));
      await tester.pumpAndSettle();
      expect(find.textContaining('程度適配'), findsWidgets);
      // The reasons list is long; the studying-elsewhere word may be far down.
      await tester.scrollUntilVisible(find.textContaining('已在學習（其他照片）'), 200,
          scrollable: find.byType(Scrollable).last);
      expect(find.textContaining('已在學習（其他照片）'), findsWidgets);
    });

    testWidgets('a photo waiting for the tagger says so', (tester) async {
      final app = await pumpApp(tester, initialTab: AppTab.album);
      app.repository.addPhoto(Photo(
        id: 'p-wait',
        title: '排隊中',
        takenAt: testNow,
        storedKey: 'p-wait',
        createdAt: testNow,
        taggingStatus: TaggingStatus.pending,
      ));
      app.navigator.openPhoto('p-wait');
      await tester.pumpAndSettle();
      // Not set up is said plainly — not an hourglass that looks like progress.
      expect(find.text('這台裝置沒有照片辨識'), findsNWidgets(2)); // photo badge + list
      expect(find.text('等待 AI 辨識'), findsNothing);
      // The notice sits under the difficulty bar, below the fold.
      await tester.ensureVisible(find.text('前往設定'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('前往設定'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(find.text('目前程度 入門（A1）'), 200,
          scrollable: find.byType(Scrollable).last);
      expect(find.text('目前程度 入門（A1）'), findsOneWidget);

      // Set up but unreachable: waiting, with the reason.
      app.settings.taggingUrl = 'http://127.0.0.1:8765/tag';
      app.repository.updatePhoto(app.repository.photo('p-wait')!.copyWith(
          taggingError: () => describeTaggingError(TimeoutException('x'), '')));
      await tester.tap(find.text('相片冊'));
      await tester.pumpAndSettle();
      expect(find.text('等待 AI 辨識'), findsNWidgets(2));
      expect(find.textContaining('太久沒有回應'), findsOneWidget);
    });
  });

  group('選擇照片 → 背景辨識 → 選詞', () {
    testWidgets('完成 saves the photo; candidates arrive; leaving creates cards',
        (tester) async {
      final settings = AppSettings.inMemory(
          taggingUrl: 'http://predator:8765/tag', apiKey: 'k');
      final requests = <http.BaseRequest>[];
      final app = await pumpApp(
        tester,
        initialTab: AppTab.album,
        settings: settings,
        createTagger: (uri, key) => TaggingService(
          endpoint: uri,
          apiKey: key,
          client: MockClient((request) async {
            requests.add(request);
            if (request.url.path == '/enrich') {
              return jsonResponse({'examples': []});
            }
            return jsonResponse({
              'candidates': [
                {
                  'word': 'pasta',
                  'pos': 'noun',
                  'meaning': '義大利麵',
                  'cefr': 'A2',
                  'point': [0.5, 0.5],
                  'visualConfidence': 0.95
                },
                {
                  'word': 'fork',
                  'pos': 'noun',
                  'meaning': '叉子',
                  'cefr': 'A1',
                  'point': [0.2, 0.55],
                  'visualConfidence': 0.9
                },
                {
                  'word': 'twirl',
                  'pos': 'verb',
                  'meaning': '捲',
                  'cefr': 'B2',
                  'point': [0.5, 0.4],
                  'visualConfidence': 0.7
                },
              ],
            });
          }),
        ),
      );
      final photosBefore = app.repository.photoCount;
      await tester.tap(find.text('選擇新照片'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('完成'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('儲存'));
      await settle(tester);

      expect(app.repository.photoCount, photosBefore + 1);
      final tag = requests.firstWhere((r) => r.url.path == '/tag');
      expect(tag.headers['X-API-Key'], 'k');
      expect(tag.url.queryParameters['level'], 'A1');
      expect(find.text('照片詳情'), findsOneWidget);
      expect(find.text('Pasta'), findsWidgets);
      expect(find.text('Fork'), findsWidgets);
      // Suggested only — no entries until the page is left.
      expect(app.repository.entryByWord('pasta'), isNull);

      await tester.tap(find.bySemanticsLabel('返回'));
      await settle(tester);
      final pasta = app.repository.entryByWord('pasta')!;
      expect(pasta.meaning, '義大利麵');
      expect(app.repository.cardOf(pasta.id), isNotNull);
      final fork = app.repository
          .occurrencesOf(app.repository.entryByWord('fork')!.id)
          .single;
      expect((fork.anchor.x, fork.anchor.y), (0.2, 0.55));
    });
  });

  group('單字詳情', () {
    testWidgets('all photos and dictionary content are expanded',
        (tester) async {
      final app = await pumpApp(tester,
          initialTab: AppTab.words, size: const Size(402, 1600));
      final apple = app.repository.entryByWord('apple')!;
      app.repository.review(app.repository.cardOf(apple.id)!.id, Rating.hard);
      app.navigator.openWord(apple.id);
      await tester.pumpAndSettle();

      expect(find.text('Apple'), findsOneWidget);
      expect(find.text('蘋果'), findsOneWidget);
      expect(find.text('出現這個單字的照片（2）'), findsOneWidget);
      expect(find.text('I eat an apple every day.'), findsOneWidget);
      expect(find.text('Fruit'),
          findsNothing); // untranslated legacy associations are not taught
      expect(find.text('apples（複數）'), findsOneWidget);
      expect(find.text('更多單字資訊'), findsNothing);
      expect(find.text('學習資訊'), findsNothing);
      expect(find.text('同音詞'), findsNothing); // empty → no heading

      await tester.tap(find.bySemanticsLabel('播放發音').first);
      expect((app.speaker as SilentSpeaker).said, ['apple']);

      await tester.tap(find.bySemanticsLabel('編輯單字'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).first, '紅蘋果');
      await tester.tap(find.text('儲存'));
      await tester.pumpAndSettle();
      expect(app.repository.entry(apple.id)!.meaning, '紅蘋果');
      expect(app.repository.entry(apple.id)!.userEdited, {WordField.meaning});

      await tester.tap(find.text('標為已學會'));
      await tester.pumpAndSettle();
      expect(app.repository.isArchived(apple.id), isTrue);
      await tester.tap(find.text('復原學習'));
      await tester.pumpAndSettle();
      expect(app.repository.isArchived(apple.id), isFalse);
    });
  });

  group('拍照', () {
    testWidgets('without a camera, shows the newest photo and its words',
        (tester) async {
      await pumpApp(tester);
      await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 100)));
      await tester.pumpAndSettle();
      expect(find.text('拍照學單字'), findsOneWidget);
      expect(find.text('目前無法使用相機'), findsOneWidget);
      expect(find.text('重試相機'), findsOneWidget);
      expect(find.text('Cutting Board'), findsOneWidget);
      expect(find.text('Plate'), findsNothing, reason: 'five words per photo');
    });

    testWidgets('with no photo yet, the bottom chip opens the picker',
        (tester) async {
      await pumpApp(tester,
          repository: WordDatabaseRepository(clock: () => testNow));
      await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 100)));
      await tester.pumpAndSettle();
      await tester.tap(find.text('先選一張照片開始學習'));
      await tester.pumpAndSettle();
      expect(find.byType(PhotoPickerScreen), findsOneWidget);
    });
  });

  group('複習 (Flashcard)', () {
    testWidgets('a card without Chinese waits and starts after enrichment',
        (tester) async {
      final repo = WordDatabaseRepository(clock: () => testNow);
      final word = repo.addWord(word: 'unfilled', pos: 'adj.', meaning: '');
      await pumpApp(tester,
          initialTab: AppTab.review,
          repository: repo,
          size: const Size(402, 900));
      expect(find.text('等待詞庫補齊'), findsOneWidget);
      expect(find.text('綜合'), findsNothing);

      repo.applyWordData(word.id,
          meaning: '尚未填寫的', status: WordDataStatus.complete);
      await tester.pump();
      // No photo, example or related word yet: review falls back to the
      // traditional flip card instead of waiting (問題回報 #207 decision A).
      expect(find.text('綜合'), findsOneWidget);
    });

    testWidgets('front without photo; flip plays the word; Again comes back',
        (tester) async {
      final repo = tinyRepository();
      final app = await pumpApp(tester,
          initialTab: AppTab.review,
          repository: repo,
          size: const Size(402, 1400));
      await tester.tap(find.text('綜合'));
      await tester.pumpAndSettle();

      String currentWord() => repo
          .entry(repo
              .card(repo.eligibleCards().isEmpty
                  ? ''
                  : repo.eligibleCards().first.id)!
              .wordEntryId)!
          .word;
      expect(currentWord(), isNotEmpty);
      // Front: one of the five interactive exercises, without revealing the answer.
      expect(find.byType(FlashcardFront), findsOneWidget);
      expect(
          ['句子填空', '看圖選單字', '相似詞配對', '母語說明＋照片', '拖曳到圖片']
              .where((label) => find.text(label).evaluate().isNotEmpty),
          isEmpty);
      expect(find.text('Railing'), findsNothing);
      expect(find.text('Coffee'), findsNothing);

      await tester.tap(find.text('顯示答案'));
      await tester.pumpAndSettle();
      expect(find.byType(FlashcardBack), findsOneWidget);
      // Card #251: both accents in a row, so the word is said twice.
      expect((app.speaker as SilentSpeaker).said, hasLength(2),
          reason: '翻到背面時自動播放英式、美式各一次');
      // Native-language grades with their next interval.
      expect(find.text('忘記'), findsOneWidget);
      expect(find.text('很容易'), findsOneWidget);

      final first = (app.speaker as SilentSpeaker).said.first;
      await tester.tap(find.text('忘記'));
      await tester.pumpAndSettle();
      // Keyboard: Space flips, 3 = Good.
      await tester.sendKeyEvent(LogicalKeyboardKey.space);
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.digit3);
      await tester.pumpAndSettle();
      // Only two cards: the Again card comes back instead of stopping.
      expect(find.byType(FlashcardFront), findsOneWidget);
      await tester.tap(find.text('顯示答案'));
      await tester.pumpAndSettle();
      expect((app.speaker as SilentSpeaker).said.last, first);
      await tester.tap(find.text('記得'));
      await tester.pumpAndSettle();
      expect(find.text('自由加練，不更動下次複習時間'), findsNothing);
      expect(find.bySemanticsLabel('刪除此卡片'), findsOneWidget);
      expect(find.textContaining('張'), findsNothing, reason: 'no card counts');
    });

    test('firstLetterHint keeps words and spaces', () {
      expect(firstLetterHint('balcony'), 'b _ _ _ _ _ _');
      expect(firstLetterHint('cutting board'), 'c _ _ _ _ _ _   _ _ _ _ _');
      expect(firstLetterHint('well-being'), 'w _ _ _ - _ _ _ _ _');
      expect(firstLetterHint('café'), 'c _ _ _');
    });
  });

  group('設定', () {
    Future<void> check(
        WidgetTester tester, MockClient client, String expected) async {
      final settings = AppSettings.inMemory(
          taggingUrl: 'http://127.0.0.1:8765/tag', apiKey: 'k');
      await pumpApp(
        tester,
        initialTab: AppTab.settings,
        settings: settings,
        size: const Size(402, 1600),
        createTagger: (uri, key) =>
            TaggingService(endpoint: uri, apiKey: key, client: client),
      );
      await tester.scrollUntilVisible(find.text('進階設定'), 300);
      await tester.tap(find.text('進階設定'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('測試連線'));
      await tester.pump();
      await tester.tap(find.text('測試連線'));
      await settle(tester, rounds: 1);
      expect(find.text(expected), findsOneWidget);
    }

    http.Response health(bool? keyOk) => jsonResponse(
        {'ok': true, 'model': 'qwen3-vl', 'ollama': true, 'keyOk': keyOk});

    testWidgets('測試連線: connected', (tester) async {
      late Uri asked;
      await check(tester, MockClient((r) async {
        if (r.url.path != '/health') return jsonResponse({'candidates': []});
        asked = r.url;
        return health(true);
      }), '✓ 已連線 · qwen3-vl');
      expect(asked.toString(), 'http://127.0.0.1:8765/health');
    });

    testWidgets('測試連線: wrong key / not running', (tester) async {
      await check(tester, MockClient((r) async => health(false)),
          '✕ 服務正常，但 API Key 不正確');
    });

    testWidgets('測試連線: 401 shows the key error without the settings hint',
        (tester) async {
      // 卡 #389／#375：401 的說明句帶「（設定 → 照片辨識連線）」，結果列不顯示它。
      await check(tester, MockClient((r) async => jsonResponse({}, 401)),
          '✕ API Key 不正確');
      expect(find.textContaining('（設定 → 照片辨識連線）'), findsNothing);
    });

    testWidgets('測試連線: service not running', (tester) async {
      await check(
        tester,
        MockClient(
            (r) async => throw http.ClientException('Connection refused')),
        '✕ 連不到 AI 辨識服務（http://127.0.0.1:8765/tag），請確認服務已啟動',
      );
    });

    testWidgets('level by hand; a dial habit suggests a new default level',
        (tester) async {
      final app = await pumpApp(tester,
          initialTab: AppTab.settings, size: const Size(402, 1600));
      expect(find.text('目前程度 入門（A1）'), findsOneWidget);
      await tester.tap(find.widgetWithText(ChoiceChip, '基礎（A2）'));
      await tester.pump();
      expect(app.repository.profile.cefr, 'A2');
      expect(app.repository.profile.source, 'user');

      // Five photos left with the dial turned up (a changed offset counts).
      for (final o in [1, 2, 1, 2, 1]) {
        app.repository
            .savePhotoWords('photo-kitchen', const [], difficultyOffset: o);
      }
      await tester.pump();
      expect(find.textContaining('要把預設程度改成 B1 嗎？'), findsOneWidget);
      await tester.tap(find.text('好'));
      await tester.pump();
      expect(app.repository.profile.cefr, 'B1');
    });

    testWidgets('unpublished learning languages stay disabled; native UI languages are available',
        (tester) async {
      final app = await pumpApp(tester,
          initialTab: AppTab.settings, size: const Size(402, 1600));
      // Unpublished learning languages are left out, with one note instead
      // of disabled chips.
      expect(find.widgetWithText(ChoiceChip, '法文（Français） · 即將推出'),
          findsNothing);
      expect(find.text('更多學習語言即將推出'), findsOneWidget);
      final frenchNative = tester.widget<ChoiceChip>(
          find.widgetWithText(ChoiceChip, '法文（Français）'));
      expect(frenchNative.onSelected, isNotNull);
      expect(app.settings.learningLanguage, 'en');
      expect(app.settings.nativeLanguage, 'zh-TW');
      // Store build without a server: no address / key fields (問題回報 #265).
      expect(app.settings.showsTaggingServer, isFalse);
      expect(find.text('照片辨識連線'), findsNothing);
      expect(find.text('照片辨識'), findsOneWidget);
    });

    testWidgets('a restored retention outside the slider is clamped (card #228)',
        (tester) async {
      final settings = AppSettings.inMemory()..desiredRetention = 0.97;
      expect(settings.desiredRetention, AppSettings.maxRetention);
      settings.desiredRetention = 0.7;
      expect(settings.desiredRetention, AppSettings.minRetention);
      await pumpApp(tester,
          initialTab: AppTab.settings,
          settings: settings,
          size: const Size(402, 1600));
      await tester.scrollUntilVisible(find.text('進階設定'), 300);
      await tester.tap(find.text('進階設定'));
      await tester.pumpAndSettle();
      expect(find.byType(Slider), findsNWidgets(3)); // + 每日上限 x2 (#398)
      expect(tester.takeException(), isNull);
    });

    testWidgets('dictionary connection card shows only on failure (問題回報 #306)',
        (tester) async {
      final sync = DictionarySync.instance;
      final (savedStatus, savedError) = (sync.status, sync.hasError);
      addTearDown(() => sync
        ..status = savedStatus
        ..hasError = savedError);
      sync
        ..status = '已連接詞庫 · 每 30 秒自動更新'
        ..hasError = false;
      await pumpApp(tester,
          initialTab: AppTab.settings, size: const Size(402, 1600));
      await tester.scrollUntilVisible(
          find.text('字卡和複習紀錄保存在此裝置。'), 300,
          scrollable: find.byType(Scrollable).first);
      expect(find.text('詞庫連線'), findsNothing);
      expect(find.textContaining('每 30 秒'), findsNothing);
      expect(find.textContaining('上次確認'), findsNothing);
      expect(find.textContaining('你的資料庫'), findsNothing);

      sync
        ..status = '暫時無法連線 · 使用已儲存的詞庫，稍後自動重試'
        ..hasError = true;
      await pumpApp(tester,
          initialTab: AppTab.settings, size: const Size(402, 1600));
      expect(find.text('詞庫連線'), findsOneWidget);
      expect(find.text(sync.status), findsOneWidget);
      expect(find.text('重新連線'), findsOneWidget);
    });
  });

  group('首次設定', () {
    testWidgets('languages → background → quick check → level', (tester) async {
      tester.view.physicalSize = const Size(402, 1200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      OnboardingResult? result;
      await tester.pumpWidget(MaterialApp(
        theme: MobileTheme.light(),
        home:
            OnboardingScreen(lexicon: testLexicon(), onDone: (r) => result = r),
      ));
      expect(find.text('歡迎使用拍照學單字'), findsOneWidget);
      await tester.tap(find.text('下一步'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('已學一段時間'));
      await tester.pump();
      await tester.tap(find.text('想測看看？試試單字程度（可略過）'));
      await tester.pumpAndSettle();
      for (final words in [
        ['apple', 'book', 'water'],
        ['kitchen', 'travel', 'weather']
      ]) {
        for (final w in words) {
          await tester.tap(find.text(w));
          await tester.pump();
        }
        await tester.tap(find.text('繼續'));
        await tester.pumpAndSettle();
      }
      await tester.tap(find.text('先到這裡，開始學習'));
      expect(result!.learningLanguage, 'en');
      expect(result!.nativeLanguage, 'zh-TW');
      expect((result!.level, result!.source), ('A2', 'check'));
      expect(
          levelFromCheck({
            'A1': [true, true, false],
            'A2': [false, false, true]
          }),
          'A1');
    });

    testWidgets('the quick check reaches C2 for a learner who knows every word',
        (tester) async {
      tester.view.physicalSize = const Size(402, 1200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      OnboardingResult? result;
      await tester.pumpWidget(MaterialApp(
        theme: MobileTheme.light(),
        home:
            OnboardingScreen(lexicon: testLexicon(), onDone: (r) => result = r),
      ));
      await tester.tap(find.text('下一步'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('熟練'));
      await tester.pump();
      await tester.tap(find.text('想測看看？試試單字程度（可略過）'));
      await tester.pumpAndSettle();
      var screens = 0;
      while (result == null && screens < 10) {
        final chips = find.byWidgetPredicate(
            (w) => w is Text && RegExp(r'^[a-z]+$').hasMatch(w.data ?? ''));
        for (final e in chips.evaluate().toList()) {
          await tester.tap(find.text((e.widget as Text).data!).first);
          await tester.pump();
        }
        await tester.tap(find.text('繼續'));
        await tester.pumpAndSettle();
        screens++;
      }
      expect(screens, 6, reason: '18 words, A1 to C2');
      expect((result!.level, result!.source), ('C2', 'check'));
    });

    testWidgets('skipping the check uses the self-assessment', (tester) async {
      tester.view.physicalSize = const Size(402, 1200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      OnboardingResult? result;
      await tester.pumpWidget(MaterialApp(
        home:
            OnboardingScreen(lexicon: testLexicon(), onDone: (r) => result = r),
      ));
      expect(find.text('法文（Français） · 即將推出'), findsWidgets);
      await tester.tap(find.text('下一步'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('會基礎單字'));
      await tester.pump();
      await tester.tap(find.text('開始使用'));
      expect((result!.learningLanguage, result!.level, result!.source),
          ('en', 'A2', 'self'));
    });
  });

  test('jsonResponse helper round-trips Chinese', () {
    expect(jsonDecode(utf8.decode(jsonResponse({'a': '中'}).bodyBytes)),
        {'a': '中'});
  });
}
