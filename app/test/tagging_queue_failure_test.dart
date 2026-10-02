import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/tagging_queue.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

void main() {
  Future<(WordDatabaseRepository, int)> run(int failStatus) async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final store = PhotoStore.inMemory();
    var calls = 0;
    final intake = PhotoIntake(
      repository: () => repo,
      photoStore: store,
      createTagger: (uri, key) => TaggingService(
        endpoint: uri,
        apiKey: key,
        client: MockClient((r) async {
          calls++;
          if (String.fromCharCodes(r.bodyBytes).contains('BADPHOTO')) {
            return http.Response('{"error":"unexpected model reply"}', failStatus);
          }
          return jsonResponse({
            'candidates': [
              {'word': 'roof', 'pos': 'noun', 'evidence': 'top', 'point': [0.5, 0.2]},
            ]
          });
        }),
      ),
    );
    for (final (i, first) in [(0, 1), (1, 2), (2, 3)]) {
      final saved = await store.save(
          'p$i', Uint8List.fromList((first == 1 ? 'BADPHOTO' : 'photo$first').codeUnits));
      repo.addPhoto(Photo(
          id: 'p$i', title: 'p$i', takenAt: testNow, storedKey: saved.storedKey,
          createdAt: testNow.add(Duration(minutes: i)), taggingStatus: TaggingStatus.pending));
    }
    final queue = TaggingQueue(
        repository: () => repo,
        settings: AppSettings.inMemory(taggingUrl: 'http://x/tag', apiKey: 'k'),
        intake: intake,
        lexicon: testLexicon);
    await queue.process();
    return (repo, calls);
  }

  test('one photo the model can\'t read doesn\'t hold back the others', () async {
    final (repo, calls) = await run(422);
    final status = {for (final p in repo.photos) p.id: p.taggingStatus};
    expect(status.values.where((s) => s == TaggingStatus.failed), hasLength(1));
    expect(status.values.where((s) => s == TaggingStatus.done), hasLength(2));
    expect(calls, 3);
    final failed = repo.photos.firstWhere((p) => p.taggingStatus == TaggingStatus.failed);
    expect(failed.taggingError, contains('格式不完整'));
  });

  test('an unreachable tagger still stops the queue (photos wait)', () async {
    final (repo, _) = await run(502);
    expect(repo.photo('p0')!.taggingStatus, TaggingStatus.pending,
        reason: 'it waits in the queue and is retried later');
    expect(repo.photos.where((p) => p.taggingStatus == TaggingStatus.failed), isEmpty);
  });
}
