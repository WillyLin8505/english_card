import '../l10n/ui_text.dart';
import '../services/learning_content.dart';
import '../services/accent_audio.dart';
import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/word_entry.dart';
import '../services/lexicon_pack.dart';
import '../services/word_database_query.dart';
import '../theme/mobile_theme.dart';
import '../widgets/recording_credit.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/dialogs.dart';
import '../widgets/mobile/m_icon.dart';
import '../services/photo_store.dart';
import '../widgets/mobile/photo_widgets.dart';
import 'database_library_screen.dart';
import 'flashcard_screen.dart';

/// 單字詳情 — Figma word-detail-view (11:173), extended with spec section
/// 7's 單字集 detail: the full WordEntry, every photo it appears in, its
/// one card with the complete review log and FSRS changes, editing of
/// all AI and dictionary data, and 已學會 / 復原.
///
/// Sections with no data are left out rather than drawn with "—" as in
/// the mock — spec section 5: "欄位沒有內容時自動省略；不可出現空白標題".
class WordDetailScreen extends StatelessWidget {
  final String wordEntryId;

  /// The photo label the user came from; its photo is shown first.
  final String? occurrenceId;

  const WordDetailScreen(
      {super.key, required this.wordEntryId, this.occurrenceId});

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    return ListenableBuilder(
      listenable: repo,
      builder: (context, _) {
        final entry = repo.entry(wordEntryId);
        if (entry == null) {
          return const Scaffold(body: Center(child: UiText('找不到這個單字')));
        }
        final card = repo.cardOf(entry.id);
        // 問題回報 #684: both accents' recordings are downloaded while the
        // page is read, so 聽發音 plays at once.
        scope.prefetchAudio(repo.language == 'en'
            ? [
                for (final accent in const ['en-GB', 'en-US'])
                  accentAudioUrl(entry, accent, orDefault: true),
              ]
            : [entry.audioUrl]);

        Future<void> edit() async {
          final result = await showEditWordDialog(context, entry);
          if (result != null) repo.editEntry(result.$1, result.$2);
        }

        return Scaffold(
          backgroundColor: MColors.canvas,
          body: SafeArea(
            bottom: false,
            child: Column(
              children: [
                MNavBar(
                  title: '單字詳情',
                  divider: false,
                  leading: const BackNavButton(),
                  trailing: NavIconButton(
                    label: '編輯單字',
                    background: MColors.primarySoft,
                    icon: const Icon(Icons.edit_outlined,
                        size: 20, color: MColors.primary),
                    onTap: edit,
                  ),
                ),
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(MSpace.xl),
                    child: _WordBody(entry: entry, occurrenceId: occurrenceId),
                  ),
                ),
                if (card != null)
                  _ArchiveButton(
                    archived: card.archived,
                    // The button's own label says what happened; a toast
                    // would cover it.
                    onTap: () => card.archived
                        ? repo.restoreWord(entry.word)
                        : repo.archiveWord(entry.id),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// Label for a non-neutral register; null for neutral or unknown (#421).
String? _registerLabel(String? register) => switch (register) {
      'written' => '書面語',
      'spoken' => '口語',
      'slang' => '俚語',
      'vulgar' => '粗俗',
      _ => null,
    };

class _WordBody extends StatelessWidget {
  final WordEntry entry;
  final String? occurrenceId;

  const _WordBody({required this.entry, required this.occurrenceId});

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    final pack = LexiconPack.instance;

    // 卡 #227 第 124 輪: common senses first, slang/obsolete/offensive last
    // (bank 動詞「把東西藏在直腸內」 was third, 「傾斜轉彎」 behind 顯示更多).
    final senseTier = <String, int>{
      for (final e in pack.entriesFor(entry.word))
        for (final s in e.senses) 'pack:${pack.target}:${s.id}': s.displayTier,
    };
    List<WordSense> orderedSenses(LexemeUsage usage) {
      final senses = usage.senses.toList();
      final rank = {for (var i = 0; i < senses.length; i++) senses[i]: i};
      senses.sort((a, b) {
        final t = (senseTier[a.id] ?? 0).compareTo(senseTier[b.id] ?? 0);
        return t != 0 ? t : rank[a]!.compareTo(rank[b]!);
      });
      return senses;
    }

    // One part of speech shows its main meaning big; its other senses were
    // missing (卡 #227 第 124 輪: pupil 只有「學生」, 沒有「瞳孔」 — the
    // 資料庫 detail lists them). Those whose words are all in the main
    // meaning are not repeated.
    final meaningWords = entry.meaning
        .split(RegExp(r'[、，,；;\s]+'))
        .where((w) => w.isNotEmpty)
        .toSet();
    final otherSenses = entry.effectiveUsages.length == 1
        ? <String>{
            for (final sense in orderedSenses(entry.effectiveUsages.single))
              if (sense.meaning.trim().isNotEmpty &&
                  !sense.meaning
                      .split(RegExp(r'[、，,；;\s]+'))
                      .where((w) => w.isNotEmpty)
                      .every(meaningWords.contains))
                sense.meaning.trim(),
          }.toList()
        : const <String>[];
    // Owner decision (#528): slang/obsolete/offensive senses (tier 2) always
    // wait behind 顯示更多, even when fewer than [cap] common ones exist
    // (fridge「胖女人」, commercial「男妓」); [floor] keeps one meaning shown.
    final rareMeanings = <String>{
      for (final usage in entry.effectiveUsages)
        for (final s in usage.senses)
          if ((senseTier[s.id] ?? 0) >= 2) s.meaning.trim(),
    }..removeAll({
        for (final usage in entry.effectiveUsages)
          for (final s in usage.senses)
            if ((senseTier[s.id] ?? 0) < 2) s.meaning.trim(),
      });
    int initialShown(Iterable<String> meanings, int cap, {int floor = 0}) =>
        meanings
            .where((m) => !rareMeanings.contains(m.trim()))
            .length
            .clamp(floor, cap);

    // Owner decision (issue #252): three per section, the rest behind 更多.
    List<({String word, String meaning})> relatedWords(String kind) {
      final seen = <String>{};
      final words = entry.userEdited.contains(WordField.related)
          ? [
              for (final r in entry.related)
                if (r.type == relationTypeFromKey(kind) &&
                    !r.hideByDefault &&
                    seen.add(r.word.toLowerCase()))
                  (word: r.word, meaning: r.native ?? ''),
            ]
          : [
              for (final usage in entry.effectiveUsages)
                for (final r in pack
                        .lookup(entry.word, pos: usage.pos)
                        ?.entry
                        .relations ??
                    const <LexRelation>[])
                  if (r.relation == kind &&
                      !r.hideByDefault &&
                      // 卡 #227 第 147 輪: not the words of a slang/obsolete
                      // sense, which waits behind 顯示更多 (#528) — 653 such
                      // words showed (bang、beef、bust…).
                      (senseTier['pack:${pack.target}:${r.senseId}'] ?? 0) <
                          2 &&
                      (r.native ?? '').trim().isNotEmpty &&
                      r.word.toLowerCase() != entry.word.toLowerCase() &&
                      seen.add(r.word.toLowerCase()))
                    (word: r.word, meaning: r.native!),
            ];
      return words;
    }

    // Same as the review back (issue #399): a word shown in an earlier
    // section (近義詞) is not repeated in a later one (衍生詞、相關詞).
    final shown = <String>{};
    Widget relatedSection(
      String label,
      List<String> kinds,
    ) {
      final words = [
        for (final kind in kinds)
          for (final w in relatedWords(kind))
            if (shown.add(w.word.toLowerCase())) w
      ];
      if (words.isEmpty) return const SizedBox.shrink();
      return _Section(
          label: label,
          child: _MoreList(
            initial: 10000,
            wrap: true,
            children: [
              for (final w in words)
                // 問題回報 #580: the short meaning; a tap shows it all.
                RelationChip(w.word, meaning: w.meaning)
            ],
          ));
    }

    final seenExamples = <String>{};
    final examples = [
      ...entry.examples,
      for (final usage in entry.effectiveUsages) ...usage.examples,
    ]
        .where((e) =>
            (e.translation ?? '').trim().isNotEmpty &&
            seenExamples.add(e.text.toLowerCase()))
        .toList();
    final forms = <String, Set<String>>{};
    void addForm(String form, String label) {
      if (form.trim().isEmpty) return;
      (forms[form.trim()] ??= {}).add(formLabel(label));
    }

    for (final usage in entry.effectiveUsages) {
      final source = pack.lookup(entry.word, pos: usage.pos)?.entry;
      if (source != null) {
        for (final form in pack.detailFor(source).inflections) {
          addForm(form.form, form.label);
        }
      }
    }
    for (final form in entry.forms) {
      addForm(form.form, form.label);
    }
    // The photo the learner came from first, then the learner's own photos
    // (newest first, 問題回報 #864), then the rest.
    int rank(PhotoOccurrence o) {
      if (o.id == occurrenceId) return 0;
      final p = repo.photo(o.photoId);
      return p != null && repo.isOwnPhoto(p) ? 1 : 2;
    }

    final occurrences = repo.occurrencesOf(entry.id)
      ..sort((a, b) {
        final r = rank(a).compareTo(rank(b));
        if (r != 0 || rank(a) != 1) return r;
        return repo.photo(b.photoId)!
            .takenAt
            .compareTo(repo.photo(a.photoId)!.takenAt);
      });
    final contexts = [
      for (final o in occurrences)
        // A photo whose original file is gone is skipped (問題回報 #283).
        if (repo.photo(o.photoId) case final p?
            when !PhotoStore.lostOriginal(p))
          (photo: p, occ: o),
    ];
    final packEntry = contexts.isEmpty
        ? pack.lookup(entry.word, pos: entry.pos)?.entry
        : null;
    final databaseImages = packEntry == null
        ? const <Map<String, dynamic>>[]
        : databaseEntryImages(pack.catalogImages, packEntry);
    // A part of speech with no meaning yet is left out whole (cigarette 動詞);
    // with none left there is no 詞性與意思 title at all.
    final meaningUsages = [
      for (final usage in entry.effectiveUsages)
        if (usage.senses.any((s) => s.meaning.trim().isNotEmpty)) usage,
    ];
    final sections = <Widget>[
      // pronounce-block
      Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                    headword(entry.word, entry.language,
                        pos: entry.pos,
                        inflections: [
                          for (final u in entry.effectiveUsages)
                            if (pack.lookup(entry.word, pos: u.pos)?.entry
                                case final s?)
                              ...pack.detailFor(s).inflections
                        ]),
                    style: MFont.manrope(32, FontWeight.w800, MColors.ink)),
                // 卡 #227 第 147 輪: the IPA in 設定's accent, like the audio.
                if ((repo.language == 'en'
                        ? accentIpa(entry, scope.settings.englishAccent)
                        : entry.ipa)
                    case final ipa?) ...[
                  const SizedBox(height: MSpace.xxs),
                  Text(ipa,
                      style: MFont.manrope(16, FontWeight.w600, MColors.muted)),
                ],
                // 問題回報 #657: who recorded the pronunciation, and its license.
                if (repo.language == 'en'
                        ? accentAudioCredit(entry, scope.settings.englishAccent)
                        : null
                    case final credit?) ...[
                  const SizedBox(height: 2),
                  RecordingCreditLine(credit),
                ],
                const SizedBox(height: MSpace.xxs + 2),
                Wrap(
                  spacing: MSpace.xxs + 2,
                  runSpacing: MSpace.xxs + 2,
                  children: [
                    if (entry.entryType != 'word')
                      TagChip(entryTypeLabel(entry.entryType)),
                    // The 詞性與意思 section below labels each part of speech,
                    // so the header shows none (#421); with no meaning yet
                    // that section is absent and the header keeps it (#469).
                    if (entry.meaning.isEmpty &&
                        entry.effectiveUsages.length <= 1 &&
                        entry.pos.isNotEmpty &&
                        entry.pos != 'unknown')
                      TagChip(posLabel(entry.pos)),
                    if (entry.level != null) LevelBadge(entry.level!),
                    // Neutral register is the default: only label the rest (#421).
                    if (_registerLabel(entry.register) case final label?)
                      TagChip(label),
                  ],
                ),
              ],
            ),
          ),
          Tap(
            label: '播放發音',
            onTap: () =>
                scope.speakEntry(context, entry, language: repo.language),
            child: Container(
              width: 56,
              height: 56,
              decoration: const BoxDecoration(
                color: MColors.primary,
                shape: BoxShape.circle,
                boxShadow: MShadows.primaryGlow,
              ),
              child:
                  const Center(child: MSvg(MIcon.audioWaveformWhite, size: 24)),
            ),
          ),
        ],
      ),
      if (entry.dataStatus != WordDataStatus.complete)
        _DataStatus(entry: entry),
      if (entry.effectiveUsages.length > 1 && meaningUsages.isNotEmpty)
        _Section(
          label: '詞性與意思',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // A part of speech with no meaning yet would be a bare chip
              // (secret 動詞, imply 名詞; 卡 #12 第 131 輪), as in the database view.
              for (final usage in meaningUsages) ...[
                TagChip(posLabel(usage.pos)),
                const SizedBox(height: MSpace.xxs),
                _MoreList(
                  initial: initialShown([
                    for (final s in usage.senses)
                      if (s.meaning.trim().isNotEmpty) s.meaning
                  ], 3, floor: 1),
                  children: [
                    for (final sense in orderedSenses(usage))
                      if (sense.meaning.trim().isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(bottom: MSpace.xxs),
                          child: Text(sense.meaning,
                              style: MFont.manrope(
                                  17, FontWeight.w700, MColors.ink)),
                        ),
                  ],
                ),
                const SizedBox(height: MSpace.xs),
              ],
            ],
          ),
        )
      else if (entry.meaning.isNotEmpty)
        // 問題回報 #469: one part of speech uses the same 詞性與意思 title and
        // POS chip as several (it used to be titled with the language name).
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SectionLabel('詞性與意思'),
            const SizedBox(height: MSpace.xs),
            if (entry.pos.isNotEmpty) ...[
              TagChip(posLabel(entry.pos)),
              const SizedBox(height: MSpace.xxs),
            ],
            Text(entry.meaning,
                style: MFont.manrope(22, FontWeight.w800, MColors.ink)),
            if (entry.definition != null &&
                entry.definition != entry.meaning) ...[
              const SizedBox(height: MSpace.xxs),
              Text(entry.definition!,
                  style: MFont.manrope(14, FontWeight.w600, MColors.muted)),
            ],
            if (otherSenses.isNotEmpty) ...[
              const SizedBox(height: MSpace.xs),
              _MoreList(
                initial: initialShown(otherSenses, 2),
                children: [
                  for (final meaning in otherSenses)
                    Padding(
                      padding: const EdgeInsets.only(bottom: MSpace.xxs),
                      child: Text(meaning,
                          style:
                              MFont.manrope(17, FontWeight.w700, MColors.ink)),
                    ),
                ],
              ),
            ],
          ],
        ),
      if (contexts.isNotEmpty)
        _Section(
          label: '出現這個單字的照片（${contexts.length}）',
          child: SizedBox(
            height: 140,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: contexts.length,
              separatorBuilder: (_, __) => const SizedBox(width: MSpace.sm - 2),
              itemBuilder: (context, i) {
                final c = contexts[i];
                return Tap(
                  label: '開啟照片「${c.photo.title}」',
                  onTap: () {
                    Navigator.of(context).pop();
                    scope.navigator.openPhoto(c.photo.id);
                  },
                  child: Container(
                    width: contexts.length == 1 ? 354 : 220,
                    decoration:
                        MDecor.card(radius: MRadii.lg, shadow: MShadows.soft),
                    clipBehavior: Clip.antiAlias,
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        _ContextCrop(
                            photo: c.photo,
                            anchor: c.occ.anchor,
                            // 問題回報 #410: the AI may mark the wrong
                            // spot; long-press the dot and drag it.
                            onMoved: (to) => AppScope.of(context)
                                .repository
                                .moveLabel(c.occ.id, to)),
                        Positioned(
                          left: MSpace.xs,
                          bottom: MSpace.xs,
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: MSpace.xs, vertical: 3),
                            decoration: MDecor.overlayPill(
                              color: MColors.ink.withValues(alpha: 0.7),
                              radius: MRadii.sm,
                            ),
                            child: Text(c.photo.title,
                                style: MFont.manrope(
                                    11, FontWeight.w700, Colors.white)),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ),
      // 問題回報 #617: a word with no photo of the learner's own (added from
      // the database or by hand) still shows the database pictures that tag
      // it, with their word labels.
      if (contexts.isEmpty && databaseImages.isNotEmpty)
        _Section(
          label: '資料庫圖片（${databaseImages.length}）',
          child: Column(
            children: [
              for (final image in databaseImages.take(3))
                Padding(
                  padding: const EdgeInsets.only(bottom: MSpace.sm),
                  child: SizedBox(
                      height: 240, child: DatabaseImageTile(image: image)),
                ),
            ],
          ),
        ),
      if (entry.tags.isNotEmpty)
        _Section(
          label: '標籤',
          child: Wrap(
            spacing: MSpace.xs,
            runSpacing: MSpace.xs,
            children: [
              for (final tag in entry.tags) TagChip(tag, localize: false)
            ],
          ),
        ),
      if (entry.meaning.isEmpty) const UiText('{N}意思尚未補齊，連線後會自動更新。'),
      if (examples.isNotEmpty)
        _Section(
          label: '例句',
          child: _MoreList(
            initial: 5,
            children: [
              for (final example in examples)
                Padding(
                  padding: const EdgeInsets.only(bottom: MSpace.sm),
                  child: ExampleText(example: example),
                ),
            ],
          ),
        ),
      relatedSection('近義詞', ['synonyms']),
      relatedSection('反義詞', ['antonyms']),
      relatedSection('同音詞', ['homophones']),
      relatedSection('衍生詞', ['derived_terms']),
      relatedSection('相關詞', ['related']),
      relatedSection('容易混淆的字', ['near_homophones', 'similar_spelling']),
      if (forms.isNotEmpty)
        _Section(
            label: '詞形變化',
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final form in forms.entries)
                  TagChip('${form.key}（${mergeFormLabels(form.value)}）')
              ],
            )),
      if (learningMorphology(entry) case final parts?)
        _TextSection('構詞', parts),
      if (learningEtymology(entry) case final origin?)
        _TextSection('詞源', origin),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final (i, s) in sections.indexed) ...[
          if (i > 0) const SizedBox(height: 20),
          s,
        ],
      ],
    );
  }
}

