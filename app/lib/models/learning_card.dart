/// Spec section 4's per-photo and per-card entities: PhotoOccurrence (one
/// appearance of a word in one photo), LearningCard (one card per word —
/// "同詞單卡"), FSRSState (that card's memory state) and ReviewLog (one
/// graded recall).
///
/// Every entity has toJson/fromJson; HiveWordDatabaseStore stores them as
/// JSON strings, so there are no hand-maintained Hive field indices here.
library;

DateTime? _date(Object? v) => v is String ? DateTime.parse(v) : null;

/// A normalized (0–1) point on a photo: where a word's label pin points
/// (the focal dot under each Figma pin badge). This is the spec's 標籤
/// 座標; the quiz front marks it as the 目標區域.
class LabelPoint {
  final double x;
  final double y;

  const LabelPoint(this.x, this.y);

  factory LabelPoint.fromJson(Map<String, dynamic> j) =>
      LabelPoint((j['x'] as num).toDouble(), (j['y'] as num).toDouble());

  Map<String, dynamic> toJson() => {'x': x, 'y': y};
}

/// One appearance of a [WordEntry] in one [Photo]. Owns everything that
/// is specific to that photo, so merging duplicate WordEntries never
/// loses it (spec: "屬於 PhotoOccurrence，不因合併重複單字而遺失").
class PhotoOccurrence {
  final String id;
  final String photoId;
  final String wordEntryId;

  /// Where the label pin points on the photo.
  final LabelPoint anchor;

  /// What the AI tagger originally said, kept when the user corrects the
  /// label (spec: AI 原始標籤 / 使用者修正版). Null for labels the user
  /// added by hand.
  final String? aiLabel;
  final bool userEdited;

  /// 情境說明 / 圖片證據 — what in the photo shows the word — and how
  /// sure the model was (AI 信心).
  final String? evidence;
  final double? confidence;

  /// A word already being learned from another photo, added here only as
  /// one more context (spec section 7: 新照片只加入該單字的照片情境). It is
  /// not one of this photo's listed words, so reopening the photo keeps it
  /// hidden like before saving, and the list stays at five words or fewer.
  final bool contextOnly;

  const PhotoOccurrence({
    required this.id,
    required this.photoId,
    required this.wordEntryId,
    required this.anchor,
    this.aiLabel,
    this.userEdited = false,
    this.evidence,
    this.confidence,
    this.contextOnly = false,
  });

  PhotoOccurrence copyWith(
          {String? wordEntryId,
          LabelPoint? anchor,
          bool? userEdited,
          bool? contextOnly}) =>
      PhotoOccurrence(
        id: id,
        photoId: photoId,
        wordEntryId: wordEntryId ?? this.wordEntryId,
        anchor: anchor ?? this.anchor,
        aiLabel: aiLabel,
        userEdited: userEdited ?? this.userEdited,
        evidence: evidence,
        confidence: confidence,
        contextOnly: contextOnly ?? this.contextOnly,
      );

  factory PhotoOccurrence.fromJson(Map<String, dynamic> j) => PhotoOccurrence(
        id: j['id'] as String,
        photoId: j['photoId'] as String,
        wordEntryId: j['wordEntryId'] as String,
        anchor: LabelPoint.fromJson(j['anchor'] as Map<String, dynamic>),
        aiLabel: j['aiLabel'] as String?,
        userEdited: j['userEdited'] as bool? ?? false,
        evidence: j['evidence'] as String?,
        confidence: (j['confidence'] as num?)?.toDouble(),
        contextOnly: j['contextOnly'] as bool? ?? false,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'photoId': photoId,
        'wordEntryId': wordEntryId,
        'anchor': anchor.toJson(),
        'aiLabel': aiLabel,
        'userEdited': userEdited,
        'evidence': evidence,
        'confidence': confidence,
        if (contextOnly) 'contextOnly': true,
      };
}

/// FSRS card states (New / Learning / Review / Relearning).
enum FsrsCardState { newCard, learning, review, relearning }

/// The four recall grades (spec section 4): Again = not recalled; Hard =
/// recalled with serious effort; Good = recalled normally; Easy =
/// recalled quickly and surely. [value] is FSRS's 1–4 grade. The buttons
/// are labelled in the learner's native language (依母語顯示).
enum Rating {
  again(1, 'Again', '忘記', 'Oublié'),
  hard(2, 'Hard', '吃力', 'Difficile'),
  good(3, 'Good', '記得', 'Correct'),
  easy(4, 'Easy', '很容易', 'Facile');

  final int value;
  final String label;
  final String labelZh;
  final String labelFr;
  const Rating(this.value, this.label, this.labelZh, this.labelFr);

  /// The label in [native] (zh-TW / en / fr).
  String labelIn(String native) => switch (native) {
        'en' => label,
        'fr' => labelFr,
        _ => labelZh,
      };
}

class FsrsState {
  final FsrsCardState state;

  /// Days until retrievability drops to 90%.
  final double stability;
  final double difficulty;

  /// Next suggested review. Null while the card is still new.
  final DateTime? due;
  final DateTime? lastReview;

  /// Interval chosen at the last review, in days.
  final int scheduledDays;
  final int reps;
  final int lapses;

