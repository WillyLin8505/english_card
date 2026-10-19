// 問題回報 #317: the review card in three new 卡片樣式 (A 簡潔留白,
// B 圖片沉浸, C 活潑遊戲) besides the current one. One set of card widgets
// reads the style's tokens; every style must render the front and the
// whole back at iPhone width without overflow.
//
// Screenshots for the owner (docs/card_styles/):
//   CARD_STYLE_CAPTURE=1 flutter test test/card_style_test.dart
import 'dart:io';
import 'dart:math';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/theme/card_style.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';

import 'helpers.dart';

/// iPhone 15 / 16 in points.
const iphone = Size(393, 852);

void loadPack() => LexiconPack.instance.loadJson({
      'schema_version': 3,
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'breakfast',
          'normalized': 'breakfast',
          'pos': 'noun',
          'cefr': 'A1',
          'pronunciations': [
            {'kind': 'ipa', 'value': '/ˈbrek.fəst/'}
          ],
          'status': 'full',
          'senses': [
            {'id': 11, 'native': '早餐', 'definition': 'the first meal of the day'}
          ],
          'forms': [
            {'field': 'form', 'form': 'breakfasts', 'normalized': 'breakfasts', 'label': 'plural'},
            {'field': 'form', 'form': 'breakfasted', 'normalized': 'breakfasted', 'label': 'past'},
          ],
          'morphemes': [
            {'part': 'break', 'kind': 'root', 'free': true, 'native': '打破'},
            {'part': 'fast', 'kind': 'root', 'free': true, 'native': '禁食', 'native_ai': true},
          ],
          'relations': [
            {'relation': 'synonyms', 'word': 'morning meal', 'native': '早飯', 'cefr': 'A2'},
            {'relation': 'related', 'word': 'lunch', 'native': '午餐', 'cefr': 'A1'},
            {'relation': 'related', 'word': 'brunch', 'native': '早午餐', 'cefr': 'B1'},
            {'relation': 'related', 'word': 'cereal', 'native': '穀片', 'cefr': 'A2'},
            {'relation': 'near_homophones', 'word': 'breakfront', 'native': '中凸式櫥櫃'},
            {'relation': 'similar_spelling', 'word': 'breakdown', 'native': '故障'},
          ],
        },
      ],
    });

Photo _photo() => Photo(
    id: 'p-breakfast',
    title: '早餐',
    takenAt: testNow,
    createdAt: testNow,
    assetPath: 'assets/sample/photo_breakfast.jpg',
    width: 1200,
    height: 900);

WordDatabaseRepository makeRepo() {
  final base = WordDatabaseRepository(clock: () => testNow);
  final word = base.addWord(word: 'breakfast', pos: 'noun', meaning: '早餐');
  base.linkLexicon(LexiconPack.instance);
  final entry = base.entry(word.id)!.copyWith(
    definition: () => 'the first meal of the day',
    examples: const [
      WordExample(
          text: 'We had breakfast by the window.', translation: '我們在窗邊吃早餐。'),
      WordExample(
          text: 'Breakfast is ready at seven.', translation: '早餐七點準備好。'),
    ],
  );
  return WordDatabaseRepository(
      clock: () => testNow,
      entries: [entry, ...base.entries.where((e) => e.id != entry.id)],
      cards: base.eligibleCards(),
      photos: [_photo()],
      occurrences: [
        PhotoOccurrence(
            id: 'occ',
            photoId: 'p-breakfast',
            wordEntryId: word.id,
            anchor: const LabelPoint(0.5, 0.55))
      ]);
}

/// The review screen as the learner sees it: nav bar with 回報 / 刪除
/// (#316), then the card view in [style].
Future<FlashcardSession> pumpReview(WidgetTester tester, CardStyle style,
    {Size size = iphone}) async {
  final repo = makeRepo();
  final session = FlashcardSession(repo, random: Random(1), continuous: true);
  addTearDown(session.dispose);
  final look = CardLook.forStyle(style);
  await pumpApp(tester,
      repository: repo,
      size: size,
      settings: AppSettings.inMemory(cardStyle: style),
      home: Scaffold(
        backgroundColor: look.canvas,
        body: SafeArea(
          bottom: false,
          child: Column(children: [
            MNavBar(
              title: '複習',
              sideWidth: 104,
              leading: BackNavButton(onTap: () {}),
              trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                NavIconButton(
                    label: '回報此卡片',
                    icon: const Icon(Icons.flag_outlined,
                        size: 20, color: MColors.label),
                    onTap: () {}),
                const SizedBox(width: 8),
                NavIconButton(
                    label: '刪除此卡片',
                    background: MColors.againBg,
                    icon: const Icon(Icons.close,
                        size: 20, color: MColors.againFg),
                    onTap: () {}),
              ]),
            ),
            Expanded(
                child: CardLookScope(
                    look: look,
                    child: ListenableBuilder(
                        listenable: session,
                        builder: (_, __) =>
                            FlashcardCardView(session: session)))),
          ]),
        ),
      ));
  await tester.pump();
  return session;
}

Future<void> showBack(WidgetTester tester, FlashcardSession s) async {
  if (!s.canAnswer) s.reportPhotoState(s.photoAttempt, true);
  s.showAnswer();
  await tester.pumpAndSettle();
}