/// One 詞形變化 chip's labels, gathered from every part of speech. A form
/// with its own meaning carries it on each label — 過去式・形容詞：有負載的,
/// 過去分詞・形容詞：有負載的, 形容詞：有負載的 — so the grammar labels are
/// listed once and the meaning once after them:
/// loaded（過去式；過去分詞・形容詞：有負載的）(卡 #227 第 142 輪).
String mergeFormLabels(Iterable<String> labels) {
  final grammar = <String>{};
  final meanings = <String>{};
  for (final label in labels) {
    final colon = label.indexOf('：');
    if (colon < 0) {
      if (label.isNotEmpty) grammar.add(label);
      continue;
    }
    final dot = label.lastIndexOf('・', colon);
    if (dot > 0) grammar.add(label.substring(0, dot));
    meanings
        .addAll(label.substring(dot + 1).split('；').where((m) => m.isNotEmpty));
  }
  return [
    if (grammar.isNotEmpty) grammar.join('；'),
    if (meanings.isNotEmpty) meanings.join('；'),
  ].join('・');
}

/// Background data fetch in progress, or failed (spec section 7: 失敗標記).
class _DataStatus extends StatelessWidget {
  final WordEntry entry;

  const _DataStatus({required this.entry});

  @override
  Widget build(BuildContext context) {
    final failed = entry.dataStatus == WordDataStatus.failed;
    final scope = AppScope.of(context);
    return Container(
      padding: const EdgeInsets.all(MSpace.sm),
      decoration: MDecor.insetCard(
        color: failed ? MColors.hardBg : MColors.primarySoft,
        radius: MRadii.md,
      ),
      child: Row(
        children: [
          Icon(failed ? Icons.error_outline : Icons.downloading_rounded,
              size: 18, color: failed ? MColors.hardFg : MColors.primary),
          const SizedBox(width: MSpace.xs),
          Expanded(
            child: UiText(
              failed
                  ? (missingFieldNames(entry).isEmpty
                      ? '部分內容尚未補齊，詞庫更新後會自動補上。'
                      : '尚缺：${missingFieldNames(entry).join('、')}。詞庫更新後會自動補上。')
                  : '正在整理單字內容…',
              style: MFont.manrope(12, FontWeight.w700,
                  failed ? MColors.hardFg : MColors.primary),
            ),
          ),
          if (failed)
            TextButton(
              onPressed: () {
                scope.repository.retryWordData(entry.id);
                scope.enricher.process();
              },
              child: const UiText('重試'),
            ),
        ],
      ),
    );
  }
}

