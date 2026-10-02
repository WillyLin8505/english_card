import 'package:flutter/foundation.dart';

import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/vocabulary_profile.dart';
import '../models/word_candidate.dart';
import '../models/word_entry.dart';
import 'tagging_queue.dart';
import 'word_database_repository.dart';
import 'word_selector.dart';

/// A word on the photo's list while 照片詳情 is open.
class SessionWord {
  WordCandidate candidate;

  /// The AI's word, kept when the learner corrects the label.
  final String aiLabel;
  bool edited = false;

  /// Where its pin is — moved by dragging (照片標籤可拖曳重新定位).
  LabelPoint anchor;

  /// ☆: kept when the dial moves; only for this visit (星星只在本次照片
  /// 選詞期間有效…離開頁面後不保存星星狀態).
  bool starred = false;

  SessionWord(this.candidate, this.anchor, {String? aiLabel})
      : aiLabel = aiLabel ?? candidate.word;

  String get word => candidate.word;
}

/// A word the list hides by default, shown with 「顯示已學會單字」.
class OldWord {
  final WordCandidate candidate;
  final LabelPoint anchor;

  /// Swiped away as known (已學會) — gets a small 復原 button.
  final bool learned;

  const OldWord(this.candidate, this.anchor, {required this.learned});

  String get word => candidate.word;
}

/// The photo-detail screen's state (spec section 7, 照片選詞與標籤操作):
///
/// - the list is picked from the photo's candidate pool by [WordSelector]
///   at the dial's level, and re-picked live while the dial moves;
/// - swiping a word left moves it to 已學會 and the next suitable
///   candidate takes its place (候選不足時不必湊滿 5 個);
/// - ☆ keeps a word when the level changes;
/// - nothing is written until the learner leaves the page ([save]); then
///   the remaining words become cards (自動保存), and if the learner
///   removed every word, the photo leaves the app's albums.
class PhotoWordSession extends ChangeNotifier {
  final WordDatabaseRepository repo;
  final String photoId;
  final TaggingQueue? queue;
  final WordSelector selector;

  PhotoWordSession({
    required this.repo,
    required this.photoId,
    this.queue,
    this.selector = const WordSelector(),
  }) {
    final photo = repo.photo(photoId);
    _target = (repo.profile.level + (photo?.difficultyOffset ?? 0)).clamp(0, 5);
    _poolSize = photo?.candidates.length ?? 0;
    if (photo != null && photo.wordsSavedAt != null) {
      words = [
        for (final l in repo.visibleLabels(photoId))
          SessionWord(_candidateFor(l.entry, l.occ), l.occ.anchor),
      ];
    } else {
      _reselect(allowTopUp: true);
      _dirty = true;
    }
    repo.addListener(_onRepo);
  }

  late int _target;
  int _poolSize = 0;
  List<SessionWord> words = [];
  final Set<String> _removed = {};
  PosBias _bias = PosBias.none;
  bool _showLearned = false;
  bool _dirty = false;
  bool _removedAny = false;
  Selection? _selection;
  bool _disposed = false;

  Photo? get photo => repo.photo(photoId);

  /// The dial: an index into cefrLevels.
  int get target => _target;
  String get targetLevel => cefrLevels[_target];

  /// The learner's level — where the dial starts for a new photo (每張照片
  /// 重設: 下一張照片回到系統目前判定的 CEFR).
  int get baseLevel => repo.profile.level;
  int get offset => _target - baseLevel;

  PosBias get bias => _bias;
  bool get showLearned => _showLearned;
  bool get hasUnsavedChanges => _dirty;
  Selection? get selection => _selection;

  /// A candidate standing in for a word already saved on this photo.
  WordCandidate _candidateFor(WordEntry e, PhotoOccurrence o) {
    final fromPool =
        photo?.candidates.where((c) => c.word == e.word).firstOrNull;
    return WordCandidate(
      word: e.word,
      pos: e.pos.isEmpty ? (fromPool?.pos ?? 'noun') : e.pos,
      meaning: e.meaning,
      level: e.level ?? fromPool?.level ?? 'B1',
      levelSource: e.levelSource ?? fromPool?.levelSource ?? 'ai',
      zipf: e.frequency ?? fromPool?.zipf,
      ipa: e.ipa,
      evidence: o.evidence ?? fromPool?.evidence ?? '',
      point: o.anchor,
      visualConfidence: o.confidence ?? fromPool?.visualConfidence ?? 0.8,
      usefulness: fromPool?.usefulness ?? 0.6,
      inferred: fromPool?.inferred ?? false,
    );
  }