void main() {
  setUp(loadPack);
  tearDown(() => LexiconPack.instance.clear());

  for (final style in CardStyle.values) {
    testWidgets('${style.name}: front and whole back fit an iPhone',
        (tester) async {
      final s = await pumpReview(tester, style);
      expect(tester.takeException(), isNull);
      expect(find.byType(FlashcardFront), findsOneWidget);
      // #253: the photo front still marks the word's spot.
      if (s.exercise?.type == ReviewExerciseType.photoRecall) {
        expect(find.byKey(const ValueKey('target-ring')), findsOneWidget);
      }
      // #316: the report button keeps its place top right.
      expect(find.bySemanticsLabel('回報此卡片'), findsOneWidget);

      await showBack(tester, s);
      expect(find.byType(FlashcardBack), findsOneWidget);
      // #251's items are all still there.
      for (final text in ['中文意思', '例句與翻譯', '詞形變化', '同義詞', '相關詞',
        '容易混淆的字', '構詞拆解']) {
        expect(find.text(text), findsOneWidget, reason: '$style $text');
      }
      expect(find.byTooltip('播放英式發音'), findsOneWidget);
      expect(find.byTooltip('播放美式發音'), findsOneWidget);
      expect(find.textContaining('breakfasts'), findsOneWidget);
      expect(find.byKey(const ValueKey('back-anchor-dot')), findsOneWidget);
      // Scroll the back to its end: nothing overflows on the way.
      final scroll = find.byType(Scrollable).first;
      for (var i = 0; i < 6; i++) {
        await tester.drag(scroll, const Offset(0, -500));
        await tester.pumpAndSettle();
      }
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('classic keeps the old look: no card frame, word as a title',
      (tester) async {
    final s = await pumpReview(tester, CardStyle.classic);
    expect(find.byKey(const ValueKey('card-frame')), findsNothing);
    await showBack(tester, s);
    expect(find.byKey(const ValueKey('hero-word')), findsNothing);
    final word = tester.widget<Text>(find.text('Breakfast').first);
    expect(word.style?.fontSize, 32);
  });

  testWidgets('A and C draw the card; B writes the word on the photo',
      (tester) async {
    for (final style in [CardStyle.minimal, CardStyle.playful]) {
      await pumpReview(tester, style);
      expect(find.byKey(const ValueKey('card-frame')), findsOneWidget,
          reason: style.name);
    }
    final s = await pumpReview(tester, CardStyle.immersive);
    await showBack(tester, s);
    expect(find.byKey(const ValueKey('hero-word')), findsOneWidget);
    // The word is written once — on the photo, not again below it.
    expect(find.text('Breakfast'), findsOneWidget);
  });

  testWidgets('new styles give word chips a 44 pt touch target',
      (tester) async {
    for (final style in [
      CardStyle.minimal,
      CardStyle.immersive,
      CardStyle.playful
    ]) {
      final s = await pumpReview(tester, style, size: const Size(393, 3000));
      await showBack(tester, s);
      final chip = find
          .ancestor(of: find.textContaining('lunch'), matching: find.byType(Container))
          .first;
      expect(tester.getSize(chip).height, greaterThanOrEqualTo(44),
          reason: style.name);
    }
  });

  testWidgets('設定 → 卡片樣式 switches the style',
      (tester) async {
    final app = await pumpApp(tester, initialTab: AppTab.settings);
    expect(app.settings.cardStyle, CardStyle.classic);
    final chip = find.text('C 活潑遊戲');
    await tester.scrollUntilVisible(chip, 300,
        scrollable: find
            .descendant(
                of: find.byType(ListView), matching: find.byType(Scrollable))
            .first);
    await tester.ensureVisible(chip);
    await tester.pumpAndSettle();
    await tester.tap(chip);
    await tester.pump();
    expect(app.settings.cardStyle, CardStyle.playful);
  });

  test('卡片樣式 is stored by name; unknown names fall back to classic', () {
    expect(CardStyle.parse('immersive'), CardStyle.immersive);
    expect(CardStyle.parse(null), CardStyle.classic);
    expect(CardStyle.parse('nonsense'), CardStyle.classic);
  });

  testWidgets('screenshots for the owner (docs/card_styles/)', (tester) async {
    await tester.runAsync(() async {
      // Latin and IPA from Segoe UI, Chinese from 微軟正黑體 (the app's
      // Manrope / Noto Sans TC are not bundled for tests).
      ByteData font(String name) => ByteData.sublistView(
          File('C:/Windows/Fonts/$name').readAsBytesSync());
      for (final family in ['Manrope', 'Inter', 'Roboto']) {
        await (FontLoader(family)..addFont(Future.value(font('segoeui.ttf'))))
            .load();
      }
      for (final family in ['Ahem', 'Noto Sans TC']) {
        await (FontLoader(family)..addFont(Future.value(font('msjh.ttc'))))
            .load();
      }
      final icons = await rootBundle.load('fonts/MaterialIcons-Regular.otf');
      await (FontLoader('MaterialIcons')..addFont(Future.value(icons))).load();
    });
    final out = Directory('../docs/card_styles')..createSync(recursive: true);
    Future<void> shot(String name) async {
      await tester.runAsync(() async {
        for (final e in find.byType(Image).evaluate()) {
          await precacheImage((e.widget as Image).image, e);
        }
      });
      await tester.pumpAndSettle();
      await tester.runAsync(() async {
        final boundary = tester.renderObject<RenderRepaintBoundary>(
            find.byType(RepaintBoundary).first);
        final image = await boundary.toImage(pixelRatio: 2);
        final png = await image.toByteData(format: ui.ImageByteFormat.png);
        File('${out.path}/$name.png')
            .writeAsBytesSync(png!.buffer.asUint8List());
        image.dispose();
      });
    }

    for (final style in CardStyle.values) {
      final s = await pumpReview(tester, style);
      await shot('${style.name}_front');
      await showBack(tester, s);
      await shot('${style.name}_back');
      // The whole back in one tall picture.
      final t = await pumpReview(tester, style, size: const Size(393, 2000));
      await showBack(tester, t);
      await shot('${style.name}_back_full');
    }
  }, skip: Platform.environment['CARD_STYLE_CAPTURE'] != '1');
}
