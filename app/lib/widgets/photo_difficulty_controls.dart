part of '../screens/photo_detail_screen.dart';

const _dialShadow = MShadows.soft;

/// Figma "Difficulty Dial / Collapsed" (48:73): gauge, needle, level.
/// Long-press to open it and drag to a level (like a camera's ISO dial);
/// a tap opens it until a level is chosen.
class _DifficultyDial extends StatelessWidget {
  final String level;
  final VoidCallback onTap;

  const _DifficultyDial({required this.level, required this.onTap});

  @override
  Widget build(BuildContext context) {
    // The mock shows B1 with the needle at 40°; other levels step 40°.
    final angle =
        (-40 + cefrLevels.indexOf(level) * 40) * 3.141592653589793 / 180;
    return Tap(
      onTap: onTap,
      label: '單字難度 ${levelLabel(level)}，點一下或長按調整',
      child: Container(
        width: 52,
        height: 58,
        decoration: MDecor.dialSurface(radius: 26, shadow: MShadows.card),
        child: Stack(
          children: [
            // Gauge: a 30px box at (10, 6) whose arc starts 20.57% in.
            const Positioned(
              left: 10 + 30 * 0.2057,
              top: 6,
              child:
                  MSvg.sized(MIcon.difficultyGauge, width: 23.8275, height: 30),
            ),
            // Needle: 10px, rotated about its centre; its 40° bounding box
            // sits at (15, 21) in the mock, so its centre is (18.83, 24.21).
            Positioned(
              left: 18.83 - 5,
              top: 24.21 - 1,
              child: Transform.rotate(
                angle: angle,
                child:
                    const MSvg.sized(MIcon.gaugeNeedle, width: 10, height: 2),
              ),
            ),
            Positioned(
              left: 0,
              right: 0,
              top: 43.5 - 6.5,
              child: Text(
                level,
                textAlign: TextAlign.center,
                style: MFont.inter(10, FontWeight.w600, MColors.dialBlue),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Figma difficulty-control-expanded (54:229).
class _LevelCircle extends StatelessWidget {
  final String level;
  final VoidCallback onTap;

  const _LevelCircle({required this.level, required this.onTap});

  @override
  Widget build(BuildContext context) => Tap(
        onTap: onTap,
        label: '收起難度選單',
        child: Container(
          width: 36,
          height: 36,
          decoration: MDecor.dialSurface(radius: 18, shadow: _dialShadow),
          child: Center(
            child: UiText(levelLabel(level),
                style: MFont.manrope(12, FontWeight.w800, MColors.dialBlue)),
          ),
        ),
      );
}

/// Figma difficulty-slider (54:231): A1–C2, the current one highlighted.
class _DifficultySlider extends StatelessWidget {
  final String level;
  final ValueChanged<String> onSelect;

  const _DifficultySlider(
      {super.key, required this.level, required this.onSelect});

  @override
  Widget build(BuildContext context) => Container(
        width: 36,
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: MSpace.sm),
        decoration: MDecor.dialSurface(radius: 18, shadow: _dialShadow),
        child: Column(
          children: [
            for (final (i, l) in cefrLevels.indexed) ...[
              if (i > 0) const SizedBox(height: MSpace.xs),
              Tap(
                onTap: () => onSelect(l),
                label: '難度 $l',
                child: Container(
                  height: 32,
                  decoration: l == level
                      ? MDecor.softPanel(
                          color: MColors.primarySoft,
                          radius: MRadii.lg,
                        )
                      : null,
                  child: Center(
                    child: Text(
                      l,
                      style: l == level
                          ? MFont.manrope(12, FontWeight.w800, MColors.dialBlue)
                          : MFont.manrope(12, FontWeight.w700, MColors.label),
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      );
}

/// The label beside the open dial: level and wording.
class _DialBubble extends StatelessWidget {
  final String text;
  final String? hint;

  const _DialBubble({required this.text, this.hint});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(
            horizontal: MSpace.sm - 2, vertical: MSpace.xxs + 2),
        decoration: MDecor.overlayPill(radius: MRadii.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            UiText(text, style: MFont.manrope(12, FontWeight.w800, Colors.white)),
            if (hint != null)
              Text(hint!,
                  style: MFont.manrope(
                      10, FontWeight.w600, MColors.onOverlayMuted)),
          ],
        ),
      );
}
