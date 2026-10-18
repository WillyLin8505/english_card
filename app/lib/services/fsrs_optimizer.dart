import 'dart:math' as math;

import '../models/learning_card.dart';
import 'fsrs_scheduler.dart';

/// Conservative local FSRS-5 calibration. The spec gives no numeric threshold:
/// require 400 next-day recalls across 20 complete card histories, with both
/// outcomes in training and validation. First encounters and same-day repeats
/// update replay state but are not independent recall observations.
class FsrsOptimizer {
  static const minimumReviews = 400;
  static const minimumCards = 20;
  static const version = 1;

  // Deliberately narrow, positive bounds around the shipped defaults. This is
  // a bounded local calibration, not a replacement for the FSRS algorithm.
  static bool validWeights(List<double> w) =>
      w.length == 19 &&
      List.generate(19, (i) => i).every((i) =>
          w[i].isFinite &&
          w[i] >= FsrsParameters.defaultWeights[i] / 4 &&
          w[i] <= FsrsParameters.defaultWeights[i] * 4);

  static List<List<ReviewLog>> histories(List<ReviewLog> logs) {
    final grouped = <String, List<ReviewLog>>{};
    for (final log in logs) {
      grouped.putIfAbsent(log.cardId, () => []).add(log);
    }
    final result = <List<ReviewLog>>[];
    for (final id in grouped.keys.toList()..sort()) {
      final rows = grouped[id]!
        ..sort((a, b) => a.reviewedAt.compareTo(b.reviewedAt));
      if (id.isEmpty || rows.first.before.state != FsrsCardState.newCard) {
        continue;
      }
      var valid = true;
      for (var i = 0; i < rows.length; i++) {
        final r = rows[i];
        final elapsed = i == 0
            ? 0
            : calendarDaysBetween(rows[i - 1].reviewedAt, r.reviewedAt);
        // Logs written before calendar days counted 24-hour periods.
        final legacy =
            i == 0 ? 0 : r.reviewedAt.difference(rows[i - 1].reviewedAt).inDays;
        if ((r.elapsedDays != elapsed && r.elapsedDays != legacy) ||
            elapsed < 0 ||
            (i > 0 && !r.reviewedAt.isAfter(rows[i - 1].reviewedAt)) ||
            r.before.reps != i ||
            r.after.reps != i + 1 ||
            r.after.lastReview != r.reviewedAt ||
            (i > 0 && r.before.lastReview != rows[i - 1].reviewedAt) ||
            !r.before.stability.isFinite ||
            !r.after.stability.isFinite ||
            !r.before.difficulty.isFinite ||
            !r.after.difficulty.isFinite ||
            (i > 0 &&
                (r.before.stability <= 0 ||
                    r.before.difficulty < 1 ||
                    r.before.difficulty > 10)) ||
            r.after.stability <= 0 ||
            r.after.difficulty < 1 ||
            r.after.difficulty > 10 ||
            r.after.algorithmVersion != FsrsScheduler.algorithmVersion ||
            r.hintCount < 0 ||
            r.attempts < 1) {
          valid = false;
        }
      }
      if (valid) result.add(rows);
    }
    // Bound CPU cost without truncating individual card histories (which
    // would make the starting memory state dependent on old parameters).
    final bounded = <List<ReviewLog>>[];
    var rowsUsed = 0;
    for (final rows in result) {
      if (bounded.length == 500) break;
      if (rowsUsed + rows.length > 10000) continue;
      bounded.add(rows);
      rowsUsed += rows.length;
    }
    return bounded;
  }

  /// A next-day-or-later recall without help. Days are counted on the
  /// calendar from the review's own timestamps, so a next-morning review
  /// logged as 0 days (24-hour count) still counts.
  static bool effective(ReviewLog r) =>
      _elapsed(r) >= 1 && r.hintCount == 0 && r.attempts == 1;

  static int _elapsed(ReviewLog r) {
    final last = r.before.lastReview;
    return last == null
        ? r.elapsedDays
        : calendarDaysBetween(last, r.reviewedAt);
  }

  static int count(List<List<ReviewLog>> histories) =>
      histories.fold(0, (n, rows) => n + rows.where(effective).length);

  static bool diverse(List<List<ReviewLog>> histories) {
    final rows = histories.expand((r) => r).where(effective).toList();
    final failures = rows.where((r) => r.rating == Rating.again).length;
    return failures >= 10 && rows.length - failures >= 10;
  }

  static FsrsMetrics evaluate(List<List<ReviewLog>> histories, List<double> w) {
    final scheduler = FsrsScheduler(FsrsParameters(w: w));
    var loss = 0.0, squared = 0.0;
    var count = 0;
    for (final rows in histories) {
      var state = FsrsState.initial;
      for (final r in rows) {
        if (effective(r)) {
          final p = scheduler
              .retrievability(state, r.reviewedAt)!
              .clamp(1e-7, 1 - 1e-7);
          final y = r.rating == Rating.again ? 0.0 : 1.0;
          loss -= y * math.log(p) + (1 - y) * math.log(1 - p);
          squared += (p - y) * (p - y);
          count++;
        }
        state = scheduler.next(state, r.rating, r.reviewedAt).state;
        if (!state.stability.isFinite || state.stability > 1e9) {
          throw StateError('Unstable FSRS replay');
        }
      }
    }
    if (count == 0) throw StateError('No effective recalls');
    return FsrsMetrics(count, loss / count, math.sqrt(squared / count));
  }

