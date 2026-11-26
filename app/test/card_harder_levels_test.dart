// Owner 11/25 「先出簡單、背景補難」: after the first scan, a photo whose
// B2/C1/C2 hold fewer than three words gets one background request with
// mode=cefr&focus=harder.
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
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
  setUp(() => TaggingQueue.autoHarderLevels = true);
  tearDown(() => TaggingQueue.autoHarderLevels = false);

  test('first scan without hard words asks once more for harder ones',
      () async {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final store = PhotoStore.inMemory();
    final calls = <Uri>[];
    final intake = PhotoIntake(
      repository: () => repo,
      photoStore: store,
      createTagger: (uri, key) => TaggingService(
        endpoint: uri,
        apiKey: key,
        client: MockClient((r) async {
          calls.add(r.url);
          final harder = r.url.queryParameters['focus'] == 'harder';
          return jsonResponse({
            'candidates': harder
                ? [
                    {'word': 'terracotta', 'pos': 'adjective', 'point': [0.5, 0.5]},
                  ]
                : [
                    {'word': 'cup', 'pos': 'noun', 'point': [0.2, 0.2]},
                    {'word': 'table', 'pos': 'noun', 'point': [0.4, 0.6]},
                  ],
          });
        }),
      ),
    );
    final saved = await store.save('p0', Uint8List.fromList('photo'.codeUnits));
    repo.addPhoto(Photo(
        id: 'p0', title: 'p0', takenAt: testNow, storedKey: saved.storedKey,
        createdAt: testNow, taggingStatus: TaggingStatus.pending));
    final queue = TaggingQueue(
        repository: () => repo,
        settings: AppSettings.inMemory(taggingUrl: 'http://x/tag', apiKey: 'k'),
        intake: intake,
        lexicon: testLexicon);
    await queue.process();
    for (var i = 0; i < 20 && calls.length < 2; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 20));
    }
    final harder =
        calls.where((u) => u.queryParameters['focus'] == 'harder').toList();
    expect(harder, hasLength(1));
    expect(harder.single.queryParameters['mode'], 'cefr');
    expect(repo.photo('p0')!.candidates.map((c) => c.word),
        containsAll(['cup', 'table', 'terracotta']));
  });
}
