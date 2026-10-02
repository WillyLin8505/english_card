import 'dart:math' as math;

import 'word_entry.dart';

/// 個人詞彙狀態 (spec section 3): 未知、正在學、熟悉、已掌握. 「看過」不等
/// 於「已知」, so seeing a word never moves it past [unknown] on its own.
enum Familiarity { unknown, learning, familiar, mastered }

/// How often a word was offered on a photo's list recently (近期曝光).
class Exposure {
  final int count;
  final DateTime last;

  const Exposure(this.count, this.last);

  factory Exposure.fromJson(Map<String, dynamic> j) =>
      Exposure(j['count'] as int, DateTime.parse(j['last'] as String));

  Map<String, dynamic> toJson() =>
      {'count': count, 'last': last.toIso8601String()};
}

/// One behaviour that says something about the learner's level (spec
/// section 7: 輪盤調高／調低、左滑同級已知詞與 Flashcard 評分都是訊號).
sealed class AbilitySignal {
  const AbilitySignal();
}

/// The dial moved [steps] levels away from the suggested level for a
/// photo: up = the words felt too easy.
class DialSignal extends AbilitySignal {
  final int steps;
  const DialSignal(this.steps);
}

/// A word at [level] was swiped away as already known.
class KnownWordSignal extends AbilitySignal {
  final String level;
  const KnownWordSignal(this.level);
}

/// A flashcard for a word at [level] was graded: [recalled] for Hard,
/// Good and Easy; [strength] is 0 (Again) … 1 (Easy).
class RecallSignal extends AbilitySignal {
  final String level;
  final double strength;
  final double? expectedRecall;

  /// [expectedRecall] is FSRS's prediction for an already-scheduled card.
  /// Routine success near that prediction should barely move language level;
  /// surprising success or failure remains a useful ability signal.
  const RecallSignal(this.level, this.strength, {this.expectedRecall});
}

/// Spec section 3's UserVocabularyProfile, kept apart from FSRS card
/// state: FSRS decides when a card comes back; this decides how hard the
/// words suggested for a photo should be (FSRS 只決定卡片何時再出現；Elo
/// 能力模型決定照片應推薦多難的詞).
///
/// Ability is an Elo-style continuous score, A1 = 0 … C2 = 5:
///   能力更新 = 舊能力分數 + K × (實際表現 − 預期表現)
/// Dial moves use a small K, active recall a larger one. The level only
/// changes after 20 valid signals, once a moving average has crossed the
/// next level's threshold by 0.2, and by one level at a time.
class UserVocabularyProfile {
  static const minEvents = 20;
  static const buffer = 0.2;
  static const kDial = 0.03;
  static const kKnown = 0.05;
  static const kRecall = 0.08;
  // Scheduled reviews repeat the same cards and are highly correlated.  They
  // remain useful evidence, but must not outweigh first encounters and the
  // learner's difficulty-dial choices simply through repetition.
  static const kScheduledRecall = 0.005;
  static const _smoothing = 0.2;

  /// Raw Elo score and its moving average (移動平均).
  final double ability;
  final double smoothed;

  /// Index into [cefrLevels] — the overall level (整體程度).
  final int level;

  /// Valid signals so far.
  final int events;

  /// How the level was estimated: 'self' (自評), 'check' (快速詞彙檢查),
  /// 'elo' (behaviour) or 'user' (set in 設定).
  final String source;

  /// Per-word state, by normalized word.
  final Map<String, Familiarity> familiarity;
  final Map<String, Exposure> exposure;

  /// Parts of speech the learner keeps (詞性偏好).
  final Map<String, int> posPreference;

  /// The last photos' dial offsets, newest last — used to suggest a new
  /// default level when the learner keeps turning the dial one way.
  final List<int> dialHistory;

  final DateTime updatedAt;

  const UserVocabularyProfile({
    required this.ability,
    required this.smoothed,
    required this.level,
    this.events = 0,
    this.source = 'self',
    this.familiarity = const {},
    this.exposure = const {},
    this.posPreference = const {},
    this.dialHistory = const [],
    required this.updatedAt,
  });

  /// A learner starting at [level] (the middle of that band).
  factory UserVocabularyProfile.start(String level,
      {String source = 'self', DateTime? now}) {
    final i = levelIndex(level);
    return UserVocabularyProfile(
      ability: i + 0.5,
      smoothed: i + 0.5,
      level: i,
      source: source,
      updatedAt: now ?? DateTime.now(),
    );
  }

  String get cefr => cefrLevels[level];

  /// Words swiped away as known — the language's 已學會 list.
  Set<String> get learned => {
        for (final e in familiarity.entries)
          if (e.value == Familiarity.mastered) e.key,
      };

  Familiarity familiarityOf(String word) =>
      familiarity[word] ?? Familiarity.unknown;

  /// Chance the learner doesn't know a word at [wordLevel] yet (未知機率).
  double unknownProbability(String word, String wordLevel) {
    switch (familiarityOf(word)) {
      case Familiarity.mastered:
        return 0;
      case Familiarity.familiar:
        return 0.25;
      case Familiarity.learning:
        return 0.6;
      case Familiarity.unknown:
        final d = levelIndex(wordLevel) + 0.5 - ability;
        return 1 / (1 + math.exp(-1.4 * d));
    }
  }

  /// Chance a learner at [ability] handles a word at [wordLevel].
  static double expected(double ability, String wordLevel) =>
      1 / (1 + math.exp(-1.4 * (ability - (levelIndex(wordLevel) + 0.5))));

