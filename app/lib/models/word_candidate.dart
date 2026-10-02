import 'learning_card.dart';

/// One stage-1 candidate from the tagger (spec section 3, 第一階段 · 理解
/// 照片): a word the model thinks could be learned from the photo, with
/// its picture evidence. A photo keeps its whole candidate pool, so the
/// difficulty dial can swap words instantly without asking the model
/// again (即時換詞). Candidates are only suggestions: nothing becomes a
/// WordEntry, PhotoOccurrence or LearningCard until the photo's word list
/// is saved (建立卡片的時機).
class WordCandidate {
  /// Dictionary form, lowercase (spec: word、lemma).
  final String word;
  final String lemma;

  /// noun / verb / adj. / adv. / phrase — never blank (詞性必須明確).
  final String pos;

  /// Native-language gloss for the sense seen in the photo (建議義項).
  final String meaning;

  /// CEFR after local correction, and where it came from: `cefr-j` (the
  /// bundled word list), `frequency` (word frequency, blended with the
  /// model's guess) or `ai` (the model's own estimate). Spec: "CEFR 優先
  /// 由本機詞彙資料庫校正，不完全信任視覺模型自評".
  final String level;
  final String levelSource;

  /// What the model itself said.
  final String? modelLevel;

  /// Zipf word frequency (0–8), when known — 使用頻率.
  final double? zipf;
  final String? ipa;

  /// 圖片證據: what in the photo supports the word, and where.
  final String evidence;
  final LabelPoint point;
  final double visualConfidence;

  /// 日常實用性 (0–1), from the model.
  final double usefulness;

  /// Can't be confirmed from the picture itself (a mood, an adverb).
  final bool inferred;

  /// The top-up request that produced it (harder / easier / actions /
  /// descriptions), or null for the first pass.
  final String? focus;

  /// The word's entry in the downloaded language pack (spec section 08:
  /// 以 lemma＋詞性查本機詞庫，照片只保存 photo ↔ lexeme_id). Null when the
  /// pack has no such word yet — a missing-word request is recorded.
  final int? lexemeId;

  bool get inDatabase => lexemeId != null;

  const WordCandidate({
    required this.word,
    String? lemma,
    required this.pos,
    required this.meaning,
    required this.level,
    required this.levelSource,
    this.modelLevel,
    this.zipf,
    this.ipa,
    this.evidence = '',
    required this.point,
    this.visualConfidence = 0.5,
    this.usefulness = 0.5,
    this.inferred = false,
    this.focus,
    this.lexemeId,
  }) : lemma = lemma ?? word;

  bool get isNoun => pos == 'noun';

  /// Verbs and verb-like phrases count as 動作詞, adjectives and adverbs
  /// as 描述詞 (spec: 2 個具體詞、2 個描述或動作詞).
  bool get isAction => pos == 'verb' || (pos == 'phrase' && !_prepositional);
  bool get isDescription => pos == 'adj.' || pos == 'adv.';

  bool get _prepositional => const {
        'on',
        'in',
        'at',
        'under',
        'next',
        'by',
        'near',
        'behind'
      }.contains(word.split(' ').first);

  WordCandidate copyWith({
    String? word,
    String? pos,
    String? meaning,
    LabelPoint? point,
    String? level,
    String? levelSource,
    int? Function()? lexemeId,
  }) =>
      WordCandidate(
        word: word ?? this.word,
        lemma: word ?? lemma,
        pos: pos ?? this.pos,
        meaning: meaning ?? this.meaning,
        level: level ?? this.level,
        levelSource: levelSource ?? this.levelSource,
        modelLevel: modelLevel,
        zipf: zipf,
        ipa: ipa,
        evidence: evidence,
        point: point ?? this.point,
        visualConfidence: visualConfidence,
        usefulness: usefulness,
        inferred: inferred,
        focus: focus,
        lexemeId: lexemeId != null ? lexemeId() : this.lexemeId,
      );

  factory WordCandidate.fromJson(Map<String, dynamic> j) => WordCandidate(
        word: j['word'] as String,
        lemma: j['lemma'] as String?,
        pos: j['pos'] as String,
        meaning: j['meaning'] as String? ?? '',
        level: j['level'] as String,
        levelSource: j['levelSource'] as String? ?? 'ai',
        modelLevel: j['modelLevel'] as String?,
        zipf: (j['zipf'] as num?)?.toDouble(),
        ipa: j['ipa'] as String?,
        evidence: j['evidence'] as String? ?? '',
        point: LabelPoint.fromJson(j['point'] as Map<String, dynamic>),
        visualConfidence: (j['visualConfidence'] as num? ?? 0.5).toDouble(),
        usefulness: (j['usefulness'] as num? ?? 0.5).toDouble(),
        inferred: j['inferred'] as bool? ?? false,
        focus: j['focus'] as String?,
        lexemeId: (j['lexemeId'] as num?)?.toInt(),
      );

  Map<String, dynamic> toJson() => {
        'word': word,
        'lemma': lemma,
        'pos': pos,
        'meaning': meaning,
        'level': level,
        'levelSource': levelSource,
        'modelLevel': modelLevel,
        'zipf': zipf,
        'ipa': ipa,
        'evidence': evidence,
        'point': point.toJson(),
        'visualConfidence': visualConfidence,
        'usefulness': usefulness,
        'inferred': inferred,
        'focus': focus,
        if (lexemeId != null) 'lexemeId': lexemeId,
      };
}
