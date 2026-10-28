import 'word_detail.dart';

/// CEFR levels, easiest first — the 等級 badge and the photo-detail
/// difficulty dial (Figma difficulty-slider, 54:231; spec section 7: 刻度為
/// A1、A2、B1、B2、C1、C2).
const cefrLevels = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];

/// Index of [level] in [cefrLevels]; unknown levels count as B1.
int levelIndex(String? level) {
  final i = cefrLevels.indexOf(level ?? '');
  return i < 0 ? 2 : i;
}

/// Photo labels and the word-detail title show words capitalised
/// ("Cutting Board"); the word database lists the normalized headword.
String displayWord(String word) => word
    .split(' ')
    .map((w) => w.isEmpty ? w : w[0].toUpperCase() + w.substring(1))
    .join(' ');

/// The headword on a card. French keeps its lowercase spelling (a capital
/// makes a noun look like a proper noun) and a noun shows with its article —
/// "un exemple" — taken from the gender inflection the pack builds as
/// `frenchWithArticle` (問題回報 #499). The article belongs to the noun only:
/// a spelling whose shown part of speech is an adjective or a verb (populaire,
/// pouvoir, être) also has a noun usage, and its "le populaire" inflection
/// must not head the adjective (卡 #496 round 5), so pass [pos] when known.
String headword(String word, String language,
    {Iterable<Inflection> inflections = const [], String? pos}) {
  if (language != 'fr') return displayWord(word);
  if (pos != null && !_nounPos.contains(pos.toLowerCase())) return word;
  final lower = word.toLowerCase();
  for (final i in inflections) {
    final form = i.form.toLowerCase();
    if (form.endsWith(' $lower') && form.length > lower.length + 1) {
      return i.form;
    }
  }
  return word;
}

const _nounPos = {'noun', 'n.', 'n', 'proper noun', 'proper_noun', '名詞'};

/// How a related word relates to its [WordEntry]. Spec section 5
/// (完整單字資訊欄位 · 詞彙關係): "關係需保存類型，不把所有相關字混成同一
/// 清單". [associated] covers topical neighbours that are none of the
/// others (balcony → railing).
enum RelationType {
  synonym,
  antonym,
  homophone,
  nearHomophone,
  similarSpelling,
  derivation,
  associated
}

RelationType relationTypeFromKey(String relation) => switch (relation) {
      'synonyms' => RelationType.synonym,
      'antonyms' => RelationType.antonym,
      'homophones' => RelationType.homophone,
      'near_homophones' => RelationType.nearHomophone,
      'similar_spelling' => RelationType.similarSpelling,
      'derived_terms' => RelationType.derivation,
      _ => RelationType.associated,
    };

class RelatedWord {
  final String? native;
  final String word;
  final RelationType type;
  final String? cefr;
  final double? zipf;
  final String? rarity;
  final bool hideByDefault;

  const RelatedWord(this.word, this.type,
      {this.native,
      this.cefr,
      this.zipf,
      this.rarity,
      this.hideByDefault = false});

  factory RelatedWord.fromJson(Map<String, dynamic> j) => RelatedWord(
        j['word'] as String,
        RelationType.values.byName(j['type'] as String),
        native: j['native'] as String?,
        cefr: j['cefr'] as String?,
        zipf: (j['zipf'] as num?)?.toDouble(),
        rarity: j['rarity'] as String?,
        hideByDefault: j['hideByDefault'] as bool? ?? false,
      );

  Map<String, dynamic> toJson() => {
        'word': word,
        'type': type.name,
        'native': native,
        'cefr': cefr,
        'zipf': zipf,
        'rarity': rarity,
        'hideByDefault': hideByDefault,
      };

  @override
  bool operator ==(Object other) =>
      other is RelatedWord &&
      word == other.word &&
      type == other.type &&
      native == other.native &&
      cefr == other.cefr &&
      zipf == other.zipf &&
      rarity == other.rarity &&
      hideByDefault == other.hideByDefault;

