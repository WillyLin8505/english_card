// M87 (卡 #564): 存到相片冊 shows each album's cover. The dialog sizes its
// content intrinsically; a cover that needs a LayoutBuilder threw during
// layout and left the dialog blank.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/widgets/mobile/dialogs.dart';

import 'helpers.dart';

void main() {
  testWidgets('存到相片冊 lays out with album covers', (tester) async {
    final app = await pumpApp(tester, initialTab: AppTab.album);
    final repo = app.repository;
    // An album whose cover is one of its photos (not a bundled cover).
    final picture = repo.photos.firstWhere((p) => p.assetPath != null);
    final album = repo.addAlbum(name: '我的相簿');
    repo.addPhoto(Photo(
        id: 'p-cover',
        albumId: album.id,
        title: '封面',
        takenAt: testNow,
        createdAt: testNow,
        assetPath: picture.assetPath));
    expect(repo.albumCoverPhoto(album.id), isNotNull);

    showSaveToAlbumDialog(tester.element(find.byType(Scaffold).first),
        repository: repo, defaultTitle: '早餐');
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('存到相片冊'), findsOneWidget);
    expect(find.text('我的相簿'), findsWidgets);
    expect(
        find.descendant(
            of: find.byType(AlertDialog), matching: find.byType(Image)),
        findsWidgets);
  });
}
