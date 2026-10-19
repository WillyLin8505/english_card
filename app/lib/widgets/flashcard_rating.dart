part of '../screens/flashcard_screen.dart';

class ExampleText extends StatelessWidget {
  final WordExample example;
  final bool showTranslation;

  /// With [links], words in the learner's database open their details
  /// (card #251 item 9).
  final WordLinks? links;
  final ValueChanged<String>? onOpenWord;

  const ExampleText(
      {super.key,
      required this.example,
      this.showTranslation = true,
      this.links,
      this.onOpenWord});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LinkedText(example.text,
              style: MFont.manrope(15, FontWeight.w800, MColors.ink),
              links: links,
              onOpenWord: onOpenWord),
          if (showTranslation && example.translation != null) ...[
            const SizedBox(height: 2),
            Text.rich(TextSpan(children: [
              TextSpan(
                  text: example.translation,
                  style: MFont.manrope(13, FontWeight.w700, MColors.muted)),
            ])),
          ],
        ],
      );
}

/// The four grades with each one's next interval, in spec section 4's
/// colours, labelled in the native language. Keys 1–4 also work.
class RatingBar extends StatelessWidget {
  final Map<Rating, SchedulingResult> previews;
  final String native;
  final bool extraPractice;
  final ValueChanged<Rating> onRate;

  const RatingBar(
      {super.key,
      required this.previews,
      required this.onRate,
      this.extraPractice = false,
      this.native = 'zh-TW'});

  static ({Color bg, Color fg}) colors(Rating r) => switch (r) {
        Rating.again => (bg: MColors.againBg, fg: MColors.againFg),
        Rating.hard => (bg: MColors.hardBg, fg: MColors.hardFg),
        Rating.good => (bg: MColors.goodBg, fg: MColors.goodFg),
        Rating.easy => (bg: MColors.easyBg, fg: MColors.easyFg),
      };

  @override
  Widget build(BuildContext context) {
    final look = CardLook.of(context);
    return Row(
        children: [
          for (final r in Rating.values) ...[
            if (r != Rating.again) const SizedBox(width: 8),
            Expanded(
              child: Tap(
                onTap: () => onRate(r),
                // The grade and when the card comes back, read once.
                label: extraPractice
                    ? r.labelIn(native)
                    : '${r.labelIn(native)}，${ui(context, extraPractice ? '繼續練習' : r == Rating.again ? '稍後再出現' : '${intervalLabel(previews[r]!.scheduledDays)}後複習')}',
                labelOnly: true,
                child: Container(
                  height: look.ratingHeight,
                  decoration: look.ratingTile(colors(r).bg, colors(r).fg),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Text(r.labelIn(native),
                              style: MFont.manrope(look.ratingLabelSize,
                                  FontWeight.w800, colors(r).fg))),
                      if (!extraPractice) const SizedBox(height: 2),
                      // An Again card comes back later in this same run.
                      if (!extraPractice)
                        UiText(
                            extraPractice
                                ? '繼續練習'
                                : r == Rating.again
                                    ? '稍後再出現'
                                    : '${intervalLabel(previews[r]!.scheduledDays)}後複習',
                            textAlign: TextAlign.center,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: MFont.manrope(11, FontWeight.w600,
                                colors(r).fg.withValues(alpha: 0.75))),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ],
      );
  }
}
