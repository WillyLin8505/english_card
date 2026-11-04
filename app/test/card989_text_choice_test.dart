import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

WordDatabaseRepository frRepo({String language = 'fr', bool synonym = false}) {
  final words = [
    ('chat', 'cat'),
    ('chien', 'dog'),
    ('cheval', 'horse'),
    ('oiseau', 'bird'),
    if (synonym) ('minet', 'cat'),
  ];
  return WordDatabaseRepository(
      clock: () => testNow,
      language: language,
      entries: [
        for (final (w, m) in words)
          WordEntry.fromUserInput(
              id: w, word: w, pos: 'noun', meaning: m, level: 'A1', now: testNow)
      ],
      cards: const [
        LearningCard(id: 'chat-card', wordEntryId: 'chat', templateId: 't'),
      ]);
}

void main() {
  test('French card without picture gets a text choice with 4 options', () {
    final session = FlashcardSession(frRepo(), random: Random(1));
    final seen = <ReviewExerciseType>{};
    for (var i = 0; i < 6 && !session.finished; i++) {
      final x = session.exercise!;
      seen.add(x.type);
      if (x.type == ReviewExerciseType.textChoice) {
        expect(x.prompt, 'cat');
        expect(x.answer, 'chat');
        expect(x.options.toSet(), {'chat', 'chien', 'cheval', 'oiseau'});
        expect(x.options, hasLength(4));
        return;
      }
      session.completeInteraction(correct: false, attempts: 1);
      session.rate(session.ratingPreviews.keys.first);
    }
    fail('no textChoice among $seen');
  });

  test('synonym of the answer is never a distractor', () {
    final session = FlashcardSession(frRepo(synonym: true), random: Random(2));
    for (var i = 0; i < 8 && !session.finished; i++) {
      final x = session.exercise!;
      if (x.type == ReviewExerciseType.textChoice) {
        expect(x.options, isNot(contains('minet')));
        expect(x.options.toSet(), {'chat', 'chien', 'cheval', 'oiseau'});
      }
      session.completeInteraction(correct: false, attempts: 1);
      session.rate(session.ratingPreviews.keys.first);
    }
  });

  test('English cards never get a text choice', () {
    final session = FlashcardSession(frRepo(language: 'en'), random: Random(3));
    for (var i = 0; i < 8 && !session.finished; i++) {
      expect(session.exercise?.type, isNot(ReviewExerciseType.textChoice));
      session.completeInteraction(correct: false, attempts: 1);
      session.rate(session.ratingPreviews.keys.first);
    }
  });

  test('answering checks right and wrong', () {
    final session = FlashcardSession(frRepo(), random: Random(1));
    for (var i = 0; i < 6; i++) {
      if (session.exercise!.type == ReviewExerciseType.textChoice) break;
      session.completeInteraction(correct: false, attempts: 1);
      session.rate(session.ratingPreviews.keys.first);
    }
    expect(session.exercise!.type, ReviewExerciseType.textChoice);
    session.submitAnswer('chien');
    expect(session.answerCorrect, isFalse);
  });
}
