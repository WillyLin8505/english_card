import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';
import 'package:in_app_review/in_app_review.dart';

/// Card #915: asks for an App Store / Play rating at a good moment.
///
/// Everyone gets the same system dialog: we never ask "do you like it?"
/// first and route only happy people to the store. Unhappy learners use
/// 設定 → 意見回饋, which stays where it is. The OS limits how often the
/// dialog really shows; on top of that we ask at most once per app version.
class RatingPrompt {
  RatingPrompt._(this._box, this._request);

  /// Keep in step with `version:` in pubspec.yaml (without the build number).
  static const appVersion = '1.0.0';
  static const minInstallDays = 7;
  static const minActiveDays = 3;

  static const _boxName = 'rating_prompt';
  static RatingPrompt? _instance;

  /// Null until [open] ran (widget tests): callers then simply skip.
  static RatingPrompt? get instance => _instance;

  final Box<String>? _box;
  final Future<void> Function() _request;
  final _memory = <String, String>{};

  static Future<RatingPrompt> open() async {
    final box = await Hive.openBox<String>(_boxName);
    return _instance = RatingPrompt._(box, _systemRequest);
  }

  @visibleForTesting
  static RatingPrompt forTest(
          Box<String>? box, Future<void> Function() request) =>
      RatingPrompt._(box, request);

  @visibleForTesting
  static set testInstance(RatingPrompt? p) => _instance = p;

  static Future<void> _systemRequest() async {
    final review = InAppReview.instance;
    if (await review.isAvailable()) await review.requestReview();
  }

  String? _get(String k) => _box?.get(k) ?? _memory[k];
  Future<void> _put(String k, String v) async {
    _memory[k] = v;
    await _box?.put(k, v);
  }

  static String _day(DateTime t) =>
      '${t.year}-${t.month.toString().padLeft(2, '0')}-${t.day.toString().padLeft(2, '0')}';

  List<String> get _days {
    final s = _get('days') ?? '';
    return s.isEmpty ? <String>[] : s.split(',');
  }

  /// Call at app start: remembers the first launch and each day of use.
  Future<void> noteUse([DateTime? now]) async {
    final t = now ?? DateTime.now();
    if (_get('installedAt') == null) {
      await _put('installedAt', t.toIso8601String());
    }
    final today = _day(t);
    final days = _days;
    if (!days.contains(today)) await _put('days', [...days, today].join(','));
  }

  /// The rules, separate from the side effect so they can be tested.
  bool shouldAsk(DateTime now) {
    if (_get('askedVersion') == appVersion) return false;
    final installed = DateTime.tryParse(_get('installedAt') ?? '');
    if (installed == null) return false;
    if (now.difference(installed).inDays < minInstallDays) return false;
    return _days.length >= minActiveDays;
  }

  /// Call right after a review run is finished (never while reviewing).
  /// Returns true when the system dialog was requested.
  Future<bool> onReviewCompleted([DateTime? now]) async {
    final t = now ?? DateTime.now();
    await noteUse(t);
    if (!shouldAsk(t)) return false;
    await _put('askedVersion', appVersion);
    try {
      await _request();
    } catch (_) {
      // Best effort: the dialog is optional.
    }
    return true;
  }
}
