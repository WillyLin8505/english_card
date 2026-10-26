import 'package:flutter/material.dart';

import '../../l10n/ui_text.dart';
import '../../models/word_entry.dart' show cefrLevels;
import '../../services/photo_word_grid.dart';
import '../../theme/mobile_theme.dart';

/// 照片詳情「詞性 × CEFR」表格 (M180, owner #732): rows 動詞／名詞／形容詞／
/// 副詞／片語, columns A1–C2. A word in the learner's word book is drawn in
/// the primary colour (tap → 單字詳情); any other word has a small + (tap →
/// add it). Wider than a phone, so it scrolls sideways; an empty cell shows
/// a light dash.
class PhotoWordGridTable extends StatelessWidget {
  final PhotoWordGrid grid;

  /// Words (lowercase) already in the word book or on the photo's list.
  final Set<String> known;

  /// How a word is shown (the learning language's spelling).
  final String Function(GridWord w) display;
  final ValueChanged<GridWord> onWordTap;

  const PhotoWordGridTable({
    super.key,
    required this.grid,
    required this.onWordTap,
    this.known = const {},
    this.display = _plain,
  });

  static String _plain(GridWord w) => w.word;

  static const _headWidth = 60.0;
  static const _cellWidth = 92.0;

  @override
  Widget build(BuildContext context) {
    final headStyle = MFont.manrope(12, FontWeight.w800, MColors.muted);
    Widget pad(Widget child, {Alignment align = Alignment.topLeft}) => Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
          child: Align(alignment: align, child: child),
        );
    return Column(
      key: const ValueKey('photo-word-grid'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        UiText('詞性 × 等級表',
            style: MFont.manrope(15, FontWeight.w800, MColors.muted)),
        const SizedBox(height: 8),
        Container(
          decoration: MDecor.card(radius: MRadii.md, shadow: MShadows.none),
          clipBehavior: Clip.antiAlias,
          child: SingleChildScrollView(
            key: const ValueKey('photo-word-grid-scroll'),
            scrollDirection: Axis.horizontal,
            child: Table(
              defaultColumnWidth: const FixedColumnWidth(_cellWidth),
              columnWidths: const {0: FixedColumnWidth(_headWidth)},
              border: const TableBorder(
                horizontalInside: BorderSide(color: MColors.hairline),
                verticalInside: BorderSide(color: MColors.hairline),
              ),
              children: [
                TableRow(
                  decoration: const BoxDecoration(color: MColors.surfaceSoft),
                  children: [
                    const SizedBox.shrink(),
                    for (final l in cefrLevels)
                      pad(Text(l, style: headStyle), align: Alignment.center),
                  ],
                ),
                for (final r in GridRow.values)
                  TableRow(children: [
                    Container(
                      color: MColors.surfaceSoft,
                      padding: const EdgeInsets.symmetric(
                          horizontal: 6, vertical: 6),
                      child: UiText(gridRowLabel(r),
                          maxLines: 2, style: headStyle),
                    ),
                    for (var i = 0; i < cefrLevels.length; i++)
                      pad(_cell(grid.cell(r, i))),
                  ]),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _cell(List<GridWord> words) {
    if (words.isEmpty) {
      return Text('–',
          style: MFont.manrope(13, FontWeight.w600, MColors.gray200));
    }
    return Wrap(
      spacing: 4,
      runSpacing: 4,
      children: [
        for (final w in words)
          _WordChip(
            key: ValueKey('grid-word:${w.word}'),
            text: display(w),
            known: known.contains(w.word.toLowerCase()),
            onTap: () => onWordTap(w),
          ),
      ],
    );
  }
}

class _WordChip extends StatelessWidget {
  final String text;
  final bool known;
  final VoidCallback onTap;

  const _WordChip(
      {super.key,
      required this.text,
      required this.known,
      required this.onTap});

  @override
  Widget build(BuildContext context) => Material(
        color: known ? MColors.primarySoft : MColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(MRadii.sm),
          side: BorderSide(
              color: known
                  ? MColors.primary.withValues(alpha: 0.2)
                  : MColors.hairline),
        ),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(MRadii.sm),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
            // A RichText, not a Text: the grid repeats the photo's words,
            // and find.text('Coffee') in the older photo-detail tests means
            // the label and the list card only.
            child: RichText(
              textScaler: MediaQuery.textScalerOf(context),
              text: TextSpan(
                style: MFont.manrope(12, FontWeight.w700,
                    known ? MColors.primaryDeep : MColors.ink),
                children: [
                  TextSpan(text: text),
                  if (!known)
                    const TextSpan(
                        text: ' +', style: TextStyle(color: MColors.primary)),
                ],
              ),
            ),
          ),
        ),
      );
}