  @override
  int get hashCode =>
      Object.hash(word, type, native, cefr, zipf, rarity, hideByDefault);
}

/// One inflected form (詞形變化), e.g. apples / 複數.
class WordForm {
  final String form;
  final String label;

  const WordForm(this.form, this.label);

  factory WordForm.fromJson(Map<String, dynamic> j) =>
      WordForm(j['form'] as String, j['label'] as String);

  Map<String, dynamic> toJson() => {'form': form, 'label': label};
}

/// An example sentence in the learning language with its translation
/// into the learner's native language. The database targets 3–5 sentences
/// for every CEFR band and stores the source. No whole-sentence audio.
class WordExample {
  final String? senseId;
  final String text;
  final String? translation;
  final String? source;

  /// Estimated CEFR level of this sentence (A1–C2).
  final String? difficulty;

  /// The sentence itself was written by the AI (no dictionary source).
  final bool aiGenerated;

  /// The translation was written by the AI (「AI 翻譯」).
  final bool aiTranslated;

  const WordExample({
    required this.text,
    this.senseId,
    this.translation,
    this.source,
    this.difficulty,
    this.aiGenerated = false,
    this.aiTranslated = false,
  });

  WordExample copyWith({String? translation, bool? aiTranslated}) =>
      WordExample(
        text: text,
        senseId: senseId,
        translation: translation ?? this.translation,
        source: source,
        difficulty: difficulty,
        aiGenerated: aiGenerated,
        aiTranslated: aiTranslated ?? this.aiTranslated,
      );

  factory WordExample.fromJson(Map<String, dynamic> j) => WordExample(
        text: (j['text'] ?? j['en']) as String,
        senseId: j['sense_id'] as String?,
        translation: (j['translation'] ?? j['zh']) as String?,
        source: j['source'] as String?,
        difficulty: (j['difficulty'] ?? j['level']) as String?,
        aiGenerated: j['aiGenerated'] as bool? ?? false,
        aiTranslated: j['aiTranslated'] as bool? ?? false,
      );

  Map<String, dynamic> toJson() => {
        'text': text,
        if (senseId != null) 'sense_id': senseId,
        'translation': translation,
        'source': source,
        'difficulty': difficulty,
        'aiGenerated': aiGenerated,
        'aiTranslated': aiTranslated,
      };
}

/// Pipeline part-of-speech names → the short forms the UI shows.
/// The lexicon pack's adj / adv are the same as the tagger's adjective /
/// adverb: one code each, so the word list doesn't offer 形容詞 twice.
String shortPos(String pos) => switch (pos) {
      'adjective' || 'adj' => 'adj.',
      'adverb' || 'adv' => 'adv.',
      _ => pos,
    };

/// Whether the full word data (IPA, examples, translations…) has been
/// fetched. Spec section 7: the main data shows at once; missing fields
/// are retried in the background, and a word whose retries still fail
/// keeps its source and failure state, shown in the word list.
enum WordDataStatus { complete, pending, failed }

/// The fields a learner can edit. Spec section 7: "使用者修改值優先於後續
/// 自動更新，不得被覆寫" — a field in [WordEntry.userEdited] is never
/// replaced by dictionary or AI data again.
abstract final class WordField {
  static const meaning = 'meaning';
  static const definition = 'definition';
  static const ipa = 'ipa';
  static const pos = 'pos';
  static const level = 'level';
  static const examples = 'examples';
  static const related = 'related';
  static const forms = 'forms';
  static const morphology = 'morphology';
  static const etymology = 'etymology';
}

/// One meaning belonging to a grammatical usage.
class WordSense {
  final String id;
  final String meaning;
  final String? definition;
  const WordSense({required this.id, required this.meaning, this.definition});
  factory WordSense.fromJson(Map<String, dynamic> j) => WordSense(
      id: j['id'] as String,
      meaning: j['meaning'] as String,
      definition: j['definition'] as String?);
  Map<String, dynamic> toJson() => {
        'id': id,
        'meaning': meaning,
        'definition': definition,
      };
}

