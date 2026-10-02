import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_selector.dart';

import 'helpers.dart';

WordCandidate cand(String w, double x, {String pos = 'verb'}) => WordCandidate(
    word: w, pos: pos, meaning: w, level: 'A2', levelSource: 'cefr-j',
    evidence: 'e', point: LabelPoint(x, .5), visualConfidence: .9, usefulness: .8);

void main() {
  test('restoring a word on another photo keeps this photo at five words (問題回報 #90)', () {
    final repo = WordDatabaseRepository(
        clock: () => testNow, profile: UserVocabularyProfile.start('A2', now: testNow));
    final words = ['run', 'jump', 'swim', 'read', 'write', 'sing', 'cook'];
    Photo photo(String id, List<String> ws) => Photo(
        id: id, title: id, takenAt: testNow, createdAt: testNow, storedKey: id,
        taggingStatus: TaggingStatus.done,
        candidates: [for (final (i, w) in ws.indexed) cand(w, .1 + i * .1)]);
    repo.addPhoto(photo('a', words));
    repo.addPhoto(photo('b', ['run', 'jump']));
    final a = PhotoWordSession(repo: repo, photoId: 'a');
    final swiped = a.words.first.word;
    a.swipe(a.words.first); // a refills its list to five
    a.save();
    a.dispose();
    int listed(String id) =>
        repo.activeLabels(id).where((l) => !l.occ.contextOnly).length;
    expect(listed('a'), lessThanOrEqualTo(WordSelector.maxWords));
    // The word comes back from the database page.
    repo.restoreWord(swiped);
    expect(listed('a'), lessThanOrEqualTo(WordSelector.maxWords));
    final again = PhotoWordSession(repo: repo, photoId: 'a');
    expect(again.words.length, lessThanOrEqualTo(WordSelector.maxWords));
  });
}