/// The word's one card: FSRS state and the complete review log with the
/// state change each grade made (spec section 7: 完整 review log 與 FSRS
/// 變化).
/// 出現這個單字的照片: the photo zoomed in around the word's label, keeping the
/// label's object centred where the edges allow.
class _ContextCrop extends StatelessWidget {
  final Photo photo;
  final LabelPoint anchor;

  final ValueChanged<LabelPoint>? onMoved;

  const _ContextCrop({required this.photo, required this.anchor, this.onMoved});

  static const _zoom = 2.0;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, c) {
          final box = c.biggest;
          // Draw the photo at _zoom× the box, then shift so the anchor
          // sits in the middle, clamped so no empty edge shows.
          final big = Size(box.width * _zoom, box.height * _zoom);
          final at = CoverGeometry(big, photo).toBox(anchor);
          final dx = (box.width / 2 - at.dx).clamp(box.width - big.width, 0.0);
          final dy =
              (box.height / 2 - at.dy).clamp(box.height - big.height, 0.0);
          return ClipRect(
            child: Stack(fit: StackFit.expand, children: [
              OverflowBox(
                alignment: Alignment.topLeft,
                minWidth: big.width,
                maxWidth: big.width,
                minHeight: big.height,
                maxHeight: big.height,
                child: Transform.translate(
                  offset: Offset(dx, dy),
                  child: SizedBox.fromSize(size: big, child: PhotoImage(photo)),
                ),
              ),
              if (onMoved != null)
                DraggableAnchorDot(
                  at: at + Offset(dx, dy),
                  onMoved: (to) => onMoved!(
                      CoverGeometry(big, photo).fromBox(to - Offset(dx, dy))),
                ),
            ]),
          );
        },
      );
}

