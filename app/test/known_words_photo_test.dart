import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

WordCandidate cand(String w, double x) => WordCandidate(
    word: w, pos: 'noun', meaning: w, level: 'A2', levelSource: 'cefr-j',
    evidence: 'e', point: LabelPoint(x, .5), visualConfidence: .9, usefulness: .8);

void main() {
  test('a photo whose words are all studied already still becomes their context (問題回報 #120)', () {
    final repo = WordDatabaseRepository(
        clock: () => testNow, profile: UserVocabularyProfile.start('A2', now: testNow));
    Photo photo(String id, List<String> ws) => Photo(
        id: id, title: id, takenAt: testNow, createdAt: testNow, storedKey: id,
        taggingStatus: TaggingStatus.done,
        candidates: [for (final (i, w) in ws.indexed) cand(w, .2 + i * .2)]);
    repo.addPhoto(photo('a', ['cup', 'plate']));
    PhotoWordSession(repo: repo, photoId: 'a').save();
    repo.addPhoto(photo('b', ['cup', 'plate']));
    final b = PhotoWordSession(repo: repo, photoId: 'b');
    expect(b.words, isEmpty, reason: '照片中沒有新詞時列表保持空白');
    b.save();
    final cup = repo.entryByWord('cup')!;
    expect(repo.photosOfWord(cup.id).map((p) => p.id), containsAll(['a', 'b']),
        reason: '新照片只加入該單字的照片情境');
    expect(repo.photo('b')!.wordsSavedAt, isNotNull);
    expect(repo.activeLabels('b').every((l) => l.occ.contextOnly), isTrue);
  });
}
