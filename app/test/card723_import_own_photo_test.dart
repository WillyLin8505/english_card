import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

WordCandidate cand(String word,
        {String pos = 'noun',
        String? lemma,
        double confidence = 0.9,
        bool inferred = false}) =>
    WordCandidate(
      word: word,
      lemma: lemma,
      pos: pos,
      meaning: '',
      level: 'A2',
      levelSource: 'test',
      point: const LabelPoint(0.3, 0.4),
      visualConfidence: confidence,
      inferred: inferred,
    );

Photo photo(String id, DateTime takenAt, List<WordCandidate> candidates,
        {String? credit, List<String> rejected = const []}) =>
    Photo(
      id: id,
      title: id,
      takenAt: takenAt,
      createdAt: takenAt,
      storedKey: 'k-$id',
      candidates: candidates,
      credit: credit,
      rejectedWords: rejected,
    );

/// 問題回報 #864 (card #723): a word the learner imports gets the learner's
/// own photo that already shows it as its picture, newest first.
void main() {
  WordDatabaseRepository repo() => WordDatabaseRepository(clock: () => testNow);

  test('a hand-added word takes the newest own photo showing it (forms too)',
      () {
    final r = repo();
    final old = DateTime(2026, 9, 1), recent = DateTime(2026, 9, 20);
    r.addPhoto(photo('old', old, [cand('cup')]));
    r.addPhoto(photo('new', recent, [cand('cups', lemma: 'cup')]));
    // A deck picture, a rejected label and a guessed word never count.
    r.addPhoto(photo('photo-deck-1', DateTime(2026, 9, 22), [cand('cup')]));
    r.addPhoto(photo('credited', DateTime(2026, 9, 22), [cand('cup')],
        credit: 'Jane · CC BY'));
    r.addPhoto(photo('rejected', DateTime(2026, 9, 21), [cand('cup')],
        rejected: ['cup']));
    r.addPhoto(photo('guess', DateTime(2026, 9, 21),
        [cand('cup', inferred: true)]));

    final e = r.addWord(word: 'cup', pos: 'noun', meaning: '杯子');
    final occ = r.occurrencesOf(e.id);
    expect(occ.map((o) => o.photoId), ['new']);
    expect(occ.single.contextOnly, isTrue);
    expect(occ.single.fromImport, isTrue);
    expect(occ.single.anchor.x, 0.3);
    // Not one of the photo's listed labels.
    expect(r.visibleLabels('new'), isEmpty);
  });

  test('parts of speech must agree when both sides have one', () {
    final r = repo();
    r.addPhoto(photo('p', testNow, [cand('fly', pos: 'verb')]));
    final e = r.addWord(word: 'fly', pos: 'noun', meaning: '蒼蠅');
    expect(r.occurrencesOf(e.id), isEmpty);
  });

  test('a saved label on an own photo counts too', () {
    final r = repo();
    r.addPhoto(photo('p', testNow, [cand('kettle')]));
    r.savePhotoWords('p', [ListedWord(cand('kettle'), cand('kettle').point)],
        difficultyOffset: 0);
    r.addPhoto(photo('q', DateTime(2026, 9, 1), [cand('teapot')]));
    final created = r.addDeckWords([
      (word: 'teapot', pos: 'noun', level: 'A2'),
      (word: 'stove', pos: 'noun', level: 'A2'),
    ]);
    final teapot = created.firstWhere((e) => e.word == 'teapot');
    final stove = created.firstWhere((e) => e.word == 'stove');
    expect(r.occurrencesOf(teapot.id).single.photoId, 'q');
    expect(r.occurrencesOf(stove.id), isEmpty);
  });

  test('removing the deck takes the imported word and its photo label out',
      () {
    final r = repo();
    r.addPhoto(photo('p', testNow, [cand('teapot'), cand('kettle')]));
    final created = r.addDeckWords([(word: 'teapot', pos: 'noun', level: null)]);
    final id = created.single.id;
    expect(r.occurrencesOf(id), hasLength(1));

    r.removeDeckContent(wordEntryIds: [id]);
    expect(r.entry(id), isNull);
    expect(r.occurrencesInPhoto('p'), isEmpty);
    expect(r.photo('p'), isNotNull, reason: 'the learner\'s photo stays');
  });

  test('a reviewed or hand-placed word keeps its photo when the deck goes',
      () {
    final r = repo();
    r.addPhoto(photo('p', testNow, [cand('teapot')]));
    final id = r.addDeckWords([(word: 'teapot', pos: 'noun', level: null)])
        .single
        .id;
    // Placed on the photo's list by the learner: their label now.
    r.savePhotoWords('p', [ListedWord(cand('teapot'), cand('teapot').point)],
        difficultyOffset: 0);
    expect(r.occurrencesOf(id).single.fromImport, isFalse);
    r.removeDeckContent(wordEntryIds: [id]);
    expect(r.entry(id), isNotNull);
  });

  test('saving a never-saved photo keeps the imported word on it', () {
    final r = repo();
    // Shown as a form: 照片詳情 would not keep it as a context by itself.
    r.addPhoto(photo('p', testNow,
        [cand('teapots', lemma: 'teapot'), cand('kettle'), cand('mug')]));
    final id = r.addWord(word: 'teapot', pos: 'noun', meaning: '茶壺').id;
    expect(r.photo('p')!.wordsSavedAt, isNull);

    final s = PhotoWordSession(repo: r, photoId: 'p');
    expect(s.words.map((w) => w.word), isNot(contains('teapot')));
    expect(s.words, isNotEmpty);
    s.save();
    expect(r.photo('p')!.wordsSavedAt, isNotNull);
    expect(r.occurrencesOf(id), hasLength(1));
    // Reopening and saving again still keeps it.
    PhotoWordSession(repo: r, photoId: 'p').save();
    r.savePhotoWords('p', const [], difficultyOffset: 0);
    expect(r.occurrencesOf(id).single.contextOnly, isTrue);
  });

  test('the import flag survives a store round trip', () {
    const o = PhotoOccurrence(
        id: 'o',
        photoId: 'p',
        wordEntryId: 'w',
        anchor: LabelPoint(0.1, 0.2),
        contextOnly: true,
        fromImport: true);
    expect(PhotoOccurrence.fromJson(o.toJson()).fromImport, isTrue);
    expect(
        PhotoOccurrence.fromJson(o.copyWith(fromImport: false).toJson())
            .fromImport,
        isFalse);
  });
}
