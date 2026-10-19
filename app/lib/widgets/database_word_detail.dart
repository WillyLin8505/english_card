part of '../screens/database_library_screen.dart';

class DatabaseWordScreen extends StatelessWidget {
  final int wordId;
  const DatabaseWordScreen({super.key, required this.wordId});
  @override
  Widget build(BuildContext context) => ListenableBuilder(
      listenable: LexiconPack.instance,
      builder: (context, _) {
        final pack = LexiconPack.instance;
        final word = pack.byId(wordId);
        if (word == null) {
          return Scaffold(
              backgroundColor: MColors.canvas,
              appBar: AppBar(title: const UiText('單字詳情')),
              body:
                  Center(child: UiText('這個單字已從資料庫移除', style: MFont.bodyMuted)));
        }
        final scope = AppScope.of(context);
        final usages = pack
            .entriesFor(word.lemma)
            .where((entry) => entry.full && !entry.cardForm)
            .toList();
        if (usages.isEmpty) usages.add(word);
        final seenExamples = <String>{};
        final examples = [
          for (final usage in usages) ...usage.examples,
        ]
            .where((example) =>
                (example.translation ?? '').trim().isNotEmpty &&
                !isColumnWordList(example.text, word.lemma) &&
                seenExamples.add(example.text.toLowerCase()))
            .toList();
        final seenRelations = <String>{};
        final relations = [
          for (final usage in usages)
            for (final relation in usage.relations)
              if (!relation.hideByDefault &&
                  (relation.native ?? '').trim().isNotEmpty &&
                  seenRelations.add(
                      '${relation.relation}:${relation.word.toLowerCase()}'))
                relation,
        ];
        final seenForms = <String>{};
        final forms = [
          for (final usage in usages)
            for (final form in usage.forms)
              if (seenForms.add(form.form.toLowerCase())) form,
        ];
        Widget section(String label, List<Widget> children) => Padding(
              padding: const EdgeInsets.only(top: MSpace.lg),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  UiText(label, style: MFont.titleSm),
                  const SizedBox(height: MSpace.xs),
                  ...children,
                ],
              ),
            );
        Widget relationSection(String label, String kind) {
          final items = relations.where((r) => r.relation == kind).toList();
          if (items.isEmpty) return const SizedBox.shrink();
          return section(label, [
            Wrap(
              spacing: MSpace.xs,
              runSpacing: MSpace.xs,
              children: [
                for (final relation in items)
                  TagChip('${relation.word}　${relation.native}',
                      localize: false),
              ],
            ),
          ]);
        }