  /// Which scheduler produced this state (spec: 演算法版本), so states can
  /// be recomputed from the ReviewLog if the algorithm changes.
  final String? algorithmVersion;

  const FsrsState({
    required this.state,
    this.stability = 0,
    this.difficulty = 0,
    this.due,
    this.lastReview,
    this.scheduledDays = 0,
    this.reps = 0,
    this.lapses = 0,
    this.algorithmVersion,
  });

  static const initial = FsrsState(state: FsrsCardState.newCard);

  factory FsrsState.fromJson(Map<String, dynamic> j) => FsrsState(
        state: FsrsCardState.values.byName(j['state'] as String),
        stability: (j['stability'] as num? ?? 0).toDouble(),
        difficulty: (j['difficulty'] as num? ?? 0).toDouble(),
        due: _date(j['due']),
        lastReview: _date(j['lastReview']),
        scheduledDays: j['scheduledDays'] as int? ?? 0,
        reps: j['reps'] as int? ?? 0,
        lapses: j['lapses'] as int? ?? 0,
        algorithmVersion: j['algorithmVersion'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'state': state.name,
        'stability': stability,
        'difficulty': difficulty,
        'due': due?.toIso8601String(),
        'lastReview': lastReview?.toIso8601String(),
        'scheduledDays': scheduledDays,
        'reps': reps,
        'lapses': lapses,
        'algorithmVersion': algorithmVersion,
      };
}

/// The one card of a word in the learning language (spec section 4: 同一
/// 學習語言中的每個標準化單字只建立一張學習卡，可連結多張照片情境並共用一份
/// FSRS 狀態). The card's back shows one of the word's photos at random.
///
/// Swiping a word away as 已學會 [archived]s its card rather than
/// deleting it, so 復原 brings back the card with its whole review
/// history and FSRS state (spec section 7).
class LearningCard {
  final String id;
  final String wordEntryId;
  final String templateId;

  /// The learning language (languageProfileId).
  final String language;
  final bool archived;
  final FsrsState fsrs;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  const LearningCard({
    required this.id,
    required this.wordEntryId,
    required this.templateId,
    this.language = 'en',
    this.archived = false,
    this.fsrs = FsrsState.initial,
    this.createdAt,
    this.updatedAt,
  });

  static String idFor(String wordEntryId) => 'card:$wordEntryId';

  LearningCard copyWith(
          {bool? archived, FsrsState? fsrs, DateTime? updatedAt}) =>
      LearningCard(
        id: id,
        wordEntryId: wordEntryId,
        templateId: templateId,
        language: language,
        archived: archived ?? this.archived,
        fsrs: fsrs ?? this.fsrs,
        createdAt: createdAt,
        updatedAt: updatedAt ?? this.updatedAt,
      );

  factory LearningCard.fromJson(Map<String, dynamic> j) => LearningCard(
        id: j['id'] as String,
        wordEntryId: j['wordEntryId'] as String,
        templateId: j['templateId'] as String,
        language: j['language'] as String? ?? 'en',
        archived: j['archived'] as bool? ?? false,
        fsrs: FsrsState.fromJson(j['fsrs'] as Map<String, dynamic>),
        createdAt: _date(j['createdAt']),
        updatedAt: _date(j['updatedAt']),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'wordEntryId': wordEntryId,
        'templateId': templateId,
        'language': language,
        'archived': archived,
        'fsrs': fsrs.toJson(),
        'createdAt': createdAt?.toIso8601String(),
        'updatedAt': updatedAt?.toIso8601String(),
      };
}

/// One graded recall (spec section 3's ReviewLog): kept so states can be
/// recomputed and, later, FSRS parameters personalised.
class ReviewLog {
  final String cardId;
  final DateTime reviewedAt;
  final Rating rating;
  final FsrsState before;
  final FsrsState after;

  /// Days since the previous review (0 for a new card).
  final int elapsedDays;
  final int scheduledDays;

  /// 作答耗時 — from the card front appearing to the grade.
  final int? durationMs;

  const ReviewLog({
    required this.cardId,
    required this.reviewedAt,
    required this.rating,
    required this.before,
    required this.after,
    required this.elapsedDays,
    required this.scheduledDays,
    this.durationMs,
  });

  factory ReviewLog.fromJson(Map<String, dynamic> j) => ReviewLog(
        cardId: j['cardId'] as String,
        reviewedAt: DateTime.parse(j['reviewedAt'] as String),
        rating: Rating.values.byName(j['rating'] as String),
        before: FsrsState.fromJson(j['before'] as Map<String, dynamic>),
        after: FsrsState.fromJson(j['after'] as Map<String, dynamic>),
        elapsedDays: j['elapsedDays'] as int,
        scheduledDays: j['scheduledDays'] as int,
        durationMs: j['durationMs'] as int?,
      );

  Map<String, dynamic> toJson() => {
        'cardId': cardId,
        'reviewedAt': reviewedAt.toIso8601String(),
        'rating': rating.name,
        'before': before.toJson(),
        'after': after.toJson(),
        'elapsedDays': elapsedDays,
        'scheduledDays': scheduledDays,
        'durationMs': durationMs,
      };
}