/// Shows the first [initial] children and a 更多 / 收起 toggle for the rest
/// ([initial] 0 starts fully collapsed).
class _MoreList extends StatefulWidget {
  final int initial;
  final bool wrap;
  final List<Widget> children;

  const _MoreList(
      {required this.initial, required this.children, this.wrap = false});

  @override
  State<_MoreList> createState() => _MoreListState();
}

class _MoreListState extends State<_MoreList> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final all = widget.children;
    final hidden = all.length - widget.initial;
    final shown =
        _open || hidden <= 0 ? all : all.take(widget.initial).toList();
    final body = widget.wrap
        ? Wrap(spacing: MSpace.xs, runSpacing: MSpace.xs, children: shown)
        : Column(crossAxisAlignment: CrossAxisAlignment.start, children: shown);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (shown.isNotEmpty) body,
        if (hidden > 0)
          Tap(
            label: _open ? '收起' : '顯示更多',
            onTap: () => setState(() => _open = !_open),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: MSpace.xxs),
              child: UiText(_open ? '收起' : '顯示更多（$hidden）',
                  style: MFont.manrope(14, FontWeight.w800, MColors.primary)),
            ),
          ),
      ],
    );
  }
}

class _Section extends StatelessWidget {
  final String label;
  final Widget child;

