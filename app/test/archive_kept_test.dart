import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/word_database_query.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

WordCandidate cand(String w, double x) => WordCandidate(
    word: w, pos: 'noun', meaning: w, level: 'A2', levelSource: 'cefr-j',
    evidence: 'e', point: LabelPoint(x, .5), visualConfidence: .9, usefulness: .8);

void main() {
  test('swiping every word of a photo removes the photo but keeps the words archived', () {
    final repo = WordDatabaseRepository(
        clock: () => testNow, profile: UserVocabularyProfile.start('A2', now: testNow));
    repo.addPhoto(Photo(
        id: 'p', title: 'p', takenAt: testNow, createdAt: testNow, storedKey: 'p',
        taggingStatus: TaggingStatus.done,
        candidates: [cand('cup', .1), cand('plate', .3), cand('fork', .5)]));
    PhotoWordSession(repo: repo, photoId: 'p').save();
    final s = PhotoWordSession(repo: repo, photoId: 'p');
    while (s.words.isNotEmpty) {
      s.swipe(s.words.first);
    }
    expect(s.save().photoRemoved, isTrue);
    expect(repo.photo('p'), isNull, reason: '照片最後一個單字被刪除後，從相片冊移除照片參照');
    final learned = repo.query(const WordDatabaseFilter(status: StudyStatus.learned));
    expect(learned.map((r) => r.entry.word).toSet(), {'cup', 'plate', 'fork'});
    repo.restoreWord('cup');
    final cup = repo.entryByWord('cup')!;
    expect(repo.cardOf(cup.id)!.archived, isFalse, reason: '復原後還原原卡片');
  });
}
