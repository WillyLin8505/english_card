import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_database_store.dart';

/// 問題回報 #1179: a deleted photo's picture leaves the device too.
void main() {
  late Directory root;
  late Directory folder;
  late PhotoStore store;
  final bytes = Uint8List.fromList([1, 2, 3]);

  String pathOf(String name) =>
      '${folder.path}${Platform.pathSeparator}$name';

  Photo photoAt(String id, String? filePath) => Photo(
      id: id,
      title: id,
      takenAt: DateTime.utc(2026),
      createdAt: DateTime.utc(2026),
      filePath: filePath);

  File oldFile(String name) {
    final f = File(pathOf(name))..writeAsBytesSync(bytes);
    f.setLastModifiedSync(DateTime.now().subtract(const Duration(days: 3)));
    return f;
  }

  setUp(() async {
    root = await Directory.systemTemp.createTemp('card925');
    folder = await Directory('${root.path}/photos').create();
    store = PhotoStore.inDirectory(folder);
    Hive.init('${root.path}/hive');
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
    await Hive.close();
    await root.delete(recursive: true);
  });

  test('removing a photo deletes its file once the record is gone', () async {
    final data = await HiveWordDatabaseStore.open();
    final repo = WordDatabaseRepository.fromData(data.load(), store: data)
      ..onPhotoRemoved =
          ((p) => store.remove(filePath: p.filePath, storedKey: p.storedKey));
    final saved = await store.save('a', bytes);
    final other = await store.save('b', bytes);
    repo.addPhoto(photoAt('a', saved.filePath));
    repo.addPhoto(photoAt('b', other.filePath));

    repo.removePhoto('a');
    await repo.flush();

    expect(File(saved.filePath!).existsSync(), isFalse);
    expect(File(other.filePath!).existsSync(), isTrue);
    expect(data.load().photos.map((p) => p.id), ['b']);
  });

  test('a file outside the photo folder is left alone', () async {
    final album = await Directory('${root.path}/album').create();
    final original =
        File('${album.path}${Platform.pathSeparator}IMG_1.jpg')
          ..writeAsBytesSync(bytes);
    await store.remove(filePath: original.path);
    expect(original.existsSync(), isTrue);
  });

  test('a path from an earlier install finds the file in this folder',
      () async {
    final saved = await store.save('a', bytes);
    await store.remove(filePath: '/var/old-container/photos/a.jpg');
    expect(File(saved.filePath!).existsSync(), isFalse);
  });

  test('a file already gone is no error', () async {
    await store.remove(filePath: pathOf('missing.jpg'));
    await store.remove();
  });

  test('stored bytes go too (web)', () async {
    final memory = PhotoStore.inMemory();
    final saved = await memory.save('a', bytes);
    await memory.remove(storedKey: saved.storedKey);
    expect(await memory.storedBytes('a'), isNull);
  });

  test('after a restore only the backup pictures stay (#1180)', () async {
    final keep = oldFile('keep.jpg');
    final stale = oldFile('stale.jpg');
    final recent = File(pathOf('recent.jpg'))..writeAsBytesSync(bytes);
    expect(await store.removeAllExcept({'keep'}), 2);
    expect(keep.existsSync(), isTrue);
    expect(stale.existsSync(), isFalse);
    expect(recent.existsSync(), isFalse);
  });

  group('sweep of files left by older versions', () {
    test('only old files no language refers to go, once', () async {
      final kept = oldFile('kept.jpg');
      final orphan = oldFile('orphan.jpg');
      final recent = File(pathOf('recent.jpg'))..writeAsBytesSync(bytes);

      final removed = await store.sweepOrphansOnce(
          () async => ['/old/install/kept.jpg', null]);

      expect(removed, 1);
      expect(kept.existsSync(), isTrue);
      expect(orphan.existsSync(), isFalse);
      expect(recent.existsSync(), isTrue);

      final second = oldFile('second.jpg');
      expect(await store.sweepOrphansOnce(() async => ['kept.jpg']), 0);
      expect(second.existsSync(), isTrue);
    });

    test('no records found: nothing goes, and it tries again', () async {
      final orphan = oldFile('orphan.jpg');
      expect(await store.sweepOrphansOnce(() async => const []), 0);
      expect(orphan.existsSync(), isTrue);
      expect(await store.sweepOrphansOnce(() async => ['other.jpg']), 1);
    });

    test('records that cannot be read: nothing goes, and it tries again',
        () async {
      final orphan = oldFile('orphan.jpg');
      expect(
          await store.sweepOrphansOnce(() async => throw StateError('box')), 0);
      expect(orphan.existsSync(), isTrue);
      expect(await store.sweepOrphansOnce(() async => ['other.jpg']), 1);
    });

    test('photos of every learning language are kept', () async {
      for (final language in ['en', 'fr']) {
        final data = await HiveWordDatabaseStore.open(language: language);
        await data.putPhoto(photoAt('p-$language', '/x/$language.jpg'));
      }
      final paths = await HiveWordDatabaseStore.savedPhotoPaths();
      expect(paths, containsAll(['/x/en.jpg', '/x/fr.jpg']));
    });
  });
}
