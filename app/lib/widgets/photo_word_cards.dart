part of '../screens/photo_detail_screen.dart';

/// The shortcuts under the difficulty bar: 「多看動詞」「多看形容詞」
/// 「重新掃描標籤」 (問題回報 #707: 簡單一點／難一點 removed), and a note while
/// more candidates load. The level itself is on
/// the difficulty bar under the photo (問題回報 #444: it used to be repeated here).
class _LevelRow extends StatelessWidget {
  final PosBias bias;
  final bool busy;

  /// What the busy note says (問題回報 #666: 「AI 正在找更多動詞…」).
  final String? busyLabel;
  final ValueChanged<PosBias> onBias;

  /// 重新掃描標籤 (問題回報 #670); null while a scan runs.
  final VoidCallback? onRescan;

  const _LevelRow({
    required this.bias,
    required this.busy,
    this.busyLabel,
    required this.onBias,
    this.onRescan,
  });

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (busy) ...[
            Row(
              children: [
                const SizedBox.square(
                    dimension: 12,
                    child: CircularProgressIndicator(strokeWidth: 1.6)),
                const SizedBox(width: MSpace.xxs),
                UiText(busyLabel ?? '補充候選詞…',
                    style: MFont.manrope(12, FontWeight.w600, MColors.label)),
              ],
            ),
            const SizedBox(height: MSpace.xs),
          ],
          Wrap(
            spacing: MSpace.xs,
            runSpacing: MSpace.xs,
            children: [
              FilterPill(
                label: '多看動詞',
                active: bias == PosBias.actions,
                onTap: () => onBias(PosBias.actions),
              ),
              FilterPill(
                label: '多看形容詞',
                active: bias == PosBias.descriptions,
                onTap: () => onBias(PosBias.descriptions),
              ),
              // 問題回報 #707: 簡單一點／難一點 are gone — the difficulty bar
              // above does the same.
              FilterPill(
                key: const ValueKey('rescan-tags'),
                label: '重新掃描標籤',
                onTap: onRescan,
              ),
            ],
          ),
        ],
      );
}

class _KnownBackground extends StatelessWidget {
  const _KnownBackground();

  @override
  Widget build(BuildContext context) => Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: MSpace.xl),
        decoration: MDecor.insetCard(color: MColors.success, radius: MRadii.xl),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.check_rounded, color: Colors.white, size: 20),
            const SizedBox(width: MSpace.xxs + 2),
            UiText('已學會',
                style: MFont.manrope(15, FontWeight.w800, Colors.white)),
          ],
        ),
      );
}

/// Figma word-card-Coffee (24:59).
class _WordCard extends StatelessWidget {
  final String word;
  final String? ipa;
  final String zh;
  final String level;

  /// A word about the whole picture, with no pin (問題回報 #703).
  final bool wholePicture;
  final bool starred;
  final VoidCallback onTap;
  final VoidCallback onAudio;
  final VoidCallback onStar;
  final VoidCallback onMore;

  const _WordCard({
    required this.word,
    required this.ipa,
    required this.zh,
    required this.level,
    this.wholePicture = false,
    required this.starred,
    required this.onTap,
    required this.onAudio,
    required this.onStar,
    required this.onMore,
  });

