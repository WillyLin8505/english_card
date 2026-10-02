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
    evidence: 'seen', point: LabelPoint(x, 0.5), visualConfidence: 0.9, usefulness: 0.8);

void main() {
  test('a word studied from another photo stays a hidden context when the photo is reopened', () {
    final repo = WordDatabaseRepository(
        clock: () => testNow, profile: UserVocabularyProfile.start('A2', now: testNow));
    Photo photo(String id, List<String> words) => Photo(
        id: id, title: id, takenAt: testNow, createdAt: testNow, storedKey: id,
        taggingStatus: TaggingStatus.done,
        candidates: [for (final (i, w) in words.indexed) cand(w, 0.1 + i * 0.1)]);
    repo.addPhoto(photo('a', ['fork', 'plate']));
    PhotoWordSession(repo: repo, photoId: 'a').save();
    expect(repo.entryByWord('fork'), isNotNull);

    repo.addPhoto(photo('b', ['fork', 'spoon', 'napkin', 'cup', 'bowl', 'knife']));
    final b = PhotoWordSession(repo: repo, photoId: 'b');
    expect(b.words.map((w) => w.word), isNot(contains('fork')));
    final listed = [for (final w in b.words) w.word]..sort();
    b.save();
    expect(repo.photosOfWord(repo.entryByWord('fork')!.id).map((p) => p.id), contains('b'),
        reason: 'b is one more context of fork');

    final again = PhotoWordSession(repo: repo, photoId: 'b');
    expect([for (final w in again.words) w.word]..sort(), listed);
    expect(again.words.length, lessThanOrEqualTo(5));
    expect(again.oldWords.map((o) => o.word), contains('fork'));
  });

  test('one entry per spelling: another part of speech is a duplicate (spec 7)', () {
    final repo = WordDatabaseRepository(clock: () => testNow);
    repo.addWord(word: 'bowl', pos: 'noun', meaning: '碗', level: 'A1');
    expect(() => repo.addWord(word: 'bowl', pos: 'verb', meaning: '打保齡球', level: 'B2'),
        throwsA(isA<DuplicateWordException>()));
    expect(repo.entries, hasLength(1));
  });

  test('a dial that leaves no words is kept for the photo', () {
    final repo = WordDatabaseRepository(
        clock: () => testNow, profile: UserVocabularyProfile.start('A2', now: testNow));
    for (final w in ['plant', 'roof']) {
      repo.addWord(word: w, pos: 'noun', meaning: w, level: 'A2');
    }
    repo.addPhoto(Photo(
        id: 'p', title: 'p', takenAt: testNow, createdAt: testNow, storedKey: 'p',
        taggingStatus: TaggingStatus.done, candidates: [cand('plant', .3), cand('roof', .6)]));
    final s = PhotoWordSession(repo: repo, photoId: 'p');
    expect(s.words, isEmpty, reason: 'both words are studied already');
    s.setTarget(4);
    s.save();
    final again = PhotoWordSession(repo: repo, photoId: 'p');
    expect(again.targetLevel, 'C1', reason: '輪盤選擇保存為此照片的 difficultyOffset');
  });
}
