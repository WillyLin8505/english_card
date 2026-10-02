/// Mirrors the JSON produced by the Python pipeline in
/// `pipeline/schema.py` (see /pipeline in the project root) — field
/// names here are kept identical to that dataclass on purpose, so the
/// pipeline's `word_db.json` output can be decoded directly with no
/// translation layer between the two halves of this project.
///
/// Every category also carries a `*Source` sibling naming which of
/// Kaikki / WordNet / CMUdict / Datamuse / Tatoeba actually answered
/// it, per spec-01-data-sources.html section 3 — kept here so the UI
/// can (optionally) show provenance/attribution, not just for the
/// pipeline's own bookkeeping.
library;

class Definition {
  final String pos;
  final String gloss;

  const Definition({required this.pos, required this.gloss});

  factory Definition.fromJson(Map<String, dynamic> json) => Definition(
        pos: json['pos'] as String? ?? '',
        gloss: json['gloss'] as String? ?? '',
      );

  Map<String, dynamic> toJson() => {'pos': pos, 'gloss': gloss};
}

class Inflection {
  final String form;
  final String label;

  const Inflection({required this.form, required this.label});

  factory Inflection.fromJson(Map<String, dynamic> json) => Inflection(
        form: json['form'] as String? ?? '',
        label: json['label'] as String? ?? '',
      );

  Map<String, dynamic> toJson() => {'form': form, 'label': label};
}

class Derivation {
  final String word;
  final String? pos;

  const Derivation({required this.word, this.pos});

  factory Derivation.fromJson(Map<String, dynamic> json) => Derivation(
        word: json['word'] as String? ?? '',
        pos: json['pos'] as String?,
      );

  Map<String, dynamic> toJson() => {'word': word, 'pos': pos};
}

class ExampleSentence {
  final String en;
  final String? zh;
  final String? audioUrl;
  final String? source;
  final String? zhSource;
  final String? audioSource;
  final String? difficulty;

  const ExampleSentence({
    required this.en,
    this.zh,
    this.audioUrl,
    this.source,
    this.zhSource,
    this.audioSource,
    this.difficulty,
  });

  factory ExampleSentence.fromJson(Map<String, dynamic> json) =>
      ExampleSentence(
        en: json['en'] as String? ?? '',
        zh: json['zh'] as String?,
        audioUrl: json['audio_url'] as String?,
        source: json['source'] as String?,
        zhSource: json['zh_source'] as String?,
        audioSource: json['audio_source'] as String?,
        difficulty: (json['difficulty'] ?? json['level']) as String?,
      );

  Map<String, dynamic> toJson() => {
        'en': en,
        'zh': zh,
        'audio_url': audioUrl,
        'source': source,
        'zh_source': zhSource,
        'audio_source': audioSource,
        'difficulty': difficulty,
      };
}

/// One typed relation from the downloaded lexicon. Rarity metadata is
/// preserved so the learner UI can hide obscure distractors by default.
class RelatedTerm {
  final String word;
  final String relation;
  final String? cefr;
  final double? zipf;
  final String? rarity;
  final bool hideByDefault;

  const RelatedTerm({
    required this.word,
    required this.relation,
    this.cefr,
    this.zipf,
    this.rarity,
    this.hideByDefault = false,
  });

  factory RelatedTerm.fromJson(Map<String, dynamic> json) => RelatedTerm(
        word: json['word'] as String? ?? '',
        relation: json['relation'] as String? ?? 'related',
        cefr: json['cefr'] as String?,
        zipf: (json['zipf'] as num?)?.toDouble(),
        rarity: json['rarity'] as String?,
        hideByDefault: json['hide_by_default'] == true,
      );

  Map<String, dynamic> toJson() => {
        'word': word,
        'relation': relation,
        'cefr': cefr,
        'zipf': zipf,
        'rarity': rarity,
        'hide_by_default': hideByDefault,
      };
}

class WordDetail {
  final String word;

  final List<Definition> definitions;
  final String? definitionsSource;

  final String? ipa;
  final String? ipaSource;
  final String? arpabet;
  final String? arpabetSource;

