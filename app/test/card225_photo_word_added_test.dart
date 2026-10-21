// Card #225 r6: words added from a photo (own album or 資料庫相片冊) were
// never reported — only manual adds sent word_added.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/analytics.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

WordCandidate cand(String word) => WordCandidate(
      word: word,
      pos: 'noun',
      meaning: '$word 的意思',
      level: 'A2',
      levelSource: 'cefr-j',
      evidence: '$word in the photo',
      point: const LabelPoint(0.3, 0.4),
      visualConfidence: 0.9,
    );

void main() {
  late WordDatabaseRepository repo;
  late List<Map<String, Object?>> events;
  setUp(() {
    repo = testRepository();
    final a = Analytics.instance;
    final saved = a.recorder;
    events = [];
    a.recorder = events.add;
    addTearDown(() => a.recorder = saved);
  });

  List<Object?> sources() => [
        for (final e in events)
          if (e['event'] == 'word_added') (e['properties'] as Map)['source']
      ];

  test('saving a photo reports each new word once, known words not', () {
    repo.savePhotoWords(
      'photo-breakfast',
      [
        ListedWord(cand('mug'), const LabelPoint(0.3, 0.4)),
        ListedWord(cand('saucer'), const LabelPoint(0.3, 0.4)),
        ListedWord(cand('coffee'), const LabelPoint(0.3, 0.4)),
      ],
      difficultyOffset: 0,
    );
    expect(sources(), ['photo', 'photo']);
  });

  test('a 資料庫相片冊 picture reports source database_album', () {
    final at = DateTime(2026, 10, 21);
    final photo =
        Photo(id: 'deck-1', title: 'deck', takenAt: at, createdAt: at);
    repo.addDeckPhoto(photo, [cand('teapot')]);
    expect(sources(), ['database_album']);
  });
}
