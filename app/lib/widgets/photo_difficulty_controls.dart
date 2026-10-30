part of '../screens/photo_detail_screen.dart';

/// A level's Chinese name without its CEFR code: 精通（C2） → 精通
/// (問題回報 #708: the bar no longer spells out A1…C2).
String levelName(String level) =>
    levelLabel(level).replaceFirst(RegExp(r'（[^）]*）$'), '');

/// The bar's wording for a level and how far it is from the learner's own.
String _barText(String level, int offset) =>
    '${levelName(level)} · ${relativeDifficulty(offset)}';

/// 問題回報 #442: the difficulty bar under the photo, easy → hard. Drag the
/// thumb or tap the track; the labels follow at once ([onMove] while the
/// thumb moves, [onSelect] when a tap or the drag settles).
///
/// 問題回報 #708: a thick track with a large thumb that is easy to grab,
/// and no A1…C2 ticks — only the level's name (入門…精通) and how hard it
/// is for the learner (剛好、挑戰…) above it, and 簡單／難 at the ends so
/// the direction is clear without the codes.
class PhotoDifficultyBar extends StatelessWidget {
  static const _pad = 26.0;
  static const _barHeight = 76.0;
  static const _trackTop = 30.0;
  static const _track = 14.0;
  static const _thumb = 34.0;

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
    final ends = MFont.manrope(12, FontWeight.w700, MColors.label);
    return Semantics(
      slider: true,
      label: ui(context, '單字難度 ${ui(context, levelName(level))}，左右拖曳調整'),
      value: _barText(level, offset),
      // 問題回報 #845: the bar sits in the page's margin like the photo
      // above it, so 簡單／難 are never cut by the screen edges.
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: MSpace.md),
        child: LayoutBuilder(
          builder: (context, c) {
            final step = (c.maxWidth - 2 * _pad) / (cefrLevels.length - 1);
            double xOf(int i) => _pad + i * step;
            int levelAt(double dx) =>
                ((dx - _pad) / step).round().clamp(0, cefrLevels.length - 1);
            return GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTapUp: (d) => onSelect(levelAt(d.localPosition.dx)),
              onHorizontalDragUpdate: (d) =>
                  onMove(levelAt(d.localPosition.dx)),
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
                      height: 20,
                      child: Center(
                        child: UiText(_barText(level, offset),
                            key: const ValueKey('difficulty-text'),
                            style: MFont.manrope(
                                14, FontWeight.w800, MColors.dialBlue)),
                      ),
                    ),
                    Positioned(
                      left: _pad - _track / 2,
                      right: _pad - _track / 2,
                      top: _trackTop,
                      child: Container(
                        key: const ValueKey('difficulty-track'),
                        height: _track,
                        decoration: BoxDecoration(
                          color: MColors.border,
                          borderRadius: BorderRadius.circular(_track / 2),
                        ),
                      ),
                    ),
                    Positioned(
                      left: _pad - _track / 2,
                      top: _trackTop,
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 150),
                        width: xOf(target) - _pad + _track,
                        height: _track,
                        decoration: BoxDecoration(
                          color: MColors.primary,
                          borderRadius: BorderRadius.circular(_track / 2),
                        ),
                      ),
                    ),
                    AnimatedPositioned(
                      duration: const Duration(milliseconds: 150),
                      left: xOf(target) - _thumb / 2,
                      top: _trackTop + _track / 2 - _thumb / 2,
                      child: Container(
                        key: const ValueKey('difficulty-thumb'),
                        width: _thumb,
                        height: _thumb,
                        decoration: BoxDecoration(
                          color: MColors.surface,
                          shape: BoxShape.circle,
                          border: Border.all(color: MColors.primary, width: 4),
                          boxShadow: MShadows.card,
                        ),
                      ),
                    ),
                    // 問題回報 #845: under the track's ends, inside the bar.
                    Positioned(
                      left: _pad - _track / 2,
                      top: _trackTop + _track + 12,
                      child: UiText('簡單',
                          key: const ValueKey('difficulty-easy'), style: ends),
                    ),
                    Positioned(
                      right: _pad - _track / 2,
                      top: _trackTop + _track + 12,
                      child: UiText('難',
                          key: const ValueKey('difficulty-hard'), style: ends),
                    ),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}
