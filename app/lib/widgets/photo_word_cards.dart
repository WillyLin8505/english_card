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

/// 問題回報 #848: the short meaning a word row shows — the first sense
/// (before 「；」 or 「：」), and of a list of synonyms joined by 、 only the
/// first two: 「不清楚、陰暗的、模糊的；難懂」 → 「不清楚、陰暗的」.
String briefMeaning(String meaning) {
  var s = meaning.split(RegExp('[；;:：]')).first.trim();
  final items = s.split('、');
  if (items.length > 2) s = items.take(2).join('、');
  return s.isEmpty ? meaning.trim() : s;
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

    final wordText = Text(word,
        key: ValueKey('word-card-word-$word'),
        softWrap: true,
        style: MFont.manrope(18, FontWeight.w800, MColors.ink));

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
                  // 問題回報 #848: the whole word, never 「Conspi…」 — it
                  // wraps instead, and the IPA moves under it when the two
                  // do not fit on one line.
                  Wrap(
                    spacing: 8,
                    crossAxisAlignment: WrapCrossAlignment.end,
                    children: [
                      // One long word is scaled down a little rather than
                      // broken mid-way; a phrase wraps at its spaces.
                      if (word.contains(' '))
                        wordText
                      else
                        FittedBox(fit: BoxFit.scaleDown, child: wordText),
                      if (ipa != null)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 2),
                          child: Text(ipa!,
                              softWrap: true,
                              style: MFont.manrope(
                                  13, FontWeight.w500, MColors.label)),
                        ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  // 問題回報 #848: a short meaning in full (up to two
                  // lines) instead of 「不清楚、陰…」.
                  Wrap(
                    spacing: 8,
                    runSpacing: 2,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      if (zh.isNotEmpty)
                        Text(briefMeaning(zh),
                            key: ValueKey('word-card-zh-$word'),
                            maxLines: 2,
                            softWrap: true,
                            style: MFont.manrope(
                                15, FontWeight.w700, MColors.primary)),
                      UiText(levelLabel(level),
                          style: MFont.manrope(
                              11, FontWeight.w800, MColors.label)),
                      if (wholePicture) ...[
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

/// 問題回報 #851: the note on the photo while the AI is still tagging it
/// (a rescan or a top-up), over the labels without a scrim.
class _PhotoScanningChip extends StatelessWidget {
  const _PhotoScanningChip();

  @override
  Widget build(BuildContext context) => Container(
        key: const ValueKey('photo-scanning-label'),
        padding: const EdgeInsets.symmetric(
            horizontal: MSpace.md, vertical: MSpace.sm - 2),
        decoration: MDecor.overlayPill(radius: MRadii.xl),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox.square(
              dimension: 14,
              child: CircularProgressIndicator(
                  strokeWidth: 2, color: Colors.white),
            ),
            const SizedBox(width: MSpace.xs),
            UiText('AI 正在找單字…',
                style: MFont.manrope(13, FontWeight.w700, Colors.white)),
          ],
        ),
      );
}

/// 問題回報 #850: after 儲存, the listed words fly one by one to the 單字本
/// tab and then the photo shrinks into the 相片冊 tab (about 1.8 s; a tap
/// anywhere skips to the end). Drawn over everything on the root overlay.
class _SaveFlight extends StatefulWidget {
  final List<String> words;
  final Photo photo;

  /// Where the photo is on screen when 儲存 is pressed.
  final Rect from;
  final VoidCallback onDone;

  const _SaveFlight({
    required this.words,
    required this.photo,
    required this.from,
    required this.onDone,
  });

  static const duration = Duration(milliseconds: 1800);

  /// The centre of a tab's icon in [MobileTabBar] (five equal tabs inside a
  /// 16 pt margin, the icon above its label).
  static Offset tabIcon(BuildContext context, AppTab tab) {
    final size = MediaQuery.sizeOf(context);
    final bottom = math.max(24.0, MediaQuery.paddingOf(context).bottom);
    final n = AppTab.values.length;
    return Offset(16 + (size.width - 32) * (tab.index + 0.5) / n,
        size.height - bottom - 36);
  }

  @override
  State<_SaveFlight> createState() => _SaveFlightState();
}

class _SaveFlightState extends State<_SaveFlight>
    with SingleTickerProviderStateMixin {
  late final AnimationController _t =
      AnimationController(vsync: this, duration: _SaveFlight.duration)
        ..addStatusListener((s) {
          if (s == AnimationStatus.completed) _finish();
        })
        ..forward();
  bool _done = false;

  void _finish() {
    if (_done) return;
    _done = true;
    widget.onDone();
  }

  @override
  void dispose() {
    _t.dispose();
    super.dispose();
  }

  /// Word [i]'s part of the run: they leave 0.1 apart, each flying 0.35.
  double _wordT(int i) =>
      ((_t.value - i * 0.1) / 0.35).clamp(0.0, 1.0).toDouble();

  /// The photo goes once the words have left.
  double get _photoT => ((_t.value - 0.55) / 0.4).clamp(0.0, 1.0).toDouble();

  @override
  Widget build(BuildContext context) {
    final words = widget.words.take(WordSelector.maxWords).toList();
    final book = _SaveFlight.tabIcon(context, AppTab.words);
    final album = _SaveFlight.tabIcon(context, AppTab.album);
    final from = widget.from;
    return GestureDetector(
      key: const ValueKey('save-flight'),
      behavior: HitTestBehavior.opaque,
      // A tap ends it at once.
      onTap: () {
        _t.stop();
        _finish();
      },
      child: AnimatedBuilder(
        animation: _t,
        builder: (context, _) {
          final p = Curves.easeInOutCubic.transform(_photoT);
          final photoRect = Rect.lerp(
              from, Rect.fromCenter(center: album, width: 28, height: 28), p)!;
          return Stack(
            children: [
              if (_photoT < 1)
                Positioned.fromRect(
                  rect: photoRect,
                  child: Opacity(
                    opacity: 1 - 0.6 * p,
                    child: ClipRRect(
                      borderRadius:
                          BorderRadius.circular(MRadii.xxl * (1 - p) + 6 * p),
                      child: PhotoImage(widget.photo, fit: BoxFit.cover),
                    ),
                  ),
                ),
              for (var i = 0; i < words.length; i++)
                if (_wordT(i) > 0 && _wordT(i) < 1)
                  _flyingWord(
                    words[i],
                    Offset(
                        from.left + from.width * (i + 1) / (words.length + 1),
                        from.center.dy),
                    book,
                    _wordT(i),
                  ),
            ],
          );
        },
      ),
    );
  }

  Widget _flyingWord(String word, Offset start, Offset end, double t) {
    final e = Curves.easeInCubic.transform(t);
    // A small arc up before it drops into the tab.
    final at =
        Offset.lerp(start, end, e)! - Offset(0, 60 * math.sin(math.pi * t));
    return Positioned(
      left: at.dx,
      top: at.dy,
      child: FractionalTranslation(
        translation: const Offset(-0.5, -0.5),
        child: Transform.scale(
          scale: 1 - 0.6 * e,
          child: Opacity(
            opacity: t > 0.8 ? (1 - t) / 0.2 : 1,
            child: Container(
              padding: const EdgeInsets.symmetric(
                  horizontal: MSpace.sm, vertical: 6),
              decoration: MDecor.primaryPill(radius: MRadii.xl),
              child: Text(word,
                  style: MFont.manrope(14, FontWeight.w800, Colors.white)),
            ),
          ),
        ),
      ),
    );
  }
}
