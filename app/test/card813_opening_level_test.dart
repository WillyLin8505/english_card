// 問題回報 #942 / #943 (owner: 預設停在這張照片實際找到的最高難度，不停在精通).
// A photo nobody has dialled opens at the highest level its candidates reach;
// that opening position is not a dial choice, so it is not saved or recorded.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

WordCandidate _c(String word, String level) => WordCandidate(
      word: word,
      pos: 'noun',
      meaning: '$word 義',
      level: level,
      levelSource: 'cefr-j',
      evidence: 'seen',
      point: const LabelPoint(0.5, 0.5),
      visualConfidence: 0.9,
      usefulness: 0.8,
    );

WordDatabaseRepository _repoWith(
    UserVocabularyProfile profile, List<WordCandidate> pool) {
  final repo = WordDatabaseRepository(clock: () => testNow, profile: profile);
  repo.addPhoto(Photo(
    id: 'p1',
    title: 'p1',
    takenAt: testNow,
    createdAt: testNow,
    placeholderColors: const [0xFF8899AA, 0xFF334455],
    width: 1200,
    height: 900,
    taggingStatus: TaggingStatus.done,
    candidates: pool,
  ));
  return repo;
}

void main() {
  final pool = [_c('building', 'A2'), _c('sign', 'B1'), _c('cart', 'B1')];

  test('an undialled photo opens at the highest level it actually found', () {
    final repo = _repoWith(UserVocabularyProfile.start('C2', now: testNow), pool);
    final session = PhotoWordSession(repo: repo, photoId: 'p1');
    addTearDown(session.dispose);
    expect(session.targetLevel, 'B1');
    expect(session.words, isNotEmpty);
  });

  test('leaving without touching the dial saves and records nothing', () {
    final repo = _repoWith(UserVocabularyProfile.start('C2', now: testNow), pool);
    final session = PhotoWordSession(repo: repo, photoId: 'p1');
    addTearDown(session.dispose);
    session.save();
    expect(repo.photo('p1')!.difficultyOffset, 0);
    expect(repo.profile.level, 5, reason: 'the learner level is not moved');
  });

  test('a photo never above the learner level keeps the learner level', () {
    final repo = _repoWith(UserVocabularyProfile.start('A1', now: testNow), pool);
    final session = PhotoWordSession(repo: repo, photoId: 'p1');
    addTearDown(session.dispose);
    expect(session.targetLevel, 'A1');
  });

  test('a dial move is what gets saved', () {
    final repo = _repoWith(UserVocabularyProfile.start('C2', now: testNow), pool);
    final session = PhotoWordSession(repo: repo, photoId: 'p1');
    addTearDown(session.dispose);
    session.setTarget(1);
    session.save();
    expect(repo.photo('p1')!.difficultyOffset, -4);
  });
}