  /// The pool, plus stand-ins for listed words the pool doesn't have
  /// (sample photos, corrected labels).
  List<WordCandidate> get _pool {
    final pool = [...?photo?.candidates];
    final have = {for (final c in pool) c.word};
    for (final w in words) {
      if (!have.contains(w.word)) pool.add(w.candidate);
    }
    for (final l in repo.activeLabels(photoId)) {
      if (!have.contains(l.entry.word) &&
          !words.any((w) => w.word == l.entry.word)) {
        pool.add(_candidateFor(l.entry, l.occ));
      }
    }
    return pool;
  }

  /// Words studied from other photos: not offered again, but this photo
  /// becomes one of their contexts when saved.
  Set<String> get _studyingElsewhere {
    final own = {
      for (final o in repo.occurrencesInPhoto(photoId))
        if (!o.contextOnly)
          if (repo.entry(o.wordEntryId) case final e?) e.word,
    };
    return repo.studyingWords
        .difference(own)
        .difference({for (final w in words) w.word});
  }

  void _reselect({bool allowTopUp = false}) {
    final sel = selector.select(
      pool: _pool,
      target: _target,
      profile: repo.profile,
      studying: _studyingElsewhere,
      removed: _removed,
      current: [for (final w in words) w.word],
      locked: {
        for (final w in words)
          if (w.starred) w.word,
      },
      bias: _bias,
      now: repo.clock(),
    );
    final byWord = {for (final w in words) w.word: w};
    words = [
      for (final c in sel.words) byWord[c.word] ?? SessionWord(c, c.point)
    ];
    _selection = sel;
    if (allowTopUp) _maybeTopUp(sel);
  }

  void _maybeTopUp(Selection sel) {
    final q = queue;
    final p = photo;
    final focus = sel.topUp;
    if (q == null || p == null || focus == null || p.candidates.isEmpty) return;
    if (!q.canTopUp(p, focus)) return;
    final level = targetLevel;
    // Not synchronously: this can run while a screen is building, and the
    // queue notifies its listeners as soon as it starts.
    Future<void>.microtask(() async {
      try {
        final added = await q.topUp(photoId, focus: focus, level: level);
        if (added > 0 && !_disposed) {
          _reselect();
          notifyListeners();
        }
      } catch (e) {
        debugPrint('Top-up for $photoId failed: $e');
      }
    });
  }

  void _onRepo() {
    final p = photo;
    if (p == null || _disposed) return;
    var updated = false;
    for (final w in words) {
      if (w.edited) continue;
      final entry = repo.entryByWord(w.word);
      if (entry != null && entry.meaning != w.candidate.meaning) {
        w.candidate = w.candidate.copyWith(meaning: entry.meaning);
        updated = true;
      }
    }
    if (updated) notifyListeners();
    // Candidates arrived (background tagging, or a top-up): refill.
    if (p.candidates.length != _poolSize) {
      _poolSize = p.candidates.length;
      if (words.length < WordSelector.maxWords) {
        _reselect();
        if (p.wordsSavedAt == null) _dirty = true;
        notifyListeners();
      }
    }
  }

  /// Moves the dial. While dragging ([live]) only the existing pool is
  /// used; on release the model may be asked for more words.
  void setTarget(int level, {bool live = false}) {
    final t = level.clamp(0, cefrLevels.length - 1);
    if (t == _target && live) return;
    _target = t;
    _dirty = true;
    _reselect(allowTopUp: !live);
    notifyListeners();
  }

  /// 更多動作 / 更多描述 (tap again to turn off).
  void setBias(PosBias b) {
    _bias = _bias == b ? PosBias.none : b;
    _dirty = true;
    _reselect(allowTopUp: true);
    notifyListeners();
  }

  void toggleStar(SessionWord w) {
    w.starred = !w.starred;
    notifyListeners();
  }

  /// 修改標籤 (spec: AI 英文標籤「可改」): another word or meaning for
  /// this spot. The level is looked up again for a new word.
  void correct(SessionWord w,
      {required String word, required String meaning, String? level}) {
    final normalized = word.trim().toLowerCase();
    if (normalized.isEmpty) return;
    final c = w.candidate;
    w.candidate = WordCandidate(
      word: normalized,
      pos: normalized == c.word
          ? c.pos
          : (normalized.contains(' ') ? 'phrase' : c.pos),
      meaning: meaning.trim(),
      level: normalized == c.word ? c.level : (level ?? c.level),
      levelSource: normalized == c.word
          ? c.levelSource
          : (level == null ? c.levelSource : 'cefr-j'),
      evidence: c.evidence,
      point: c.point,
      visualConfidence: c.visualConfidence,
      usefulness: c.usefulness,
      inferred: c.inferred,
    );
    w.edited = true;
    _dirty = true;
    notifyListeners();
  }

