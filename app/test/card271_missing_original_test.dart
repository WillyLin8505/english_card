import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/photo_store.dart';

import 'helpers.dart';

Photo photoAt(String? filePath, {String? assetPath}) => Photo(
      id: 'p',
      title: '照片',
      takenAt: testNow,
      createdAt: testNow,
      filePath: filePath,
      assetPath: assetPath,
    );

void main() {
  test('a photo whose original file exists can be shown', () {
    final dir = Directory.systemTemp.createTempSync('card271_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final file = File('${dir.path}${Platform.pathSeparator}p.jpg')
      ..writeAsBytesSync([0xFF, 0xD8]);

    expect(PhotoStore.canShow(photoAt(file.path)), isTrue);
  });

  test('a photo whose original file is gone cannot be shown', () {
    final dir = Directory.systemTemp.createTempSync('card271_');
    addTearDown(() => dir.deleteSync(recursive: true));

    final missing = '${dir.path}${Platform.pathSeparator}gone.jpg';
    expect(PhotoStore.canShow(photoAt(missing)), isFalse);
  });

  test('bundled and photos without any picture keep their old behaviour', () {
    expect(PhotoStore.canShow(photoAt(null, assetPath: 'assets/a.jpg')),
        isTrue);
    expect(PhotoStore.canShow(photoAt(null)), isFalse);
  });
}