/// A spelling owns usages; each usage owns senses and bound examples.
/// Pack row ids remain stable usage ids while the legacy pack is POS-based.
class LexemeUsage {
  final String id;
  final String pos;
  final List<WordSense> senses;
  final List<WordExample> examples;

  /// A rarer part of speech of the spelling (問題回報 #468): review skips it.
  /// Stored with the usage; absent in older data means common.
  final bool rare;
  const LexemeUsage(
      {required this.id,
      required this.pos,
      this.senses = const [],
      this.examples = const [],
      this.rare = false});
  factory LexemeUsage.fromJson(Map<String, dynamic> j) => LexemeUsage(
          id: j['id'] as String,
          pos: j['pos'] as String,
          rare: j['rare'] == true,
          senses: [
            for (final s in j['senses'] as List? ?? [])
              WordSense.fromJson(Map<String, dynamic>.from(s as Map))
          ],
          examples: [
            for (final e in j['examples'] as List? ?? [])
              WordExample.fromJson(Map<String, dynamic>.from(e as Map))
          ]);
  Map<String, dynamic> toJson() => {
        'id': id,
        'pos': pos,
        if (rare) 'rare': true,
        'senses': [for (final s in senses) s.toJson()],
        'examples': [for (final e in examples) e.toJson()],
      };
}

/// One lexical entry per normalized spelling; usages hold POS differences.
/// Photos and learning cards reference this shared entry.
class WordEntry {
  final String entryType;
  final List<LexemeUsage> usages;

  /// Legacy entries receive deterministic local identities without deleting data.
  /// User edits to the primary meaning/examples remain authoritative.
  List<LexemeUsage> get effectiveUsages {
    if (usages.isEmpty) {
      return [
        LexemeUsage(
            id: 'local:$id',
            pos: pos,
            senses: [
              WordSense(
                  id: 'local:$id:main',
                  meaning: meaning,
                  definition: definitionEn)
            ],
            examples: examples)
      ];
    }
    return [
      for (final u in usages)
        if (shortPos(u.pos) == shortPos(pos) &&
            (u.id.startsWith('local:') ||
                userEdited.contains(WordField.meaning) ||
                userEdited.contains(WordField.examples)))
          LexemeUsage(
              id: u.id,
              pos: pos,
              rare: u.rare,
              senses: [
                for (var i = 0; i < u.senses.length; i++)
                  if (i == 0 &&
                      (u.id.startsWith('local:') ||
                          userEdited.contains(WordField.meaning)))
                    WordSense(
                        id: u.senses[i].id,
                        meaning: meaning,
                        definition: u.senses[i].definition)
                  else
                    u.senses[i]
              ],
              examples: u.id.startsWith('local:') ||
                      userEdited.contains(WordField.examples)
                  ? examples
                  : u.examples)
        else
          u,
    ];
  }

  List<String> get partsOfSpeech =>
      effectiveUsages.map((u) => shortPos(u.pos)).toSet().toList();
  final String id;

  /// Normalized spelling; unique per language, regardless of part of speech.
  final String word;

  /// Short part of speech ("noun", "verb", "adj.", "adv.", "phrase").
  final String pos;

  /// Main sense's language register: neutral, written, spoken, or slang.
  final String? register;

  /// The learning language ("en", "fr", "zh-TW").
  final String language;

  /// Short gloss in the learner's native language (主要釋義).
  final String meaning;

  /// Fuller native-language explanation, when known.
  final String? definition;

  /// English gloss, e.g. from WordNet via the pipeline.
  final String? definitionEn;

  final String? ipa;

  /// Where [ipa] came from ("cmudict", "ai", …).
  final String? ipaSource;

  /// Accent label for [ipa] ("US", "UK").
  final String? accent;

  /// Word recording (單字真人音檔); TTS is used when there is none.
  final String? audioUrl;

  /// CEFR level, one of [cefrLevels], and where it came from
  /// ("cefr-j", "frequency", "ai", "user").
  final String? level;
  final String? levelSource;

