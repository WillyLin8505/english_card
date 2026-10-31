import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'helpers.dart';

WordDatabaseRepository ratingRepo() {
  WordEntry word(String word) => WordEntry.fromUserInput(
              id: word,
              word: word,
              pos: 'noun',
              meaning: '測試$word',
              level: 'A1',
              now: testNow)
          .copyWith(examples: [
        WordExample(text: 'This is a $word.', translation: '測試句意')
      ]);
  final entries = [
    for (final w in ['apple', 'cup', 'book']) word(w)
  ];
  // Two more labelled words on every photo (no cards): a drag question
  // always places three labels.
  final others = [
    for (final w in ['plate', 'spoon']) word(w)
  ];
  return WordDatabaseRepository(clock: () => testNow, entries: [
    ...entries,
    ...others
  ], cards: [
    for (final e in entries)
      LearningCard(
          id: LearningCard.idFor(e.id), wordEntryId: e.id, templateId: 'test')
  ], photos: [
    for (final e in entries)
      Photo(
          id: 'p-${e.id}',
          title: 'test',
          takenAt: testNow,
          createdAt: testNow,
          assetPath: 'assets/sample/photo_kitchen.jpg')
  ], occurrences: [
    for (final e in entries) ...[
      PhotoOccurrence(
          id: 'o-${e.id}',
          photoId: 'p-${e.id}',
          wordEntryId: e.id,
          anchor: const LabelPoint(.5, .5)),
      for (final (i, o) in others.indexed)
        PhotoOccurrence(
            id: 'o-${e.id}-${o.id}',
            photoId: 'p-${e.id}',
            wordEntryId: o.id,
            anchor: LabelPoint(.2 + .5 * i, .8)),
    ]
  ]);
}

void main() {
  test(
      'photo recall and drag wait for a loaded image; photo choice does not',
      () {
    final repo = ratingRepo();
    final session = FlashcardSession(repo);
    final guarded = <ReviewExerciseType>{};
    var steps = 0;
    while (!session.finished && steps++ < 20) {
      final type = session.exercise!.type;
      session.guardPhoto();
      if (type == ReviewExerciseType.photoChoice ||
          type == ReviewExerciseType.photoRecall ||
          type == ReviewExerciseType.imageDrag) {
        guarded.add(type);
        if (type == ReviewExerciseType.imageDrag) {
          // Always three labels, one of them this card's word.
          final x = session.exercise!;
          expect(x.targets, hasLength(FlashcardSession.dragTargets));
          expect(x.targets.map((t) => t.word), contains(x.answer));
        }
        // 卡 #901: photo choice is words, tappable before the picture loads.
        if (type != ReviewExerciseType.photoChoice) {
          final attempt = session.photoAttempt;
          session.showAnswer();
          session.submitAnswer(session.exercise!.answer);
          session.completeInteraction(correct: true, attempts: 1);
          expect(session.showingBack, isFalse);
          expect(session.attempts, 0);
          session.reportPhotoState(attempt, false);
          expect(session.photoFailed, isTrue);
          session.reportPhotoState(attempt, true);
        } else {
          expect(session.canAnswer, isTrue);
        }
      }
      session.showAnswer();
      session.rate(Rating.again);
    }
    expect(guarded, {
      ReviewExerciseType.photoChoice,
      ReviewExerciseType.photoRecall,
      ReviewExerciseType.imageDrag
    });
    expect(session.finished, isTrue);
    session.dispose();
  });
  for (final (correct, grade) in [
    (true, Rating.hard),
    (true, Rating.good),
    (true, Rating.easy),
    (false, Rating.good)
  ]) {
    testWidgets(
        'photo choice preview matches actual schedule: correct=$correct grade=$grade',
        (tester) async {
      final repo = ratingRepo();
      await pumpApp(tester, repository: repo, initialTab: AppTab.review);
      await tester.tap(find.text('綜合'));
      await tester.pumpAndSettle();
      var front = tester.widget<FlashcardFront>(find.byType(FlashcardFront));
      await tester.enterText(find.byType(TextField), front.entry.word);
      await tester.tap(find.byTooltip('送出答案'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('記得'));
      await tester.pumpAndSettle();
      front = tester.widget<FlashcardFront>(find.byType(FlashcardFront));
      final s = front.session!;
      expect(s.exercise!.type, ReviewExerciseType.photoChoice);
      final id = s.card!.id;
      await tester.runAsync(() => precacheImage(
          const AssetImage('assets/sample/photo_kitchen.jpg'),
          tester.element(find.byType(FlashcardFront))));
      await tester.pumpAndSettle();
      expect(s.canAnswer, isTrue);
      final answer = correct
          ? s.exercise!.answer
          : s.exercise!.options.firstWhere((o) => o != s.exercise!.answer);
      await tester.tap(find.text(displayWord(answer)));
      await tester.pumpAndSettle();
      final preview =
          tester.widget<RatingBar>(find.byType(RatingBar)).previews[grade]!;
      await tester.tap(find.text(grade.labelIn('zh-TW')));
      await tester.pumpAndSettle();
      final log = repo.logsOf(id).single;
      expect(log.requestedRating, grade);
      expect(ReviewLog.fromJson(log.toJson()).requestedRating, grade);
      expect(log.scheduledDays, preview.scheduledDays);
      expect(log.after.due, preview.state.due);
      expect(log.after.stability, preview.state.stability);
      expect(log.rating,
          correct && grade.value > 2 ? Rating.values[grade.index - 1] : grade);
    });
  }
}
