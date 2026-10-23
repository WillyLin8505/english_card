import 'dart:math' as math;

import '../models/vocabulary_profile.dart';
import '../models/word_candidate.dart';
import '../models/word_entry.dart';

/// 「更多動作」/「更多描述」 on the photo-detail list.
enum PosBias { none, actions, descriptions }

/// One candidate with its recommendation score and, if it can't be
/// shown, why (spec: 推薦分數、淘汰原因 — 保存排序依據，方便除錯並解釋為何
/// 出現或未出現).
class ScoredCandidate {
  final WordCandidate candidate;

  /// The spec's parts, each 0–1.
  final double levelFit;
  final double unknown;
  final double relevance;
  final double usefulness;
  final double penalty;

  /// Score before the part-of-speech diversity term, which depends on
  /// what else is picked.
  final double base;
  final String? rejected;

  const ScoredCandidate({
    required this.candidate,
    required this.levelFit,
    required this.unknown,
    required this.relevance,
    required this.usefulness,
    required this.penalty,
    required this.base,
    this.rejected,
  });

  String get word => candidate.word;

  /// 推薦分數 with a given diversity term (0–1).
  double score(double diversity) => base + 0.10 * diversity;

  String explain() => [
        '${candidate.level}（${_sourceLabel(candidate.levelSource)}）',
        '程度適配 ${(levelFit * 100).round()}%',
        '未知機率 ${(unknown * 100).round()}%',
        '圖片關聯 ${(relevance * 100).round()}%',
        '實用 ${(usefulness * 100).round()}%',
        if (penalty > 0) '近期出現 −${(penalty * 100).round()}',
      ].join(' · ');

  static String _sourceLabel(String source) => switch (source) {
        'cefr-j' => '本機詞表',
        'frequency' => '詞頻',
        'user' => '自訂',
        _ => 'AI 估計',
      };
}

class Selection {
  /// At most five words, in list order.
  final List<WordCandidate> words;

  /// Every candidate, best first, with scores and rejection reasons.
  final List<ScoredCandidate> scored;

  /// Set when the pool has too few suitable candidates for this level:
  /// the focus (harder / easier / actions / descriptions) to ask the
  /// model for more (候選不足才重新呼叫模型).
  final String? topUp;

  const Selection(this.words, this.scored, this.topUp);
}

/// Stage 2 of the spec's recognition (第二階段 · 選擇學習詞): re-scores
/// the model's candidates on this device and picks at most five.
///
///   推薦分數 = 30% 程度適配 + 25% 未知機率 + 20% 圖片關聯性
///            + 15% 日常實用性 + 10% 詞性多樣性 − 重複與近期曝光懲罰
///
/// Hard rules: at most 5 words and 3 nouns; synonyms and one word family
/// keep one member; learned words and words already being studied from
/// other photos are not offered; starred words stay; when the level
/// changes, words that still fit (same or adjacent level) stay and only
/// the clearly unsuitable ones are replaced (保留跨級詞). If too few
/// candidates are good enough, fewer than five are shown (不強行湊滿).
class WordSelector {
  static const maxWords = 5;
  static const maxNouns = 3;

  /// How many words of the asked-for kind 多看動詞／多看形容詞 brings in.
  static const biasWords = 2;
  static const minScore = 0.38;

  const WordSelector();

  static double levelFit(int candidateLevel, int target) =>
      switch (candidateLevel - target) {
        0 => 1.0,
        1 => 0.75,
        -1 => 0.6,
        2 => 0.3,
        -2 => 0.2,
        _ => 0.0,
      };

  static String _posClass(WordCandidate c) => c.isNoun
      ? 'noun'
      : c.isAction
          ? 'action'
          : c.isDescription
              ? 'description'
              : 'phrase';

  static const _suffixes = [
    'ingly', 'edly', 'ness', 'ment', 'ing', 'ers', 'ies', 'ed', 'er', 'ly',
    'es', 's', 'e', //
  ];

  /// A rough stem: the word without one common suffix.
  static String stem(String word) {
    for (final s in _suffixes) {
      if (word.endsWith(s) && word.length - s.length >= 3) {
        return word.substring(0, word.length - s.length);
      }
    }
    return word;
  }

  /// Synonyms (same native gloss) or one word family (bake / baker /
  /// baking) — spec: 同義詞或同詞族通常只留一個.
  static bool related(WordCandidate a, WordCandidate b) {
    if (a.word == b.word || a.lemma == b.lemma) return true;
    if (a.meaning.isNotEmpty && a.meaning == b.meaning) return true;
    if (a.word.contains(' ') || b.word.contains(' ')) return false;
    if (stem(a.word) == stem(b.word)) return true;
    final n = math.min(a.word.length, b.word.length);
    var common = 0;
    while (common < n && a.word[common] == b.word[common]) {
      common++;
    }
    return common >= 5 &&
        a.word.length - common <= 3 &&
        b.word.length - common <= 3;
  }

