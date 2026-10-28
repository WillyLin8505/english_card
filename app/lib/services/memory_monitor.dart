import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:hive/hive.dart';

import '../widgets/mobile/photo_cache.dart';
import 'card_report.dart';
import 'feedback_context.dart';
import 'lexicon_pack.dart';

/// The app's memory use at one moment, in bytes (問題回報 #824).
/// [available] is what iOS still lets the app take before closing it
/// (os_proc_available_memory); 0 where there is no limit (the simulator).
/// [footprint] is the app's phys_footprint, -1 when unknown.
@immutable
class MemorySnapshot {
  final int available;
  final int footprint;

  const MemorySnapshot({required this.available, required this.footprint});

  static int mb(int bytes) => (bytes / (1024 * 1024)).round();

  int get availableMb => mb(available);
  int get footprintMb => mb(footprint);

  /// False on the simulator, which has no per-app limit.
  bool get hasLimit => available > 0;

  @override
  String toString() =>
      'MemorySnapshot(footprint: $footprintMb MB, available: $availableMb MB)';
}

/// Which screens have already sent a memory report today (問題回報 #824:
/// 同一畫面同一天只報一次). Keys are `<yyyy-mm-dd>|<screen>`.
abstract interface class MemoryReportLog {
  Future<bool> contains(String key);
  Future<void> add(String key, {required String today});
}

/// Kept in memory only: tests, and a phone where Hive cannot open the box.
class MemoryReportLogInMemory implements MemoryReportLog {
  final keys = <String>{};

  @override
  Future<bool> contains(String key) async => keys.contains(key);

  @override
  Future<void> add(String key, {required String today}) async {
    keys
      ..removeWhere((k) => !k.startsWith('$today|'))
      ..add(key);
  }
}

class _HiveMemoryReportLog implements MemoryReportLog {
  static const boxName = 'memory_reports';
  final _fallback = MemoryReportLogInMemory();
  Box<String>? _box;
  bool _opened = false;

  Future<Box<String>?> _open() async {
    if (_opened) return _box;
    _opened = true;
    try {
      _box = await Hive.openBox<String>(boxName);
    } catch (_) {}
    return _box;
  }

  @override
  Future<bool> contains(String key) async {
    final box = await _open();
    if (box == null) return _fallback.contains(key);
    return box.containsKey(key);
  }

  @override
  Future<void> add(String key, {required String today}) async {
    final box = await _open();
    if (box == null) return _fallback.add(key, today: today);
    try {
      // Only today's entries matter; older days are dropped.
      final old = [
        for (final k in box.keys)
          if (k is String && !k.startsWith('$today|')) k
      ];
      if (old.isNotEmpty) await box.deleteAll(old);
      await box.put(key, '1');
    } catch (_) {
      await _fallback.add(key, today: today);
    }
  }
}

/// 問題回報 #824: watches how close the app is to iOS's memory limit (a
/// 4 GB iPhone 12 closes it near ~2 GB; the simulator has no limit, so a
/// crash there never shows). Every [interval] while in the foreground, and
/// whenever Flutter passes on a memory warning, it asks the
/// `photo_english/memory` channel (ios/Runner/AppDelegate.swift) for the
/// numbers. Below [threshold] left, or on a warning, it sends one report
/// through the 意見回饋 path (CardReportService, POST /api/issues) titled
/// 「[記憶體] <畫面>」— at most one per screen per day. A warning also
/// drops caches that are rebuilt on demand ([releaseCaches]).
///
/// Off on the web, Android and in tests: there the channel is missing and
/// [start] does nothing.
class MemoryMonitor with WidgetsBindingObserver {
  static final instance = MemoryMonitor();

  /// Report when less than this is left (owner's suggestion, #824).
  static const threshold = 300 * 1024 * 1024;

  /// A memory warning is reported only below this much left (owner #906
  /// A): iOS also warns right after install or launch with gigabytes free
  /// (#900, 2.7 GB left), which is noise. Caches are dropped either way.
  static const warningReportBelow = 1024 * 1024 * 1024;

  /// How often the numbers are checked while the app is in the foreground.
  static const interval = Duration(seconds: 60);

  static const channelName = 'photo_english/memory';

  final MethodChannel _channel;
  final CardReportService? _service;
  final DateTime Function() _now;
  final MemoryReportLog _log;
  final String Function() _page;
  final bool? _enabledOverride;

  MemoryMonitor({
    MethodChannel? channel,
    CardReportService? service,
    DateTime Function()? now,
    MemoryReportLog? log,
    String Function()? page,
    bool? enabled,
  })  : _channel = channel ?? const MethodChannel(channelName),
        _service = service,
        _now = now ?? DateTime.now,
        _log = log ?? _HiveMemoryReportLog(),
        _page = page ?? (() => FeedbackContext.instance.page),
        _enabledOverride = enabled;

  CardReportService get service => _service ?? CardReportService.instance;

  /// The X-API-Key reports are sent with, like 意見回饋 (may be empty).
  String Function() apiKey = () => '';

  /// More caches to drop on a memory warning (the speaker's, …).
  final _releasers = <VoidCallback>[];

  void addReleaser(VoidCallback release) => _releasers.add(release);
  void removeReleaser(VoidCallback release) => _releasers.remove(release);

  Timer? _timer;
  bool _started = false;
  bool _channelMissing = false;
  Map<String, String>? _device;

