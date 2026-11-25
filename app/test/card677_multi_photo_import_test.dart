import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/screens/photo_picker_screen.dart';

import 'helpers.dart';

/// 問題回報 #677: 匯入照片要能一次選多張; #1730: every photo is added at once
/// (no album question) and waits in the tagging queue.
void main() {
  const files = [
    'test/fixtures/photos/recent_1.jpg',
    'test/fixtures/photos/recent_2.jpg',
    'test/fixtures/photos/recent_3.jpg',
  ];
  var pickerCalls = 0;

  Future<List<XFile>> fakeLibrary(int n) async {
    pickerCalls++;
    return [
      for (final f in files.take(n))
        XFile.fromData(File(f).readAsBytesSync(), name: f.split('/').last),
    ];
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

  // Owner 11/24 (問題回報 #1730): picked = added, no album question, and
  // recognition starts at once.
  testWidgets('three photos: added at once, one album, three queued',
      (tester) async {
    final app = await pumpApp(tester);
    final before = app.repository.allPhotos.length;
    final oldIds = {for (final p in app.repository.allPhotos) p.id};
    final pendingBefore = app.queue.pending;
    tester.state<NavigatorState>(find.byType(Navigator).first).push(
        MaterialPageRoute<void>(
            builder: (_) =>
                PhotoPickerScreen(pickLibrary: () => fakeLibrary(3))));
    await settle(tester);
    await tester.tap(find.text('從相簿選擇'));
    await waitFor(
        tester,
        () =>
            app.repository.allPhotos.length == before + 3 &&
            find.byType(PhotoPickerScreen).evaluate().isEmpty);

    expect(pickerCalls, 1);
    expect(find.textContaining('存到相片冊'), findsNothing);
    final added =
        app.repository.allPhotos.where((p) => !oldIds.contains(p.id)).toList();
    expect(added, hasLength(3));
    expect(added.map((p) => p.id).toSet(), hasLength(3));
    expect(added.map((p) => p.albumId).toSet(), hasLength(1));
    for (final p in added) {
      expect(p.taggingStatus, TaggingStatus.pending);
    }
    expect(app.queue.pending, pendingBefore + 3);
    expect(find.byType(PhotoPickerScreen), findsNothing);
    expect(find.text('已加入 3 張照片，AI 會一張一張辨識'), findsOneWidget);
  });

  testWidgets('one photo: added at once and opens 照片詳情', (tester) async {
    final app = await pumpApp(tester);
    final before = app.repository.allPhotos.length;
    tester.state<NavigatorState>(find.byType(Navigator).first).push(
        MaterialPageRoute<void>(
            builder: (_) =>
                PhotoPickerScreen(pickLibrary: () => fakeLibrary(1))));
    await settle(tester);
    await tester.tap(find.text('從相簿選擇'));
    await waitFor(
        tester,
        () =>
            app.repository.allPhotos.length == before + 1 &&
            find.byType(PhotoPickerScreen).evaluate().isEmpty);

    expect(find.textContaining('存到相片冊'), findsNothing);
    expect(app.repository.allPhotos.length, before + 1);
    expect(find.byType(PhotoPickerScreen), findsNothing);
    expect(find.text('照片詳情'), findsWidgets);
  });

  testWidgets('no bundled sample photos in the picker', (tester) async {
    await pumpApp(tester);
    tester.state<NavigatorState>(find.byType(Navigator).first).push(
        MaterialPageRoute<void>(
            builder: (_) =>
                PhotoPickerScreen(pickLibrary: () => fakeLibrary(0))));
    await settle(tester);
    expect(find.text('範例照片'), findsNothing);
    expect(find.text('已選照片與範例'), findsNothing);
  });
}
