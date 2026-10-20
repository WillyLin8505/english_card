part of '../screens/photo_detail_screen.dart';

/// The bar's wording for a level and how far it is from the learner's own.
String _barText(String level, int offset) =>
    '${levelLabel(level)} · ${relativeDifficulty(offset)}';

/// 問題回報 #442: the difficulty bar under the photo, A1 → C2. Drag the thumb
/// or tap a level; the labels follow at once ([onMove] while the thumb moves,
/// [onSelect] when a tap or the drag settles).
class PhotoDifficultyBar extends StatelessWidget {
  static const _pad = 20.0;
  static const _barHeight = 78.0;

  final int target;
  final int offset;
  final ValueChanged<int> onMove;
  final ValueChanged<int> onSelect;

  const PhotoDifficultyBar({
    super.key,
    required this.target,
    required this.offset,
    required this.onMove,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    final level = cefrLevels[target];
    return Semantics(
      slider: true,
      label: '單字難度 ${levelLabel(level)}，拖曳或點刻度調整',
      value: _barText(level, offset),
      child: LayoutBuilder(
        builder: (context, c) {
          final step = (c.maxWidth - 2 * _pad) / (cefrLevels.length - 1);
          double xOf(int i) => _pad + i * step;
          int levelAt(double dx) =>
              ((dx - _pad) / step).round().clamp(0, cefrLevels.length - 1);
          return GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTapUp: (d) => onSelect(levelAt(d.localPosition.dx)),
            onHorizontalDragUpdate: (d) => onMove(levelAt(d.localPosition.dx)),
            onHorizontalDragEnd: (_) => onSelect(target),
            child: SizedBox(
              height: _barHeight,
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  Positioned(
                    left: 0,
                    right: 0,
                    top: 0,
                    height: 18,
                    child: Center(
                      child: UiText(_barText(level, offset),
                          style: MFont.manrope(
                              12, FontWeight.w800, MColors.dialBlue)),
                    ),
                  ),
                  Positioned(
                    left: _pad,
                    right: _pad,
                    top: 32,
                    child: Container(
                      height: 4,
                      decoration: BoxDecoration(
                        color: MColors.border,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  Positioned(
                    left: xOf(0),
                    width: xOf(cefrLevels.length - 1) - xOf(0),
                    top: 32,
                    child: Container(
                      height: 4,
                      decoration: BoxDecoration(
                        color: MColors.primary,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  for (final (i, l) in cefrLevels.indexed) ...[
                    Positioned(
                      left: xOf(i) - 4,
                      top: 30,
                      child: Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color:
                              i <= target ? MColors.primary : MColors.surface,
                          shape: BoxShape.circle,
                          border: Border.all(color: MColors.border),
                        ),
                      ),
                    ),
                    Positioned(
                      left: xOf(i) - step / 2,
                      width: step,
                      top: 48,
                      child: Text(
                        l,
                        textAlign: TextAlign.center,
                        style: l == level
                            ? MFont.manrope(
                                12, FontWeight.w800, MColors.dialBlue)
                            : MFont.manrope(12, FontWeight.w700, MColors.label),
                      ),
                    ),
                  ],
                  Positioned(
                    left: xOf(target) - 11,
                    top: 23,
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 150),
                      width: 22,
                      height: 22,
                      decoration: BoxDecoration(
                        color: MColors.surface,
                        shape: BoxShape.circle,
                        border: Border.all(color: MColors.primary, width: 3),
                        boxShadow: MShadows.card,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