  Selection select({
    required List<WordCandidate> pool,
    required int target,
    required UserVocabularyProfile profile,
    Set<String> studying = const {},
    Set<String> removed = const {},
    List<String> current = const [],
    Set<String> locked = const {},
    PosBias bias = PosBias.none,
    Set<String> fresh = const {},
    required DateTime now,
  }) {
    final learned = profile.learned;
    final scored = <ScoredCandidate>[];
    for (final c in pool) {
      final lf = levelFit(levelIndex(c.level), target);
      final unknown = profile.unknownProbability(c.word, c.level);
      final relevance = c.visualConfidence * (c.inferred ? 0.7 : 1.0);
      final freq =
          c.zipf == null ? c.usefulness : ((c.zipf! - 2) / 4).clamp(0.0, 1.0);
      final usefulness = 0.6 * c.usefulness + 0.4 * freq;
      final exp = profile.exposure[c.word];
      final recent = exp != null &&
          !current.contains(c.word) &&
          now.difference(exp.last).inDays < 14;
      final penalty = recent ? math.min(0.15, 0.05 * exp.count) : 0.0;
      final bonus = switch (bias) {
        PosBias.actions when c.isAction => 0.12,
        PosBias.descriptions when c.isDescription => 0.12,
        _ => 0.0,
      };
      final String? rejected =
          learned.contains(c.word) && !locked.contains(c.word)
              ? '已學會'
              : studying.contains(c.word)
                  ? '已在學習（其他照片）'
                  : removed.contains(c.word)
                      ? '本次已移除'
                      : c.visualConfidence < 0.3 && !locked.contains(c.word)
                          ? '與照片關聯太低'
                          : null;
      scored.add(ScoredCandidate(
        candidate: c,
        levelFit: lf,
        unknown: unknown,
        relevance: relevance,
        usefulness: usefulness,
        penalty: penalty,
        base: 0.30 * lf +
            0.25 * unknown +
            0.20 * relevance +
            0.15 * usefulness -
            penalty +
            bonus,
        rejected: rejected,
      ));
    }
    scored.sort((a, b) => b.base.compareTo(a.base));
    final byWord = {for (final s in scored) s.word: s};

    // Slots follow the current list so words that stay don't jump.
    final slots = <ScoredCandidate?>[];
    for (final w in current) {
      final s = byWord[w];
      if (s == null) continue;
      final keep =
          locked.contains(w) || (s.rejected == null && s.levelFit >= 0.6);
      slots.add(keep ? s : null);
    }
    List<ScoredCandidate> picked() =>
        slots.whereType<ScoredCandidate>().toList();

    double diversity(ScoredCandidate s) {
      final cls = _posClass(s.candidate);
      final same =
          picked().where((p) => p != s && _posClass(p.candidate) == cls).length;
      return same == 0 ? 1.0 : (same == 1 ? 0.5 : 0.0);
    }

    bool allowed(ScoredCandidate s,
        {ScoredCandidate? replacing, bool nounCap = true}) {
      if (s.rejected != null) return false;
      final others = picked().where((p) => p != replacing).toList();
      if (others.contains(s)) return false;
      if (others.any((p) => related(p.candidate, s.candidate))) return false;
      if (nounCap &&
          s.candidate.isNoun &&
          others.where((p) => p.candidate.isNoun).length >= maxNouns) {
        return false;
      }
      return true;
    }

    ScoredCandidate? best(
        {ScoredCandidate? replacing, bool Function(ScoredCandidate)? where}) {
      ScoredCandidate? top;
      var topScore = -1.0;
      for (final s in scored) {
        if (where != null && !where(s)) continue;
        if (!allowed(s, replacing: replacing)) continue;
        final sc = s.score(diversity(s));
        if (sc >= minScore && sc > topScore) {
          top = s;
          topScore = sc;
        }
      }
      return top;
    }

    // Fill emptied slots in place, then append.
    for (var i = 0; i < slots.length; i++) {
      if (slots[i] == null) slots[i] = best();
    }
    while (picked().length < maxWords) {
      final s = best();
      if (s == null) break;
      slots.add(s);
    }
    slots.removeWhere((s) => s == null);

    // 問題回報 #442: every position shows five labels when the photo has
    // them. Short of five, take the nearest levels whatever their fit score:
    // the next level easier first, then the next harder, and so on.
    int distance(ScoredCandidate s) {
      final lv = levelIndex(s.candidate.level);
      return (lv - target).abs() * 2 + (lv > target ? 1 : 0);
    }

    final nearest = [...scored]..sort((a, b) {
        final d = distance(a).compareTo(distance(b));
        return d != 0 ? d : b.base.compareTo(a.base);
      });
    for (final s in nearest) {
      if (picked().length >= maxWords) break;
      if (s.rejected != null || !allowed(s)) continue;
      slots.add(s);
    }

    bool isLocked(ScoredCandidate s) => locked.contains(s.word);
    ScoredCandidate? weakest(bool Function(ScoredCandidate) where) {
      ScoredCandidate? w;
      for (final s in picked()) {
        if (isLocked(s) || !where(s)) continue;
        if (w == null || s.score(diversity(s)) < w.score(diversity(w))) w = s;
      }
      return w;
    }

    // At least two parts of speech when the photo allows it.
    final classes = {for (final s in picked()) _posClass(s.candidate)};
    if (picked().length >= 3 && classes.length == 1) {
      final out = weakest((_) => true);
      final alt = out == null
          ? null
          : best(
              replacing: out,
              where: (s) => _posClass(s.candidate) != classes.first);
      if (out != null && alt != null) slots[slots.indexOf(out)] = alt;
    }
    // 多看動詞／多看形容詞 (問題回報 #666): the asked-for kind gets in even
    // when the list is full — the words already shown must not block it.
    bool wanted(ScoredCandidate s) => switch (bias) {
          PosBias.actions => s.candidate.isAction,
          PosBias.descriptions => s.candidate.isDescription,
          PosBias.none => false,
        };
    if (bias != PosBias.none) {
      while (picked().where(wanted).length < biasWords) {
        if (picked().length < maxWords) {
          final c = best(where: wanted);
          if (c == null) break;
          slots.add(c);
          continue;
        }
        final out = weakest((s) => !wanted(s));
        final c = out == null ? null : best(replacing: out, where: wanted);
        if (out == null || c == null) break;
        slots[slots.indexOf(out)] = c;
      }
    }
    // 問題回報 #670/#671: words the recognizer just found because the learner
    // asked (多看動詞, 難一點, 重新掃描) take the weakest unlocked places —
    // up to [biasWords] of them — so the tap visibly changes the list.
    bool isFresh(ScoredCandidate s) => fresh.contains(s.word);
    if (fresh.isNotEmpty) {
      var brought = picked().where(isFresh).length;
      for (final s in scored) {
        if (brought >= biasWords) break;
        if (!isFresh(s) || s.rejected != null || picked().contains(s)) {
          continue;
        }
        if (!wanted(s) && s.levelFit < 0.6) continue;
        if (picked().length < maxWords) {
          if (!allowed(s)) continue;
          slots.add(s);
          brought++;
          continue;
        }
        // A new word of the asked-for kind replaces an older one of that
        // kind once enough are shown, so the other kinds stay; anything
        // else replaces a word of another kind.
        final out = wanted(s) && picked().where(wanted).length >= biasWords
            ? weakest((p) => !isFresh(p) && wanted(p)) ??
                weakest((p) => !isFresh(p))
            : weakest((p) => !isFresh(p) && !wanted(p)) ??
                (wanted(s) ? weakest((p) => !isFresh(p)) : null);
        if (out == null) break;
        // A noun for a noun doesn't add one (deck pictures start over the cap).
        if (!allowed(s, replacing: out, nounCap: !out.candidate.isNoun)) {
          continue;
        }
        slots[slots.indexOf(out)] = s;
        brought++;
      }
    }
    // One challenge word (挑戰詞) above the target level.
    if (!picked().any((s) => levelIndex(s.candidate.level) > target)) {
      bool harder(ScoredCandidate s) => levelIndex(s.candidate.level) > target;
      if (picked().length < maxWords) {
        final c = best(where: harder);
        if (c != null) slots.add(c);
      } else {
        final out = weakest((s) =>
            levelIndex(s.candidate.level) <= target &&
            !wanted(s) &&
            !isFresh(s));
        final c = out == null ? null : best(replacing: out, where: harder);
        if (out != null && c != null) slots[slots.indexOf(out)] = c;
      }
    }

    final words = [for (final s in picked()) s.candidate];

    // Too few good words at this level → ask the model for more.
    String? topUp;
    final spare =
        scored.where((s) => s.rejected == null && s.levelFit >= 0.6).length;
    if (words.length < 3 || spare <= words.length) {
      final levels = [for (final c in pool) levelIndex(c.level)]..sort();
      final median = levels.isEmpty ? target : levels[levels.length ~/ 2];
      topUp = switch (bias) {
        PosBias.actions => 'actions',
        PosBias.descriptions => 'descriptions',
        PosBias.none =>
          target > median ? 'harder' : (target < median ? 'easier' : null),
      };
      if (topUp == null && words.length < 3) topUp = 'harder';
    }
    // A vision reply can satisfy the requested 6–8 candidates while still
    // returning only nouns.  The three-noun cap then leaves empty learning
    // slots, but the old "spare" check saw the unused nouns and incorrectly
    // decided that no top-up was needed. Ask specifically for another part
    // of speech; do not weaken the noun cap or pad the list with more nouns.
    final nounCount = words.where((c) => c.isNoun).length;
    if (topUp == null && words.length < maxWords && nounCount >= maxNouns) {
      topUp = bias == PosBias.descriptions ? 'descriptions' : 'actions';
    }
    // The whole pool is short of five labels: all of them show, and the
    // model is asked for more in the background (問題回報 #442).
    if (topUp == null && pool.length < maxWords) topUp = 'harder';
    return Selection(words, scored, topUp);
  }
}