        final images = databaseEntryImages(pack.catalogImages, word);
        final sharesNounPicture =
            word.pictureIds != null && word.pictureIds!.isEmpty;
        return Scaffold(
            backgroundColor: MColors.canvas,
            appBar: AppBar(title: const UiText('單字詳情')),
            body: ListView(padding: const EdgeInsets.all(MSpace.md), children: [
              Text(word.lemma,
                  style: MFont.manrope(28, FontWeight.w800, MColors.ink)),
              const SizedBox(height: 4),
              Row(
                children: [
                  // Flexible: 「動詞 · B2 進階 · 罕見用法」 + badge is wider
                  // than a phone (390 px); the label wraps instead.
                  Flexible(
                    child: UiText(
                        '${[
                          if (word.entryType != 'word')
                            entryTypeLabel(word.entryType),
                          posLabel(word.pos)
                        ].join(' / ')}${word.cefr == null || word.rareUsage ? '' : ' · ${levelLabel(word.cefr!)}'}'
                        '${word.rareUsage ? ' · 罕見用法' : ''}',
                        style: MFont.bodyMuted),
                  ),
                  if (word.cefr != null && !word.rareUsage) ...[
                    const SizedBox(width: 8),
                    LevelBadge(word.cefr!),
                  ],
                ],
              ),
              if (word.ipa != null) ...[
                const SizedBox(height: 2),
                Text(word.ipa!, style: MFont.caption),
              ],
              const SizedBox(height: MSpace.sm),
              Align(
                alignment: Alignment.centerLeft,
                child: Tap(
                  onTap: () => scope.speak(context, word.lemma,
                      language: pack.target ?? 'en',
                      audioUrl: word.audio == null
                          ? null
                          : packRecordingUrl(pack.mediaBase, word.audio!)),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: MSpace.sm, vertical: 6),
                    constraints:
                        const BoxConstraints(minWidth: 48, minHeight: 48),
                    decoration: MDecor.chipSurface(active: true),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.volume_up_outlined,
                            size: 16, color: MColors.primary),
                        const SizedBox(width: 6),
                        UiText('聽發音',
                            style: MFont.manrope(
                                13, FontWeight.w700, MColors.primaryDeep)),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(height: MSpace.md),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                    onPressed: () {
                      final repo = scope.repository;
                      final messenger = ScaffoldMessenger.of(context)
                        ..removeCurrentSnackBar();
                      try {
                        final added = repo.addWord(
                            word: word.lemma,
                            pos: shortPos(word.pos),
                            meaning: word.learnerMeaning ?? '',
                            level: word.cefr);
                        // No Chinese yet: the card waits (問題回報 #44, #100).
                        // Checked before linkLexicon: a form folded into an
                        // existing card (問題回報 #51) drops this id, which
                        // would otherwise read back as "no meaning yet"
                        // even though it was added with one.
                        final waiting = (repo.entry(added.id)?.meaning ?? '')
                            .trim()
                            .isEmpty;
                        repo.linkLexicon(pack);
                        messenger.showSnackBar(SnackBar(
                            content: UiText(waiting
                                ? '已加入我的單字本；中文意思補齊後會自動排進複習'
                                : '已加入我的單字本與複習')));
                      } on DuplicateWordException {
                        // Swiped away as 已學會 earlier: adding it again means
                        // studying it again (問題回報 #99).
                        final e = repo.entryByWord(word.lemma);
                        final archived = e != null && repo.isArchived(e.id);
                        if (archived) repo.restoreWord(e.word);
                        messenger.showSnackBar(SnackBar(
                            content: UiText(
                                archived ? '已從「已學會」放回複習' : '這個單字已在我的單字本')));
                      }
                    },
                    child: const UiText('加入我的單字本與複習')),
              ),
              const SizedBox(height: MSpace.md),
              section('詞性與意思', [
                for (final usage in usages)
                  if (usage.senses.any(
                      (sense) => (sense.native ?? '').trim().isNotEmpty)) ...[
                    TagChip(posLabel(usage.pos)),
                    const SizedBox(height: 6),
                    for (final sense in usage.senses)
                      if ((sense.native ?? '').trim().isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(bottom: MSpace.xxs),
                          child: Text(sense.native!,
                              style: MFont.manrope(
                                  16, FontWeight.w700, MColors.primary)),
                        ),
                    const SizedBox(height: MSpace.sm),
                  ],
              ]),
              if (examples.isNotEmpty)
                section('例句', [
                  for (final example in examples)
                    Container(
                      width: double.infinity,
                      margin: const EdgeInsets.only(bottom: MSpace.xs),
                      padding: const EdgeInsets.all(MSpace.md),
                      decoration: MDecor.softCard(color: MColors.surfaceSoft),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(example.text,
                              style: MFont.manrope(
                                  15, FontWeight.w700, MColors.ink)),
                          const SizedBox(height: 4),
                          Text(example.translation!, style: MFont.bodyMuted),
                        ],
                      ),
                    ),
                ]),
              relationSection('近義詞', 'synonyms'),
              relationSection('反義詞', 'antonyms'),
              relationSection('同音詞', 'homophones'),
              relationSection('近音詞', 'near_homophones'),
              relationSection('拼寫相似詞', 'similar_spelling'),
              relationSection('衍生詞', 'derived_terms'),
              relationSection('相關詞', 'related'),
              if (forms.isNotEmpty)
                section('詞形變化', [
                  Wrap(
                    spacing: MSpace.xs,
                    runSpacing: MSpace.xs,
                    children: [
                      for (final form in forms)
                        TagChip(
                            '${form.form}（${formLabel(form.label ?? form.field)}）',
                            localize: false),
                    ],
                  ),
                ]),
              if (usages.any((usage) => usage.morphemes.length > 1))
                section('構詞', [
                  for (final usage in usages)
                    if (usage.morphemes.length > 1)
                      Text(
                        usage.morphemes
                            .map((part) => (part.native ?? '').trim().isEmpty
                                ? part.part
                                : '${part.part}（${part.native}）')
                            .join(' ＋ '),
                        style: MFont.body,
                      ),
                ]),
              if (usages.any(
                  (usage) => (usage.etymology?.native ?? '').trim().isNotEmpty))
                section('詞源', [
                  for (final usage in usages)
                    if ((usage.etymology?.native ?? '').trim().isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(bottom: MSpace.xs),
                        child:
                            Text(usage.etymology!.native!, style: MFont.body),
                      ),
                ]),
              const SizedBox(height: MSpace.lg),
              UiText('資料庫圖片（${images.length}）', style: MFont.titleSm),
              const SizedBox(height: MSpace.xs),
              if (sharesNounPicture)
                Container(
                  padding: const EdgeInsets.all(MSpace.lg),
                  decoration: MDecor.emptyStateCard(),
                  child: UiText('這個詞性顯示同拼法名詞的圖片。這個拼法沒有名詞。',
                      style: MFont.bodyMuted),
                )
              else if (images.isEmpty)
                Container(
                  padding: const EdgeInsets.all(MSpace.lg),
                  decoration: MDecor.emptyStateCard(),
                  child: UiText('資料庫尚未加入這個單字的圖片', style: MFont.bodyMuted),
                ),
              for (final image in images)
                Padding(
                    padding: const EdgeInsets.only(top: MSpace.sm),
                    child: SizedBox(
                        height: 240, child: DatabaseImageTile(image: image))),
            ]));
      });
}
