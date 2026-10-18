import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/photo_store.dart';

import 'helpers.dart';

void main() {
  // 問題回報 #283: the album cover skips a photo whose original is gone.
  test('album cover skips a newer photo whose original file is gone', () {
    final dir = Directory.systemTemp.createTempSync('card276_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final kept = File('${dir.path}${Platform.pathSeparator}kept.jpg')
      ..writeAsBytesSync([0xFF, 0xD8]);
    final gone = '${dir.path}${Platform.pathSeparator}gone.jpg';

    final repo = testRepository();
    final album = repo.addAlbum(name: '廚房');
    Photo photo(String id, String path, int minutes) => Photo(
        id: id,
        title: id,
        albumId: album.id,
        takenAt: testNow.add(Duration(minutes: minutes)),
        createdAt: testNow,
        filePath: path);
    repo.addPhoto(photo('old', kept.path, 0));
    repo.addPhoto(photo('new', gone, 5));

    expect(repo.photosInAlbum(album.id).map((p) => p.id),
        containsAll(['old', 'new']),
        reason: '相簿仍列出原檔遺失的照片，讓使用者可以刪除');
    expect(repo.albumCoverPhoto(album.id)?.id, 'old');
    expect(PhotoStore.canShow(repo.photo('new')!), isFalse);
  });

  test('an album whose only photo lost its original has no cover', () {
    final dir = Directory.systemTemp.createTempSync('card276_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final repo = testRepository();
    final album = repo.addAlbum(name: '客廳');
    repo.addPhoto(Photo(
        id: 'gone',
        title: 'gone',
        albumId: album.id,
        takenAt: testNow,
        createdAt: testNow,
        filePath: '${dir.path}${Platform.pathSeparator}gone.jpg'));

    expect(repo.albumCoverPhoto(album.id), isNull);
  });

  test('only a photo pointing at a gone file counts as lost', () {
    final dir = Directory.systemTemp.createTempSync('card276_');
    addTearDown(() => dir.deleteSync(recursive: true));
    Photo at(String? path) => Photo(
        id: 'p', title: 'p', takenAt: testNow, createdAt: testNow,
        filePath: path);
    expect(PhotoStore.lostOriginal(at(null)), isFalse,
        reason: '沒有圖片的照片照舊畫漸層佔位');
    expect(
        PhotoStore.lostOriginal(
            at('${dir.path}${Platform.pathSeparator}gone.jpg')),
        isTrue);
  });
}
