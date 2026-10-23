// 問題回報 #614: iOS moves the app container on every install and update, so
// a saved Photo.filePath can name a folder that is gone while the picture is
// still in this install's photo folder.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/photo_store.dart';

void main() {
  late Directory tmp;
  setUp(() {
    tmp = Directory.systemTemp.createTempSync('photos614');
    PhotoStore.photosDirectory = tmp.path;
  });
  tearDown(() {
    PhotoStore.photosDirectory = null;
    tmp.deleteSync(recursive: true);
  });

  Photo photo(String path) => Photo(
      id: 'p',
      title: '',
      takenAt: DateTime(2026),
      createdAt: DateTime(2026),
      filePath: path);

  test('a path from an old container finds the file in this install', () {
    File('${tmp.path}/photo-1792730973924683.jpg').writeAsBytesSync([1, 2, 3]);
    const old = '/var/mobile/Containers/Data/Application/'
        '87AAF059-D418-49A0-A878-9E6847AE4018/Documents/english_card_photos/'
        'photo-1792730973924683.jpg';
    expect(PhotoStore.localPath(old).replaceAll(r'\', '/'),
        '${tmp.path.replaceAll(r'\', '/')}/photo-1792730973924683.jpg');
    expect(PhotoStore.lostOriginal(photo(old)), isFalse);
    expect(PhotoStore.canShow(photo(old)), isTrue);
  });

  test('a path that exists is kept; a file gone everywhere is still lost', () {
    final here = File('${tmp.path}/photo-2.jpg')..writeAsBytesSync([1]);
    expect(PhotoStore.localPath(here.path), here.path);
    const gone = '/var/mobile/Containers/Data/Application/X/Documents/'
        'english_card_photos/photo-3.jpg';
    expect(PhotoStore.localPath(gone), gone);
    expect(PhotoStore.lostOriginal(photo(gone)), isTrue);
  });
}
