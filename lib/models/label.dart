class ExampleSentence {
  final String en;
  final String zh;

  ExampleSentence({required this.en, required this.zh});

  factory ExampleSentence.fromJson(Map<String, dynamic> json) {
    return ExampleSentence(
      en: json['en'] as String? ?? '',
      zh: json['zh'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {'en': en, 'zh': zh};

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is ExampleSentence && other.en == en && other.zh == zh;
  }

  @override
  int get hashCode => Object.hash(en, zh);
}

class Phrase {
  final String en;
  final String zh;

  Phrase({required this.en, required this.zh});

  factory Phrase.fromJson(Map<String, dynamic> json) {
    return Phrase(
      en: json['en'] as String? ?? '',
      zh: json['zh'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {'en': en, 'zh': zh};

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is Phrase && other.en == en && other.zh == zh;
  }

  @override
  int get hashCode => Object.hash(en, zh);
}

class Label {
  String en;
  String? zh;
  String? ipa;
  double? confidence;
  List<ExampleSentence> examples;
  List<Phrase> phrases;

  Label({
    required this.en,
    this.zh,
    this.ipa,
    this.confidence,
    List<ExampleSentence>? examples,
    List<Phrase>? phrases,
  })  : examples = examples ?? [],
        phrases = phrases ?? [];

  factory Label.fromJson(Map<String, dynamic> json) {
    final examplesJson = json['examples'] as List<dynamic>?;
    final phrasesJson = json['phrases'] as List<dynamic>?;
    return Label(
      en: json['en'] as String,
      zh: json['zh'] as String?,
      ipa: json['ipa'] as String?,
      confidence: (json['confidence'] as num?)?.toDouble(),
      examples: examplesJson
              ?.map((e) => ExampleSentence.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      phrases: phrasesJson
              ?.map((e) => Phrase.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'en': en,
      if (zh != null) 'zh': zh,
      if (ipa != null) 'ipa': ipa,
      if (confidence != null) 'confidence': confidence,
      if (examples.isNotEmpty) 'examples': examples.map((e) => e.toJson()).toList(),
      if (phrases.isNotEmpty) 'phrases': phrases.map((p) => p.toJson()).toList(),
    };
  }

  Label copyWith({
    String? en,
    String? zh,
    String? ipa,
    double? confidence,
    List<ExampleSentence>? examples,
    List<Phrase>? phrases,
  }) {
    return Label(
      en: en ?? this.en,
      zh: zh ?? this.zh,
      ipa: ipa ?? this.ipa,
      confidence: confidence ?? this.confidence,
      examples: examples ?? this.examples,
      phrases: phrases ?? this.phrases,
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is Label &&
        other.en == en &&
        other.zh == zh &&
        other.ipa == ipa &&
        other.confidence == confidence;
  }

  @override
  int get hashCode => Object.hash(en, zh, ipa, confidence);
}
