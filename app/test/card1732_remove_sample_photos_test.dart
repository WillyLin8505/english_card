// 問題回報 #1732 (owner 11/24): the stock 範例照片 older builds added from
// 選擇照片 (the puppy, pancakes, …) are taken out of the learner's albums;
// the learner's own photos stay.
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

void main() {
  test('the listed fingerprints are the sample files hashed by the App', () {
    final files = Directory('test/fixtures/photos')
        .listSync()
        .whereType<File>()
        .where((f) => f.path.endsWith('.jpg'));
    expect(files, isNotEmpty);
    for (final f in files) {
      expect(WordDatabaseRepository.bundledSampleHashes,
          contains(PhotoIntake.hashBytes(f.readAsBytesSync())),
          reason: f.path);
    }
  });

  test('sample photos go, the learner\'s own photo stays', () async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final intake =
        PhotoIntake(repository: () => repo, photoStore: PhotoStore.inMemory());
    final sample =
        File('test/fixtures/photos/recent_pasta.jpg').readAsBytesSync();
    await intake.addPhoto(sample, title: '範例');
    final own = await intake.addPhoto(Uint8List.fromList([1, 2, 3, 4]),
        title: '我的照片');

    expect(repo.removeBundledSamplePhotos(), 1);
    expect(repo.allPhotos.map((p) => p.id), [own.id]);
    expect(repo.removeBundledSamplePhotos(), 0);
  });
}
