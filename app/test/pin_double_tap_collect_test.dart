// Owner 11/25: 「點兩下是收藏單字 不是開啟單字詳情」 — on the photo, one tap
// on a label opens 單字詳情, a double tap collects the word instead.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';
import 'helpers.dart';

void main() {
  testWidgets('double tap on a label collects, single tap opens', (t) async {
    final taps = <String>[], doubles = <String>[];
    final photo = Photo(
        id: 'p',
        title: '',
        takenAt: testNow,
        createdAt: testNow,
        networkUrl: 'http://127.0.0.1:1/x.jpg',
        width: 800,
        height: 600);
    await t.pumpWidget(MaterialApp(
      theme: MobileTheme.light(),
      home: Align(
        alignment: Alignment.topLeft,
        child: SizedBox(
          width: 400,
          height: 300,
          child: PinnedPhoto(
            photo: photo,
            pins: const [
              PinData(
                  id: 'keyboard',
                  anchor: LabelPoint(0.5, 0.5),
                  word: 'keyboard',
                  zh: '鍵盤'),
            ],
            onPinTap: (p) => taps.add(p.id),
            onPinDoubleTap: (p) => doubles.add(p.id),
          ),
        ),
      ),
    ));
    await t.pumpAndSettle();
    final pin = find.byType(WordPin);
    await t.tap(pin);
    await t.pump(const Duration(milliseconds: 50));
    await t.tap(pin);
    await t.pumpAndSettle();
    expect(doubles, ['keyboard']);
    expect(taps, isEmpty);

    await t.tap(pin);
    await t.pumpAndSettle(const Duration(milliseconds: 400));
    expect(taps, ['keyboard']);
    expect(doubles, ['keyboard']);
  });
}
