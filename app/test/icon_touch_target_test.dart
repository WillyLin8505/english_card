import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';
import 'helpers.dart';

void main() {
  testWidgets('photo row actions have separate 48px edge targets',
      (tester) async {
    final app = await pumpApp(tester, size: const Size(360, 740));
    app.navigator.openPhoto('photo-breakfast');
    await tester.pumpAndSettle();
    final row = find.byKey(const ValueKey('word:apple'));
    await tester.ensureVisible(row);
    await tester.pumpAndSettle();
    final star = find.descendant(
      of: row,
      matching: find.bySemanticsLabel('鎖定（調整難度時保留）'),
    );
    final audio = find.descendant(
      of: row,
      matching: find.bySemanticsLabel('播放發音'),
    );
    final starRect = tester.getRect(star);
    final audioRect = tester.getRect(audio);
    for (final rect in [starRect, audioRect]) {
      expect(rect.width, greaterThanOrEqualTo(48));
      expect(rect.height, greaterThanOrEqualTo(48));
    }
    expect(starRect.overlaps(audioRect), isFalse);
    await tester.tapAt(starRect.bottomRight - const Offset(1, 1));
    await tester.pump();
    expect(find.descendant(of: row, matching: find.bySemanticsLabel('取消鎖定')),
        findsOneWidget);
    expect(find.text('單字詳情'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  for (final width in [320.0, 402.0]) {
    testWidgets('navigation targets remain tappable at their edges on $width',
        (tester) async {
      await tester.binding.setSurfaceSize(Size(width, 700));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      var back = 0;
      var action = 0;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: MNavBar(
            title: 'A long navigation title',
            leading: NavIconButton(
              label: 'Back',
              icon: const Icon(Icons.arrow_back, size: 16),
              onTap: () => back++,
            ),
            trailing: NavIconButton(
              label: 'Action',
              icon: const Icon(Icons.edit, size: 10),
              onTap: () => action++,
            ),
          ),
        ),
      ));
      for (final label in ['Back', 'Action']) {
        final rect = tester.getRect(find.bySemanticsLabel(label));
        expect(rect.width, greaterThanOrEqualTo(48));
        expect(rect.height, greaterThanOrEqualTo(48));
        await tester.tapAt(rect.topLeft + const Offset(1, 1));
        await tester.tapAt(rect.bottomRight - const Offset(1, 1));
      }
      expect(back, 2);
      expect(action, 2);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('album close target fits the picker header and accepts edge taps',
      (tester) async {
    var taps = 0;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SizedBox(
          height: 72,
          child: AlbumTopBar(
            title: 'Photos',
            leading: RoundIconButton(
              label: 'Close',
              icon: const Icon(Icons.close, size: 16),
              onTap: () => taps++,
            ),
            trailing: const SizedBox(width: 48),
          ),
        ),
      ),
    ));
    final rect = tester.getRect(find.bySemanticsLabel('Close'));
    expect(rect.size, const Size(48, 48));
    await tester.tapAt(rect.topLeft + const Offset(1, 1));
    await tester.tapAt(rect.bottomRight - const Offset(1, 1));
    expect(taps, 2);
    expect(tester.takeException(), isNull);
  });
}
