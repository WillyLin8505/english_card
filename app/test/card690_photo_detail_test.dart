// 問題回報 #690、#707、#709（owner, 2026-10-24，照片詳情）:
// - #690 一次長按多個地方辨識標籤：每個點都轉圈、排隊一個一個送，結果依序讓人選。
// - #707 標籤選項列拿掉「難一點」「簡單一點」。
// - #709 點一下照片收起所有標籤，再點一下展開；放位置模式優先。

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

import 'helpers.dart';

Map<String, Object> _candidate(String word, String meaning) => {
      'word': word,
      'pos': 'noun',
      'meaning': meaning,
      'cefr': 'B1',
      'point': [0.5, 0.5],
      'visualConfidence': 0.9,
    };

void main() {
  testWidgets('#690 several long-presses queue up and are answered in turn',
      (tester) async {
    final settings = AppSettings.inMemory(
        taggingUrl: 'http://predator:8765/tag', apiKey: 'k');
    var inFlight = 0;
    var most = 0;
    var sent = 0;
    final replies = [
      _candidate('teapot', '茶壺'),
      _candidate('napkin', '餐巾'),
    ];
    final app = await pumpApp(
      tester,
      initialTab: AppTab.album,
      settings: settings,
      size: const Size(402, 1400),
      createTagger: (uri, key) => TaggingService(
        endpoint: uri,
        apiKey: key,
        client: MockClient((http.Request request) async {
          inFlight++;
          most = inFlight > most ? inFlight : most;
          await Future<void>.delayed(const Duration(milliseconds: 50));
          inFlight--;
          return jsonResponse({
            'candidates': [replies[sent++ % replies.length]],
          });
        }),
      ),
    );
    app.navigator.openPhoto('photo-breakfast');
    await tester.pumpAndSettle();

    final photo = find.byType(PinnedPhoto).first;
    final rect = tester.getRect(photo);
    final first = rect.topLeft + Offset(rect.width * 0.12, rect.height * 0.9);
    final second = rect.topLeft + Offset(rect.width * 0.85, rect.height * 0.9);
    await tester.longPressAt(first);
    await tester.longPressAt(second);
    await tester.pump();
    // Both spots show a ring at once.
    expect(find.byKey(const ValueKey('spot-scanning')), findsOneWidget);
    expect(find.byKey(const ValueKey('spot-scanning-1')), findsOneWidget);

    Future<void> waitFor(Finder f) async {
      for (var i = 0; i < 30 && f.evaluate().isEmpty; i++) {
        await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 100)));
        await tester.pump(const Duration(milliseconds: 100));
      }
    }

    // The first spot's choices open first.
    await waitFor(find.byKey(const ValueKey('spot-teapot')));
    expect(find.byKey(const ValueKey('spot-teapot')), findsOneWidget);
    // The sheet slides up; the second spot waits behind it.
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('略過，看下一個位置（還有 1 個）'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('spot-teapot')));
    // The second spot may still be turning: no pumpAndSettle.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    // Then the second spot's.
    await waitFor(find.byKey(const ValueKey('spot-napkin')));
    expect(find.byKey(const ValueKey('spot-napkin')), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.tap(find.byKey(const ValueKey('spot-napkin')));
    await tester.pumpAndSettle();

    expect(sent, 2);
    expect(most, 1, reason: 'the spots go to the server one at a time');
    final pins = tester.widget<PinnedPhoto>(photo).pins;
    final teapot = pins.singleWhere((p) => p.id == 'teapot');
    final napkin = pins.singleWhere((p) => p.id == 'napkin');
    expect(teapot.anchor.x, closeTo(0.12, 0.05));
    expect(napkin.anchor.x, closeTo(0.85, 0.05));
    expect(find.byKey(const ValueKey('spot-scanning')), findsNothing);
    expect(find.byKey(const ValueKey('spot-waiting-0')), findsNothing);
    await tester.pump(const Duration(seconds: 5));
  });

  testWidgets('#707 the label options have no 簡單一點／難一點', (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.album, size: const Size(402, 1400));
    app.navigator.openPhoto('photo-breakfast');
    await tester.pumpAndSettle();
    expect(find.text('多看動詞'), findsOneWidget);
    expect(find.text('多看形容詞'), findsOneWidget);
    expect(find.byKey(const ValueKey('rescan-tags')), findsOneWidget);
    expect(find.text('簡單一點'), findsNothing);
    expect(find.text('難一點'), findsNothing);
  });

  testWidgets('#709 a tap on the photo folds the labels away and back',
      (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.album, size: const Size(402, 1400));
    app.navigator.openPhoto('photo-breakfast');
    await tester.pumpAndSettle();

    final photo = find.byType(PinnedPhoto).first;
    double opacity() => tester
        .widget<AnimatedOpacity>(find.byKey(const ValueKey('pins-layer')))
        .opacity;
    expect(opacity(), 1);
    expect(tester.widget<PinnedPhoto>(photo).hidePins, isFalse);

    final rect = tester.getRect(photo);
    final empty = rect.topLeft + Offset(rect.width * 0.05, rect.height * 0.97);
    await tester.tapAt(empty);
    await tester.pumpAndSettle();
    expect(tester.widget<PinnedPhoto>(photo).hidePins, isTrue);
    expect(opacity(), 0);
    expect(find.byKey(const ValueKey('pins-hidden')), findsOneWidget);
    // Hidden labels can't be tapped by accident.
    expect(tester.widget<PinnedPhoto>(photo).pins, isNotEmpty);

    await tester.tapAt(empty);
    await tester.pumpAndSettle();
    expect(tester.widget<PinnedPhoto>(photo).hidePins, isFalse);
    expect(opacity(), 1);
    expect(find.byKey(const ValueKey('pins-hidden')), findsNothing);
  });

  testWidgets('#709 while a word waits for its spot, a tap places it',
      (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.album, size: const Size(402, 1400));
    app.navigator.openPhoto('photo-breakfast');
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(const ValueKey('add-word')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('add-word')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, 'teapot');
    await tester.tap(find.text('儲存'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('placing-bar')), findsOneWidget);

    final photo = find.byType(PinnedPhoto).first;
    final rect = tester.getRect(photo);
    await tester
        .tapAt(rect.topLeft + Offset(rect.width * 0.1, rect.height * 0.95));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('placing-bar')), findsNothing);
    expect(tester.widget<PinnedPhoto>(photo).hidePins, isFalse,
        reason: 'the tap placed the word instead of hiding the labels');
    expect(tester.widget<PinnedPhoto>(photo).pins.map((p) => p.id),
        contains('teapot'));
  });
}
