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
        // 問題回報 #684: the recordings are downloaded while the page is read.
        scope.prefetchAudio((pack.target ?? 'en') == 'en'
            ? [
                for (final accent in const ['en-GB', 'en-US'])
                  packAccentAudioUrl(word, accent, orDefault: true),
              ]
            : [
                if (word.audio != null)
                  packRecordingUrl(pack.mediaBase, word.audio!),
              ]);
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
        // 卡 #227 第 147 輪: words of a slang/obsolete sense are left out.
        final rareSenses = {
          for (final usage in usages)
            for (final s in usage.senses)
              if (s.displayTier >= 2) s.id,
        };
        final relations = [
          for (final usage in usages)
            for (final relation in usage.relations)
              if (!relation.hideByDefault &&
                  !rareSenses.contains(relation.senseId) &&
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
        // Issue #399: a word already shown in an earlier section is skipped.
        final shown = <String>{};
        Widget relationSection(String label, String kind) {
          final items = relations
              .where((r) =>
                  r.relation == kind && shown.add(r.word.toLowerCase()))
              .toList();
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

        // A part of speech with no Chinese yet is left out whole, and the
        // section with it when no part of speech has any (stub words).
        final meaningUsages = [
          for (final usage in usages)
            if (usage.senses
                .any((sense) => (sense.native ?? '').trim().isNotEmpty))
              usage,
        ];
        // 「包含待補齊單字」: a stub (pos unknown, no Chinese, no photo).
        final stub = !word.full;
        final noMeaning = (word.learnerMeaning ?? '').trim().isEmpty;
        final headerLabel = '${[
          if (word.entryType != 'word') entryTypeLabel(word.entryType),
          if (word.pos != 'unknown') posLabel(word.pos)
        ].join(' / ')}${word.cefr == null || word.rareUsage ? '' : ' · ${levelLabel(word.cefr!)}'}'
            '${word.rareUsage ? ' · 罕見用法' : ''}';
        final images = databaseEntryImages(pack.catalogImages, word);
        final sharesNounPicture =
            word.pictureIds != null && word.pictureIds!.isEmpty;
        return Scaffold(
            backgroundColor: MColors.canvas,
            appBar: AppBar(title: const UiText('單字詳情')),
            body: ListView(padding: const EdgeInsets.all(MSpace.md), children: [
              Text(word.lemma,
                  style: MFont.manrope(28, FontWeight.w800, MColors.ink)),
              if (headerLabel.isNotEmpty ||
                  (word.cefr != null && !word.rareUsage)) ...[
                const SizedBox(height: 4),
                Row(
                  children: [
                    // Flexible: 「動詞 · B2 進階 · 罕見用法」 + badge is wider
                    // than a phone (390 px); the label wraps instead.
                    if (headerLabel.isNotEmpty)
                      Flexible(
                        child: UiText(headerLabel, style: MFont.bodyMuted),
                      ),
                    if (word.cefr != null && !word.rareUsage) ...[
                      if (headerLabel.isNotEmpty) const SizedBox(width: 8),
                      LevelBadge(word.cefr!),
                    ],
                  ],
                ),
              ],
              if (stub) ...[
                const SizedBox(height: MSpace.xs),
                UiText('這個字還在補齊資料', style: MFont.bodyMuted),
              ],
              // 卡 #227 第 147 輪: the IPA in 設定's accent, like the audio.
              if (((pack.target ?? 'en') == 'en'
                      ? packAccentIpa(word, scope.settings.englishAccent)
                      : word.ipa)
                  case final ipa?) ...[
                const SizedBox(height: 2),
                Text(ipa, style: MFont.caption),
              ],
              // 問題回報 #657: who recorded the pronunciation, and its license.
              if (((pack.target ?? 'en') == 'en'
                      ? packAccentAudioCredit(word, scope.settings.englishAccent)
                      : null)
                  case final credit?) ...[
                const SizedBox(height: 2),
                RecordingCreditLine(credit),
              ],
              const SizedBox(height: MSpace.sm),
              Align(
                alignment: Alignment.centerLeft,
                child: Tap(
                  onTap: () => scope.speak(context, word.lemma,
                      language: pack.target ?? 'en',
                      // 問題回報 #510: the recording in 設定's accent.
                      audioUrl: (pack.target ?? 'en') == 'en'
                          ? packAccentAudioUrl(word, scope.settings.englishAccent,
                              orDefault: true)
                          : word.audio == null
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
              // Already collected: says so before any tap.
              ListenableBuilder(
                  listenable: scope.repository,
                  builder: (context, _) {
                    final collected = databaseWordCollected(context, word);
                    return SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                          key: const ValueKey('database-add'),
                          onPressed: collected
                              ? null
                              : () => addDatabaseWord(context, pack, word),
                          child: UiText(collected
                              ? '已在我的單字本 ✓'
                              : noMeaning
                                  ? '加入單字本（{N}補齊後排進複習）'
                                  : '加入我的單字本與複習')),
                    );
                  }),
              const SizedBox(height: MSpace.md),
              if (meaningUsages.isNotEmpty)
                section('詞性與意思', [
                  for (final usage in meaningUsages) ...[
                    TagChip(posLabel(usage.pos)),
                    const SizedBox(height: 6),
                    // Common senses first, slang/obsolete last (卡 #227).
                    for (final sense in [
                      for (final tier in const [0, 1, 2])
                        ...usage.senses.where((s) => s.displayTier == tier)
                    ])
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
                            form.field == 'fr_gender'
                                ? '${frenchWithArticle(word.lemma, form.form)}'
                                    '（${frenchGenderLabel(form.form)}）'
                                : '${form.form}（${formLabel(form.label ?? form.field)}）'),
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
              // No photo: no empty 「資料庫圖片（0）」 section — one muted line,
              // and nothing at all for a stub (its notice says it is pending).
              if (images.isEmpty && !sharesNounPicture) ...[
                if (!stub) ...[
                  const SizedBox(height: MSpace.lg),
                  UiText('資料庫尚未加入這個單字的圖片', style: MFont.caption),
                ],
              ] else ...[
                const SizedBox(height: MSpace.lg),
                UiText('資料庫圖片（${images.length}）', style: MFont.titleSm),
                const SizedBox(height: MSpace.xs),
              ],
              if (sharesNounPicture)
                Container(
                  padding: const EdgeInsets.all(MSpace.lg),
                  decoration: MDecor.emptyStateCard(),
                  child: UiText('這個詞性顯示同拼法名詞的圖片。這個拼法沒有名詞。',
                      style: MFont.bodyMuted),
                ),
              for (final image in images)
                Padding(
                    padding: const EdgeInsets.only(top: MSpace.sm),
                    child: SizedBox(
                        height: 240, child: DatabaseImageTile(image: image))),
            ]));
      });
}

/// Adds a pack word to 我的單字本 and review; shared by the word detail and
/// the photo's tag list (問題回報 #577). Returns true when newly added.
/// [quiet] skips the snackbar (bulk add reports once).
bool addDatabaseWord(BuildContext context, LexiconPack pack, LexEntry word,
    {bool quiet = false}) {
  final repo = AppScope.of(context).repository;
  final messenger = ScaffoldMessenger.of(context);
  if (!quiet) messenger.removeCurrentSnackBar();
  try {
    final added = repo.addWord(
        word: word.lemma,
        pos: shortPos(word.pos),
        meaning: word.learnerMeaning ?? '',
        level: word.cefr);
    // No Chinese yet: the card waits (問題回報 #44, #100). Checked before
    // linkLexicon: a form folded into an existing card (問題回報 #51) drops
    // this id, which would read back as "no meaning yet".
    final waiting = (repo.entry(added.id)?.meaning ?? '').trim().isEmpty;
    repo.linkLexicon(pack);
    if (!quiet) {
      messenger.showSnackBar(SnackBar(
          content: UiText(waiting
              ? '已加入我的單字本；{N}意思補齊後會自動排進複習'
              : '已加入我的單字本與複習')));
    }
    return true;
  } on DuplicateWordException {
    // Swiped away as 已學會 earlier: adding it again means studying it
    // again (問題回報 #99).
    final e = repo.entryByWord(word.lemma);
    final archived = e != null && repo.isArchived(e.id);
    if (archived) repo.restoreWord(e.word);
    if (!quiet) {
      messenger.showSnackBar(SnackBar(
          content: UiText(archived ? '已從「已學會」放回複習' : '這個單字已在我的單字本')));
    }
    return archived;
  }
}

/// In 我的單字本 and not archived.
bool databaseWordCollected(BuildContext context, LexEntry word) {
  final repo = AppScope.of(context).repository;
  final e = repo.entryByWord(word.lemma);
  return e != null && !repo.isArchived(e.id);
}
