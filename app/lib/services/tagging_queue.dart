import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/photo.dart';
import '../models/word_candidate.dart';
import '../models/word_entry.dart';
import 'app_settings.dart';
import 'cefr_lexicon.dart';
import 'lexicon_pack.dart';
import 'photo_intake.dart';
import 'tagging_service.dart';
import 'word_database_repository.dart';

/// Tags photos in the background (spec section 7, 非同步辨識與連線): a new
/// photo waits in a local queue — the 相片冊 shows an hourglass on it —
/// until the tagger answers. Whenever the tagger is reachable again the
/// queue picks up where it left off; there is no completion notice, the
/// learner simply finds the words when they come back to the album.
class TaggingQueue extends ChangeNotifier {
  final WordDatabaseRepository Function() repository;
  final AppSettings settings;
  final PhotoIntake intake;
  final CefrLexicon Function() lexicon;

  /// How often waiting photos are retried.
  final Duration retryEvery;

  TaggingQueue({
    required this.repository,
    required this.settings,
    required this.intake,
    required this.lexicon,
    this.retryEvery = const Duration(minutes: 1),
  });

  Timer? _timer;
  bool _running = false;
  String? _current;
  bool _offline = false;
  bool _disposed = false;
  Timer? _progressTimer;
  final Stopwatch _photoWatch = Stopwatch();
  int _completed = 0;
  int _total = 0;
  int _samples = 0;
  int _sampleMilliseconds = 0;
  int _failed = 0;

  int get failed => _failed;
  int get pending => repository()
      .allPhotos
      .where((p) =>
          p.taggingStatus == TaggingStatus.pending ||
          p.taggingStatus == TaggingStatus.tagging)
      .length;
  bool get hasWork => _current != null || pending > 0;

  int get completed => _completed;
  int get total => _total;
  int get position => _current == null ? _completed : _completed + 1;

  /// Initially allow one minute per photo; adapt to this session's replies.
  /// An overdue request remains an estimate, never a false zero-second promise.
  Duration get estimatedRemaining {
    if (!hasWork) return Duration.zero;
    final average = _samples == 0 ? 60000 : _sampleMilliseconds ~/ _samples;
    if (_current == null) return Duration(milliseconds: pending * average);
    final currentLeft =
        (average - _photoWatch.elapsedMilliseconds).clamp(10000, 1 << 40);
    final queued = (_total - _completed - 1).clamp(0, 1 << 30);
    return Duration(milliseconds: currentLeft + queued * average);
  }

  String get progressLabel {
    if (_current == null) {
      final reason =
          settings.taggingConfigured ? '等待 AI 服務恢復，會自動重試' : '請先設定 AI 辨識服務';
      return '已處理 $_completed/${_completed + pending} 張 · $reason';
    }
    final seconds = estimatedRemaining.inSeconds;
    final time = seconds < 60
        ? '${((seconds + 9) ~/ 10) * 10} 秒'
        : '${(seconds / 60).ceil()} 分鐘';
    return '第 $position/$_total 張 · 大約剩 $time';
  }

  @override
  void notifyListeners() {
    if (!_disposed) super.notifyListeners();
  }

  /// The photo being tagged right now.
  String? get current => _current;

  /// The last attempt couldn't reach the tagger.
  bool get offline => _offline;

  /// Starts the periodic retry and processes what is waiting.
  void start() {
    _timer ??= Timer.periodic(retryEvery, (_) => process());
    settings.addListener(_onSettings);
    unawaited(process());
  }

  String _lastConfig = '';
  void _onSettings() {
    final config = '${settings.taggingUrl}|${settings.apiKey}';
    if (config == _lastConfig) return;
    _lastConfig = config;
    // New address or key: failed photos get another chance.
    for (final p in repository().allPhotos) {
      if (p.taggingStatus == TaggingStatus.failed) {
        repository()
            .updatePhoto(p.copyWith(taggingStatus: TaggingStatus.pending));
      }
    }
    unawaited(process());
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    _progressTimer?.cancel();
    settings.removeListener(_onSettings);
    super.dispose();
  }

  /// Puts [photoId] (back) in the queue and processes it.
  Future<void> enqueue(String photoId) async {
    final repo = repository();
    final p = repo.photo(photoId);
    if (p == null) return;
    repo.updatePhoto(p.copyWith(
        taggingStatus: TaggingStatus.pending, taggingError: () => null));
    await process();
  }

  /// Tags waiting photos, oldest first, until the queue is empty or the
  /// tagger can't be reached. A photo that fails on its own is marked
  /// failed and the queue goes on.
  Future<void> process() async {
    if (_running || _disposed) return;
    _running = true;
    // A temporary outage is still the same batch, including its completed
    // photos. Start a fresh count only after the previous batch drained.
    if (_completed >= _total) {
      _completed = 0;
      _failed = 0;
    }
    _total = _completed + pending;
    try {
      while (!_disposed) {
        final repo = repository();
        final waiting = repo.allPhotos.reversed
            .where((p) =>
                p.taggingStatus == TaggingStatus.pending ||
                p.taggingStatus == TaggingStatus.tagging)
            .toList();
        if (waiting.isEmpty || !settings.taggingConfigured) break;
        _total = _completed + waiting.length;
        final ok = await _tag(repo, waiting.first);
        if (!ok) break;
        _completed++;
      }
    } finally {
      _running = false;
      _current = null;
      _total = _completed + pending;
      _progressTimer?.cancel();
      notifyListeners();
    }
  }

