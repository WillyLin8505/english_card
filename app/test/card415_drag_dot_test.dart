import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

void main() {
  testWidgets('long-press then drag moves the dot and reports the drop',
      (tester) async {
    Offset? dropped;
    await tester.pumpWidget(MaterialApp(
      home: Center(
        child: SizedBox(
          width: 300,
          height: 200,
          child: Stack(children: [
            DraggableAnchorDot(
                at: const Offset(100, 100), onMoved: (to) => dropped = to),
          ]),
        ),
      ),
    ));
    final dot = find.byKey(const ValueKey('draggable-anchor-dot'));
    final g = await tester.startGesture(tester.getCenter(dot));
    await tester.pump(const Duration(milliseconds: 700));
    await g.moveBy(const Offset(40, -30));
    await tester.pump();
    await g.up();
    await tester.pump();
    expect(dropped, isNotNull);
    expect(dropped!.dx, closeTo(140, 1));
    expect(dropped!.dy, closeTo(70, 1));
  });

  testWidgets('a plain drag (no long press) does not move the dot',
      (tester) async {
    Offset? dropped;
    await tester.pumpWidget(MaterialApp(
      home: Stack(children: [
        DraggableAnchorDot(
            at: const Offset(100, 100), onMoved: (to) => dropped = to),
      ]),
    ));
    await tester.drag(
        find.byKey(const ValueKey('draggable-anchor-dot')), const Offset(40, 0));
    await tester.pump();
    expect(dropped, isNull);
  });
}
