// 卡 #1417: a label dragged past the photo edge keeps following the finger
// and is collected when let go over the tray; inside the photo it just moves.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';
import 'helpers.dart';

void main() {
  Future<(List<Offset?>, List<LabelPoint>, List<Offset>)> run(
      WidgetTester t, Offset by) async {
    final over = <Offset?>[], moved = <LabelPoint>[], dropped = <Offset>[];
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
            onPinMoved: (p, to) => moved.add(to),
            onPinDragAt: over.add,
            onPinDropped: (p, g) {
              dropped.add(g);
              return g.dy > 330;
            },
          ),
        ),
      ),
    ));
    await t.pumpAndSettle();
    await t.drag(find.byType(WordPin), by);
    await t.pumpAndSettle();
    return (over, moved, dropped);
  }

  testWidgets('dragged below the photo: reported, dropped, not moved',
      (t) async {
    final (over, moved, dropped) = await run(t, const Offset(0, 250));
    expect(over.whereType<Offset>().any((o) => o.dy > 300), isTrue);
    expect(over.last, isNull);
    expect(dropped.single.dy, greaterThan(330));
    expect(moved, isEmpty);
  });

  testWidgets('dragged inside the photo: moved', (t) async {
    final (_, moved, _) = await run(t, const Offset(30, 20));
    expect(moved, hasLength(1));
  });
}
