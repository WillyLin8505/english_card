import '../services/learning_content.dart';
import 'package:flutter/material.dart';

import '../app/app_scope.dart';
import '../models/learning_card.dart';
import '../models/photo.dart';
import '../models/word_entry.dart';
import '../services/app_settings.dart';
import '../services/word_database_query.dart';
import '../theme/mobile_theme.dart';
import '../widgets/mobile/common.dart';
import '../widgets/mobile/dialogs.dart';
import '../widgets/mobile/m_icon.dart';
import '../widgets/mobile/photo_widgets.dart';
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
          return const Scaffold(body: Center(child: Text('找不到這個單字')));
        }
        final card = repo.cardOf(entry.id);

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
                    padding: const EdgeInsets.all(24),
                    child: _WordBody(
                        entry: entry, card: card, occurrenceId: occurrenceId),
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

class _WordBody extends StatelessWidget {
  final WordEntry entry;
  final LearningCard? card;
  final String? occurrenceId;

  const _WordBody(
      {required this.entry, required this.card, required this.occurrenceId});

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;

    Widget relatedSection(String label, String kind) {
      final words = learningRelations(entry, repo.profile.cefr, kind);
      if (words.isEmpty) return const SizedBox.shrink();
      return _Section(
          label: label,
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final w in words) TagChip('${w.word}　${w.meaning}')
            ],
          ));
    }

    final examples = learningExamples(entry, repo.profile.cefr);
    // The photo the learner came from first, then the rest.
    final occurrences = repo.occurrencesOf(entry.id)
      ..sort((a, b) => (a.id == occurrenceId ? 0 : 1)
          .compareTo(b.id == occurrenceId ? 0 : 1));
    final contexts = [
      for (final o in occurrences)
        if (repo.photo(o.photoId) case final p?) (photo: p, occ: o),
    ];
    final sections = <Widget>[
      // pronounce-block
      Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(displayWord(entry.word),
                    style: MFont.manrope(32, FontWeight.w800, MColors.ink)),
                if (entry.ipa != null) ...[
                  const SizedBox(height: 4),
                  Text(entry.ipa!,
                      style: MFont.manrope(16, FontWeight.w600, MColors.muted)),
                ],
                const SizedBox(height: 6),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    if (entry.pos.isNotEmpty) TagChip(posLabel(entry.pos)),
                    if (entry.level != null) LevelBadge(entry.level!),
                  ],
                ),
              ],
            ),
          ),
          Tap(
            label: '播放發音',
            onTap: () => scope.speaker.say(entry.word,
                language: repo.language, audioUrl: entry.audioUrl),
            child: Container(
              width: 56,
              height: 56,
              decoration: const BoxDecoration(
                  color: MColors.primary, shape: BoxShape.circle),
              child:
                  const Center(child: MSvg(MIcon.audioWaveformWhite, size: 24)),
            ),
          ),
        ],
      ),
      if (entry.dataStatus != WordDataStatus.complete)
        _DataStatus(entry: entry),
      if (entry.meaning.isNotEmpty)
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SectionLabel(
                supportedLanguages[scope.settings.nativeLanguage] ?? '釋義'),
            const SizedBox(height: 4),
            Text(entry.meaning,
                style: MFont.manrope(22, FontWeight.w800, MColors.primary)),
            if (entry.definition != null &&
                entry.definition != entry.meaning) ...[
              const SizedBox(height: 4),
              Text(entry.definition!,
                  style: MFont.manrope(14, FontWeight.w600, MColors.muted)),
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
              separatorBuilder: (_, __) => const SizedBox(width: 10),
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
                    decoration: MDecor.card(radius: MRadii.lg, shadow: MShadows.soft),
                    clipBehavior: Clip.antiAlias,
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        _ContextCrop(photo: c.photo, anchor: c.occ.anchor),
                        Positioned(
                          left: 8,
                          bottom: 8,
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 3),
                            decoration: MDecor.card(
                              color: const Color.fromRGBO(28, 36, 52, 0.7),
                              borderColor: Colors.transparent,
                              radius: MRadii.sm,
                              shadow: MShadows.soft,
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
      if (entry.meaning.isEmpty) const Text('中文意思尚未補齊，連線後會自動更新。'),
      if (examples.isNotEmpty)
        _Section(label: '實用例句', child: ExampleText(example: examples.first)),
      if (examples.length > 1)
        ExpansionTile(title: const Text('查看更多例句'), children: [
          for (final x in examples.skip(1))
            Padding(
                padding: const EdgeInsets.all(12),
                child: ExampleText(example: x)),
        ]),
      ExpansionTile(title: const Text('更多單字資訊'), children: [
        relatedSection('意思相近的單字', 'synonyms'),
        relatedSection('意思相反的單字', 'antonyms'),
        if (entry.forms.isNotEmpty)
          _Section(
              label: '詞形變化',
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final f in entry.forms.take(4))
                    TagChip('${f.form}（${formLabel(f.label)}）')
                ],
              )),
        if (learningMorphology(entry) case final parts?)
          _TextSection('構詞', parts),
        if (learningEtymology(entry) case final origin?)
          _TextSection('詞源', origin),
        if (_sources(entry).isNotEmpty)
          _TextSection('資料來源', _sources(entry).join('、')),
      ]),
      if (card != null) _CardInfo(card: card!),
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

  static List<String> _sources(WordEntry e) => [
        if (e.levelSource != null)
          '等級：${switch (e.levelSource) {
            'cefr-j' => 'CEFR-J 詞表',
            'lexicon' => '後台詞庫',
            'frequency' => '詞頻估計',
            'user' => '自訂',
            _ => 'AI 估計',
          }}',
        if (e.ipaSource != null)
          '音標：${switch (e.ipaSource) {
            'cmudict' => 'CMUdict',
            'lexicon' => '後台詞庫',
            'user' => '自訂',
            'ai' => 'AI',
            final s => s!,
          }}',
        if (e.examples.any((x) => x.aiGenerated)) '例句：AI 產生',
        if (e.userEdited.isNotEmpty) '有你修改過的欄位',
      ];
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
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: failed ? MColors.hardBg : MColors.primarySoft,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          Icon(failed ? Icons.error_outline : Icons.downloading_rounded,
              size: 18, color: failed ? MColors.hardFg : MColors.primary),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
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
              child: const Text('重試'),
            ),
        ],
      ),
    );
  }
}