  @override
  Widget build(BuildContext context) {
    Widget action(Color bg, Widget icon, String label, VoidCallback onTap) =>
        Tap(
          onTap: onTap,
          label: label,
          child: Container(
            padding: const EdgeInsets.all(15),
            decoration: MDecor.iconWell(color: bg, radius: MRadii.sm),
            child: SizedBox.square(dimension: 18, child: Center(child: icon)),
          ),
        );

    return Tap(
      onTap: onTap,
      label: '$word $zh',
      child: Container(
        padding: const EdgeInsets.all(MSpace.md),
        decoration: MDecor.card(
          color: MColors.surface,
          borderColor: MColors.borderSoft,
          radius: MRadii.xl,
          shadow: MShadows.soft,
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.baseline,
                    textBaseline: TextBaseline.alphabetic,
                    children: [
                      Flexible(
                        child: Text(word,
                            overflow: TextOverflow.ellipsis,
                            style: MFont.manrope(
                                18, FontWeight.w800, MColors.ink)),
                      ),
                      if (ipa != null) ...[
                        const SizedBox(width: 8),
                        Flexible(
                          child: Text(ipa!,
                              overflow: TextOverflow.ellipsis,
                              style: MFont.manrope(
                                  13, FontWeight.w500, MColors.label)),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      if (zh.isNotEmpty)
                        Flexible(
                          child: Text(zh,
                              overflow: TextOverflow.ellipsis,
                              style: MFont.manrope(
                                  15, FontWeight.w700, MColors.primary)),
                        ),
                      const SizedBox(width: 8),
                      UiText(levelLabel(level),
                          style: MFont.manrope(
                              11, FontWeight.w800, MColors.label)),
                      if (wholePicture) ...[
                        const SizedBox(width: MSpace.xs),
                        // Same chip as the catalog pictures' (card #510).
                        Container(
                          key: ValueKey('whole-picture-$word'),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 6, vertical: 1),
                          decoration: BoxDecoration(
                              color: MColors.surfaceSoft,
                              borderRadius:
                                  BorderRadius.circular(MRadii.sm)),
                          child: UiText('整張圖', style: MFont.caption),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
            IconButton(
                tooltip: ui(context, '管理這個單字'),
                onPressed: onMore,
                icon: const Icon(Icons.more_horiz)),
            action(MColors.primarySoft,
                const MSvg(MIcon.audioWaveform, size: 18), '播放發音', onAudio),
            const SizedBox(width: MSpace.sm - 2),
            action(
              starred ? MColors.successSoft : MColors.surfaceSoft,
              MSvg(starred ? MIcon.star : MIcon.starOff, size: 18),
              starred ? '取消鎖定' : '鎖定（調整難度時保留）',
              onStar,
            ),
          ],
        ),
      ),
    );
  }
}

/// A hidden word shown with 「顯示已學會單字」: 已學會 ones have a small
/// 復原 button (spec: 每個封存詞旁提供小型復原按鈕).
class _OldWordRow extends StatelessWidget {
  final String word;
  final String zh;
  final bool learned;
  final VoidCallback? onRestore;

  const _OldWordRow({
    required this.word,
    required this.zh,
    required this.learned,
    required this.onRestore,
  });

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(
            horizontal: MSpace.md, vertical: MSpace.sm - 2),
        decoration:
            MDecor.softPanel(color: MColors.surfaceSoft, radius: MRadii.lg),
        child: Row(
          children: [
            Expanded(
              child: Text.rich(
                TextSpan(children: [
                  TextSpan(
                      text: word,
                      style: MFont.manrope(15, FontWeight.w800, MColors.muted)),
                  TextSpan(
                      text: '  $zh',
                      style: MFont.manrope(13, FontWeight.w600, MColors.label)),
                ]),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            UiText(learned ? '已學會' : '學習中',
                style: MFont.manrope(12, FontWeight.w700,
                    learned ? MColors.success : MColors.primary)),
            if (onRestore != null) ...[
              const SizedBox(width: MSpace.xs),
              Tap(
                onTap: onRestore,
                label: '復原 $word',
                child: Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: MSpace.sm - 2, vertical: MSpace.xxs),
                  decoration: MDecor.card(
                    color: MColors.surface,
                    borderColor: MColors.borderSoft,
                    radius: MRadii.sm,
                    shadow: MShadows.none,
                  ),
                  child: UiText('復原',
                      style:
                          MFont.manrope(12, FontWeight.w800, MColors.primary)),
                ),
              ),
            ],
          ],
        ),
      );
}

class _PhotoBadgeOverlay extends StatelessWidget {
  final IconData? icon;
  final String text;

  const _PhotoBadgeOverlay({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) => ColoredBox(
        color: MColors.photoScrimLight,
        child: Center(
          child: Container(
            padding: const EdgeInsets.symmetric(
                horizontal: MSpace.md, vertical: MSpace.sm - 2),
            decoration: MDecor.overlayPill(radius: MRadii.xl),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (icon == null)
                  const SizedBox.square(
                    dimension: 14,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white),
                  )
                else
                  Icon(icon, size: 16, color: Colors.white),
                const SizedBox(width: MSpace.xs),
                UiText(text,
                    style: MFont.manrope(13, FontWeight.w700, Colors.white)),
              ],
            ),
          ),
        ),
      );
}