  /// Only iOS has the channel.
  bool get enabled =>
      _enabledOverride ??
      (!kIsWeb && defaultTargetPlatform == TargetPlatform.iOS);

  @visibleForTesting
  bool get running => _timer != null;

  /// Starts watching; does nothing where the channel is missing.
  Future<void> start({String Function()? apiKey}) async {
    if (apiKey != null) this.apiKey = apiKey;
    if (_started || !enabled) return;
    if (await snapshot() == null) return;
    _started = true;
    WidgetsBinding.instance.addObserver(this);
    _schedule();
    unawaited(check());
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    if (_started) WidgetsBinding.instance.removeObserver(this);
    _started = false;
  }

  void _schedule() {
    _timer?.cancel();
    _timer = Timer.periodic(interval, (_) => unawaited(check()));
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _schedule();
      unawaited(check());
    } else if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden) {
      _timer?.cancel();
      _timer = null;
    }
  }

  @override
  void didHaveMemoryPressure() => unawaited(onMemoryWarning());

  /// The numbers now, or null without the channel (web, Android, tests).
  /// Also the debug hook a memory-budget test reads.
  Future<MemorySnapshot?> snapshot() async {
    if (_channelMissing) return null;
    try {
      final m = await _channel.invokeMapMethod<String, Object?>('snapshot');
      if (m == null) return null;
      return MemorySnapshot(
        available: (m['available'] as num?)?.toInt() ?? 0,
        footprint: (m['footprint'] as num?)?.toInt() ?? -1,
      );
    } on MissingPluginException {
      _channelMissing = true;
      return null;
    } catch (e) {
      debugPrint('MemoryMonitor: snapshot failed: $e');
      return null;
    }
  }

  Future<Map<String, String>> _deviceInfo() async {
    if (_device case final d?) return d;
    try {
      final m = await _channel.invokeMapMethod<String, Object?>('device');
      return _device = {
        for (final e in (m ?? const {}).entries)
          if (e.value != null) e.key: '${e.value}'
      };
    } catch (_) {
      return const {};
    }
  }

  /// Sends a report when less than [threshold] is left. Returns whether
  /// one was sent (or queued).
  Future<bool> check() async {
    final snap = await snapshot();
    if (snap == null || !snap.hasLimit || snap.available >= threshold) {
      return false;
    }
    return _report(warning: false, snap: snap);
  }

  /// A memory warning from iOS (via Flutter): drop rebuildable caches,
  /// then report. Returns whether a report was sent (or queued).
  Future<bool> onMemoryWarning() async {
    releaseCaches();
    if (!enabled) return false;
    final snap = await snapshot();
    if (snap == null) return false;
    if (snap.hasLimit && snap.available >= warningReportBelow) return false;
    return _report(warning: true, snap: snap);
  }

  /// Caches that are rebuilt when needed: decoded images (the current
  /// screen keeps the ones it shows), the photo and audio caches' in-memory
  /// lists (files on disk stay) and the lexicon's per-word lookups.
  /// No learner data is touched.
  void releaseCaches() {
    try {
      final images = PaintingBinding.instance.imageCache;
      images.clear();
      images.clearLiveImages();
    } catch (_) {}
    CachedNetworkPhoto.releaseMemory();
    LexiconPack.instance.releaseCaches();
    for (final release in List.of(_releasers)) {
      try {
        release();
      } catch (_) {}
    }
  }

  static String _day(DateTime t) => '${t.year.toString().padLeft(4, '0')}-'
      '${t.month.toString().padLeft(2, '0')}-'
      '${t.day.toString().padLeft(2, '0')}';

  Future<bool> _report(
      {required bool warning, required MemorySnapshot snap}) async {
    final now = _now();
    final page = _page();
    final today = _day(now);
    final key = '$today|$page';
    if (await _log.contains(key)) return false;
    await _log.add(key, today: today);
    final device = await _deviceInfo();
    final issue = memoryIssue(
        page: page,
        warning: warning,
        snap: snap,
        model: device['model'],
        system: device['system'],
        time: now);
    await service.submitIssue(issue, apiKey: apiKey());
    return true;
  }
}

/// The issue JSON for a memory report (問題回報 #824):
/// 「[記憶體] <畫面>」 with the numbers in the detail.
Map<String, dynamic> memoryIssue({
  required String page,
  required bool warning,
  required MemorySnapshot snap,
  String? model,
  String? system,
  DateTime? time,
}) =>
    {
      'kind': 'bug',
      'severity': 'medium',
      'area': 'app',
      'title': '[記憶體] $page',
      'detail': [
        '原因：${warning ? '收到 iOS 記憶體警告' : '剩餘可用記憶體低於 ${MemorySnapshot.mb(MemoryMonitor.threshold)} MB'}',
        '畫面：$page',
        if ((model ?? '').isNotEmpty) '裝置型號：$model',
        if ((system ?? '').isNotEmpty) 'iOS 版本：$system',
        'App 佔用：${snap.footprint < 0 ? '不明' : '${snap.footprintMb} MB'}',
        '剩餘可用：${snap.hasLimit ? '${snap.availableMb} MB' : '不明（無上限，模擬器）'}',
        if (time != null) '時間：${time.toIso8601String()}',
        'App 版本：${CardReport.appVersion}',
      ].join('\n'),
      'reporter': 'App 使用者',
    };
