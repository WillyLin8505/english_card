import 'package:flutter/material.dart';

import '../../l10n/ui_text.dart';
import '../../models/word_entry.dart' show cefrLevels;
import '../../services/photo_word_grid.dart';
import '../../theme/mobile_theme.dart';
import 'pos_accent.dart';

/// 卡 #744 (owner #889): under the difficulty bar, the table's column for the
/// level the bar is on — noun, verb, adjective and adverb rows, always all
/// four. An empty cell says so in one line instead of dropping the row.
/// Phrases are not shown (the data stays).
const levelColumnRows = [
  GridRow.noun,
  GridRow.verb,
  GridRow.adjective,
  GridRow.adverb,
];

class LevelColumnPanel extends StatelessWidget {
  final PhotoWordGrid grid;

  /// Index into [cefrLevels] (0 = A1).
  final int level;
  final Set<String> known;
  final String Function(GridWord w) display;
  final ValueChanged<GridWord> onWordTap;

  const LevelColumnPanel({
    super.key,
    required this.grid,
    required this.level,
    required this.onWordTap,
    this.known = const {},
    this.display = _plain,
  });

  static String _plain(GridWord w) => w.word;

  @override
  Widget build(BuildContext context) {
    final head = MFont.manrope(12, FontWeight.w800, MColors.muted);
    return Container(
      key: const ValueKey('level-column'),
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(10),
      decoration: MDecor.card(radius: MRadii.md, shadow: MShadows.none),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          UiText('${cefrLevels[level]} 的字', style: head),
          for (final r in levelColumnRows) ...[
            const SizedBox(height: 8),
            Row(
              key: ValueKey('level-row-${r.name}'),
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                    width: 52,
                    child: UiText(gridRowLabel(r),
                        style: MFont.manrope(
                            12, FontWeight.w800, posAccent(r.name, '') ?? MColors.muted))),
                Expanded(child: _cell(r, grid.cell(r, level))),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _cell(GridRow r, List<GridWord> words) {
    if (words.isEmpty) {
      return UiText('這個難度沒有合適的${gridRowLabel(r)}',
          key: ValueKey('level-empty-${r.name}'),
          style: MFont.manrope(12, FontWeight.w600, MColors.gray200));
    }
    return Wrap(spacing: 6, runSpacing: 6, children: [
      for (final w in words)
        GestureDetector(
          key: ValueKey('level-word:${w.word}'),
          onTap: () => onWordTap(w),
          child: Text(display(w),
              style: MFont.manrope(
                  13,
                  FontWeight.w700,
                  known.contains(w.word.toLowerCase())
                      ? MColors.primaryDeep
                      : MColors.ink)),
        ),
    ]);
  }
}
