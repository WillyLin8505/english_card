import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

WordDatabaseRepository ownedRepo({required bool photo, int candidates = 2,
    bool archived = false}) {
  final entries = [
    for (final (word, meaning) in [
      ('coat', '外套'),
      if (candidates >= 1) ('boat', '小船'),
      if (candidates >= 2) ('goat', '山羊'),
    ])
      WordEntry.fromUserInput(id: word, word: word, pos: 'noun',
          meaning: meaning, level: 'A1', now: testNow)
  ];
  entries[0] = entries[0].copyWith(related: const [
    RelatedWord('circuit card', RelationType.associated),
    RelatedWord('carte du jour', RelationType.associated),
    RelatedWord('boat', RelationType.associated),
    RelatedWord('goat', RelationType.associated),
  ]);
  return WordDatabaseRepository(clock: () => testNow, entries: entries,
      cards: [
        const LearningCard(id: 'coat-card', wordEntryId: 'coat', templateId: 'test'),
        if (archived)
          const LearningCard(id: 'goat-card', wordEntryId: 'goat',
              templateId: 'test', archived: true),
      ],
      photos: [if (photo) Photo(id: 'mine', title: 'Coat', takenAt: testNow,
          createdAt: testNow, assetPath: 'assets/photos/kitchen.jpg')],
      occurrences: [if (photo) const PhotoOccurrence(id: 'o', photoId: 'mine',
          wordEntryId: 'coat', anchor: LabelPoint(0.5, 0.5))]);
}

void main() {
  for (final photo in [false, true]) {
    test('wrong answer and repeated review keep the owned option set, photo=$photo', () {
      final repo = ownedRepo(photo: photo);
      final session = FlashcardSession(repo, random: Random(7));
      var checked = 0;
      for (var step = 0; step < 12 && !session.finished; step++) {
        final exercise = session.exercise!;
        final words = exercise.type == ReviewExerciseType.photoChoice
            ? exercise.options
            : exercise.pairs.map((p) => p.word).toList();
        if (words.isNotEmpty) {
          checked++;
          expect(words, hasLength(3));
          expect(words.toSet(), {'coat', 'boat', 'goat'});
          expect(words.where((w) => w == exercise.answer), hasLength(1));
        }
        session.completeInteraction(correct: false, attempts: 1);
        expect(identical(session.exercise, exercise), isTrue);
        session.rate(Rating.again);
      }
      expect(checked, greaterThan(1));
      session.dispose();
    });
  }
  for (final count in [0, 1, 2, 3]) {
    test('catalog drag excludes unowned labels, owned extras=$count', () {
      final lexicon = LexiconPack()..loadJson({
        'target_language': 'en', 'native_language': 'zh-TW',
        'lexemes': [
          for (final (id, name, meaning) in [(1, 'coat', '外套'), (2, 'boat', '小船'), (3, 'goat', '山羊')])
            {'id': id, 'lemma': name, 'normalized': name, 'pos': 'noun', 'status': 'full',
              'senses': [{'id': id * 10, 'native': meaning}]},
        ],
        'catalog_images': [{
          'id': 1, 'url': '/api/image?id=1', 'status': 'ready',
          'tags': [{'lexeme_id': 1, 'sense_id': 10, 'review_status': 'approved'}],
          'labels': [for (final id in [1, 2, 3])
            {'lexeme_id': id, 'point': [id * 0.2, 0.5]}],
        }],
      });
      final base = ownedRepo(photo: false, candidates: count);
      final repo = WordDatabaseRepository(clock: () => testNow,
        entries: base.entries,
        cards: [for (var i = 0; i < 5; i++)
          LearningCard(id: 'coat-$i', wordEntryId: 'coat', templateId: 'test'),
          if (count == 3) const LearningCard(id: 'archived-goat',
            wordEntryId: 'goat', templateId: 'test', archived: true)])
        ..linkLexicon(lexicon);
      final session = FlashcardSession(repo, lexicon: lexicon, random: Random(1));
      var dragCount = 0;
      while (!session.finished) {
        final exercise = session.exercise!;
        if (exercise.type == ReviewExerciseType.imageDrag) {
          dragCount++;
          expect(exercise.targets, hasLength(3));
          expect(exercise.targets.every((t) => repo.entryByWord(t.word) != null), isTrue);
        }
        session.showAnswer();
        session.rate(Rating.good);
      }
      expect(dragCount, count == 2 ? greaterThan(0) : 0);
      session.dispose();
    });
  }
  for (final photo in [false, true]) {
    test('owned candidates only, photo=$photo', () {
      // These words exist in the dictionary, but not in the personal library.
      final lexicon = LexiconPack()..loadJson({
        'target_language': 'en', 'native_language': 'zh-TW',
        'lexemes': [
          for (final word in ['circuit card', 'carte du jour'])
            {'id': word == 'circuit card' ? 99 : 100, 'lemma': word,
              'normalized': word, 'pos': 'noun', 'status': 'full',
              'senses': <Object>[]}
        ],
      });
      final repo = ownedRepo(photo: photo);
      final session = FlashcardSession(repo, lexicon: lexicon, random: Random(1));
      expect(session.exercise!.type, photo
          ? ReviewExerciseType.photoChoice : ReviewExerciseType.similarMatch);
      final words = photo ? session.exercise!.options
          : session.exercise!.pairs.map((p) => p.word).toList();
      expect(words.toSet(), {'coat', 'boat', 'goat'});
      expect(words.every((w) => repo.entryByWord(w) != null), isTrue);
      session.dispose();
    });

    for (final archived in [false, true]) {
      test('insufficient owned candidates skip type, photo=$photo archived=$archived', () {
        final repo = ownedRepo(photo: photo, candidates: archived ? 2 : 1,
            archived: archived);
        final session = FlashcardSession(repo, random: Random(1));
        expect(session.exercise?.type, isNot(ReviewExerciseType.photoChoice));
        expect(session.exercise?.type, isNot(ReviewExerciseType.similarMatch));
        // No safe exercise falls back to the traditional flip card rather
        // than skipping the card (問題回報 #207 decision A).
        if (!photo) {
          expect(session.exercise, isNull);
          expect(session.finished, isFalse);
        }
        expect(repo.logsOf('coat-card'), isEmpty);
        session.dispose();
      });
    }
  }
}