  /// Zipf word frequency (使用頻率), when known.
  final double? frequency;

  /// Free-form user tags ("home").
  final List<String> tags;

  final List<WordExample> examples;
  final List<RelatedWord> related;

  /// 詞形變化.
  final List<WordForm> forms;

  /// 字根 and 字首／字尾.
  final String? root;
  final List<String> affixes;
  final String? morphology;
  final String? etymology;

  final WordDataStatus dataStatus;

  /// Why the last background fetch failed, and how many times it has.
  final String? dataError;
  final int dataAttempts;

  /// [WordField]s the learner changed by hand.
  final Set<String> userEdited;

  /// The native language [meaning], [definition] and the example
  /// translations are in; null = Traditional Chinese (older data). When
  /// the learner changes their native language, words are translated
  /// again in the background.
  final String? translatedFor;

  /// The word's entry in the downloaded language pack (stable id; spec
  /// section 08). Null for words the pack doesn't have yet.
  final int? lexemeId;

  final DateTime createdAt;
  final DateTime updatedAt;

  const WordEntry({
    required this.id,
    this.usages = const [],
    this.entryType = 'word',
    required this.word,
    required this.pos,
    this.register,
    this.language = 'en',
    required this.meaning,
    this.definition,
    this.definitionEn,
    this.ipa,
    this.ipaSource,
    this.accent,
    this.audioUrl,
    this.level,
    this.levelSource,
    this.frequency,
    this.tags = const [],
    this.examples = const [],
    this.related = const [],
    this.forms = const [],
    this.root,
    this.affixes = const [],
    this.morphology,
    this.etymology,
    this.dataStatus = WordDataStatus.complete,
    this.dataError,
    this.dataAttempts = 0,
    this.userEdited = const {},
    this.translatedFor,
    this.lexemeId,
    required this.createdAt,
    required this.updatedAt,
  });

  String get nativeOfData => translatedFor ?? 'zh-TW';

  /// Builds an entry for a word the user typed in or the tagger returned,
  /// filling every field the offline pipeline already knows from
  /// [detail] (its `assets/word_db.json` entry, if any). The meaning comes
  /// from the user/tagger, since the pipeline doesn't produce a
  /// native-language gloss.
  factory WordEntry.fromUserInput({
    required String id,
    required String word,
    String? pos,
    String language = 'en',
    required String meaning,
    String? level,
    String? levelSource,
    String? ipa,
    String? ipaSource,
    double? frequency,
    WordDetail? detail,
    WordDataStatus dataStatus = WordDataStatus.complete,
    int? lexemeId,
    required DateTime now,
  }) {
    final related = detail != null && detail.relations.isNotEmpty
        ? <RelatedWord>[
            for (final r in detail.relations)
              RelatedWord(r.word, relationTypeFromKey(r.relation),
                  native: r.native,
                  cefr: r.cefr,
                  zipf: r.zipf,
                  rarity: r.rarity,
                  hideByDefault: r.hideByDefault),
          ]
        : <RelatedWord>[
            if (detail != null) ...[
              for (final w in detail.synonyms)
                RelatedWord(w, RelationType.synonym),
              for (final w in detail.homophones)
                RelatedWord(w, RelationType.homophone),
              for (final w in detail.similarSpelling)
                RelatedWord(w, RelationType.similarSpelling),
              for (final d in detail.derivations)
                RelatedWord(d.word, RelationType.derivation),
            ],
          ];
    return WordEntry(
      id: id,
      word: word.trim().toLowerCase(),
      pos: pos ?? shortPos(detail?.definitions.firstOrNull?.pos ?? ''),
      register: detail?.definitions.firstOrNull?.register,
      language: language,
      meaning: meaning.trim(),
      definitionEn: detail?.definitions.firstOrNull?.gloss,
      ipa: detail?.ipa ?? ipa,
      ipaSource: detail?.ipa != null ? detail?.ipaSource : ipaSource,
      audioUrl: detail?.wordAudioUrl,
      level: level,
      levelSource: levelSource,
      frequency: frequency,
      examples: [
        for (final e in detail?.exampleSentences ?? const <ExampleSentence>[])
          WordExample(
              text: e.en,
              translation: e.zh,
              source: e.source,
              difficulty: e.difficulty,
              // The word database's AI source (a level it filled / a
              // translation it lacked).
              aiGenerated: e.source == 'ai_translate',
              aiTranslated: e.zhSource == 'ai_translate'),
      ],
      related: related,
      forms: [
        for (final i in detail?.inflections ?? const <Inflection>[])
          WordForm(i.form, i.label),
      ],
      root: detail?.root,
      affixes: detail?.affixes ?? const [],
      morphology: detail?.morphology,
      etymology: detail?.etymology,
      dataStatus: dataStatus,
      lexemeId: lexemeId,
      createdAt: now,
      updatedAt: now,
    );
  }

