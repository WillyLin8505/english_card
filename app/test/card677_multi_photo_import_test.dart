import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/screens/photo_picker_screen.dart';

import 'helpers.dart';

/// 問題回報 #677: 匯入照片要能一次選多張. The album is asked once, every
/// photo is added and waits in the tagging queue; cancelling adds nothing.
void main() {
  const files = [
    'assets/sample/recent_1.jpg',
    'assets/sample/recent_2.jpg',
    'assets/sample/recent_3.jpg',
  ];
  var pickerCalls = 0;

  Future<List<XFile>> fakeLibrary(int n) async {
    pickerCalls++;
    return [
      for (final f in files.take(n))
        XFile.fromData(File(f).readAsBytesSync(), name: f.split('/').last),
    ];
  }

  Future<TestApp> openPicker(WidgetTester tester, int n) async {
    final app = await pumpApp(tester);
    tester.state<NavigatorState>(find.byType(Navigator).first).push(
        MaterialPageRoute<void>(
            builder: (_) =>
                PhotoPickerScreen(pickLibrary: () => fakeLibrary(n))));
    await settle(tester);
    await tester.tap(find.text('從相簿選擇'));
    await settle(tester);
    return app;
  }

  /// Real async work (saving, decoding) with plain pumps: a spinner or a
  /// queue banner may keep animating, so pumpAndSettle can't be used.
  Future<void> waitFor(WidgetTester tester, bool Function() done) async {
    for (var i = 0; i < 400 && !done(); i++) {
      await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 20)));
      await tester.pump(const Duration(milliseconds: 50));
    }
    await tester.pump(const Duration(milliseconds: 500));
  }

  setUp(() => pickerCalls = 0);

  testWidgets('three photos: one album question, three added and queued',
      (tester) async {
    final app = await openPicker(tester, 3);
    expect(pickerCalls, 1);
    expect(find.text('已選 3 張'), findsOneWidget);
    final before = app.repository.allPhotos.length;
    final oldIds = {for (final p in app.repository.allPhotos) p.id};
    final pendingBefore = app.queue.pending;

    await tester.tap(find.text('加入 3 張'));
    await tester.pumpAndSettle();
    expect(find.text('存到相片冊（3 張）'), findsOneWidget);
    await tester.tap(find.text('儲存'));
    await waitFor(
        tester,
        () =>
            app.repository.allPhotos.length == before + 3 &&
            find.byType(PhotoPickerScreen).evaluate().isEmpty);

    // Asked once, not once per photo.
    expect(find.text('存到相片冊（3 張）'), findsNothing);
    expect(find.text('存到相片冊'), findsNothing);
    final added =
        app.repository.allPhotos.where((p) => !oldIds.contains(p.id)).toList();
    expect(added, hasLength(3));
    expect(added.map((p) => p.id).toSet(), hasLength(3));
    expect(added.map((p) => p.albumId).toSet(), hasLength(1));
    expect(added.first.albumId, isNotNull);
    for (final p in added) {
      expect(p.taggingStatus, TaggingStatus.pending);
    }
    expect(app.queue.pending, pendingBefore + 3);
    // Back to the album, with the note that AI goes one by one.
    expect(find.byType(PhotoPickerScreen), findsNothing);
    expect(find.text('已加入 3 張照片，AI 會一張一張辨識'), findsOneWidget);
  });

  testWidgets('cancelling the album question adds nothing', (tester) async {
    final app = await openPicker(tester, 3);
    final before = app.repository.allPhotos.length;

    await tester.tap(find.text('加入 3 張'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('取消'));
    await settle(tester);

    expect(app.repository.allPhotos.length, before);
    expect(find.byType(PhotoPickerScreen), findsOneWidget);
    expect(find.text('存到相片冊（3 張）'), findsNothing);
  });

  testWidgets('one photo keeps the old flow and opens 照片詳情', (tester) async {
    final app = await openPicker(tester, 1);
    final before = app.repository.allPhotos.length;

    await tester.tap(find.text('完成'));
    await tester.pumpAndSettle();
    expect(find.text('存到相片冊'), findsOneWidget);
    await tester.tap(find.text('儲存'));
    await waitFor(
        tester,
        () =>
            app.repository.allPhotos.length == before + 1 &&
            find.byType(PhotoPickerScreen).evaluate().isEmpty);

    expect(app.repository.allPhotos.length, before + 1);
    expect(find.byType(PhotoPickerScreen), findsNothing);
    expect(find.text('照片詳情'), findsWidgets);
  });
}
