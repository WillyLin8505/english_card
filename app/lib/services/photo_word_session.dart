import 'package:flutter/foundation.dart';

import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/vocabulary_profile.dart';
import '../models/word_candidate.dart';
import '../models/word_entry.dart';
import 'lexicon_pack.dart';
import 'photo_intake.dart';
import 'tagging_queue.dart';
import 'word_database_repository.dart';
import 'word_selector.dart';

/// A word on the photo's list while 照片詳情 is open.
class SessionWord {
  WordCandidate candidate;

  /// The AI's word, kept when the learner corrects the label.
  final String aiLabel;
  bool edited = false;

  /// Typed in by the learner (自己加字, 問題回報 #323).
  final bool added;

  /// The meaning is one the learner typed: kept over the pack's.
  bool ownMeaning = false;

  /// Where its pin is — moved by dragging (照片標籤可拖曳重新定位).
  LabelPoint anchor;

  /// False for an added word that was never put on the photo: no pin.
  bool placed;

  /// ☆ collects the word (卡 #835／#899): kept when the dial moves, and it
  /// goes to the word book only on 儲存 (not 鎖定 any more).
  bool starred = false;

  SessionWord(this.candidate, this.anchor,
      {String? aiLabel, this.added = false, this.placed = true})
      : aiLabel = aiLabel ?? candidate.word;

  String get word => candidate.word;
}

/// A word the list hides by default, shown with 「顯示已學會單字」.
class OldWord {
  final WordCandidate candidate;
  final LabelPoint anchor;

  /// Swiped away as known (已學會) — gets a small 復原 button.
  final bool learned;

  /// False for a whole-picture word (問題回報 #703): no muted pin either.
  final bool placed;

  const OldWord(this.candidate, this.anchor,
      {required this.learned, this.placed = true});

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

  /// Where corrected and added words are looked up again (lemma, meaning,
  /// lexeme id); words it lacks become missing-word requests (/api/missing).
  final LexiconPack pack;

  PhotoWordSession({
    required this.repo,
    required this.photoId,
    this.queue,
    this.selector = const WordSelector(),
    LexiconPack? pack,
  }) : pack = pack ?? LexiconPack.instance {
    final photo = repo.photo(photoId);
    _rejected.addAll(photo?.rejectedWords ?? const []);
    _target = _openingTarget(photo);
    _poolSize = photo?.candidates.length ?? 0;
    if (photo != null && photo.wordsSavedAt != null) {
      words = [
        for (final l in repo.visibleLabels(photoId))
          SessionWord(_candidateFor(l.entry, l.occ), l.occ.anchor,
              aiLabel: l.occ.aiLabel,
              added: l.occ.aiLabel == null,
              placed: l.occ.placed)
            ..edited = l.occ.userEdited && l.occ.aiLabel != l.entry.word,
      ];
      // 問題回報 #691: a photo saved with fewer than five labels (its other
      // candidates arrived later, or were learned elsewhere since) is
      // filled up when it opens again; the saved labels all stay.
      if (words.length < WordSelector.maxWords && photo.candidates.isNotEmpty) {
        final before = words.length;
        _reselect(allowTopUp: true, keep: {for (final w in words) w.word});
        if (words.length != before) _dirty = true;
      }
      _shownAt[_target] = [for (final w in words) w.word];
    } else {
      _reselect(allowTopUp: true);
      _dirty = true;
    }
    _home = [for (final w in words) w.word];
    repo.addListener(_onRepo);
  }

  late int _target;

  /// 問題回報 #942 / #943: a photo the learner has not dialled yet opens at
  /// the highest level its own candidates reach, not at the learner's level
  /// (on about half the photos the top level has no word, so the list is
  /// blank). Saved photos keep the dial they were left on.
  int _openingTarget(Photo? photo) {
    final learner = (repo.profile.level + (photo?.difficultyOffset ?? 0))
        .clamp(0, cefrLevels.length - 1);
    if (photo == null ||
        photo.wordsSavedAt != null ||
        photo.difficultyOffset != 0 ||
        photo.candidates.isEmpty) {
      return learner;
    }
    var top = -1;
    for (final c in photo.candidates) {
      final i = cefrLevels.indexOf(c.level);
      if (i > top) top = i;
    }
    return top < 0 || top >= learner ? learner : top;
  }