  WordExample? get primaryExample => examples.firstOrNull;

  /// Sentences recommended for the learner's current CEFR level.
  /// Exact-level bilingual pairs come first. If that band has fewer than
  /// [minimum] items, adjacent bands fill the gap; untranslated sentences
  /// are always the last fallback.
  List<WordExample> examplesForLevel(String userLevel,
      {int minimum = 3, int limit = 5}) {
    final wanted = levelIndex(userLevel);
    int distance(WordExample example) {
      final i = cefrLevels.indexOf(example.difficulty ?? '');
      return i < 0 ? cefrLevels.length : (i - wanted).abs();
    }

    final ranked = [...examples]..sort((a, b) {
        final translationOrder = (a.translation == null ? 1 : 0)
            .compareTo(b.translation == null ? 1 : 0);
        final distanceOrder = distance(a).compareTo(distance(b));
        if (translationOrder != 0) return translationOrder;
        if (distanceOrder != 0) return distanceOrder;
        return examples.indexOf(a).compareTo(examples.indexOf(b));
      });
    final exact = ranked
        .where((e) => e.difficulty == userLevel && e.translation != null)
        .toList();
    if (exact.length >= minimum) return exact.take(limit).toList();
    return ranked.take(limit).toList();
  }

  List<String> relatedOf(Set<RelationType> types) => [
        for (final r in related)
          if (types.contains(r.type) && !r.hideByDefault) r.word,
      ];

  List<String> relatedForLevel(Set<RelationType> types, String userLevel) => [
        for (final r in related)
          if (types.contains(r.type) &&
              !r.hideByDefault &&
              (r.cefr == null ||
                  levelIndex(r.cefr) <= levelIndex(userLevel) + 1))
            r.word,
      ];

  WordEntry copyWith({
    String? entryType,
    List<LexemeUsage>? usages,
    String? pos,
    String? meaning,
    String? Function()? definition,
    String? Function()? ipa,
    String? Function()? ipaSource,
    String? Function()? level,
    String? Function()? levelSource,
    List<WordExample>? examples,
    List<RelatedWord>? related,
    List<WordForm>? forms,
    String? Function()? morphology,
    String? Function()? etymology,
    WordDataStatus? dataStatus,
    String? Function()? dataError,
    int? dataAttempts,
    Set<String>? userEdited,
    String? translatedFor,
    int? Function()? lexemeId,
    DateTime? updatedAt,
  }) =>
      WordEntry(
        id: id,
        usages: usages ?? this.usages,
        entryType: entryType ?? this.entryType,
        word: word,
        pos: pos ?? this.pos,
        register: register,
        language: language,
        meaning: meaning ?? this.meaning,
        definition: definition != null ? definition() : this.definition,
        definitionEn: definitionEn,
        ipa: ipa != null ? ipa() : this.ipa,
        ipaSource: ipaSource != null ? ipaSource() : this.ipaSource,
        accent: accent,
        audioUrl: audioUrl,
        level: level != null ? level() : this.level,
        levelSource: levelSource != null ? levelSource() : this.levelSource,
        frequency: frequency,
        tags: tags,
        examples: examples ?? this.examples,
        related: related ?? this.related,
        forms: forms ?? this.forms,
        root: root,
        affixes: affixes,
        morphology: morphology != null ? morphology() : this.morphology,
        etymology: etymology != null ? etymology() : this.etymology,
        dataStatus: dataStatus ?? this.dataStatus,
        dataError: dataError != null ? dataError() : this.dataError,
        dataAttempts: dataAttempts ?? this.dataAttempts,
        userEdited: userEdited ?? this.userEdited,
        translatedFor: translatedFor ?? this.translatedFor,
        lexemeId: lexemeId != null ? lexemeId() : this.lexemeId,
        createdAt: createdAt,
        updatedAt: updatedAt ?? this.updatedAt,
      );

