import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import '../models/learning_card.dart';
import '../models/photo.dart';
import 'word_database_repository.dart';

/// One continuous flashcard run (spec section 7, 連續卡流): no fixed
/// number of cards. Each next card is drawn by mixing FSRS forgetting
/// probability, how recently it was shown and photo variety; the run
/// ends when no card meets the review condition. A card graded Again
/// comes back a few cards later in the same run (按 Again 的卡會在同一次
/// 連續測驗稍後再次出現), at most twice, so one forgotten card cannot
/// keep a low-pressure review run open forever.
class FlashcardSession extends ChangeNotifier {
  /// How many cards later an Again card returns.
  static const againGap = 3;

  /// Maximum same-run appearances after the card's first appearance.
  static const maxAgainRepeats = 2;

  final WordDatabaseRepository repo;
  final math.Random _random;

  FlashcardSession(this.repo, {math.Random? random})
      : _random = random ?? math.Random() {
    _advance();
  }

  int _step = 0;
  final _shownAt = <String, int>{};
  final _again = <String, int>{};
  final _againRepeats = <String, int>{};
  final _recentPhotos = <String>[];
  String? _lastPhoto;

  String? _cardId;
  Photo? _photo;
  LabelPoint? _anchor;
  bool _back = false;
  final _watch = Stopwatch();
  int _reviewed = 0;

  LearningCard? get card => _cardId == null ? null : repo.card(_cardId!);
  bool get finished => _cardId == null;
  bool get showingBack => _back;

  /// The photo shown on the back: one of the word's photos, avoiding the
  /// ones shown recently (多張相關照片在背面隨機輪流顯示，避免連續重複).
  Photo? get photo => _photo;
  LabelPoint? get anchor => _anchor;

  int get reviewed => _reviewed;

  void showAnswer() {
    if (finished || _back) return;
    _back = true;
    notifyListeners();
  }

  void rate(Rating rating) {
    final id = _cardId;
    if (id == null || !_back) return;
    repo.review(id, rating, duration: _watch.elapsed);
    _reviewed++;
    if (rating == Rating.again) {
      final repeats = _againRepeats[id] ?? 0;
      if (repeats < maxAgainRepeats) {
        _againRepeats[id] = repeats + 1;
        _again[id] = _step + againGap;
      }
    }
    _step++;
    _advance();
  }

  void _advance() {
    _back = false;
    _cardId = _pick();
    if (_cardId != null) {
      _shownAt[_cardId!] = _step;
      _choosePhoto();
    } else {
      _photo = null;
      _anchor = null;
    }
    _watch
      ..reset()
      ..start();
    notifyListeners();
  }

  String? _pick() {
    // An Again card whose turn has come.
    final back = _again.entries.where((e) => e.value <= _step).toList()
      ..sort((a, b) => a.value.compareTo(b.value));
    if (back.isNotEmpty) {
      _again.remove(back.first.key);
      if (repo.card(back.first.key) case final c? when !c.archived) return c.id;
    }
    final now = repo.clock();
    final eligible = [
      for (final c in repo.eligibleCards())
        if (!_shownAt.containsKey(c.id) && !_again.containsKey(c.id)) c,
    ];
    if (eligible.isEmpty) {
      // Only Again cards left: show the next one now rather than stop.
      if (_again.isEmpty) return null;
      final next = (_again.entries.toList()
            ..sort((a, b) => a.value.compareTo(b.value)))
          .first;
      _again.remove(next.key);
      return next.key;
    }
    final photosByWord = repo.photoIdsByWord();
    double score(LearningCard c) {
      final r = repo.scheduler.retrievability(c.fsrs, now);
      final forgetting = r == null ? 0.5 : 1 - r;
      final photos = photosByWord[c.wordEntryId] ?? const <String>{};
      final variety =
          _lastPhoto != null && photos.contains(_lastPhoto) ? 0.0 : 1.0;
      return 0.6 * forgetting + 0.3 * variety + 0.1 * _random.nextDouble();
    }

    // Each card scored once (sort would call it again for every comparison).
    final scores = {for (final c in eligible) c.id: score(c)};
    eligible.sort((a, b) => scores[b.id]!.compareTo(scores[a.id]!));
    return eligible.first.id;
  }

  void _choosePhoto() {
    final c = card;
    if (c == null) return;
    final options = [
      for (final o in repo.occurrencesOf(c.wordEntryId))
        if (repo.photo(o.photoId) case final p? when p.hasImage) (p, o.anchor),
    ];
    if (options.isEmpty) {
      _photo = null;
      _anchor = null;
      return;
    }
    final fresh =
        options.where((o) => !_recentPhotos.contains(o.$1.id)).toList();
    final pickFrom = fresh.isEmpty ? options : fresh;
    final chosen = pickFrom[_random.nextInt(pickFrom.length)];
    _photo = chosen.$1;
    _anchor = chosen.$2;
    _lastPhoto = chosen.$1.id;
    _recentPhotos.add(chosen.$1.id);
    if (_recentPhotos.length > 3) _recentPhotos.removeAt(0);
  }
}