/// The word's one card: FSRS state and the complete review log with the
/// state change each grade made (spec section 7: 完整 review log 與 FSRS
/// 變化).
class _CardInfo extends StatelessWidget {
  final LearningCard card;

  const _CardInfo({required this.card});

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final repo = scope.repository;
    final f = card.fsrs;
    final now = scope.clock();
    final logs = repo.logsOf(card.id).reversed.toList();
    String date(DateTime d) => '${d.year}/${d.month}/${d.day}';
    final status = StudyStatus.of(card);
    return _Section(
      label: '學習資訊',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              TagChip(status.label),
              if (!card.archived) TagChip('下次：${dueLabel(card, now)}'),
              if (f.state != FsrsCardState.newCard) ...[
                TagChip('穩定度 ${f.stability.toStringAsFixed(1)} 天'),
                TagChip('難度 ${f.difficulty.toStringAsFixed(1)}'),
                TagChip('複習 ${f.reps} 次'),
                TagChip('忘記 ${f.lapses} 次'),
              ],
            ],
          ),
          if (logs.isNotEmpty) ...[
            const SizedBox(height: 12),
            for (final l in logs)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  children: [
                    SizedBox(
                      width: 78,
                      child: Text(date(l.reviewedAt),
                          style: MFont.manrope(
                              12, FontWeight.w600, MColors.muted)),
                    ),
                    Container(
                      width: 54,
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      decoration: BoxDecoration(
                        color: RatingBar.colors(l.rating).bg,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                          l.rating.labelIn(scope.settings.nativeLanguage),
                          textAlign: TextAlign.center,
                          style: MFont.manrope(11, FontWeight.w800,
                              RatingBar.colors(l.rating).fg)),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '穩定度 ${l.before.stability.toStringAsFixed(1)} → '
                        '${l.after.stability.toStringAsFixed(1)} · 間隔 ${intervalLabel(l.scheduledDays)}',
                        style: MFont.manrope(12, FontWeight.w600, MColors.ink),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ],
      ),
    );
  }
}

/// 出現這個單字的照片: the photo zoomed in around the word's label, keeping the
/// label's object centred where the edges allow.
class _ContextCrop extends StatelessWidget {
  final Photo photo;
  final LabelPoint anchor;

  const _ContextCrop({required this.photo, required this.anchor});

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
            child: OverflowBox(
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
          );
        },
      );
}

class _Section extends StatelessWidget {
  final String label;
  final Widget child;

  const _Section({required this.label, required this.child});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [SectionLabel(label), const SizedBox(height: 8), child],
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
          const SizedBox(height: 4),
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
      padding: EdgeInsets.fromLTRB(24, 16, 24, 24 + bottom),
      child: Tap(
        onTap: onTap,
        label: archived ? '復原學習' : '標為已學會',
        child: Container(
          height: 54,
          decoration: BoxDecoration(
            color: archived ? MColors.primary : MColors.successSoft,
            borderRadius: BorderRadius.circular(27),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(archived ? Icons.undo_rounded : Icons.check_rounded,
                  size: 20, color: archived ? Colors.white : MColors.success),
              const SizedBox(width: 8),
              Text(
                archived ? '復原學習' : '標為已學會',
                style: MFont.manrope(16, FontWeight.w800,
                    archived ? Colors.white : MColors.success),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
