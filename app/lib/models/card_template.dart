/// The back-of-card fields in spec section 4's default order
/// (背面預設順序). [word] is always the card title, so it isn't
/// reorderable — every other field can be moved and hidden.
enum CardBackField {
  word('英文單字'),
  pronunciation('發音與 IPA'),
  posAndMeaning('詞性與釋義'),
  photoContext('照片情境'),
  example('例句與翻譯'),
  formsAndDerivations('詞形與衍生'),
  related('相關字'),
  morphology('構詞與詞源'),
  source('來源'),
  learningInfo('學習資訊');

  final String label;
  const CardBackField(this.label);
}

class TemplateField {
  final CardBackField field;
  final bool visible;
  final int? limit;
  final bool? collapsed;
  final bool expandAll;

  const TemplateField(this.field,
      {this.visible = true, this.limit, this.collapsed, this.expandAll = true});

  TemplateField copyWith({bool? visible}) => TemplateField(field,
      visible: visible ?? this.visible,
      limit: limit,
      collapsed: collapsed,
      expandAll: expandAll);

  factory TemplateField.fromJson(Map<String, dynamic> j) => TemplateField(
        CardBackField.values.byName(j['field'] as String),
        visible: j['visible'] as bool? ?? true,
        limit: j['limit'] as int?,
        collapsed: j['collapsed'] as bool?,
        expandAll: j['expand_all'] as bool? ?? true,
      );

  Map<String, dynamic> toJson() => {
        'field': field.name,
        'visible': visible,
        'limit': limit,
        'collapsed': collapsed,
        'expand_all': expandAll
      };
}

/// Spec section 4's CardTemplate: stores field references and display
/// settings only, never copies word data, so a change here applies to
/// every card using the template without touching any WordEntry.
class CardTemplate {
  final String id;
  final String name;
  final Map<String, dynamic>? publishedLayout;

  /// Back-side fields after the title, in display order.
  final List<TemplateField> backFields;

  const CardTemplate({
    required this.id,
    required this.name,
    required this.backFields,
    this.publishedLayout,
  });

  /// MVP's single built-in template (spec: "MVP 提供一個內建「照片單字卡」
  /// 模板").
  static final photoWordCard = CardTemplate(
    id: 'photo-word-card',
    name: '照片單字卡',
    backFields: [
      for (final f in CardBackField.values)
        if (f != CardBackField.word) TemplateField(f),
    ],
  );

  /// Translate the studio v1 layout without copying any learning data.
  factory CardTemplate.fromPublished(Map<String, dynamic> published) {
    final layout = published['layout'] as Map<String, dynamic>;
    if (layout['schema_version'] != 1) {
      throw const FormatException('Unsupported card template');
    }
    const mapping = {
      'pronunciation': CardBackField.pronunciation,
      'senses': CardBackField.posAndMeaning,
      'images': CardBackField.photoContext,
      'examples': CardBackField.example,
      'forms': CardBackField.formsAndDerivations,
      'relations': CardBackField.related,
      'etymology': CardBackField.morphology,
      'sources': CardBackField.source,
    };
    return CardTemplate(
      id: 'published:${published['id']}:${published['version']}',
      name: published['name'] as String,
      publishedLayout: layout,
      backFields: [
        for (final raw in layout['sections'] as List)
          if (mapping.containsKey(raw['key']))
            TemplateField(mapping[raw['key']]!,
                visible: raw['visible'] == true && raw['side'] == 'back',
                limit: raw['limit'] as int,
                collapsed: raw['collapsed'] as bool,
                expandAll: raw['expand_all'] as bool),
      ],
    );
  }

  CardTemplate copyWith({List<TemplateField>? backFields}) => CardTemplate(
        id: id,
        name: name,
        publishedLayout: publishedLayout,
        backFields: backFields ?? this.backFields,
      );

  /// Fields added to [CardBackField] after a template was saved are
  /// appended (visible) so they never silently disappear.
  factory CardTemplate.fromJson(Map<String, dynamic> j) {
    final fields = <TemplateField>[
      for (final m in j['backFields'] as List)
        if (CardBackField.values.any((f) => f.name == (m as Map)['field']))
          TemplateField.fromJson(m as Map<String, dynamic>),
    ];
    for (final f in CardBackField.values) {
      if (j['publishedLayout'] == null &&
          f != CardBackField.word &&
          fields.every((t) => t.field != f)) {
        fields.add(TemplateField(f));
      }
    }
    return CardTemplate(
      id: j['id'] as String,
      name: j['name'] as String,
      publishedLayout: j['publishedLayout'] as Map<String, dynamic>?,
      backFields: fields,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'publishedLayout': publishedLayout,
        'backFields': [for (final f in backFields) f.toJson()],
      };
}