  /// Whether the learner moved the dial on this photo. The opening position
  /// is not a choice, so it is not recorded as a dial signal or saved.
  bool _dialMoved = false;
  int _poolSize = 0;

  /// 問題回報 #852: the words each dial position has shown, so sliding away
  /// and back shows the same labels. A position's words depend only on the
  /// photo's candidates and the position (plus the learner's own words);
  /// candidates that arrive later only fill a position's empty places.
  /// Cleared when the learner asks for a different list (多看動詞、重新掃描).
  final Map<int, List<String>> _shownAt = {};
  final Map<String, SessionWord> _seen = {};

  /// The words the photo opened with (or the last list the learner asked
  /// for): a position not shown yet keeps those that fit it.
  List<String> _home = const [];
  List<SessionWord> words = [];
  final Set<String> _removed = {};

  /// Not in this photo, says the learner: deleted as wrong, or an AI label
  /// corrected to another word. Saved with the photo ([Photo.rejectedWords]).
  final Set<String> _rejected = {};
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

  /// What 照片辨識 is being asked for right now because the learner tapped
  /// 多看動詞 / 難一點 (問題回報 #666, #671): 'actions', 'descriptions',
  /// 'harder' or 'easier'.
  String? get fetchingMore => _fetching;
  String? _fetching;

  /// 重新掃描標籤 is on its way (問題回報 #670).
  bool get rescanning => _rescanning;
  bool _rescanning = false;

  /// Told when such a tap brings nothing new — the pool and the recognizer
  /// have no more of it, or no recognizer can be asked — so the tap never
  /// looks ignored. The screen shows it as a snack bar.
  void Function(String message)? onNotice;

  /// 「動詞」「形容詞」「更難的字」「更簡單的字」 for a top-up focus.
  static String focusLabel(String focus) => switch (focus) {
        'actions' => '動詞',
        'descriptions' => '形容詞',
        'harder' => '更難的字',
        'easier' => '更簡單的字',
        _ => '單字',
      };

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
      grounded: o.placed || (fromPool?.grounded ?? true),
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

  void _reselect(
      {bool allowTopUp = false,
      Set<String> fresh = const {},
      Set<String> keep = const {},
      bool repick = false}) {
    // The learner's own words stay whatever the dial says.
    final own = {
      ...keep,
      for (final w in words)
        if (w.starred || w.added || w.edited) w.word,
    };
    final removed = {..._removed, ..._rejected};
    final studying = _studyingElsewhere;
    final learned = repo.profile.learned;
    bool gone(String w) =>
        !own.contains(w) &&
        (removed.contains(w) || studying.contains(w) || learned.contains(w));
    // 問題回報 #852: what a dial position shows depends only on the photo's
    // candidates and the position — never on the position shown just
    // before. Three cases:
    // - the learner asked for a new list (重新掃描、多看動詞): picked again
    //   from the words shown now, and every position starts over;
    // - a position shown before: its words stay where they were (a word
    //   swiped away, deleted or learned since gives way), later candidates
    //   only fill empty places;
    // - a position not shown yet: picked from the pool, keeping the words
    //   the photo opened with where they still fit (保留跨級詞).
    final List<String> shown;
    final Set<String> locked;
    final cached = _shownAt[_target];
    if (repick || fresh.isNotEmpty) {
      _shownAt.clear();
      shown = [for (final w in words) w.word];
      locked = own;
    } else {
      final base = [
        for (final w in cached ?? _home)
          if (!gone(w)) w,
      ];
      shown = [
        ...base,
        for (final w in own)
          if (!base.contains(w)) w,
      ];
      // At most five: earlier words that aren't the learner's give way.
      while (shown.length > WordSelector.maxWords) {
        final i = shown.lastIndexWhere((w) => !own.contains(w));
        if (i < 0) break;
        shown.removeAt(i);
      }
      locked = cached == null ? own : {...own, ...shown};
    }
    final sel = selector.select(
      pool: _pool,
      target: _target,
      profile: repo.profile,
      studying: studying,
      removed: removed,
      current: shown,
      locked: locked,
      bias: _bias,
      fresh: fresh,
      relaxNounCap: _nounsAsked,
      now: repo.clock(),
    );
    // 問題回報 #852: a word coming back to the list is the same entry (its
    // pin where it was), not a new one.
    for (final w in words) {
      _seen[w.word] = w;
    }
    final byWord = {..._seen};
    words = [
      for (final c in sel.words)
        byWord[c.word] ??
            // 問題回報 #703 / Windows 卡 #631: a word the recognizer could
            // not place is listed with no pin (saved unplaced).
            SessionWord(c, c.point, placed: c.grounded)
    ];
    _selection = sel;
    _shownAt[_target] = [for (final w in words) w.word];
    if (repick || fresh.isNotEmpty) _home = _shownAt[_target]!;
    if (allowTopUp) _maybeTopUp(sel);
  }

