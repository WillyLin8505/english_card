import 'dart:io';
import 'dart:convert';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/services/fsrs_optimizer.dart';
import 'package:photo_english_app/services/fsrs_scheduler.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_database_store.dart';

// Ground truth is a slower learner. Logs are produced by the default scheduler,
// while Bernoulli outcomes come from an independent latent memory trajectory.
List<ReviewLog> simulatedLogs(
    {int seed = 32, int cards = 100, int reviews = 16}) {
  final rng = Random(seed);
  final truthWeights = [...FsrsParameters.defaultWeights];
  for (final i in [0, 1, 2, 3, 11]) {
    truthWeights[i] *= 0.45;
  }
  truthWeights[8] *= 0.65;
  final truth = FsrsScheduler(FsrsParameters(w: truthWeights));
  const actual = FsrsScheduler();
  final logs = <ReviewLog>[];
  for (var c = 0; c < cards; c++) {
    var now = DateTime.utc(2024, 1, 1);
    var latent = FsrsState.initial, state = FsrsState.initial;
    for (var j = 0; j < reviews; j++) {
      final p = truth.retrievability(latent, now) ?? 1;
      final rating = rng.nextDouble() > p
          ? Rating.again
          : [
              Rating.hard,
              Rating.good,
              Rating.good,
              Rating.easy
            ][rng.nextInt(4)];
      final next = actual.next(state, rating, now);
      logs.add(ReviewLog(
          cardId: 'c${c.toString().padLeft(3, '0')}',
          reviewedAt: now,
          rating: rating,
          before: state,
          after: next.state,
          elapsedDays: next.elapsedDays,
          scheduledDays: next.scheduledDays));
      latent = truth.next(latent, rating, now).state;
      state = next.state;
      now = now.add(Duration(days: 2 + rng.nextInt(25)));
    }
  }
  return logs;
}

