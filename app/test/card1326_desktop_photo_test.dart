import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:photo_english_app/screens/photo_picker_screen.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/dialogs.dart';

import 'helpers.dart';

/// 問題回報 #1768: a learner with no album yet loses the first photo (it is
/// saved in no album and 相片冊 shows none), and on desktop 選擇新照片 opened
/// an empty picker page that needed a second 從相簿選擇 tap.
void main() {
  const file = 'test/fixtures/photos/recent_1.jpg';

  Future<List<XFile>> fakeLibrary() async => [
        XFile.fromData(File(file).readAsBytesSync(), name: 'recent_1.jpg'),
      ];

  Future<void> waitFor(WidgetTester tester, bool Function() done) async {
    for (var i = 0; i < 400 && !done(); i++) {
      await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 20)));
      await tester.pump(const Duration(milliseconds: 50));
    }
    await tester.pump(const Duration(milliseconds: 500));
  }

  test('no album yet: autoSaveChoice makes one and reuses it', () {
    final repo = WordDatabaseRepository();
    expect(repo.albums, isEmpty);

    final first = autoSaveChoice(repo, defaultTitle: '10/19 14:32');
    expect(repo.albums, hasLength(1));
    expect(first.albumId, repo.albums.single.id);

    final second = autoSaveChoice(repo, defaultTitle: '10/19 14:33');
    expect(repo.albums, hasLength(1));
    expect(second.albumId, first.albumId);
  });

  testWidgets('desktop: 選擇新照片 opens the file picker at once and goes to '
      '照片詳情', (tester) async {
    final app = await pumpApp(tester);
    final before = app.repository.allPhotos.length;
    var pickerCalls = 0;
    debugDefaultTargetPlatformOverride = TargetPlatform.windows;
    try {
      tester.state<NavigatorState>(find.byType(Navigator).first).push(
          MaterialPageRoute<void>(
              builder: (_) => PhotoPickerScreen(pickLibrary: () async {
                    pickerCalls++;
                    return fakeLibrary();
                  })));
      // The picker opens its file dialog after the first frame, with no tap.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(pickerCalls, 1);
      await waitFor(
          tester,
          () =>
              app.repository.allPhotos.length == before + 1 &&
              find.text('留在這裡').evaluate().isNotEmpty);
      // 問題回報 #1874: the album question comes after the save; keep the album.
      await tester.tap(find.text('留在這裡'));
      await waitFor(
          tester, () => find.byType(PhotoPickerScreen).evaluate().isEmpty);
      expect(app.repository.allPhotos.length, before + 1);
      expect(find.byType(PhotoPickerScreen), findsNothing);
      expect(find.text('照片詳情'), findsWidgets);
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });
}
