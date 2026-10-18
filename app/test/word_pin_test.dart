import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

/// A photo label shows its word and meaning in full (owner 2026-10-14:
/// 標籤的單字跟說明展開): one line when it fits, else the word above its
/// meaning, wrapped inside the photo's width (問題回報 #61) — never cut
/// short with ….
void main() {
  Future<void> pump(WidgetTester tester, Widget pin) =>
      tester.pumpWidget(MaterialApp(
          home:
              Scaffold(body: Align(alignment: Alignment.topLeft, child: pin))));

  testWidgets('a long label wraps in full inside the photo', (tester) async {
    const word = 'semantic interpretations', zh = '語義上的詮釋與說明';
    await pump(tester, const WordPin(word: word, zh: zh, maxWidth: 160));
    expect(tester.takeException(), isNull, reason: 'no RenderFlex overflow');
    final size = tester.getSize(find.byType(WordPin));
    expect(size.width, lessThanOrEqualTo(160));
    for (final text in [word, zh]) {
      final t = tester.widget<Text>(find.text(text));
      expect(t.overflow, isNot(TextOverflow.ellipsis));
      expect(t.maxLines, isNull);
    }
    // The word sits above its meaning, and the layout reserved that height.
    expect(tester.getTopLeft(find.text(zh)).dy,
        greaterThan(tester.getTopLeft(find.text(word)).dy));
    final measured = WordPin.badgeSize(word, zh, false, TextScaler.noScaling,
        maxWidth: 160,
        base: DefaultTextStyle.of(tester.element(find.byType(WordPin))).style);
    expect(measured.width, lessThanOrEqualTo(160));
    expect(size.height, closeTo(measured.height, 1));
  });

  testWidgets('a label laid out at its own width keeps every word whole',
      (tester) async {
    // The album's thumbnails: the layout gives each badge its measured width.
    await pump(tester, const SizedBox());
    final base =
        DefaultTextStyle.of(tester.element(find.byType(SizedBox))).style;
    for (final (word, zh) in [
      ('green', '呈綠色'),
      ('calendar', '日曆'),
      ('ink', '墨水')
    ]) {
      final width = WordPin.badgeSize(word, zh, false, TextScaler.noScaling,
              maxWidth: 160, base: base)
          .width;
      await pump(tester, WordPin(word: word, zh: zh, maxWidth: width));
      expect(tester.takeException(), isNull);
      expect(tester.getTopLeft(find.text(zh)).dy,
          closeTo(tester.getTopLeft(find.text(word)).dy, 3),
          reason: '$word $zh on one line');
      final line = tester.getSize(find.text(word)).height;
      final single = tester.getSize(find.text(zh)).height;
      expect(line, lessThanOrEqualTo(single + 4), reason: '$word not split');
    }
  });

  testWidgets('a short label stays on one line', (tester) async {
    await pump(tester, const WordPin(word: 'mug', zh: '馬克杯', maxWidth: 160));
    expect(tester.getTopLeft(find.text('馬克杯')).dy,
        closeTo(tester.getTopLeft(find.text('mug')).dy, 3));
  });
}