void main() {
  final logs = simulatedLogs();
  late FsrsOptimization fitted;

  test('independent holdout improves log loss and RMSE', () {
    fitted = FsrsOptimizer.optimize(logs)!;
    expect(fitted.effectiveReviews, 1500);
    expect(fitted.fitted.logLoss, lessThan(fitted.baseline.logLoss));
    expect(fitted.fitted.rmse, lessThanOrEqualTo(fitted.baseline.rmse));
    expect(FsrsOptimizer.validate(fitted, logs), isTrue);
    // A third, independently generated dataset was never used by fitting or
    // acceptance. This measures generalisation beyond the adoption holdout.
    final unseen = FsrsOptimizer.histories(simulatedLogs(seed: 3201));
    final baseline =
        FsrsOptimizer.evaluate(unseen, FsrsParameters.defaultWeights);
    final personalized = FsrsOptimizer.evaluate(unseen, fitted.weights);
    expect(personalized.logLoss, lessThan(baseline.logLoss));
    expect(personalized.rmse, lessThan(baseline.rmse));
    // ignore: avoid_print
    print('CARD32_EVALUATION ${jsonEncode({
          'validationDefault': fitted.baseline.toJson(),
          'validationPersonalized': fitted.fitted.toJson(),
          'unseenDefault': baseline.toJson(),
          'unseenPersonalized': personalized.toJson(),
          'weights': fitted.weights
        })}');
  });

  test('below threshold preserves exact default scheduling', () async {
    final small = simulatedLogs(cards: 26); // 390 effective recalls
    expect(FsrsOptimizer.optimize(small), isNull);
    final repo = WordDatabaseRepository(reviewLogs: small);
    await repo.flush();
    expect(repo.scheduler.params.w, FsrsParameters.defaultWeights);
    final state = small.last.after;
    final now = state.lastReview!.add(const Duration(days: 10));
    expect(repo.scheduler.next(state, Rating.good, now).state.toJson(),
        const FsrsScheduler().next(state, Rating.good, now).state.toJson());
    repo.dispose();
  });

  test(
      'bad histories, duplicate events, same-day and assisted recalls do not qualify',
      () {
    expect(FsrsOptimizer.optimize([...logs, ...logs]), isNull);
    final assisted = logs
        .map((r) => ReviewLog.fromJson({...r.toJson(), 'hintCount': 1}))
        .toList();
    expect(FsrsOptimizer.optimize(assisted), isNull);
    final broken = logs
        .map((r) => ReviewLog.fromJson({...r.toJson(), 'elapsedDays': -1}))
        .toList();
    expect(FsrsOptimizer.optimize(broken), isNull);
    expect(FsrsOptimizer.validWeights(List.filled(19, double.nan)), isFalse);
    expect(FsrsOptimizer.validWeights(List.filled(19, 1000)), isFalse);
    expect(FsrsOptimization.decode({'version': 999}), isNull);
    expect(
        FsrsOptimizer.acceptable(
            const FsrsMetrics(100, .4, .3), const FsrsMetrics(100, .5, .2)),
        isFalse);
    expect(
        FsrsOptimizer.acceptable(
            const FsrsMetrics(100, .4, .3), const FsrsMetrics(100, .3, .4)),
        isFalse);
  });

  test('same-day repetitions and one-card histories cannot enable fitting', () {
    final rows = <ReviewLog>[];
    var state = FsrsState.initial;
    var now = DateTime.utc(2024);
    for (var i = 0; i < 500; i++) {
      final next = const FsrsScheduler().next(state, Rating.again, now);
      rows.add(ReviewLog(
          cardId: 'one',
          reviewedAt: now,
          rating: Rating.again,
          before: state,
          after: next.state,
          elapsedDays: next.elapsedDays,
          scheduledDays: next.scheduledDays));
      state = next.state;
      now = now.add(const Duration(minutes: 1));
    }
    expect(FsrsOptimizer.count(FsrsOptimizer.histories(rows)), 0);
    expect(FsrsOptimizer.optimize(rows), isNull);
    expect(
        FsrsOptimizer.optimize(simulatedLogs(cards: 1, reviews: 450)), isNull);
  });

  test('a saved default or worse model is rejected despite forged metrics',
      () async {
    final fake = FsrsOptimization(
        FsrsParameters.defaultWeights,
        1500,
        const FsrsMetrics(300, .9, .9),
        const FsrsMetrics(300, .01, .01),
        DateTime.now());
    expect(FsrsOptimizer.validate(fake, logs), isFalse);
    final repo =
        WordDatabaseRepository(reviewLogs: logs, fsrsOptimization: fake);
    await repo.flush();
    expect(repo.fsrsOptimization, isNull);
    expect(repo.scheduler.params.w, FsrsParameters.defaultWeights);
    repo.dispose();
  });

  test('automatic fit, Hive restart, retention and logs remain intact',
      () async {
    final dir = await Directory('build').createTemp('card32-hive-test-');
    Hive.init(dir.path);
    final store = await HiveWordDatabaseStore.open(language: 'fr');
    // Isolated test database; no user ReviewLog is read or changed.
    for (final log in logs) {
      await store.addReviewLog(log);
    }
    final last = logs.last;
    final card = LearningCard(
        id: last.cardId,
        wordEntryId: 'word',
        templateId: 't',
        fsrs: last.after);
    await store.putCard(card);
    final repo = WordDatabaseRepository.fromData(store.load(), store: store);
    await repo.flush();
    expect(repo.fsrsOptimization, isNotNull);
    expect(repo.scheduler.params.w, isNot(FsrsParameters.defaultWeights));
    expect(repo.card(card.id)!.fsrs.due, card.fsrs.due);
    expect(repo.card(card.id)!.fsrs.stability, isNot(card.fsrs.stability));
    final prediction =
        repo.previewReview(card.id)[Rating.good]!.state.stability;
    final expected = repo.scheduler
        .next(repo.card(card.id)!.fsrs, Rating.good, repo.clock())
        .state
        .stability;
    expect(prediction, expected);
    repo.setDesiredRetention(.85);
    expect(repo.scheduler.params.w, repo.fsrsOptimization!.weights);
    expect(repo.scheduler.params.desiredRetention, .85);
    final saved = repo.fsrsOptimization!.toJson();
    repo.dispose();
    await Hive.close();
    Hive.init(dir.path);
    final reopened = await HiveWordDatabaseStore.open(language: 'fr');
    final data = reopened.load();
    final storedJson =
        data.reviewLogs.map((l) => jsonEncode(l.toJson())).toList()..sort();
    final originalJson = logs.map((l) => jsonEncode(l.toJson())).toList()
      ..sort();
    expect(storedJson, originalJson);
    expect(data.fsrsOptimization!.toJson(), saved);
    final restored = WordDatabaseRepository.fromData(data, store: reopened);
    await restored.flush();
    expect(restored.fsrsOptimization!.toJson(), saved);
    restored.dispose();
    final english = await HiveWordDatabaseStore.open();
    expect(english.load().fsrsOptimization, isNull);
    await Hive.close();
    // Keep test artifacts in build/; never delete existing data.
  });

  test('crossing 400 effective reviews automatically optimizes', () async {
    final rows = simulatedLogs(cards: 100, reviews: 5);
    final last = rows.last;
    final repo = WordDatabaseRepository(
      reviewLogs: rows.sublist(0, rows.length - 1),
      cards: [
        LearningCard(
            id: last.cardId,
            wordEntryId: 'w',
            templateId: 't',
            fsrs: last.before)
      ],
      clock: () => last.reviewedAt,
    );
    await repo.flush();
    expect(repo.fsrsOptimization, isNull);
    repo.review(last.cardId, last.rating);
    await repo.flush();
    expect(repo.fsrsOptimization, isNotNull);
    expect(repo.scheduler.params.w, repo.fsrsOptimization!.weights);
    repo.dispose();
  });

  test('invalid saved model and persistence failure fall back to defaults',
      () async {
    final bad = FsrsOptimization(
        List.filled(19, 1000),
        1500,
        const FsrsMetrics(300, .5, .5),
        const FsrsMetrics(300, .1, .1),
        DateTime.now());
    final repo =
        WordDatabaseRepository(reviewLogs: logs, fsrsOptimization: bad);
    await repo.flush();
    expect(repo.fsrsOptimization, isNull);
    expect(repo.scheduler.params.w, FsrsParameters.defaultWeights);
    repo.dispose();
    Hive.init(
        (await Directory('build').createTemp('card32-failure-test-')).path);
    final closed = await HiveWordDatabaseStore.open();
    await Hive.close();
    final failed = WordDatabaseRepository(reviewLogs: logs, store: closed);
    await failed.flush();
    expect(failed.fsrsOptimization, isNull);
    expect(failed.scheduler.params.w, FsrsParameters.defaultWeights);
    failed.dispose();
  });

  test('a next-morning recall logged as 0 days (24-hour count) still counts',
      () {
    const scheduler = FsrsScheduler();
    final evening = DateTime(2026, 9, 1, 20);
    final first = scheduler.next(FsrsState.initial, Rating.good, evening);
    final morning = DateTime(2026, 9, 2, 8);
    final second = scheduler.next(first.state, Rating.good, morning);
    ReviewLog log(int elapsed) => ReviewLog(
        cardId: 'c',
        reviewedAt: morning,
        rating: Rating.good,
        before: first.state,
        after: second.state,
        elapsedDays: elapsed,
        scheduledDays: second.scheduledDays);
    expect(FsrsOptimizer.effective(log(0)), isTrue, reason: 'legacy log');
    expect(FsrsOptimizer.effective(log(1)), isTrue);
    expect(second.elapsedDays, 1);
  });
}
