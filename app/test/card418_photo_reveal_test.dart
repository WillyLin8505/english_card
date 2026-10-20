import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';
import 'package:photo_english_app/widgets/mobile/dialogs.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

// 問題回報 #409: no name / 找什麼 questions, and labels pop in one by one.
final _now = DateTime(2026, 10, 20, 9);

Photo _photo() => Photo(
      id: 'p',
      title: 'p',
      takenAt: _now,
      placeholderColors: const [0xFF000000, 0xFF333333],
      createdAt: _now,
    );

// Reading order is top to bottom: Cup (0.2), Plate (0.5), Spoon (0.8).
const _cup =
    PinData(id: 'cup', anchor: LabelPoint(0.5, 0.2), word: 'Cup', zh: '杯子');
const _plate =
    PinData(id: 'plate', anchor: LabelPoint(0.5, 0.5), word: 'Plate', zh: '盤子');
const _spoon =
    PinData(id: 'spoon', anchor: LabelPoint(0.5, 0.8), word: 'Spoon', zh: '湯匙');

Widget _host(List<PinData> pins) => MaterialApp(
      theme: MobileTheme.light(),
      home: Center(
        child: SizedBox(
          width: 300,
          height: 200,
          child: PinnedPhoto(photo: _photo(), pins: pins, revealNew: true),
        ),
      ),
    );

void main() {
  testWidgets('the photo dialog asks for an album only, not name or 找什麼',
      (tester) async {
    final repository = WordDatabaseRepository();
    SavePhotoChoice? result;
    await tester.pumpWidget(MaterialApp(
      home: Builder(builder: (context) {
        return FilledButton(
          onPressed: () async {
            result = await showSaveToAlbumDialog(
              context,
              repository: repository,
              defaultTitle: '10/20 09:00',
            );
          },
          child: const Text('開啟'),
        );
      }),
    ));

    await tester.tap(find.text('開啟'));
    await tester.pumpAndSettle();
    expect(find.text('照片名稱'), findsNothing);
    expect(find.text('要找什麼'), findsNothing);
    expect(find.text('找物品'), findsNothing);
    expect(find.text('找文字'), findsNothing);

    await tester.tap(find.text('＋ 新相片冊'));
    await tester.pump();
    await tester.enterText(find.byType(TextField), '旅行');
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, '儲存'));
    await tester.pumpAndSettle();

    expect(result?.title, '10/20 09:00');
    expect(result?.scanMode, PhotoScanMode.both);
    expect(result?.albumId, isNotNull);
  });

  testWidgets('labels already there show at once, with no chip',
      (tester) async {
    await tester.pumpWidget(_host([_cup, _plate]));
    expect(find.text('Cup'), findsOneWidget);
    expect(find.text('Plate'), findsOneWidget);
    expect(find.textContaining('找到'), findsNothing);
  });

  testWidgets('new labels pop in one by one, top to bottom, 200 ms apart',
      (tester) async {
    await tester.pumpWidget(_host([]));
    // Given the list in the wrong order: reading order decides the pop.
    await tester.pumpWidget(_host([_spoon, _cup, _plate]));
    expect(find.text('Cup'), findsNothing);
    expect(find.text('Plate'), findsNothing);
    expect(find.text('跳過動畫'), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text('Cup'), findsOneWidget);
    expect(find.text('Plate'), findsNothing);

    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text('Plate'), findsOneWidget);
    expect(find.text('Spoon'), findsNothing);

    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text('Spoon'), findsOneWidget);
    // Done: the chip now says how many words were found.
    expect(find.text('跳過動畫'), findsNothing);
    expect(find.text('找到 3 個字'), findsOneWidget);

    // …and goes away after a while.
    await tester.pump(const Duration(seconds: 3));
    expect(find.textContaining('找到'), findsNothing);
    expect(find.text('Cup'), findsOneWidget);
  });

  testWidgets('跳過動畫 shows every label at once', (tester) async {
    await tester.pumpWidget(_host([]));
    await tester.pumpWidget(_host([_cup, _plate, _spoon]));
    expect(find.text('Cup'), findsNothing);

    await tester.tap(find.text('跳過動畫'));
    await tester.pump();
    expect(find.text('Cup'), findsOneWidget);
    expect(find.text('Plate'), findsOneWidget);
    expect(find.text('Spoon'), findsOneWidget);
    expect(find.text('找到 3 個字'), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('Spoon'), findsOneWidget);
  });
}
