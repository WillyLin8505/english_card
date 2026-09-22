class Label {
  String en;
  String? zh;
  double? confidence;

  Label({
    required this.en,
    this.zh,
    this.confidence,
  });

  factory Label.fromJson(Map<String, dynamic> json) {
    return Label(
      en: json['en'] as String,
      zh: json['zh'] as String?,
      confidence: (json['confidence'] as num?)?.toDouble(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'en': en,
      if (zh != null) 'zh': zh,
      if (confidence != null) 'confidence': confidence,
    };
  }

  Label copyWith({String? en, String? zh, double? confidence}) {
    return Label(
      en: en ?? this.en,
      zh: zh ?? this.zh,
      confidence: confidence ?? this.confidence,
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is Label &&
        other.en == en &&
        other.zh == zh &&
        other.confidence == confidence;
  }

  @override
  int get hashCode => Object.hash(en, zh, confidence);
}