  /// Applies one signal.
  UserVocabularyProfile update(AbilitySignal signal, DateTime now) {
    final double delta = switch (signal) {
      DialSignal(:final steps) => kDial * steps.clamp(-2, 2),
      KnownWordSignal(:final level) => kKnown * (1 - expected(ability, level)),
      RecallSignal(:final level, :final strength, :final expectedRecall) =>
        (expectedRecall == null ? kRecall : kScheduledRecall) *
            (strength -
                (expectedRecall ?? expected(ability, level)).clamp(0.0, 1.0)),
    };
    final nextAbility = (ability + delta).clamp(0.0, 5.99);
    final nextSmoothed = smoothed + _smoothing * (nextAbility - smoothed);
    final nextEvents = events + 1;
    var nextLevel = level;
    if (nextEvents >= minEvents) {
      if (nextSmoothed >= level + 1 + buffer && level < cefrLevels.length - 1) {
        nextLevel = level + 1;
      } else if (nextSmoothed < level - buffer && level > 0) {
        nextLevel = level - 1;
      }
    }
    return _copy(
      ability: nextAbility,
      smoothed: nextSmoothed,
      level: nextLevel,
      events: nextEvents,
      source: nextLevel != level ? 'elo' : source,
      dialHistory: signal is DialSignal ? dialHistory : null,
      updatedAt: now,
    );
  }

  /// Sets the level by hand (設定) or from onboarding; the score restarts
  /// in the middle of that band.
  UserVocabularyProfile withLevel(String cefr, String source, DateTime now) {
    final i = levelIndex(cefr);
    return _copy(
        ability: i + 0.5,
        smoothed: i + 0.5,
        level: i,
        source: source,
        // The dial offsets were relative to the old level: after 改成 B1 the
        // same history would at once suggest B2 as well.
        dialHistory: const [],
        updatedAt: now);
  }

  UserVocabularyProfile withFamiliarity(
          String word, Familiarity f, DateTime now) =>
      _copy(familiarity: {...familiarity, word: f}, updatedAt: now);

  UserVocabularyProfile withoutFamiliarity(String word, DateTime now) =>
      _copy(familiarity: {...familiarity}..remove(word), updatedAt: now);

  /// Records that [words] were offered on a photo's list.
  UserVocabularyProfile exposed(Iterable<String> words, DateTime now) => _copy(
        exposure: {
          ...exposure,
          for (final w in words)
            w: Exposure((exposure[w]?.count ?? 0) + 1, now),
        },
        updatedAt: now,
      );

  UserVocabularyProfile keptPos(Iterable<String> pos, DateTime now) => _copy(
        posPreference: {
          ...posPreference,
          for (final p in pos) p: (posPreference[p] ?? 0) + 1,
        },
        updatedAt: now,
      );

  /// Records the dial offset a photo was left at (last 8 photos).
  UserVocabularyProfile dialled(int offset, DateTime now) {
    final history = [...dialHistory, offset];
    return _copy(
      dialHistory:
          history.length > 8 ? history.sublist(history.length - 8) : history,
      updatedAt: now,
    );
  }

  /// +1 / −1 when the learner kept choosing harder / easier words on at
  /// least 5 of the last 8 photos (spec: 若使用者經常選擇更難或更簡單，系統
  /// 才提出調整預設程度的建議), else 0.
  int get suggestedShift {
    if (dialHistory.length < 5) return 0;
    final up = dialHistory.where((o) => o > 0).length;
    final down = dialHistory.where((o) => o < 0).length;
    if (up >= 5 && level < cefrLevels.length - 1) return 1;
    if (down >= 5 && level > 0) return -1;
    return 0;
  }

  UserVocabularyProfile _copy({
    double? ability,
    double? smoothed,
    int? level,
    int? events,
    String? source,
    Map<String, Familiarity>? familiarity,
    Map<String, Exposure>? exposure,
    Map<String, int>? posPreference,
    List<int>? dialHistory,
    required DateTime updatedAt,
  }) =>
      UserVocabularyProfile(
        ability: ability ?? this.ability,
        smoothed: smoothed ?? this.smoothed,
        level: level ?? this.level,
        events: events ?? this.events,
        source: source ?? this.source,
        familiarity: familiarity ?? this.familiarity,
        exposure: exposure ?? this.exposure,
        posPreference: posPreference ?? this.posPreference,
        dialHistory: dialHistory ?? this.dialHistory,
        updatedAt: updatedAt,
      );

  factory UserVocabularyProfile.fromJson(Map<String, dynamic> j) =>
      UserVocabularyProfile(
        ability: (j['ability'] as num).toDouble(),
        smoothed: (j['smoothed'] as num).toDouble(),
        level: j['level'] as int,
        events: j['events'] as int? ?? 0,
        source: j['source'] as String? ?? 'self',
        familiarity: {
          for (final e in (j['familiarity'] as Map? ?? const {}).entries)
            e.key as String: Familiarity.values.byName(e.value as String),
        },
        exposure: {
          for (final e in (j['exposure'] as Map? ?? const {}).entries)
            e.key as String: Exposure.fromJson(e.value as Map<String, dynamic>),
        },
        posPreference: {
          for (final e in (j['posPreference'] as Map? ?? const {}).entries)
            e.key as String: e.value as int,
        },
        dialHistory: [
          for (final o in (j['dialHistory'] as List? ?? const [])) o as int
        ],
        updatedAt: DateTime.parse(j['updatedAt'] as String),
      );

  Map<String, dynamic> toJson() => {
        'ability': ability,
        'smoothed': smoothed,
        'level': level,
        'events': events,
        'source': source,
        'familiarity': {
          for (final e in familiarity.entries) e.key: e.value.name
        },
        'exposure': {for (final e in exposure.entries) e.key: e.value.toJson()},
        'posPreference': posPreference,
        'dialHistory': dialHistory,
        'updatedAt': updatedAt.toIso8601String(),
      };
}
