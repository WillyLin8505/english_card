import 'dart:math' as math;

import '../models/learning_card.dart';

/// FSRS-5 parameters. [defaults] are the published FSRS-5 defaults — spec
/// section 3: "初期使用預設參數；累積足夠有效複習紀錄後，才啟用個人化參數
/// 最佳化" (optimisation from ReviewLogs isn't built yet).
class FsrsParameters {
  final List<double> w;

  /// 期望記憶率 (UserLearningSettings); intervals aim to review a card when
  /// its recall probability has dropped to this.
  final double desiredRetention;
  final int maximumInterval;

  const FsrsParameters({
    this.w = defaultWeights,
    this.desiredRetention = 0.9,
    this.maximumInterval = 36500,
  });

  static const defaultWeights = <double>[
    0.40255, 1.18385, 3.173, 15.69105, 7.1949, 0.5345, 1.4604, 0.0046, //
    1.54575, 0.1192, 1.01925, 1.9395, 0.11, 0.29605, 2.2698, 0.2315, //
    2.9898, 0.51655, 0.6621,
  ];
}

class SchedulingResult {
  final FsrsState state;
  final int elapsedDays;

  const SchedulingResult(this.state, this.elapsedDays);

  int get scheduledDays => state.scheduledDays;
}

/// The FSRS-5 memory model (same formulas as the reference py-fsrs 5 /
/// ts-fsrs 4), in "long-term" mode: every grade schedules at least one
/// day ahead — there are no minute-level learning steps. That matches
/// the spec's low-pressure tone (no "come back in 10 minutes") and keeps
/// reviews at most once per card per day in normal use.
///
/// Intervals are kept in grade order (Again < Hard < Good < Easy) so the
/// four buttons never show the same number, as ts-fsrs does.
///
/// State labels: a new card graded Again becomes Learning, a review card
/// graded Again becomes Relearning (both read 學習中 in the UI); any
/// other grade leaves the card in Review.
class FsrsScheduler {
  static const algorithmVersion = 'fsrs-5';
  static const _decay = -0.5;
  static final double _factor =
      math.pow(0.9, 1 / _decay).toDouble() - 1; // 19/81

  final FsrsParameters params;

  const FsrsScheduler([this.params = const FsrsParameters()]);

  List<double> get _w => params.w;

  /// Probability of recalling the card at [now]; null for a new card.
  double? retrievability(FsrsState s, DateTime now) {
    final last = s.lastReview;
    if (s.state == FsrsCardState.newCard || last == null || s.stability <= 0) {
      return null;
    }
    return _forgettingCurve(_elapsedDays(last, now).toDouble(), s.stability);
  }

  /// All four outcomes, for showing each button's next interval.
  Map<Rating, SchedulingResult> preview(FsrsState s, DateTime now) {
    final raw = {for (final r in Rating.values) r: _nextMemory(s, r, now)};
    final ivl = {
      for (final r in Rating.values) r: _nextInterval(raw[r]!.stability),
    };
    // Keep the buttons in order.
    ivl[Rating.again] = math.min(ivl[Rating.again]!, ivl[Rating.hard]!);
    ivl[Rating.hard] = math.max(ivl[Rating.hard]!, ivl[Rating.again]! + 1);
    ivl[Rating.good] = math.max(ivl[Rating.good]!, ivl[Rating.hard]! + 1);
    ivl[Rating.easy] = math.max(ivl[Rating.easy]!, ivl[Rating.good]! + 1);

    final elapsed = s.lastReview == null ? 0 : _elapsedDays(s.lastReview!, now);
    return {
      for (final r in Rating.values)
        r: SchedulingResult(
          FsrsState(
            state: _nextCardState(s.state, r),
            stability: raw[r]!.stability,
            difficulty: raw[r]!.difficulty,
            due: now.add(Duration(days: ivl[r]!)),
            lastReview: now,
            scheduledDays: ivl[r]!,
            reps: s.reps + 1,
            lapses: s.lapses +
                (r == Rating.again && s.state != FsrsCardState.newCard ? 1 : 0),
            algorithmVersion: algorithmVersion,
          ),
          elapsed,
        ),
    };
  }

  SchedulingResult next(FsrsState s, Rating rating, DateTime now) =>
      preview(s, now)[rating]!;

  FsrsCardState _nextCardState(FsrsCardState from, Rating r) {
    if (r != Rating.again) return FsrsCardState.review;
    return from == FsrsCardState.newCard
        ? FsrsCardState.learning
        : FsrsCardState.relearning;
  }

  ({double stability, double difficulty}) _nextMemory(
    FsrsState s,
    Rating r,
    DateTime now,
  ) {
    final last = s.lastReview;
    if (s.state == FsrsCardState.newCard || last == null || s.stability <= 0) {
      return (
        stability: _initialStability(r),
        difficulty: _clampD(_initialDifficulty(r)),
      );
    }
    final elapsed = _elapsedDays(last, now);
    final double stability;
    if (elapsed < 1) {
      stability = _shortTermStability(s.stability, r);
    } else {
      final retr = _forgettingCurve(elapsed.toDouble(), s.stability);
      stability = r == Rating.again
          ? _forgetStability(s.difficulty, s.stability, retr)
          : _recallStability(s.difficulty, s.stability, retr, r);
    }
    return (
      stability: math.max(stability, 0.01),
      difficulty: _nextDifficulty(s.difficulty, r),
    );
  }

  static int _elapsedDays(DateTime last, DateTime now) =>
      math.max(0, now.difference(last).inDays);

  double _forgettingCurve(double elapsedDays, double stability) =>
      math.pow(1 + _factor * elapsedDays / stability, _decay).toDouble();

  int _nextInterval(double stability) {
    final ivl = stability /
        _factor *
        (math.pow(params.desiredRetention, 1 / _decay) - 1);
    return ivl.round().clamp(1, params.maximumInterval);
  }

  double _initialStability(Rating r) => math.max(_w[r.value - 1], 0.01);

  double _initialDifficulty(Rating r) =>
      _w[4] - math.exp(_w[5] * (r.value - 1)) + 1;

  double _clampD(double d) => d.clamp(1.0, 10.0);

  double _nextDifficulty(double d, Rating r) {
    final delta = -_w[6] * (r.value - 3);
    final damped = d + delta * (10 - d) / 9;
    final reverted =
        _w[7] * _initialDifficulty(Rating.easy) + (1 - _w[7]) * damped;
    return _clampD(reverted);
  }

  double _recallStability(double d, double s, double retr, Rating r) {
    final hardPenalty = r == Rating.hard ? _w[15] : 1.0;
    final easyBonus = r == Rating.easy ? _w[16] : 1.0;
    return s *
        (1 +
            math.exp(_w[8]) *
                (11 - d) *
                math.pow(s, -_w[9]) *
                (math.exp((1 - retr) * _w[10]) - 1) *
                hardPenalty *
                easyBonus);
  }

  double _forgetStability(double d, double s, double retr) {
    final longTerm = _w[11] *
        math.pow(d, -_w[12]) *
        (math.pow(s + 1, _w[13]) - 1) *
        math.exp((1 - retr) * _w[14]);
    final shortTerm = s / math.exp(_w[17] * _w[18]);
    return math.min(longTerm, shortTerm);
  }

  /// Same-day re-review (FSRS-5's short-term stability).
  double _shortTermStability(double s, Rating r) =>
      s * math.exp(_w[17] * (r.value - 3 + _w[18]));
}