  /// 問題回報 #691: whether the recognizer has had its chance to add
  /// words other than nouns (or can't be asked): then the three-noun cap
  /// gives way rather than leave the list short.
  bool get _nounsAsked {
    final q = queue;
    final p = photo;
    if (p == null) return false;
    if (q == null || !q.canAskMore(p)) return true;
    return !q.isToppingUp(photoId) && !q.canTopUp(p, 'actions');
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
        // Even with nothing new, the list is picked again: the nouns held
        // back for this request may now fill it (問題回報 #691).
        if (!_disposed && (added > 0 || words.length < WordSelector.maxWords)) {
          final before = [for (final w in words) w.word];
          _reselect();
          if (added > 0 ||
              !listEquals(before, [for (final w in words) w.word])) {
            _dirty = true;
            notifyListeners();
          }
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

  /// Moves the dial. Only the photo's existing candidates are used — the
  /// AI is never asked again by a dial move (問題回報 #1154, which
  /// supersedes the harder/easier rescans of #666, #671).
  void setTarget(int level, {bool live = false}) {
    final t = level.clamp(0, cefrLevels.length - 1);
    if (t == _target && live) return;
    final from = _target;
    _target = t;
    if (t != from) _dialMoved = true;
    _dirty = true;
    if (live || t == from) {
      _reselect(allowTopUp: !live);
    } else {
      // 問題回報 #1154: a step on the bar only picks from the words the AI
      // already found — no new scan. The AI reads the photo again only on
      // 重新掃描, a long press on the photo, or when the photo is taken.
      _reselect();
    }
    notifyListeners();
  }

  /// 更多動作 / 更多描述 (tap again to turn off). Turning one on brings
  /// that kind into the list and asks 照片辨識 for more of it every time
  /// (問題回報 #666, #671) — also for downloaded deck pictures; what it
  /// finds is swapped in, and the learner is told when there is none.
  void setBias(PosBias b) {
    _bias = _bias == b ? PosBias.none : b;
    _dirty = true;
    // 問題回報 #852: another kind of word asked for — every position is
    // picked again (once) with it.
    if (_bias == PosBias.none) {
      _reselect(allowTopUp: true, repick: true);
    } else {
      final before = _shownOfBias();
      _reselect(repick: true);
      final asked = _bias;
      _askForMore(asked == PosBias.actions ? 'actions' : 'descriptions',
          () => _bias == asked && _shownOfBias().difference(before).isNotEmpty,
          stillWanted: () => _bias == asked);
    }
    notifyListeners();
  }

  /// The listed words of the kind [bias] asks for.
  Set<String> _shownOfBias() => {
        for (final w in words)
          if (_bias == PosBias.actions
              ? w.candidate.isAction
              : _bias == PosBias.descriptions && w.candidate.isDescription)
            w.word,
      };

  /// Asks the recognizer for more words of [focus] because the learner
  /// asked for them; [improved] says whether the list then shows some.
  /// What arrives is swapped into the list while [stillWanted] (the
  /// learner hasn't turned it off or moved on). A tap while the same kind
  /// is being fetched joins that request.
  void _askForMore(String focus, bool Function() improved,
      {required bool Function() stillWanted, bool swapIn = true}) {
    final what = focusLabel(focus);
    final q = queue;
    final p = photo;
    if (q == null || p == null || !q.canAskMore(p)) {
      if (!improved()) _notice('這張照片沒有更多$what了，連上照片辨識後可以再找');
      return;
    }
    if (_fetching == focus) return;
    _fetching = focus;
    final level = targetLevel;
    Future<void>.microtask(() async {
      String? message;
      try {
        final pool = {
          for (final c in photo?.candidates ?? const <WordCandidate>[]) c.word,
        };
        final added =
            await q.topUp(photoId, focus: focus, level: level, again: true);
        if (_disposed) return;
        final fresh = {
          for (final c in photo?.candidates ?? const <WordCandidate>[])
            if (!pool.contains(c.word)) c.word,
        };
        if (swapIn && fresh.isNotEmpty && stillWanted()) {
          _reselect(fresh: fresh);
          _dirty = true;
        } else if (added > 0) {
          _reselect();
        }
        if (!improved()) message = '這張照片沒有更多$what了';
      } catch (e) {
        debugPrint('Top-up for $photoId failed: $e');
        message = '連不到照片辨識，暫時找不到更多$what，稍後再試';
      }
      if (_disposed) return;
      if (_fetching == focus) _fetching = null;
      notifyListeners();
      if (message != null) _notice(message);
    });
  }

  /// 重新掃描標籤 (問題回報 #670): the whole photo is read again. New words
  /// join the pool and the list is picked again — words already there and
  /// the learner's own (starred, corrected, added) stay — and the learner
  /// is told how many arrived.
  Future<void> rescan() async {
    final q = queue;
    final p = photo;
    if (_rescanning || q == null || p == null) return;
    if (!q.canRescan(p)) {
      _notice('這台裝置還沒有照片辨識，請到「設定」連上照片辨識後再重新掃描');
      return;
    }
    _rescanning = true;
    notifyListeners();
    String message;
    try {
      final fresh = await q.rescan(photoId);
      if (_disposed) return;
      if (fresh.isEmpty) {
        message = '重新掃描完成，沒有新的單字';
      } else {
        _reselect(fresh: fresh.toSet());
        _dirty = true;
        message = '重新掃描完成，新增了 ${fresh.length} 個單字';
      }
    } catch (e) {
      debugPrint('Rescan of $photoId failed: $e');
      message = e is TaggingNotConfigured
          ? '這台裝置還沒有照片辨識，請到「設定」連上照片辨識後再重新掃描'
          : '連不到照片辨識，暫時無法重新掃描，稍後再試';
    } finally {
      _rescanning = false;
    }
    if (_disposed) return;
    notifyListeners();
    _notice(message);
  }

  void _notice(String message) => onNotice?.call(message);

  void toggleStar(SessionWord w) {
    w.starred = !w.starred;
    notifyListeners();
  }

  /// 卡 #835 單字收集區: the starred words, in list order.
  List<SessionWord> get collected => [
        for (final w in words)
          if (w.starred) w
      ];

  /// A label dragged into the 單字收集區 (or a word starred by hand).
  void collect(SessionWord w) {
    if (w.starred) return;
    w.starred = true;
    notifyListeners();
  }

  /// 修改標籤 (spec: AI 英文標籤「可改」; 問題回報 #323): another word or
  /// meaning for this spot. A new word is looked up again — lemma, sense
  /// and lexeme id from the language pack, [level] from the CEFR list — and
  /// the AI's word is never offered on this photo again. A meaning left as
  /// it was (the old word's) or blank takes the pack's; a typed one is the
  /// learner's and background updates leave it alone.
  void correct(SessionWord w,
      {required String word, required String meaning, String? level}) {
    final normalized = LexiconPack.normalize(word);
    if (normalized.isEmpty) return;
    final c = w.candidate;
    final typed = meaning.trim();
    if (normalized == c.word) {
      if (typed.isEmpty || typed == c.meaning) return;
      w.candidate = c.copyWith(meaning: typed);
      w.ownMeaning = true;
    } else {
      final relinked = _lookUp(
        normalized,
        pos: normalized.contains(' ') ? 'phrase' : c.pos,
        meaning: typed == c.meaning ? '' : typed,
        level: level,
        point: c.point,
        evidence: c.evidence,
        visualConfidence: c.visualConfidence,
      ).copyWith(grounded: c.grounded);
      if (words.any((o) => o != w && o.word == relinked.word)) {
        // Already on the list: the wrong label just goes.
        delete(w);
        return;
      }
      w.candidate = relinked;
      w.ownMeaning = typed.isNotEmpty && typed != c.meaning;
      if (w.aiLabel != relinked.word) _rejected.add(w.aiLabel);
      _rejected.remove(relinked.word);
    }
    w.edited = true;
    _dirty = true;
    notifyListeners();
  }

  /// [word] as a candidate linked to the pack (a form leads to its lemma).
  WordCandidate _lookUp(String word,
      {required String pos,
      required String meaning,
      String? level,
      required LabelPoint point,
      String evidence = '',
      double visualConfidence = 1.0}) {
    final hit = pack.lookup(word, pos: pos);
    // No pack downloaded yet: nothing to link, and nothing is "missing".
    WordCandidate link(WordCandidate c) => pack.isEmpty ? c : pack.link(c);
    final c = link(WordCandidate(
      word: word,
      pos: hit == null ? pos : _appPos(hit.entry.pos, pos),
      meaning: meaning,
      level: level ?? hit?.entry.cefr ?? 'B1',
      levelSource: level == null && hit?.entry.cefr == null ? 'ai' : 'cefr-j',
      zipf: hit?.entry.zipf,
      ipa: hit?.entry.ipa,
      evidence: evidence,
      point: point,
      visualConfidence: visualConfidence,
      usefulness: 0.8,
    ));
    // The learner's meaning wins over the pack's.
    return meaning.isEmpty ? c : c.copyWith(meaning: meaning);
  }

  static String _appPos(String packPos, String fallback) => switch (packPos) {
        'noun' || 'verb' || 'phrase' => packPos,
        'adj' => 'adj.',
        'adv' => 'adv.',
        _ => fallback,
      };

  /// 刪掉錯的 (問題回報 #323): the label is wrong — not "already known", so
  /// nothing is marked 已學會 and the word stays out of this photo.
  void delete(SessionWord w) {
    words.remove(w);
    if (!w.added) _rejected.add(w.aiLabel);
    _rejected.add(w.word);
    _dirty = true;
    _reselect(allowTopUp: true);
    notifyListeners();
  }

  /// 自己加字 (問題回報 #323): a word the AI missed. [at] is where the
  /// learner tapped on the photo; without it the word has no pin. It is
  /// looked up in the pack like a recognized word (a missing-word request
  /// when the pack lacks it) and becomes a card when the page is left.
  /// Returns the word as listed, or null when [word] is blank.
  SessionWord? add(
      {required String word,
      String meaning = '',
      String? level,
      LabelPoint? at}) {
    final normalized = LexiconPack.normalize(word);
    if (normalized.isEmpty) return null;
    final c = _lookUp(
      normalized,
      pos: normalized.contains(' ') ? 'phrase' : 'noun',
      meaning: meaning.trim(),
      level: level,
      point: at ?? const LabelPoint(0.5, 0.5),
    );
    final existing = words.where((w) => w.word == c.word).firstOrNull;
    if (existing != null) {
      if (at != null) move(existing, at);
      return existing;
    }
    _rejected.remove(c.word);
    _removed.remove(c.word);
    final w = SessionWord(c, c.point, added: true, placed: at != null)
      ..edited = meaning.trim().isNotEmpty
      ..ownMeaning = meaning.trim().isNotEmpty;
    words.add(w);
    _dirty = true;
    notifyListeners();
    return w;
  }

  /// 長按辨識 (問題回報 #616): a word the AI found at [at], pinned there.
  /// The learner chose it (like 自己加字), but its meaning stays the
  /// pack's / AI's, not one the learner typed. A word already on the
  /// photo moves to [at]. With no [at] (a whole-picture word picked from
  /// the 詞性 × CEFR grid, 問題回報 #703) it is listed without a pin.
  SessionWord addFound(WordCandidate found, LabelPoint? at) {
    final existing = words.where((w) => w.word == found.word).firstOrNull;
    if (existing != null) {
      if (at != null) move(existing, at);
      return existing;
    }
    // A real spot: grounded there whatever the crop's reply said (#703).
    final linked = pack.isEmpty ? found : pack.link(found);
    final c = at == null ? linked : linked.copyWith(point: at, grounded: true);
    _rejected.remove(c.word);
    _removed.remove(c.word);
    final w = SessionWord(c, c.point, added: true, placed: at != null);
    words.add(w);
    _dirty = true;
    notifyListeners();
    return w;
  }

  void move(SessionWord w, LabelPoint anchor) {
    w.anchor = anchor;
    w.placed = true;
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
      out.add(OldWord(_candidateFor(e, o), o.anchor,
          learned: true, placed: o.placed));
    }
    final learned = repo.profile.learned;
    final studying = _studyingElsewhere;
    for (final c in photo?.candidates ?? const <WordCandidate>[]) {
      if (seen.contains(c.word) || words.any((w) => w.word == c.word)) continue;
      if (learned.contains(c.word)) {
        seen.add(c.word);
        out.add(OldWord(c, c.point, learned: true, placed: c.grounded));
      } else if (studying.contains(c.word)) {
        seen.add(c.word);
        out.add(OldWord(c, c.point, learned: false, placed: c.grounded));
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
      words.add(SessionWord(o.candidate, o.anchor, placed: o.placed));
    }
    _rejected.remove(o.word);
    _dirty = true;
    notifyListeners();
  }

  /// What leaving the page does. Returns the words created (to fetch
  /// their full data) and whether the photo was removed.
  ({List<WordEntry> created, bool photoRemoved}) save() {
    var p = photo;
    if (p == null || (!_dirty && p.wordsSavedAt != null)) {
      return (created: const [], photoRemoved: false);
    }
    if (!setEquals(_rejected, p.rejectedWords.toSet())) {
      p = p.copyWith(rejectedWords: [..._rejected]..sort());
      repo.updatePhoto(p);
    }
    // Still waiting for the tagger: nothing to save yet, so the list is
    // picked fresh when the candidates arrive.
    // A tagged photo whose words are all being studied from other photos
    // still saves them as its contexts (spec: 新照片只加入該單字的照片情境;
    // 問題回報 #120) — only an untagged or truly empty one returns here.
    final knownHere =
        p.candidates.any((c) => _studyingElsewhere.contains(c.word));
    if (words.isEmpty && !_removedAny && p.wordsSavedAt == null && !knownHere) {
      // Tagged, but the dial left nothing to learn at this level: keep the
      // dial for this photo (spec: 輪盤選擇只保存為此照片的
      // difficultyOffset), so reopening shows the same empty level.
      if (p.candidates.isNotEmpty &&
          _dialMoved &&
          offset != p.difficultyOffset) {
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
          ListedWord(c, c.point, placed: c.grounded),
    ];
    // The opening position (see _openingTarget) is not the learner's choice.
    final savedOffset = _dialMoved ? offset : p.difficultyOffset;
    if (_dialMoved && offset != p.difficultyOffset && offset != 0) {
      repo.recordSignal(DialSignal(offset));
    }
    final created = repo.savePhotoWords(
      photoId,
      [
        // 卡 #835: once the learner has collected words, only those go to
        // the word book; with none collected the whole list is saved as before.
        for (final w in words)
          if (w.starred || !words.any((x) => x.starred))
            ListedWord(w.candidate, w.anchor,
                aiLabel: w.edited ? w.aiLabel : null,
                edited: w.edited,
                added: w.added,
                placed: w.placed,
                ownMeaning: w.ownMeaning),
      ],
      difficultyOffset: savedOffset,
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
