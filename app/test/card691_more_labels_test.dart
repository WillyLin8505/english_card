// 問題回報 #691 (owner 2026-10-24): 「檢視為什麼標籤這麼少，沒有到標準」.
// App-side causes found and fixed:
// - an all-noun pool stayed at three labels (the noun cap) even after the
//   recognizer had been asked for verbs and had none;
// - a list short of five because the pool's other words are learned or
//   studied elsewhere never asked the recognizer for more;
// - a photo saved with fewer than five labels was never filled up again.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_selector.dart';

import 'helpers.dart';

WordCandidate _c(String word, {String pos = 'noun', String level = 'A2'}) =>
    WordCandidate(
      word: word,
      pos: pos,
      meaning: '$word 義',
      level: level,
      levelSource: 'cefr-j',
      evidence: 'seen',
      point: const LabelPoint(0.5, 0.5),
      visualConfidence: 0.9,
      usefulness: 0.8,
    );

final _street = [
  _c('building'), _c('sign'), _c('cart'), _c('pavement'),
  _c('lantern'), _c('crowd'), _c('banner'), //
];

void main() {
  final profile = UserVocabularyProfile.start('A2', now: testNow);

  test('the noun cap gives way once the recognizer had its chance', () {
    final capped = const WordSelector()
        .select(pool: _street, target: 1, profile: profile, now: testNow);
    expect(capped.words, hasLength(WordSelector.maxNouns));
    expect(capped.topUp, 'actions');

    final relaxed = const WordSelector().select(
        pool: _street,
        target: 1,
        profile: profile,
        relaxNounCap: true,
        now: testNow);
    expect(relaxed.words, hasLength(WordSelector.maxWords));
  });

  test('short of five for any reason asks the recognizer for more', () {
    final sel = const WordSelector().select(
      pool: [
        _c('run', pos: 'verb'),
        _c('red', pos: 'adj.'),
        _c('cat'),
        _c('dog'),
        _c('sun'),
        _c('tree'),
      ],
      target: 1,
      profile: profile,
      studying: {'cat', 'dog', 'sun'},
      now: testNow,
    );
    expect(sel.words.length, lessThan(WordSelector.maxWords));
    expect(sel.topUp, isNotNull);
  });

  test('a photo saved with three labels is filled up when it opens again', () {
    final repo = WordDatabaseRepository(clock: () => testNow, profile: profile);
    final pool = [
      _c('building'),
      _c('walk', pos: 'verb'),
      _c('busy', pos: 'adj.'),
      _c('sign'),
      _c('cart'),
      _c('carry', pos: 'verb'),
    ];
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
    repo.savePhotoWords(
        'p1',
        [
          for (final c in pool.take(3)) ListedWord(c, c.point),
        ],
        difficultyOffset: 0);

    final session = PhotoWordSession(repo: repo, photoId: 'p1');
    addTearDown(session.dispose);
    final words = [for (final w in session.words) w.word];
    expect(words.take(3), ['building', 'walk', 'busy'],
        reason: 'the saved labels stay where they were');
    expect(words, hasLength(WordSelector.maxWords));
    expect(session.hasUnsavedChanges, isTrue);
  });
}
