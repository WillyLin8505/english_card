// 問題回報 #616 (owner, 2026-10-23): long-press anywhere on a photo → that
// part of the picture goes to the AI → pick the word → it is pinned there.
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/spot_crop.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

import 'helpers.dart';

void main() {
  group('cropRegion', () {
    test('a square around the spot, moved inside the picture', () {
      const pic = Size2(1000, 800);
      expect(cropRegion(pic, const LabelPoint(0.5, 0.5), 200),
          const ui.Rect.fromLTWH(400, 300, 200, 200));
      // Near a corner the square slides in rather than leaving the picture.
      expect(cropRegion(pic, const LabelPoint(0.02, 0.98), 200),
          const ui.Rect.fromLTWH(0, 600, 200, 200));
      // Never larger than the picture.
      expect(cropRegion(pic, const LabelPoint(0.5, 0.5), 5000).width, 800);
    });
  });

  testWidgets('long-press asks the AI about that spot and pins the pick there',
      (tester) async {
    final settings = AppSettings.inMemory(
        taggingUrl: 'http://predator:8765/tag', apiKey: 'k');
    final sent = <http.BaseRequest>[];
    final app = await pumpApp(
      tester,
      initialTab: AppTab.album,
      settings: settings,
      size: const Size(402, 1400),
      createTagger: (uri, key) => TaggingService(
        endpoint: uri,
        apiKey: key,
        client: MockClient((request) async {
          sent.add(request);
          return jsonResponse({
            'candidates': [
              {
                'word': 'teapot',
                'pos': 'noun',
                'meaning': '茶壺',
                'cefr': 'B1',
                'point': [0.5, 0.5],
                'visualConfidence': 0.9
              },
            ],
          });
        }),
      ),
    );
    app.navigator.openPhoto('photo-breakfast');
    await tester.pumpAndSettle();

    final photo = find.byType(PinnedPhoto).first;
    final rect = tester.getRect(photo);
    // A spot away from the existing labels.
    final at = rect.topLeft + Offset(rect.width * 0.12, rect.height * 0.9);
    await tester.longPressAt(at);
    await tester.pump();
    expect(find.byKey(const ValueKey('spot-scanning')), findsOneWidget);
    // Decoding and cropping the photo runs outside the fake clock.
    for (var i = 0; i < 20 && find.text('AI 在這裡看到').evaluate().isEmpty; i++) {
      await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 100)));
      await tester.pump();
    }
    expect(find.text('AI 在這裡看到'), findsOneWidget);
    expect(sent, hasLength(1), reason: 'one request for the cut-out spot');
    expect(find.byKey(const ValueKey('spot-scanning')), findsNothing);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('spot-teapot')));
    await tester.pumpAndSettle();
    final pins = tester.widget<PinnedPhoto>(photo).pins;
    final teapot = pins.where((p) => p.id == 'teapot').single;
    expect(teapot.anchor.x, closeTo(0.12, 0.05));
    expect(teapot.anchor.y, closeTo(0.9, 0.05));
  });

  testWidgets('without a recognizer it says where to set one up',
      (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.album,
        settings: AppSettings.inMemory(),
        size: const Size(402, 1400));
    app.navigator.openPhoto('photo-breakfast');
    await tester.pumpAndSettle();
    final rect = tester.getRect(find.byType(PinnedPhoto).first);
    await tester.longPressAt(rect.center);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.textContaining('照片辨識連線'), findsOneWidget);
    // Let the toast time out.
    await tester.pump(const Duration(seconds: 5));
  });
}