  Future<bool> _tag(WordDatabaseRepository repo, Photo photo) async {
    _current = photo.id;
    _offline = false;
    _photoWatch
      ..reset()
      ..start();
    _progressTimer?.cancel();
    _progressTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      final waiting = repository()
          .allPhotos
          .where((p) =>
              p.taggingStatus == TaggingStatus.pending ||
              p.taggingStatus == TaggingStatus.tagging)
          .length;
      _total = _completed + waiting.clamp(1, 1 << 30);
      notifyListeners();
    });
    notifyListeners();
    repo.updatePhoto(photo.copyWith(taggingStatus: TaggingStatus.tagging));
    try {
      final level = cefrLevels[(repo.profile.level + photo.difficultyOffset)
          .clamp(0, cefrLevels.length - 1)];
      final found = await _request(photo, level: level);
      _samples++;
      _sampleMilliseconds +=
          _photoWatch.elapsedMilliseconds.clamp(1000, 1 << 40);
      final latest = repo.photo(photo.id);
      if (latest == null) return true;
      repo.updatePhoto(latest.copyWith(
        taggingStatus: TaggingStatus.done,
        safetyStatus: PhotoSafetyStatus.safe,
        taggingError: () => null,
        candidates: _merge(latest.candidates, found),
      ));
      _offline = false;
      return true;
    } catch (e) {
      final latest = repo.photo(photo.id);
      if (e is TaggingApiException && e.statusCode == 451) {
        if (latest != null) repo.removePhoto(photo.id);
        _offline = false;
        debugPrint('Blocked unsafe photo ${photo.id}');
        return true;
      }
      final offline = isOffline(e) || e is TaggingNotConfigured;
      _offline = offline;
      if (!offline) _failed++;
      if (latest != null) {
        repo.updatePhoto(latest.copyWith(
          taggingStatus: offline ? TaggingStatus.pending : TaggingStatus.failed,
          taggingError: () => describeTaggingError(e, settings.taggingUrl),
        ));
      }
      debugPrint('Tagging ${photo.id} failed: $e');
      // Only an unreachable tagger stops the queue; a photo of its own
      // failing (問題回報: one bad reply held back every later photo)
      // lets the next one be tagged.
      return !offline;
    } finally {
      _photoWatch.stop();
      _progressTimer?.cancel();
    }
  }

  Future<List<WordCandidate>> _request(
    Photo photo, {
    required String level,
    String? focus,
    List<String> exclude = const [],
  }) async {
    if (!settings.taggingConfigured) throw TaggingNotConfigured();
    final bytes = await intake.bytesOf(photo);
    if (bytes == null) throw TaggingApiException('這張照片沒有影像可以辨識');
    final tagger =
        intake.createTagger(Uri.parse(settings.taggingUrl), settings.apiKey);
    try {
      return LexiconPack.instance.linkAll(await tagger.candidates(
        bytes,
        level: level,
        lexicon: lexicon(),
        lang: repository().language,
        native: settings.nativeLanguage,
        focus: focus,
        exclude: exclude,
      ));
    } finally {
      tagger.close();
    }
  }

  static List<WordCandidate> _merge(
      List<WordCandidate> pool, List<WordCandidate> found) {
    final have = {for (final c in pool) c.word};
    return [
      ...pool,
      for (final c in found)
        if (have.add(c.word)) c,
    ];
  }

  final _toppingUp = <String>{};
  final _asked = <String>{};

  bool isToppingUp(String photoId) => _toppingUp.contains(photoId);

  /// Whether more candidates of [focus] can still be asked for.
  bool canTopUp(Photo photo, String focus) =>
      settings.taggingConfigured &&
      !_asked.contains('${photo.id}|$focus') &&
      !photo.candidates.any((c) => c.focus == focus);

  /// Asks the model for more candidates of one kind for [photoId] and
  /// adds them to its pool (spec: 候選不足才重新呼叫模型). Returns how many
  /// new words arrived; each focus is asked for once per photo.
  Future<int> topUp(String photoId,
      {required String focus, required String level}) async {
    final repo = repository();
    final photo = repo.photo(photoId);
    if (photo == null ||
        _toppingUp.contains(photoId) ||
        !canTopUp(photo, focus)) {
      return 0;
    }
    _asked.add('$photoId|$focus');
    _toppingUp.add(photoId);
    notifyListeners();
    try {
      final found = await _request(photo,
          level: level,
          focus: focus,
          exclude: [for (final c in photo.candidates) c.word]);
      final latest = repo.photo(photoId);
      if (latest == null) return 0;
      final merged = _merge(latest.candidates, found);
      repo.updatePhoto(latest.copyWith(candidates: merged));
      return merged.length - latest.candidates.length;
    } finally {
      _toppingUp.remove(photoId);
      notifyListeners();
    }
  }
}