  final String? wordAudioUrl;
  final String? wordAudioSource;

  final List<String> synonyms;
  final String? synonymsSource;

  final List<String> homophones;
  final String? homophonesSource;

  final List<String> similarSpelling;
  final String? similarSpellingSource;

  final List<Inflection> inflections;
  final String? inflectionsSource;

  final List<Derivation> derivations;
  final String? derivationsSource;

  final String? root;
  final List<String> affixes;
  final String? morphologySource;

  final List<ExampleSentence> exampleSentences;
  final List<RelatedTerm> relations;

  const WordDetail({
    required this.word,
    this.definitions = const [],
    this.definitionsSource,
    this.ipa,
    this.ipaSource,
    this.arpabet,
    this.arpabetSource,
    this.wordAudioUrl,
    this.wordAudioSource,
    this.synonyms = const [],
    this.synonymsSource,
    this.homophones = const [],
    this.homophonesSource,
    this.similarSpelling = const [],
    this.similarSpellingSource,
    this.inflections = const [],
    this.inflectionsSource,
    this.derivations = const [],
    this.derivationsSource,
    this.root,
    this.affixes = const [],
    this.morphologySource,
    this.exampleSentences = const [],
    this.relations = const [],
  });

  factory WordDetail.fromJson(Map<String, dynamic> json) {
    List<T> list<T>(String key, T Function(Map<String, dynamic>) fromJson) {
      final raw = json[key];
      if (raw is! List) return const [];
      return raw
          .whereType<Map<String, dynamic>>()
          .map(fromJson)
          .toList(growable: false);
    }

    List<String> strings(String key) {
      final raw = json[key];
      if (raw is! List) return const [];
      return raw.whereType<String>().toList(growable: false);
    }

    return WordDetail(
      word: json['word'] as String? ?? '',
      definitions: list('definitions', Definition.fromJson),
      definitionsSource: json['definitions_source'] as String?,
      ipa: json['ipa'] as String?,
      ipaSource: json['ipa_source'] as String?,
      arpabet: json['arpabet'] as String?,
      arpabetSource: json['arpabet_source'] as String?,
      wordAudioUrl: json['word_audio_url'] as String?,
      wordAudioSource: json['word_audio_source'] as String?,
      synonyms: strings('synonyms'),
      synonymsSource: json['synonyms_source'] as String?,
      homophones: strings('homophones'),
      homophonesSource: json['homophones_source'] as String?,
      similarSpelling: strings('similar_spelling'),
      similarSpellingSource: json['similar_spelling_source'] as String?,
      inflections: list('inflections', Inflection.fromJson),
      inflectionsSource: json['inflections_source'] as String?,
      derivations: list('derivations', Derivation.fromJson),
      derivationsSource: json['derivations_source'] as String?,
      root: json['root'] as String?,
      affixes: strings('affixes'),
      morphologySource: json['morphology_source'] as String?,
      exampleSentences: list('example_sentences', ExampleSentence.fromJson),
      relations: list('relations', RelatedTerm.fromJson),
    );
  }

  Map<String, dynamic> toJson() => {
        'word': word,
        'definitions': definitions.map((d) => d.toJson()).toList(),
        'definitions_source': definitionsSource,
        'ipa': ipa,
        'ipa_source': ipaSource,
        'arpabet': arpabet,
        'arpabet_source': arpabetSource,
        'word_audio_url': wordAudioUrl,
        'word_audio_source': wordAudioSource,
        'synonyms': synonyms,
        'synonyms_source': synonymsSource,
        'homophones': homophones,
        'homophones_source': homophonesSource,
        'similar_spelling': similarSpelling,
        'similar_spelling_source': similarSpellingSource,
        'inflections': inflections.map((i) => i.toJson()).toList(),
        'inflections_source': inflectionsSource,
        'derivations': derivations.map((d) => d.toJson()).toList(),
        'derivations_source': derivationsSource,
        'root': root,
        'affixes': affixes,
        'morphology_source': morphologySource,
        'example_sentences': exampleSentences.map((e) => e.toJson()).toList(),
        'relations': relations.map((r) => r.toJson()).toList(),
      };
}
