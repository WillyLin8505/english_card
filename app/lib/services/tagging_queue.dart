import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/word_candidate.dart';
import '../models/word_entry.dart';
import 'app_settings.dart';
import 'cefr_lexicon.dart';
import 'dev_photo_upload.dart';
import 'lexicon_pack.dart';
import 'photo_intake.dart';
import 'spot_crop.dart';
import 'tagging_service.dart';
import 'text_scan.dart';
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
          settings.taggingConfigured ? '等待 AI 服務恢復，會自動重試' : '這台裝置沒有照片辨識';
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
        final next = waiting.where(_canTag).firstOrNull;
        if (next == null) break;
        _total = _completed + waiting.length;
        bool ok;
        try {
          ok = await _tag(repo, next);
        } catch (e) {
          // Whatever went wrong inside one photo (a bad picture, a platform
          // error while recording the failure) must not escape: process()
          // runs unawaited, so an escaped error would crash the app
          // (問題回報 #408). The photo is marked failed and the queue goes on.
          debugPrint('Tagging ${next.id} crashed: $e');
          _failed++;
          try {
            final latest = repo.photo(next.id);
            if (latest != null) {
              repo.updatePhoto(latest.copyWith(
                taggingStatus: TaggingStatus.failed,
                taggingError: () => '這張照片暫時無法辨識，請換一張再試',
              ));
            }
          } catch (_) {
            break;
          }
          ok = true;
        }
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
      _uploadForDeveloper(photo.id);
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
          taggingError: () =>
              describeTaggingError(e, settings.taggingUrl, showUrl: false),
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
    // Top-ups ask for more things in the picture; text is read once.
    final mode = focus == null ? photo.scanMode : PhotoScanMode.objects;
    final objects = mode.findsObjects &&
        (mode == PhotoScanMode.objects || settings.taggingConfigured);
    final text =
        mode.findsText && (mode == PhotoScanMode.text || TextScan.available);
    if (!objects && !text) throw TaggingNotConfigured();
    final bytes = await intake.bytesOf(photo);
    if (bytes == null) throw TaggingApiException('這張照片沒有影像可以辨識');
    return [
      if (objects)
        ...await _ask(_objectTagger(), bytes,
            level: level, focus: focus, exclude: exclude),
      if (text)
        ...await _ask(intake.createTextTagger(), bytes,
            level: level, exclude: exclude),
    ];
  }

  /// 長按辨識 (問題回報 #616): what is at [at] on [photo]. The picture
  /// around that spot is cut out and sent to the recognizer on its own, at
  /// the photo's level; the learner picks a word and it is pinned there.
  Future<List<WordCandidate>> recognizeSpot(Photo photo, LabelPoint at) async {
    if (!settings.taggingConfigured) throw TaggingNotConfigured();
    final bytes = await intake.bytesOf(photo);
    if (bytes == null) throw TaggingApiException('這張照片沒有影像可以辨識');
    final crop = await cropAround(bytes, at);
    final repo = repository();
    final level = cefrLevels[(repo.profile.level + photo.difficultyOffset)
        .clamp(0, cefrLevels.length - 1)];
    return _ask(_objectTagger(), crop, level: level);
  }

  /// Whether [photo] can be recognized now: things in the picture need a
  /// recognizer (the phone's or a server), text needs the phone's reader —
  /// a text-only photo on the web is tried and fails with an explanation.
  bool _canTag(Photo photo) => switch (photo.scanMode) {
        PhotoScanMode.objects => settings.taggingConfigured,
        PhotoScanMode.text => true,
        PhotoScanMode.both => settings.taggingConfigured || TextScan.available,
      };

  // The phone's own classifier unless a server address is set (問題回報
  // #265: the store build has no server).
  PhotoTagger _objectTagger() => settings.usesLocalRecognition
      ? intake.createLocalTagger()
      : intake.createTagger(Uri.parse(settings.taggingUrl), settings.apiKey);

  Future<List<WordCandidate>> _ask(
    PhotoTagger tagger,
    Uint8List bytes, {
    required String level,
    String? focus,
    List<String> exclude = const [],
  }) async {
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

  /// Developer build only (問題回報 #853): the photo and its labels go to 後台.
  void _uploadForDeveloper(String photoId) {
    if (!DevPhotoUpload.enabled(settings)) return;
    final photo = repository().photo(photoId);
    if (photo == null) return;
    intake.bytesOf(photo).then((bytes) {
      if (bytes == null) return false;
      return DevPhotoUpload.send(settings, photo, bytes,
          language: repository().language);
    }).catchError((_) => false);
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

  final _toppingUp = <String, Future<int>>{};
  final _toppingFocus = <String, String?>{};
  final _asked = <String>{};

  bool isToppingUp(String photoId) => _toppingUp.containsKey(photoId);

  /// Whether a recognizer could be asked about [photo] at all: things in
  /// the picture need the phone's classifier or a server. Downloaded deck
  /// pictures (卡片集) count too — they have their image (問題回報 #666).
  bool canAskMore(Photo photo) =>
      settings.taggingConfigured && photo.scanMode.findsObjects;

  /// Whether 重新掃描標籤 (問題回報 #670) can read [photo] again: things in
  /// it need a recognizer, text needs the phone's reader.
  bool canRescan(Photo photo) =>
      canAskMore(photo) || (photo.scanMode.findsText && TextScan.available);

  /// Whether more candidates of [focus] can still be asked for.
  bool canTopUp(Photo photo, String focus) =>
      canAskMore(photo) &&
      !_asked.contains('${photo.id}|$focus') &&
      !photo.candidates.any((c) => c.focus == focus);

  /// Asks the model for more candidates of one kind for [photoId] and
  /// adds them to its pool (spec: 候選不足才重新呼叫模型). Returns how many
  /// new words arrived; each focus is asked for once per photo — unless the
  /// request failed (offline, server error), then it can be tried again.
  /// [again]: the learner tapped 多看動詞 / 難一點 (問題回報 #671), so the
  /// photo is scanned for that kind every time; the same request already
  /// on its way is waited for instead of sent twice.
  /// A request while another one for the photo runs waits for it first
  /// (問題回報 #666: the learner's tap must not be dropped as "nothing").
  Future<int> topUp(String photoId,
      {required String focus,
      required String level,
      bool again = false}) async {
    for (var running = _toppingUp[photoId];
        running != null;
        running = _toppingUp[photoId]) {
      if (again && _toppingFocus[photoId] == focus) return running;
      try {
        await running;
      } catch (_) {
        // That request's caller reports it.
      }
    }
    final repo = repository();
    final photo = repo.photo(photoId);
    if (photo == null ||
        !(again ? canAskMore(photo) : canTopUp(photo, focus))) {
      return 0;
    }
    final key = '$photoId|$focus';
    _asked.add(key);
    try {
      return await _run(photoId, focus,
          () => _topUp(repo, photo, focus: focus, level: level));
    } catch (_) {
      _asked.remove(key);
      rethrow;
    }
  }

  /// 重新掃描標籤 (問題回報 #670): the whole photo is read again, without a
  /// focus, asking for words its pool doesn't have yet. New ones join the
  /// pool — nothing in it is replaced — and are returned.
  Future<List<String>> rescan(String photoId) async {
    for (var running = _toppingUp[photoId];
        running != null;
        running = _toppingUp[photoId]) {
      try {
        await running;
      } catch (_) {
        // That request's caller reports it.
      }
    }
    final repo = repository();
    final photo = repo.photo(photoId);
    if (photo == null) return const [];
    if (!canRescan(photo)) throw TaggingNotConfigured();
    final level = cefrLevels[(repo.profile.level + photo.difficultyOffset)
        .clamp(0, cefrLevels.length - 1)];
    final fresh = <String>[];
    await _run(photoId, null, () async {
      final found = await _request(photo,
          level: level, exclude: _topUpExclude(repo, photo, level));
      final latest = repo.photo(photo.id);
      if (latest == null) return 0;
      final merged = _merge(latest.candidates, found);
      fresh.addAll([
        for (final c in merged.skip(latest.candidates.length)) c.word,
      ]);
      repo.updatePhoto(latest.copyWith(
        candidates: merged,
        taggingStatus: TaggingStatus.done,
        safetyStatus: PhotoSafetyStatus.safe,
        taggingError: () => null,
      ));
      _uploadForDeveloper(photo.id);
      return fresh.length;
    });
    return fresh;
  }

  /// What a top-up asks the recognizer to skip (問題回報 #691, Windows 卡
  /// #625): this photo's words first, then words the learner already has
  /// in the word book at or below [level] — the everyday words their other
  /// photos taught — so 更多 brings new words. The server takes 40.
  static List<String> _topUpExclude(
      WordDatabaseRepository repo, Photo photo, String level) {
    final out = <String>[];
    final seen = <String>{};
    void add(String word) {
      final key = word.trim().toLowerCase();
      if (key.isEmpty || !seen.add(key) || out.length >= 40) return;
      out.add(word.trim());
    }

    for (final c in photo.candidates) {
      add(c.word);
    }
    final top = cefrLevels.indexOf(level);
    for (final e in repo.entries.reversed) {
      if (out.length >= 40) break;
      final at = e.level == null ? -1 : cefrLevels.indexOf(e.level!);
      if (at >= 0 && at <= top && !e.word.contains(' ')) add(e.word);
    }
    return out;
  }

  Future<int> _run(
      String photoId, String? focus, Future<int> Function() ask) async {
    final request = ask();
    _toppingUp[photoId] = request;
    _toppingFocus[photoId] = focus;
    notifyListeners();
    try {
      return await request;
    } finally {
      _toppingUp.remove(photoId);
      _toppingFocus.remove(photoId);
      if (!_disposed) notifyListeners();
    }
  }

  Future<int> _topUp(WordDatabaseRepository repo, Photo photo,
      {required String focus, required String level}) async {
    final found = await _request(photo,
        level: level,
        focus: focus,
        exclude: _topUpExclude(repo, photo, level));
    final latest = repo.photo(photo.id);
    if (latest == null) return 0;
    final merged = _merge(latest.candidates, found);
    repo.updatePhoto(latest.copyWith(candidates: merged));
    return merged.length - latest.candidates.length;
  }
}
