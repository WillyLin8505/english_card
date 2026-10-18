import 'package:flutter/foundation.dart';

/// Where a background service (sync, queues — nothing with a BuildContext
/// of its own) reports a failure so it reaches the screen, instead of only
/// the debug log (問題回報 #175: 錯誤被默默吞掉). One active message at a
/// time, tagged by its reporting source, so an unrelated success doesn't
/// dismiss a still-failing source's message, and a source repeating the
/// same failure doesn't resend it on every retry.
class BackgroundErrors extends ChangeNotifier {
  static final instance = BackgroundErrors();

  String? message;
  Future<void> Function()? retry;
  Object? _source;

  /// Bumped on every new message so a listener can tell "still this one"
  /// apart from "a new one arrived with the same text".
  int version = 0;

  void report(Object source, String message, {Future<void> Function()? retry}) {
    if (_source == source && this.message == message) return;
    _source = source;
    this.message = message;
    this.retry = retry;
    version++;
    notifyListeners();
  }

  void clear(Object source) {
    if (_source != source) return;
    _source = null;
    message = null;
    retry = null;
    notifyListeners();
  }

  /// The learner dismissed or retried it from the banner itself: clear
  /// whichever source is currently showing, without needing its token.
  void dismiss() {
    if (message == null) return;
    _source = null;
    message = null;
    retry = null;
    notifyListeners();
  }
}