  const _Section({required this.label, required this.child});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionLabel(label),
          const SizedBox(height: MSpace.xs),
          child
        ],
      );
}

class _TextSection extends StatelessWidget {
  final String label;
  final String text;

  const _TextSection(this.label, this.text);

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionLabel(label),
          const SizedBox(height: MSpace.xxs),
          Text(text, style: MFont.manrope(15, FontWeight.w600, MColors.ink)),
        ],
      );
}

/// Figma bottom-cta-area (11:218), now for 已學會 / 復原: archiving keeps
/// the card's history, so 復原 brings everything back.
class _ArchiveButton extends StatelessWidget {
  final bool archived;
  final VoidCallback onTap;

  const _ArchiveButton({required this.archived, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.paddingOf(context).bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(
          MSpace.xl, MSpace.md, MSpace.xl, MSpace.xl + bottom),
      child: Tap(
        onTap: onTap,
        label: archived ? '復原學習' : '標為已學會',
        child: Container(
          height: 54,
          decoration: archived
              ? MDecor.primaryPill(radius: 27)
              : MDecor.insetCard(color: MColors.successSoft, radius: 27),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(archived ? Icons.undo_rounded : Icons.check_rounded,
                  size: 20, color: archived ? Colors.white : MColors.success),
              const SizedBox(width: MSpace.xs),
              // 問題回報 #534: the French label overflowed at 375 pt (the
              // end screen's forgotten words open this page).
              Flexible(
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: UiText(
                    archived ? '復原學習' : '標為已學會',
                    style: MFont.manrope(16, FontWeight.w800,
                        archived ? Colors.white : MColors.success),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
