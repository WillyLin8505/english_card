import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/tagging_queue.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

// 問題回報 #1774: a photo is read for every level (A1–C2) in one call, and
// moving the difficulty bar only filters what is already there. A photo read
// before that (one level only) is read for all levels once, not per move.

final _png = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAEElEQVR4nGNocFCAIwacHADRZwqBZaYHGAAAAABJRU5ErkJggg==');

const _bands = {'peel': 'A1', 'wash': 'B1', 'vase': 'C1'};

WordCandidate _fruit(String w, int i) => WordCandidate(
      word: w,
      pos: 'noun',
      meaning: '$w 義',
      level: 'A1',
      levelSource: 'cefr-j',
      evidence: 'deck',
      point: LabelPoint(0.1 + i * 0.18, 0.4),
      visualConfidence: 0.9,
      usefulness: 0.8,
    );

Map<String, Object> _allLevels() => {
      'candidates': [
        for (final (i, e) in _bands.entries.indexed)
          {
            'word': e.key,
            'pos': e.key == 'wash' ? 'verb' : 'noun',
            'meaning': '${e.key} 義',
            'cefr': e.value,
            'point': [0.2 + i * 0.2, 0.6],
          },
      ],
    };

void main() {
  late WordDatabaseRepository repo;
  late TaggingQueue queue;
  late List<http.Request> seen;

  setUp(() {
    repo = WordDatabaseRepository(
        clock: () => testNow,
        profile: UserVocabularyProfile.start('A1', now: testNow));
    seen = [];
    final intake = PhotoIntake(
      repository: () => repo,
      photoStore: PhotoStore.inMemory(),
      createTagger: (uri, key) => TaggingService(
        endpoint: uri,
        apiKey: key,
        client: MockClient((r) async {
          seen.add(r);
          return jsonResponse(_allLevels());
        }),
      ),
    );
    queue = TaggingQueue(
        repository: () => repo,
        settings: AppSettings.inMemory(
            taggingUrl: 'http://127.0.0.1:8765/tag', apiKey: 'k'),
        intake: intake,
        lexicon: testLexicon);
  });

  /// A deck picture is tagged already; [levelsAsked] false makes it an old
  /// one-level photo, as tagged before #1774.
  Future<String> oldPhoto(WidgetTester tester, {required bool levelsAsked}) async {
    final saved = await tester.runAsync(() => queue.intake.addDeckPicture(
        Uint8List.fromList(_png),
        title: '水果',
        labels: [
          for (final (i, w) in ['apple', 'pear', 'grape'].indexed) _fruit(w, i),
        ]));
    final id = saved!.photo.id;
    repo.updatePhoto(repo.photo(id)!.copyWith(levelsAsked: levelsAsked));
    return id;
  }

  Future<void> idle(WidgetTester tester, PhotoWordSession s) =>
      tester.runAsync(() async {
        for (var i = 0; i < 50 && s.fetchingMore != null; i++) {
          await Future<void>.delayed(const Duration(milliseconds: 10));
        }
      });

  testWidgets('a one-level photo is read for all levels once, then never again',
      (tester) async {
    final id = await oldPhoto(tester, levelsAsked: false);

    final added = await tester.runAsync(() => queue.fillLevels(id));
    expect(seen, hasLength(1));
    expect(seen.single.url.queryParameters['mode'], 'cefr');
    expect(seen.single.url.queryParameters.containsKey('focus'), isFalse);
    expect(added, 3);
    expect(repo.photo(id)!.levelsAsked, isTrue);
    expect(repo.photo(id)!.candidates.map((c) => c.word),
        containsAll(['peel', 'wash']));

    await tester.runAsync(() => queue.fillLevels(id));
    expect(seen, hasLength(1), reason: 'the flag stops a second read');
  });

  testWidgets('moving the level bar on an all-level photo asks nothing',
      (tester) async {
    final id = await oldPhoto(tester, levelsAsked: true);
    final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
    // Opening may ask for more verbs (the nouns are capped); the bar must not.
    await idle(tester, s);
    final opened = seen.length;
    final target = s.target;
    s.setTarget(target + 1, live: true);
    s.setTarget(target + 1);
    s.setTarget(target + 2);
    await idle(tester, s);
    expect(seen, hasLength(opened));
    s.dispose();
  });

  testWidgets('releasing the bar on a one-level photo reads it once',
      (tester) async {
    final id = await oldPhoto(tester, levelsAsked: false);
    final s = PhotoWordSession(repo: repo, photoId: id, queue: queue);
    await idle(tester, s);
    final opened = seen.length;
    final target = s.target;
    s.setTarget(target, live: true);
    s.setTarget(target);
    await idle(tester, s);
    expect(seen, hasLength(opened + 1));
    expect(seen.last.url.queryParameters['mode'], 'cefr');

    s.setTarget(target + 1);
    s.setTarget(target);
    await idle(tester, s);
    expect(seen, hasLength(opened + 1),
        reason: 'the bar never asks the photo again');
    s.dispose();
  });
}