  factory WordEntry.fromJson(Map<String, dynamic> j) {
    List<T> list<T>(String key, T Function(Map<String, dynamic>) f) => [
          for (final m in (j[key] as List? ?? const []))
            f(m as Map<String, dynamic>)
        ];
    List<String> strings(String key) =>
        [for (final t in (j[key] as List? ?? const [])) t as String];
    return WordEntry(
      id: j['id'] as String,
      usages: list('lexeme_usages', LexemeUsage.fromJson),
      entryType: j['entry_type'] as String? ?? 'word',
      word: j['word'] as String,
      pos: j['pos'] as String,
      register: j['register'] as String?,
      language: j['language'] as String? ?? 'en',
      meaning: (j['meaning'] ?? j['meaningZh']) as String,
      definition: (j['definition'] ?? j['definitionZh']) as String?,
      definitionEn: j['definitionEn'] as String?,
      ipa: j['ipa'] as String?,
      ipaSource: j['ipaSource'] as String?,
      accent: j['accent'] as String?,
      audioUrl: j['audioUrl'] as String?,
      level: j['level'] as String?,
      levelSource: j['levelSource'] as String?,
      frequency: (j['frequency'] as num?)?.toDouble(),
      tags: strings('tags'),
      examples: list('examples', WordExample.fromJson),
      related: list('related', RelatedWord.fromJson),
      forms: list('forms', WordForm.fromJson),
      root: j['root'] as String?,
      affixes: strings('affixes'),
      morphology: j['morphology'] as String?,
      etymology: j['etymology'] as String?,
      dataStatus: WordDataStatus.values.asNameMap()[j['dataStatus']] ??
          WordDataStatus.complete,
      dataError: j['dataError'] as String?,
      dataAttempts: j['dataAttempts'] as int? ?? 0,
      userEdited: strings('userEdited').toSet(),
      translatedFor: j['translatedFor'] as String?,
      lexemeId: (j['lexemeId'] as num?)?.toInt(),
      createdAt: DateTime.parse(j['createdAt'] as String),
      updatedAt: DateTime.parse(j['updatedAt'] as String),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'lexeme_usages': [for (final u in effectiveUsages) u.toJson()],
        'entry_type': entryType,
        'word': word,
        'pos': pos,
        'register': register,
        'language': language,
        'meaning': meaning,
        'definition': definition,
        'definitionEn': definitionEn,
        'ipa': ipa,
        'ipaSource': ipaSource,
        'accent': accent,
        'audioUrl': audioUrl,
        'level': level,
        'levelSource': levelSource,
        'frequency': frequency,
        'tags': tags,
        'examples': [for (final e in examples) e.toJson()],
        'related': [for (final r in related) r.toJson()],
        'forms': [for (final f in forms) f.toJson()],
        'root': root,
        'affixes': affixes,
        'morphology': morphology,
        'etymology': etymology,
        'dataStatus': dataStatus.name,
        'dataError': dataError,
        'dataAttempts': dataAttempts,
        'userEdited': userEdited.toList(),
        'translatedFor': translatedFor,
        if (lexemeId != null) 'lexemeId': lexemeId,
        'createdAt': createdAt.toIso8601String(),
        'updatedAt': updatedAt.toIso8601String(),
      };
}
