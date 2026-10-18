part of '../screens/flashcard_screen.dart';

class FlashcardBack extends StatelessWidget {
  final WordEntry entry;
  // The usage/sense this exercise actually tested; overrides entry.pos and
  // entry.meaning on the back so they match the front's question rather
  // than the entry's default usage (問題回報 #4).
  final String? activePos;
  final String? activeMeaning;
  final String? activeDefinition;
  final LearningCard card;
  final Photo? photo;
  final LabelPoint? anchor;
  final String? photoCredit;
  final bool? answerCorrect;
  final String? submittedAnswer;
  final String? correctAnswer;
  final CardTemplate template;
  final String learnerLevel;
  final VoidCallback onPlay;
  final VoidCallback onOpen;

  const FlashcardBack({
    super.key,
    required this.entry,
    this.activePos,
    this.activeMeaning,
    this.activeDefinition,
    required this.card,
    required this.photo,
    required this.anchor,
    this.photoCredit,
    this.answerCorrect,
    this.submittedAnswer,
    this.correctAnswer,
    required this.template,
    required this.learnerLevel,
    required this.onPlay,
    required this.onOpen,
  });

  // Related words and word forms are not proper nouns: keep their original
  // casing rather than title-casing every word (問題回報 #255).
  Widget _chips(List<String> words) => Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [for (final w in words) TagChip(w, localize: false)],
      );

  Widget _items(CardBackField field, List<Widget> items) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: items);

  Widget? _configuredField(TemplateField setting) {
    final block = _field(setting.field);
    if (block is _Block) return _Block(block.label, block.child);
    return block;
  }

  Widget? _field(CardBackField field) {
    switch (field) {
      case CardBackField.word:
      case CardBackField.pronunciation:
        return null; // in the header
      case CardBackField.posAndMeaning:
        final pos = activePos ?? entry.pos;
        final meaning = activeMeaning ?? entry.meaning;
        final definition = activeDefinition ?? entry.definition;
        if (template.publishedLayout != null) {
          final source =
              LexiconPack.instance.lookup(entry.word, pos: pos)?.entry;
          final meanings =
              source?.senses.where((s) => (s.native ?? '').isNotEmpty).toList();
          return _Block(
              '逐義釋義',
              _items(field, [
                if (meanings == null || meanings.isEmpty)
                  Text(meaning)
                else
                  for (final sense in meanings) Text(sense.native!),
              ]));
        }
        return _Block(
          '中文意思',
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  if (pos.isNotEmpty) ...[
                    TagChip(posLabel(pos)),
                    const SizedBox(width: 8)
                  ],
                  if (entry.level != null) TagChip(levelLabel(entry.level!)),
                ],
              ),
              const SizedBox(height: 6),
              Text(meaning,
                  style: MFont.manrope(22, FontWeight.w800, MColors.primary)),
              if (definition != null)
                Text(definition,
                    style: MFont.manrope(14, FontWeight.w600, MColors.muted)),
            ],
          ),
        );
      case CardBackField.photoContext:
        final p = photo;
        if (p == null) return null;
        // Attribution stays off the card back (learner glanceability).
        // Long-press the photo to read license/author when needed.
        return _Block(
          '照片情境',
          Builder(builder: (context) {
            final photoWidget = SizedBox(
              height: 200,
              child: PinnedPhoto(
                photo: p,
                radius: 16,
                imageErrorBuilder: p.networkUrl == null
                    ? null
                    : (_) => const Center(child: UiText('圖片暫時無法載入，稍後再試')),
                // Only this word's label (其他英文標籤全部隱藏).
                pins: [
                  if (anchor != null)
                    PinData(
                        id: entry.id,
                        anchor: anchor!,
                        word: displayWord(entry.word),
                        zh: entry.meaning,
                        entryType: entry.entryType),
                ],
              ),
            );
            final credit = photoCredit?.trim();
            if (credit == null || credit.isEmpty) return photoWidget;
            return GestureDetector(
              onLongPress: () {
                showDialog<void>(
                  context: context,
                  builder: (ctx) => AlertDialog(
                    title: const UiText('圖片來源'),
                    content: Text(credit),
                    actions: [
                      TextButton(
                        onPressed: () => Navigator.of(ctx).pop(),
                        child: const UiText('關閉'),
                      ),
                    ],
                  ),
                );
              },
              child: photoWidget,
            );
          }),
        );
      case CardBackField.example:
        // Spec sections 4 and 7: 3–5 examples at the learner's level.
        final recommended = learningExamples(entry, learnerLevel,
            maxItems: template.publishedLayout == null ? 5 : 10000);
        if (recommended.isEmpty) return null;
        return _Block(
          '例句與翻譯',
          _items(field, [
            for (final x in recommended)
              Container(
                margin: const EdgeInsets.only(bottom: MSpace.xs),
                padding: const EdgeInsets.all(MSpace.sm),
                decoration: MDecor.softPanel(
                  color: MColors.surfaceSoft,
                  radius: MRadii.md,
                ),
                child: ExampleText(
                    example: x,
                    showTranslation:
                        template.publishedLayout?['show_translation'] != false),
              ),
          ]),
        );
      case CardBackField.formsAndDerivations:
        final pack = LexiconPack.instance;
        final source =
            (entry.lexemeId == null ? null : pack.byId(entry.lexemeId!)) ??
                pack.lookup(entry.word, pos: entry.pos)?.entry;
        final forms = <String, Set<String>>{};
        void add(String form, String label) {
          if (form.trim().isEmpty) return;
          (forms[form.trim()] ??= {}).add(formLabel(label));
        }
        if (source != null) {
          for (final f in pack.detailFor(source).inflections) {
            add(f.form, f.label);
          }
        }
        for (final f in entry.forms) {
          add(f.form, f.label);
        }
        return forms.isEmpty
            ? null
            : _Block(
                '詞形變化',
                _chips([
                  for (final f in forms.entries)
                    '${f.key}（${f.value.where((s) => s.isNotEmpty).join('；')}）',
                ]),
              );
      case CardBackField.related:
        // Every related word with its native meaning (spec section 08).
        final words = {
          for (final kind in const [
            'synonyms',
            'antonyms',
            'derived_terms',
            'related',
          ])
            for (final r in learningRelations(entry, learnerLevel, kind,
                maxItems: (template.publishedLayout?['relation_limits']
                        as Map?)?[kind] as int? ??
                    5))
              '${r.word} ${r.meaning}',
        }.toList();
        return words.isEmpty
            ? null
            : _Block(
                '相關字',
                _items(field, [
                  for (final w in words) _chips([w])
                ]),
                collapsed: true);
      case CardBackField.morphology:
        final parts = learningMorphology(entry);
        final origin = learningEtymology(entry);
        return parts == null && origin == null
            ? null
            : _Block(
                '構詞與詞源',
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (parts != null)
                      Text(parts,
                          style:
                              MFont.manrope(15, FontWeight.w600, MColors.ink)),
                    if (parts != null && origin != null)
                      const SizedBox(height: 6),
                    if (origin != null)
                      Text(origin,
                          style: MFont.manrope(
                              13, FontWeight.w600, MColors.muted)),
                  ],
                ),
                collapsed: true);
      case CardBackField.source:
        return null; // Back cards omit provenance for every template.
      case CardBackField.learningInfo:
        return null; // Review history belongs in word details, not the answer.
    }
  }

  Future<void> _playAccent(BuildContext context, String accent) async {
    final pack = LexiconPack.instance;
    final source =
        (entry.lexemeId == null ? null : pack.byId(entry.lexemeId!)) ??
            pack.lookup(entry.word, pos: entry.pos)?.entry;
    final aliases = accent == 'en-GB' ? {'uk', 'gb', 'en-gb'} : {'us', 'en-us'};
    final recording = source?.recordings
        .where((r) => aliases.contains(r.accent?.toLowerCase()))
        .firstOrNull;
    String? url;
    if (recording != null) {
      url = pack.mediaBase == null
          ? 'assets/lexicon/media/${recording.path}'
          : Uri.base
              .resolve(pack.mediaBase!)
              .replace(queryParameters: {'path': recording.path}).toString();
    } else if (aliases.contains(entry.accent?.toLowerCase())) {
      url = entry.audioUrl;
    }
    final ok = await AppScope.of(context).speaker.say(entry.word,
        language: entry.language, accent: accent, audioUrl: url);
    if (!ok && context.mounted) {
      showToast(context, '播放發音失敗，請檢查音量或稍後再試');
    }
  }

  @override
  Widget build(BuildContext context) {
    final pack = LexiconPack.instance;
    final source =
        (entry.lexemeId == null ? null : pack.byId(entry.lexemeId!)) ??
            pack.lookup(entry.word, pos: entry.pos)?.entry;
    final ipa =
        (entry.ipa?.trim().isNotEmpty ?? false) ? entry.ipa : source?.ipa;
    // 發音與 IPA sits in the header; switched off in 卡片背面順序, the IPA
    // and the play button go (the switch used to do nothing).
    final showPronunciation = template.backFields
        .where((f) => f.field == CardBackField.pronunciation)
        .every((f) => f.visible);
    // Every visible template field that has data (spec: 可用時一併顯示；
    // 欄位沒有內容時自動省略).
    final fields = [
      for (final f in template.backFields)
        if (f.visible) _configuredField(f),
    ].whereType<Widget>();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (entry.entryType != 'word') TagChip(entryTypeLabel(entry.entryType)),
        if (answerCorrect != null) ...[
          Container(
            padding: const EdgeInsets.all(MSpace.md),
            decoration: MDecor.softPanel(
              color: answerCorrect! ? MColors.successSoft : MColors.againBg,
              radius: MRadii.md,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                UiText(answerCorrect! ? '答對了' : '答錯了',
                    style: MFont.manrope(17, FontWeight.w800,
                        answerCorrect! ? MColors.success : MColors.againFg)),
                if (submittedAnswer?.isNotEmpty == true) ...[
                  const SizedBox(height: 4),
                  UiText('你的答案：${displayWord(submittedAnswer!)}',
                      style:
                          MFont.manrope(14, FontWeight.w600, MColors.gray700)),
                ],
                if (answerCorrect == false &&
                    correctAnswer?.isNotEmpty == true) ...[
                  const SizedBox(height: 2),
                  UiText('正確答案：${displayWord(correctAnswer!)}',
                      style:
                          MFont.manrope(14, FontWeight.w700, MColors.gray900)),
                ],
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
        Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(displayWord(entry.word),
                      style: MFont.manrope(32, FontWeight.w800, MColors.ink)),
                  if (ipa != null && showPronunciation)
                    Text(ipa,
                        style:
                            MFont.manrope(16, FontWeight.w600, MColors.muted)),
                ],
              ),
            ),
            if (showPronunciation) ...[
              for (final accent in const ['en-GB', 'en-US'])
                IconButton(
                  tooltip: accent == 'en-GB' ? '播放英式發音' : '播放美式發音',
                  onPressed: () => _playAccent(context, accent),
                  icon: Column(mainAxisSize: MainAxisSize.min, children: [
                    const Icon(Icons.volume_up_outlined),
                    UiText(accent == 'en-GB' ? '英式' : '美式',
                        style: MFont.caption),
                  ]),
                ),
            ],
          ],
        ),
        for (final w in fields) ...[const SizedBox(height: 16), w],
      ],
    );
  }
}

/// An example sentence with its translation; an AI-written translation is
/// marked 「AI 翻譯」 (spec section 7).