  void move(SessionWord w, LabelPoint anchor) {
    w.anchor = anchor;
    _dirty = true;
    notifyListeners();
  }

  /// 左滑已學會: the word leaves the list for the 已學會 list — its card,
  /// if it has one, is archived (not deleted) — and the next suitable
  /// candidate fills the gap.
  void swipe(SessionWord w) {
    words.remove(w);
    _removed.add(w.word);
    _removedAny = true;
    _dirty = true;
    final e = repo.entryByWord(w.word);
    if (e != null && repo.cardOf(e.id) != null) {
      repo.archiveWord(e.id);
    } else {
      repo.markKnown(w.candidate);
    }
    _reselect(allowTopUp: true);
    notifyListeners();
  }

  void setShowLearned(bool v) {
    _showLearned = v;
    notifyListeners();
  }

  /// Hidden words of this photo: 已學會 ones (with 復原) and words already
  /// studied from other photos.
  List<OldWord> get oldWords {
    final out = <OldWord>[];
    final seen = <String>{};
    for (final o in repo.occurrencesInPhoto(photoId)) {
      final e = repo.entry(o.wordEntryId);
      if (e == null || !repo.isArchived(e.id) || !seen.add(e.word)) continue;
      out.add(OldWord(_candidateFor(e, o), o.anchor, learned: true));
    }
    final learned = repo.profile.learned;
    final studying = _studyingElsewhere;
    for (final c in photo?.candidates ?? const <WordCandidate>[]) {
      if (seen.contains(c.word) || words.any((w) => w.word == c.word)) continue;
      if (learned.contains(c.word)) {
        seen.add(c.word);
        out.add(OldWord(c, c.point, learned: true));
      } else if (studying.contains(c.word)) {
        seen.add(c.word);
        out.add(OldWord(c, c.point, learned: false));
      }
    }
    return out;
  }

  /// 復原: back to learning, with its card, history and FSRS state; it
  /// rejoins the list (replacing the weakest unstarred word if full).
  void restore(OldWord o) {
    repo.restoreWord(o.word);
    _removed.remove(o.word);
    if (!words.any((w) => w.word == o.word)) {
      if (words.length >= WordSelector.maxWords) {
        final drop =
            words.lastWhere((w) => !w.starred, orElse: () => words.last);
        words.remove(drop);
      }
      words.add(SessionWord(o.candidate, o.anchor));
    }
    _dirty = true;
    notifyListeners();
  }

  /// What leaving the page does. Returns the words created (to fetch
  /// their full data) and whether the photo was removed.
  ({List<WordEntry> created, bool photoRemoved}) save() {
    final p = photo;
    if (p == null || (!_dirty && p.wordsSavedAt != null)) {
      return (created: const [], photoRemoved: false);
    }
    // Still waiting for the tagger: nothing to save yet, so the list is
    // picked fresh when the candidates arrive.
    // A tagged photo whose words are all being studied from other photos
    // still saves them as its contexts (spec: 新照片只加入該單字的照片情境;
    // 問題回報 #120) — only an untagged or truly empty one returns here.
    final knownHere = p.candidates.any((c) => _studyingElsewhere.contains(c.word));
    if (words.isEmpty && !_removedAny && p.wordsSavedAt == null && !knownHere) {
      // Tagged, but the dial left nothing to learn at this level: keep the
      // dial for this photo (spec: 輪盤選擇只保存為此照片的
      // difficultyOffset), so reopening shows the same empty level.
      if (p.candidates.isNotEmpty && offset != p.difficultyOffset) {
        repo.updatePhoto(p.copyWith(difficultyOffset: offset));
        _dirty = false;
      }
      return (created: const [], photoRemoved: false);
    }
    if (words.isEmpty && _removedAny) {
      repo.removePhoto(photoId);
      _dirty = false;
      return (created: const [], photoRemoved: true);
    }
    final studying = _studyingElsewhere;
    final alsoSeen = [
      for (final c in p.candidates)
        if (studying.contains(c.word) &&
            c.visualConfidence >= 0.6 &&
            !c.inferred)
          ListedWord(c, c.point),
    ];
    if (offset != p.difficultyOffset && offset != 0) {
      repo.recordSignal(DialSignal(offset));
    }
    final created = repo.savePhotoWords(
      photoId,
      [
        for (final w in words)
          ListedWord(w.candidate, w.anchor,
              aiLabel: w.edited ? w.aiLabel : null, edited: w.edited),
      ],
      difficultyOffset: offset,
      alsoSeen: alsoSeen,
    );
    _dirty = false;
    _removedAny = false;
    return (created: created, photoRemoved: false);
  }

  @override
  void dispose() {
    _disposed = true;
    repo.removeListener(_onRepo);
    super.dispose();
  }
}
