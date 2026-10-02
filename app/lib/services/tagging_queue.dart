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
    for (final p in repository().photos) {
      if (p.taggingStatus == TaggingStatus.failed) {
        repository()
            .updatePhoto(p.copyWith(taggingStatus: TaggingStatus.pending));
      }
    }
    unawaited(process());
  }

  @override
  void dispose() {
    _timer?.cancel();
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
    if (_running) return;
    _running = true;
    try {
      while (true) {
        final repo = repository();
        final waiting = repo.photos.reversed
            .where((p) =>
                p.taggingStatus == TaggingStatus.pending ||
                p.taggingStatus == TaggingStatus.tagging)
            .toList();
        if (waiting.isEmpty || !settings.taggingConfigured) break;
        final ok = await _tag(repo, waiting.first);
        if (!ok) break;
      }
    } finally {
      _running = false;
      _current = null;
      notifyListeners();
    }
  }

  Future<bool> _tag(WordDatabaseRepository repo, Photo photo) async {
    _current = photo.id;
    notifyListeners();
    repo.updatePhoto(photo.copyWith(taggingStatus: TaggingStatus.tagging));
    try {
      final level = cefrLevels[(repo.profile.level + photo.difficultyOffset)
          .clamp(0, cefrLevels.length - 1)];
      final found = await _request(photo, level: level);
      final latest = repo.photo(photo.id);
      if (latest == null) return true;
      repo.updatePhoto(latest.copyWith(
        taggingStatus: TaggingStatus.done,
        taggingError: () => null,
        candidates: _merge(latest.candidates, found),
      ));
      _offline = false;
      return true;
    } catch (e) {
      final latest = repo.photo(photo.id);
      final offline = isOffline(e) || e is TaggingNotConfigured;
      _offline = offline;
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
