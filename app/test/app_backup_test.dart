import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:photo_english_app/data/sample_word_database.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/app_backup.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_database_store.dart';

import 'helpers.dart';

/// 問題回報 #278: 備份還原 — one file, restorable on another install.
void main() {
  final now = testNow;
  late Directory dir;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('backup_test');
    Hive.init(dir.path);
  });

  tearDown(() async {
    await Hive.close();
    await dir.delete(recursive: true);
  });

  Future<WordDatabaseRepository> open({String language = 'en'}) async {
    final store = await HiveWordDatabaseStore.open(language: language);
    if (store.needsSeed) await store.seed(const WordDatabaseData());
    return WordDatabaseRepository.fromData(store.load(),
        language: language, store: store, clock: () => now);
  }

  /// A device with words, a web-style photo, a file photo, a review and
  /// a French collection.
  Future<(WordDatabaseRepository, PhotoStore, Uint8List)> fill() async {
    final store = await HiveWordDatabaseStore.open();
    await store.seed(sampleWordDatabaseData(now: now, lexicon: testLexicon()));
    final repo = WordDatabaseRepository.fromData(store.load(),
        store: store, clock: () => now);
    final photos = PhotoStore.inMemory();
    final pixels = Uint8List.fromList(List.generate(300000, (i) => i % 251));
    await photos.save('photo-web', pixels);
    repo.addPhoto(Photo(
        id: 'photo-web',
        title: '網頁照片',
        takenAt: now,
        storedKey: 'photo-web',
        createdAt: now));
    final file = File('${dir.path}/photo-file.jpg')
      ..writeAsBytesSync([1, 2, 3, 4]);
    repo.addPhoto(Photo(
        id: 'photo-file',
        title: '手機照片',
        takenAt: now,
        filePath: file.path,
        createdAt: now));
    repo.addWord(word: 'patio', pos: 'noun', meaning: '露台');
    final card = repo.cardOf(repo.entryByWord('balcony')!.id)!;
    repo.review(card.id, Rating.good,
        duration: const Duration(seconds: 3),
        templateType: 'cloze',
        correct: true,
        hintCount: 0,
        attempts: 1);
    await repo.flush();
    final fr = await open(language: 'fr');
    fr.addWord(word: 'chat', pos: 'noun', meaning: '貓');
    await fr.flush();
    return (repo, photos, pixels);
  }

  Future<void> wipeDevice() async {
    await Hive.deleteFromDisk();
    Hive.init(dir.path);
  }

  test('a backup restores every language, photo, review and setting', () async {
    final (before, photos, pixels) = await fill();
    final settings = AppSettings.inMemory(apiKey: 'secret-key')
      ..desiredRetention = 0.85
      ..englishAccent = 'en-US'
      ..cardStyle = CardStyle.playful;
    final (bytes, made) =
        await AppBackup.toBytes(settings: settings, photoStore: photos);
    expect(made.photos, 2);
    expect(made.reviews, greaterThan(0));
    expect(utf8.decode(bytes, allowMalformed: true),
        isNot(contains('secret-key')));
    // Photos are raw bytes: the file is not much bigger than its pixels.
    expect(bytes.length, lessThan(pixels.length * 1.2 + 200000));

    await wipeDevice();
    final newPhotos = PhotoStore.inMemory();
    final newSettings = AppSettings.inMemory();
    // Arrives in small chunks, like a file stream.
    final chunks = [
      for (var i = 0; i < bytes.length; i += 4096)
        bytes.sublist(i, (i + 4096).clamp(0, bytes.length))
    ];
    final restored = await AppBackup.restore(Stream.fromIterable(chunks),
        settings: newSettings, photoStore: newPhotos);
    expect(restored.photos, before.photoCount);
    expect(restored.reviews, made.reviews);
    expect(newSettings.desiredRetention, 0.85);
    expect(newSettings.englishAccent, 'en-US');
    expect(newSettings.cardStyle, CardStyle.playful);
    expect(newSettings.apiKey, '');

    final after = await open();
    expect((after.wordCount, after.photoCount, after.cardCount),
        (before.wordCount, before.photoCount, before.cardCount));
    expect(after.entryByWord('patio'), isNotNull);
    final card = after.cardOf(after.entryByWord('balcony')!.id)!;
    expect(card.fsrs.reps,
        before.cardOf(before.entryByWord('balcony')!.id)!.fsrs.reps);
    // Bytes come back, and photos point at this device's copy.
    final web = after.photo('photo-web')!;
    expect(await newPhotos.storedBytes(web.storedKey!), pixels);
    final moved = after.photo('photo-file')!;
    expect(moved.filePath, isNull);
    expect(await newPhotos.storedBytes(moved.storedKey!), [1, 2, 3, 4]);
    expect((await open(language: 'fr')).entryByWord('chat'), isNotNull);
  });

  test('a cut-off, newer or foreign file is refused and changes nothing',
      () async {
    final (before, photos, _) = await fill();
    final settings = AppSettings.inMemory();
    final (bytes, _) =
        await AppBackup.toBytes(settings: settings, photoStore: photos);
    final text = utf8.decode(bytes, allowMalformed: true);
    final newer = utf8.encode(text.replaceFirst(
        '"schema":"${HiveWordDatabaseStore.schemaVersion}"',
        '"schema":"${HiveWordDatabaseStore.schemaVersion + 1}"'));
    final cases = {
      'cut off': bytes.sublist(0, bytes.length - 100),
      'newer schema': newer,
      'newer file': utf8.encode('${AppBackup.magic} 9\n{}\n'),
      'not a backup': utf8.encode('hello\n'),
      'empty': <int>[],
    };
    for (final c in cases.entries) {
      await expectLater(
          AppBackup.restore(Stream.value(c.value),
              settings: settings, photoStore: PhotoStore.inMemory()),
          throwsA(isA<BackupException>()),
          reason: c.key);
    }
    final after = await open();
    expect((after.wordCount, after.photoCount),
        (before.wordCount, before.photoCount));
  });
}