  /// Hold out whole cards, not rows, to prevent correlated history leakage.
  /// The holdout is never used for choosing coordinates or step sizes.
  static FsrsOptimization? optimize(List<ReviewLog> logs) {
    try {
      final all = histories(logs);
      if (all.length < minimumCards || count(all) < minimumReviews) return null;
      final train = <List<ReviewLog>>[], validation = <List<ReviewLog>>[];
      for (var i = 0; i < all.length; i++) {
        (i % 5 == 0 ? validation : train).add(all[i]);
      }
      if (count(train) < 320 ||
          !diverse(train) ||
          !diverse(validation) ||
          count(validation) < 80) {
        return null;
      }
      var w = [...FsrsParameters.defaultWeights];
      var best = evaluate(train, w).logLoss;
      // Fit long-term stability parameters only. Difficulty and short-term
      // parameters remain default to limit overfitting on modest histories.
      for (final step in [0.5, 0.25, 0.125]) {
        for (final i in [0, 1, 2, 3, 8, 9, 10, 11, 13, 14, 15, 16]) {
          for (final direction in [-1, 1]) {
            final candidate = [...w];
            candidate[i] *= math.exp(step * direction);
            if (!validWeights(candidate)) continue;
            final loss = evaluate(train, candidate).logLoss;
            if (loss < best - 1e-8) {
              w = candidate;
              best = loss;
            }
          }
        }
      }
      final baseline = evaluate(validation, FsrsParameters.defaultWeights);
      final fitted = evaluate(validation, w);
      if (!acceptable(baseline, fitted)) return null;
      return FsrsOptimization(
          List.unmodifiable(w), count(all), baseline, fitted, DateTime.now());
    } catch (_) {
      return null;
    }
  }

  static bool acceptable(FsrsMetrics baseline, FsrsMetrics fitted) =>
      fitted.logLoss.isFinite &&
      fitted.rmse.isFinite &&
      fitted.logLoss < baseline.logLoss - 1e-6 &&
      fitted.rmse <= baseline.rmse;

  /// Treat disk metadata as untrusted; recompute its validation evidence.
  static bool validate(FsrsOptimization result, List<ReviewLog> logs) {
    try {
      if (!validWeights(result.weights)) return false;
      final all = histories(logs);
      if (all.length < minimumCards || count(all) < minimumReviews) {
        return false;
      }
      final holdout = [for (var i = 0; i < all.length; i += 5) all[i]];
      return count(holdout) >= 80 &&
          diverse(holdout) &&
          acceptable(evaluate(holdout, FsrsParameters.defaultWeights),
              evaluate(holdout, result.weights));
    } catch (_) {
      return false;
    }
  }
}

class FsrsMetrics {
  final int count;
  final double logLoss, rmse;
  const FsrsMetrics(this.count, this.logLoss, this.rmse);
  Map<String, dynamic> toJson() =>
      {'count': count, 'logLoss': logLoss, 'rmse': rmse};
  factory FsrsMetrics.fromJson(Map<String, dynamic> j) => FsrsMetrics(
      j['count'] as int,
      (j['logLoss'] as num).toDouble(),
      (j['rmse'] as num).toDouble());
}

class FsrsOptimization {
  final List<double> weights;
  final int effectiveReviews;
  final FsrsMetrics baseline, fitted;
  final DateTime updatedAt;
  const FsrsOptimization(this.weights, this.effectiveReviews, this.baseline,
      this.fitted, this.updatedAt);
  Map<String, dynamic> toJson() => {
        'version': FsrsOptimizer.version,
        'algorithm': FsrsScheduler.algorithmVersion,
        'weights': weights,
        'effectiveReviews': effectiveReviews,
        'baseline': baseline.toJson(),
        'fitted': fitted.toJson(),
        'updatedAt': updatedAt.toIso8601String(),
      };
  static FsrsOptimization? decode(Map<String, dynamic> j) {
    try {
      if (j['version'] != FsrsOptimizer.version ||
          j['algorithm'] != FsrsScheduler.algorithmVersion) {
        return null;
      }
      final w =
          (j['weights'] as List).map((v) => (v as num).toDouble()).toList();
      if (!FsrsOptimizer.validWeights(w)) return null;
      return FsrsOptimization(
          List.unmodifiable(w),
          j['effectiveReviews'] as int,
          FsrsMetrics.fromJson(j['baseline'] as Map<String, dynamic>),
          FsrsMetrics.fromJson(j['fitted'] as Map<String, dynamic>),
          DateTime.parse(j['updatedAt'] as String));
    } catch (_) {
      return null;
    }
  }
}

/// Optional capability so existing in-memory/test stores remain compatible.
abstract interface class FsrsOptimizationStore {
  Future<void> putFsrsOptimization(FsrsOptimization? result);
}
