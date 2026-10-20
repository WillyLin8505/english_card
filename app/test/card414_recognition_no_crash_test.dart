import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/tagging_queue.dart';
import 'package:photo_english_app/services/text_scan.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

/// 問題回報 #408: whatever the recognizer throws, process() (run unawaited)
/// must finish normally and leave the photo marked failed.
void main() {
  tearDown(() => TextScan.recognizer = null);

  for (final error in <Object>[
    StateError('boom'),
    ArgumentError('bad image'),
    const FormatException('heic'),
    RangeError('index'),
  ]) {
    test('recognizer throwing ${error.runtimeType} does not escape', () async {
      TextScan.recognizer = (_) async => throw error;
      final repo = WordDatabaseRepository(clock: () => testNow);
      final store = PhotoStore.inMemory();
      final intake = PhotoIntake(repository: () => repo, photoStore: store);
      final saved = await store.save('p0', Uint8List.fromList([1, 2, 3]));
      repo.addPhoto(Photo(
          id: 'p0',
          title: 'p0',
          takenAt: testNow,
          storedKey: saved.storedKey,
          createdAt: testNow,
          scanMode: PhotoScanMode.text,
          taggingStatus: TaggingStatus.pending));
      final queue = TaggingQueue(
          repository: () => repo,
          settings: AppSettings.inMemory(),
          intake: intake,
          lexicon: testLexicon);
      await queue.process();
      expect(repo.photo('p0')!.taggingStatus, TaggingStatus.failed);
      expect(repo.photo('p0')!.taggingError, isNotEmpty);
    });
  }
}
