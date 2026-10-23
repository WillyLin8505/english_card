import '../../services/learning_content.dart';
import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart' show listEquals;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show HapticFeedback;

import '../../app/app_scope.dart';
import '../../l10n/ui_text.dart';
import '../../models/learning_card.dart';
import '../../models/photo.dart';
import '../../theme/mobile_theme.dart';
import 'common.dart';
import 'm_icon.dart';
import 'photo_cache.dart';
import 'pin_layout.dart';

export 'photo_cache.dart' show precachePhoto;

/// Where a label anchor (a fraction of the ORIGINAL image) lands in a box
/// that shows the photo with [BoxFit.cover], and back. Photos without a
/// known size (placeholders) simply fill the box. [alignment] is the
/// photo's (the same as [Image.alignment]): which part of an image larger
/// than the box stays in view. With [fit] [BoxFit.contain] (照片詳情,
/// 問題回報 #664) the whole photo shows, letterboxed: nothing is cropped.
class CoverGeometry {
  final double scale;
  final double imageWidth;
  final double imageHeight;
  final Offset offset;

  CoverGeometry._(this.scale, this.imageWidth, this.imageHeight, this.offset);

  factory CoverGeometry(Size box, Photo photo,
      {Alignment alignment = Alignment.center, BoxFit fit = BoxFit.cover}) {
    final w = photo.width?.toDouble(), h = photo.height?.toDouble();
    if (!photo.hasImage || w == null || h == null || w <= 0 || h <= 0) {
      return CoverGeometry._(1, box.width, box.height, Offset.zero);
    }
    final sx = box.width / w, sy = box.height / h;
    final s = fit == BoxFit.contain ? math.min(sx, sy) : math.max(sx, sy);
    final free = Offset(box.width - w * s, box.height - h * s) / 2;
    return CoverGeometry._(s, w, h,
        Offset(free.dx * (1 + alignment.x), free.dy * (1 + alignment.y)));
  }

  /// The geometry of [photo] drawn in a [PinnedPhoto] above [context]: it
  /// may have moved the photo to keep its focus in view (問題回報 #651).
  factory CoverGeometry.of(BuildContext context, Size box, Photo photo) =>
      CoverGeometry(box, photo,
          alignment: PhotoAlignment.of(context),
          fit: PhotoAlignment.fitOf(context));

  /// 問題回報 #651: with [BoxFit.cover] centred, a spot near the edge of a
  /// photo much wider (or taller) than its box is cropped away, and its dot
  /// would land outside the frame. This is the alignment that shows the
  /// photo with [focus] at least [margin] inside the box — moving the photo
  /// as little as it can from centred, so a spot already in view changes
  /// nothing. The dot stays on its object: the photo moves, not the dot.
  static Alignment focusing(Size box, Photo photo, LabelPoint focus,
      {double margin = 40}) {
    final g = CoverGeometry(box, photo);
    double axis(double boxLen, double imageLen, double f) {
      final free = boxLen - imageLen; // ≤ 0: how much is cropped
      if (free > -0.5) return 0;
      final m = math.min(margin, boxLen / 2);
      // Offsets o (free ≤ o ≤ 0) that put o + f·imageLen in [m, boxLen − m].
      final lo = math.max(free, m - f * imageLen);
      final hi = math.min(0.0, boxLen - m - f * imageLen);
      final centred = free / 2;
      if (lo <= centred && centred <= hi) return 0; // already in view
      final o = lo > hi
          ? (f < 0.5 ? 0.0 : free) // too near the edge: show that edge
          : centred.clamp(lo, hi);
      return (2 * o / free - 1).clamp(-1.0, 1.0);
    }

    return Alignment(
      axis(box.width, g.imageWidth * g.scale, focus.x),
      axis(box.height, g.imageHeight * g.scale, focus.y),
    );
  }

  /// The part of [box] the photo covers (問題回報 #664): the whole box with
  /// [BoxFit.cover], the photo's letterboxed rectangle with contain.
  Rect visibleIn(Size box) =>
      (offset & Size(imageWidth * scale, imageHeight * scale))
          .intersect(Offset.zero & box);

  Offset toBox(LabelPoint p) =>
      offset + Offset(p.x * imageWidth * scale, p.y * imageHeight * scale);

  LabelPoint fromBox(Offset o) => LabelPoint(
        ((o.dx - offset.dx) / (imageWidth * scale)).clamp(0.0, 1.0),
        ((o.dy - offset.dy) / (imageHeight * scale)).clamp(0.0, 1.0),
      );
}

/// The alignment a [PinnedPhoto] drew its photo with, for overlays drawn
/// over it ([TargetRing], dots) to map anchors the same way.
class PhotoAlignment extends InheritedWidget {
  final Alignment alignment;

  /// How the photo is fitted in its box (問題回報 #664).
  final BoxFit fit;

  const PhotoAlignment(
      {super.key,
      required this.alignment,
      this.fit = BoxFit.cover,
      required super.child});

  static Alignment of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<PhotoAlignment>()?.alignment ??
      Alignment.center;

  static BoxFit fitOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<PhotoAlignment>()?.fit ??
      BoxFit.cover;

  @override
  bool updateShouldNotify(PhotoAlignment old) =>
      old.alignment != alignment || old.fit != fit;
}

/// A photo's pixels, whichever way they are stored (see [Photo]); photos
/// without an image draw their placeholder gradient, as the Figma
/// 項目照片 cards do ("Photo / 晨光陽台": gradient-to-r).
class PhotoImage extends StatelessWidget {
  final Photo photo;
  final BoxFit fit;
  final Alignment alignment;
  final WidgetBuilder? imageErrorBuilder;
  final ValueChanged<bool>? onImageState;

  const PhotoImage(
    this.photo, {
    super.key,
    this.fit = BoxFit.cover,
    this.alignment = Alignment.center,
    this.imageErrorBuilder,
    this.onImageState,
  });

  void _report(bool ready) {
    if (onImageState == null) return;
    WidgetsBinding.instance
        .addPostFrameCallback((_) => onImageState?.call(ready));
  }

  Widget _error(BuildContext context) {
    _report(false);
    return imageErrorBuilder?.call(context) ?? _placeholder();
  }

  Widget _frame(
      BuildContext context, Widget child, int? frame, bool synchronous) {
    if (synchronous || frame != null) {
      _report(true);
      return child;
    }
    // Still loading: the placeholder holds the photo's place.
    return Stack(fit: StackFit.expand, children: [_placeholder(), child]);
  }

  @override
  Widget build(BuildContext context) {
    // Decoded at the size it is shown, not the original's (card #252).
    return LayoutBuilder(builder: (context, c) {
      final screen = MediaQuery.maybeSizeOf(context) ?? Size.zero;
      final box = Size(c.hasBoundedWidth ? c.maxWidth : screen.width,
          c.hasBoundedHeight ? c.maxHeight : screen.height);
      final image = photoProvider(
          photo,
          context.dependOnInheritedWidgetOfExactType<AppScope>()?.photoStore,
          box,
          MediaQuery.maybeDevicePixelRatioOf(context) ?? 1,
          fit: fit);
      if (image == null) {
        _report(false);
        return _placeholder();
      }
      // Another photo starts from its placeholder (no stale pixels); the
      // same photo at a new decode size keeps showing until it is ready.
      return KeyedSubtree(
        key: ValueKey((
          photo.id,
          photo.assetPath,
          photo.networkUrl,
          photo.filePath,
          photo.storedKey
        )),
        child: Image(
          image: image,
          fit: fit,
          alignment: alignment,
          width: double.infinity,
          height: double.infinity,
          gaplessPlayback: true,
          frameBuilder: _frame,
          errorBuilder: (context, _, __) => _error(context),
        ),
      );
    });
  }

  Widget _placeholder() {
    final c = photo.placeholderColors ?? const [0xFFB8C4D6, 0xFFDDE4EE];
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(colors: [Color(c[0]), Color(c[1])]),
      ),
      child: const SizedBox.expand(),
    );
  }
}

/// One label badge (Figma "pin-Coffee"): the word and its native meaning
/// on a white pill. [PinnedPhoto] draws the focal dot on the object and a
/// leader line from the dot to the badge. [large] is the camera view's
/// bigger variant; [muted] badges are words already learned, shown only
/// with 「顯示已學會單字」; [linked] is false for a word the downloaded
/// language pack doesn't have yet (shown as 未收錄).
class WordPin extends StatelessWidget {
  final String word;
  final String zh;
  final String entryType;
  final bool large;
  final bool muted;
  final bool lifted;
  final bool linked;

  /// The widest the badge may be (the photo's width). A label that doesn't
  /// fit on one line shows the word above its meaning, both wrapped in full
  /// — never cut short with … (owner 2026-10-14: 標籤的單字跟說明展開).
  final double? maxWidth;

  const WordPin({
    super.key,
    required this.word,
    required this.zh,
    this.entryType = 'word',
    this.large = false,
    this.muted = false,
    this.lifted = false,
    this.linked = true,
    this.maxWidth,
  });

  static TextStyle wordStyle(bool large) =>
      MFont.manrope(large ? 13 : 12, FontWeight.w700, MColors.primary);
  static TextStyle zhStyle(bool large) =>
      MFont.manrope(large ? 11 : 10, FontWeight.w600, MColors.muted);

  /// What the badge shows after the word.
  static String secondLine(String zh, bool linked) =>
      zh.isNotEmpty ? zh : (linked ? '' : '未收錄');

  /// The badge's size, measured the way it will be laid out: one line, or
  /// with [maxWidth] too narrow for that, the word above its meaning.
  /// [base] is the surrounding DefaultTextStyle the badge's text inherits
  /// (its line height).
  static Size badgeSize(String word, String zh, bool large, TextScaler scaler,
      {bool linked = true,
      double? maxWidth,
      TextStyle? base,
      String entryType = 'word'}) {
    final second = secondLine(typedMeaning(zh, entryType), linked);
    final line = _measure(word, second, large, scaler, null, base);
    if (maxWidth == null || line.width <= maxWidth) return line;
    return _measure(word, second, large, scaler, maxWidth, base);
  }

  // 問題回報：Mac 實機量測第二輪 照片詳情 64ms／翻卡 87ms（M-PERF2）: every
  // build measured each label again with TextPainter (twice: for the layout
  // and for the badge). The sizes are kept until the fonts change.
  static final _sizes = <(
    String,
    String,
    bool,
    TextScaler,
    bool,
    double?,
    TextStyle?,
    String
  ),
      Size>{};
  static bool _watchingFonts = false;

  /// [badgeSize], measured once per label (M-PERF2).
  static Size _sizeOf(String word, String zh, bool large, TextScaler scaler,
      {bool linked = true,
      double? maxWidth,
      TextStyle? base,
      String entryType = 'word'}) {
    if (!_watchingFonts) {
      _watchingFonts = true;
      PaintingBinding.instance.systemFonts.addListener(_sizes.clear);
    }
    if (_sizes.length > 500) _sizes.clear();
    return _sizes.putIfAbsent(
        (word, zh, large, scaler, linked, maxWidth, base, entryType),
        () => badgeSize(word, zh, large, scaler,
            linked: linked,
            maxWidth: maxWidth,
            base: base,
            entryType: entryType));
  }

  // Padding 10 + 10, border 1 + 1.
  static const _sides = 22.0;

  static Size _measure(String word, String second, bool large,
      TextScaler scaler, double? stackedWidth, TextStyle? base) {
    final inner = stackedWidth == null
        ? double.infinity
        : math.max(stackedWidth - _sides, 1.0);
    TextPainter measure(String text, TextStyle style) => TextPainter(
        text: TextSpan(
            text: text, style: (base ?? const TextStyle()).merge(style)),
        textDirection: TextDirection.ltr,
        textScaler: scaler)
      ..layout(maxWidth: inner);
    final w = measure(word, wordStyle(large));
    final z = second.isEmpty ? null : measure(second, zhStyle(large));
    final vertical = (large ? 12 : 8) + 2;
    if (stackedWidth == null) {
      // +1: rounding must not push the meaning onto a second line.
      return Size(
          _sides + w.width + (z == null ? 0 : (large ? 6 : 4) + z.width) + 1,
          vertical + math.max(w.height, z?.height ?? 0));
    }
    return Size(_sides + math.max(w.width, z?.width ?? 0),
        vertical + w.height + (z == null ? 0 : 2 + z.height));
  }

  @override
  Widget build(BuildContext context) {
    final second = secondLine(typedMeaning(zh, entryType), linked);
    final zhText = zh.isEmpty && !linked
        ? zhStyle(large).copyWith(fontStyle: FontStyle.italic)
        : zhStyle(large);
    final stacked = maxWidth != null &&
        _sizeOf(word, zh, large, MediaQuery.textScalerOf(context),
                    linked: linked,
                    entryType: entryType,
                    base: DefaultTextStyle.of(context).style)
                .width >
            maxWidth!;
    final badge = Container(
      padding: EdgeInsets.symmetric(horizontal: 10, vertical: large ? 6 : 4),
      decoration: MDecor.card(
        radius: MRadii.xl,
        borderColor: lifted
            ? MColors.primary
            : (linked
                ? MColors.hairline
                : MColors.muted.withValues(alpha: 0.45)),
        shadow: lifted
            ? MShadows.pinLifted
            : (large ? MShadows.pin : MShadows.soft),
      ).copyWith(
        border: lifted ? Border.all(color: MColors.primary, width: 1.5) : null,
      ),
      child: stacked
          ? Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(word, style: wordStyle(large)),
                if (second.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(second, style: zhText),
                ],
              ],
            )
          // One line; squeezed by a narrower parent, the meaning moves
          // under the word rather than splitting it or overflowing.
          : Wrap(
              spacing: large ? 6 : 4,
              crossAxisAlignment: WrapCrossAlignment.end,
              children: [
                Text(word, style: wordStyle(large)),
                if (second.isNotEmpty) Text(second, style: zhText),
              ],
            ),
    );
    final sized = maxWidth == null
        ? badge
        : ConstrainedBox(
            constraints: BoxConstraints(maxWidth: maxWidth!), child: badge);
    return muted ? Opacity(opacity: 0.55, child: sized) : sized;
  }
}

/// The light bar that sweeps down a photo while it is being read (問題回報
/// #409). Only the bar repaints; the photo under it is not rebuilt.
class PhotoScanSweep extends StatefulWidget {
  const PhotoScanSweep({super.key});

  @override
  State<PhotoScanSweep> createState() => _PhotoScanSweepState();
}

class _PhotoScanSweepState extends State<PhotoScanSweep>
    with SingleTickerProviderStateMixin {
  static const _band = 40.0;
  late final AnimationController _sweep = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1800),
  )..repeat();

  @override
  void dispose() {
    _sweep.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => IgnorePointer(
        child: RepaintBoundary(
          child: LayoutBuilder(
            builder: (context, c) => AnimatedBuilder(
              animation: _sweep,
              builder: (context, _) => Stack(
                children: [
                  Positioned(
                    left: 0,
                    right: 0,
                    height: _band,
                    top: (c.maxHeight + _band) * _sweep.value - _band,
                    child: const DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [
                            Color(0x00FFFFFF),
                            Color(0x66FFFFFF),
                            Color(0x00FFFFFF),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
}

class PinData {
  final String id;
  final LabelPoint anchor;
  final String word;
  final String zh;
  final String entryType;
  final bool muted;

  /// In the downloaded language pack (has a lexeme id).
  final bool linked;

  /// Where the word is printed on the photo, framed (問題回報 #324).
  final LabelBox? frame;

  /// The pinned lexeme, when known: a tap opens it, not whatever entry the
  /// spelling looks up first (soil noun, not soil verb).
  final int? lexemeId;

  const PinData({
    required this.id,
    required this.anchor,
    required this.word,
    required this.zh,
    this.entryType = 'word',
    this.muted = false,
    this.linked = true,
    this.frame,
    this.lexemeId,
  });
}

/// A photo with word labels. Each object gets a focal dot at its anchor
/// (mapped through [CoverGeometry]); its badge is placed by [layoutPins]
/// so labels spread over the photo in balance, never overlap each other
/// or cover a dot, and join their dot with a short leader line. With
/// [onPinMoved], a label can be dragged — its dot moves with it — to put
/// it on the right spot (spec: 照片標籤可拖曳重新定位).
class PinnedPhoto extends StatefulWidget {
  final Photo photo;
  final List<PinData> pins;
  final double radius;
  final bool largePins;
  final ValueChanged<PinData>? onPinTap;
  final void Function(PinData pin, LabelPoint to)? onPinMoved;

  /// A tap on the photo itself (not a label): where, as a fraction of the
  /// original image — used to place a word the learner added by hand.
  final ValueChanged<LabelPoint>? onPhotoTap;

  /// Long-press on the photo (e.g. the photo-credit dialog).
  final VoidCallback? onPhotoLongPress;

  /// Long-press anywhere on the photo, with where (a fraction of the
  /// original image): 長按辨識 asks the AI what is there (問題回報 #616).
  final ValueChanged<LabelPoint>? onPhotoLongPressAt;

  /// A spot being recognized: drawn as a ring until the answer comes.
  final LabelPoint? scanning;
  final Widget? overlay;
  final WidgetBuilder? imageErrorBuilder;
  final ValueChanged<bool>? onImageState;

  /// Bands at the top / bottom that labels keep clear of (chips or
  /// notices drawn over the photo).
  final double reserveTop;
  final double reserveBottom;

  /// Rectangles over the photo (in its coordinates) that labels avoid.
  final List<Rect> avoid;

  /// New labels that show up after the photo opened pop in one by one, in
  /// reading order, then 「找到 N 個字」 (問題回報 #409). Labels already there
  /// when the photo opens show at once.
  final bool revealNew;

  /// The spot that must stay in view (問題回報 #651): the photo is moved
  /// off centre when [BoxFit.cover] would crop it away. Defaults to the
  /// only label's anchor when there is exactly one.
  final LabelPoint? focus;

  /// How the photo fills the box. [BoxFit.contain] (照片詳情, 問題回報 #664)
  /// shows all of it: no label lands on a part cropped away, and badges
  /// stay on the photo, not on the bars beside it.
  final BoxFit fit;

  /// The fit [photo] is drawn with when [fit] is asked for: a photo of
  /// unknown size keeps [BoxFit.cover], the only fit its labels can be
  /// mapped through ([CoverGeometry] then simply fills the box).
  static BoxFit fitFor(Photo photo, BoxFit fit) {
    final w = photo.width, h = photo.height;
    return photo.hasImage && w != null && h != null && w > 0 && h > 0
        ? fit
        : BoxFit.cover;
  }

  /// 問題回報 #664: the height of a frame [width] wide that shows all of
  /// [photo] at its own shape — at most [maxHeight] (a very tall photo is
  /// then shown whole with [BoxFit.contain], with bars beside it). A photo
  /// of unknown size gets [fallback].
  static double frameHeight(Photo photo, double width,
      {required double maxHeight,
      double minHeight = 160,
      double fallback = 320}) {
    final w = photo.width, h = photo.height;
    final natural = fitFor(photo, BoxFit.contain) == BoxFit.contain
        ? width * h! / w!
        : fallback;
    return natural.clamp(math.min(minHeight, maxHeight), maxHeight).toDouble();
  }

  const PinnedPhoto({
    super.key,
    required this.photo,
    required this.pins,
    this.radius = 24,
    this.largePins = false,
    this.onPinTap,
    this.onPinMoved,
    this.onPhotoTap,
    this.onPhotoLongPress,
    this.onPhotoLongPressAt,
    this.scanning,
    this.overlay,
    this.imageErrorBuilder,
    this.onImageState,
    this.reserveTop = 0,
    this.reserveBottom = 0,
    this.avoid = const [],
    this.revealNew = false,
    this.focus,
    this.fit = BoxFit.cover,
  });

  @override
  State<PinnedPhoto> createState() => _PinnedPhotoState();
}

class _PinnedPhotoState extends State<PinnedPhoto> {
  String? _dragging;
  Offset _dragBy = Offset.zero;

  // 問題回報 #409: `_queue` holds the ids still waiting to pop in, one every
  // [_popGap]; `_popped` the ids that have popped in (they animate once).
  static const _popGap = Duration(milliseconds: 200);
  final List<String> _queue = [];
  final Set<String> _popped = {};
  Timer? _ticker;

  /// Labels in the read that is popping in, and the 「找到 N 個字」 shown
  /// after it (gone after [_foundFor]).
  int _batch = 0;
  int? _found;
  Timer? _foundTimer;
  static const _foundFor = Duration(milliseconds: 2500);

  // 問題回報 #442: a label that drops off the photo fades out where it was;
  // `_lastPlaced` keeps where each label was drawn last.
  final Map<String, PinData> _leaving = {};
  final Map<String, PinPlacement> _lastPlaced = {};

  @override
  void didUpdateWidget(PinnedPhoto old) {
    super.didUpdateWidget(old);
    final ids = {for (final p in widget.pins) p.id};
    for (final p in old.pins) {
      if (ids.contains(p.id) || !_lastPlaced.containsKey(p.id)) continue;
      _leaving.putIfAbsent(p.id, () => p);
    }
    _leaving.removeWhere((id, _) => ids.contains(id));
    _queue.removeWhere((id) => !ids.contains(id));
    if (!widget.revealNew) return;
    final known = {for (final p in old.pins) p.id};
    // 問題回報 #665: a label already shown on this photo (gone for a moment
    // while the 難度 bar moved) comes back where it was, without popping in.
    final fresh = [
      for (final p in widget.pins)
        if (!p.muted &&
            !known.contains(p.id) &&
            !_queue.contains(p.id) &&
            !_memory.containsKey(p.id))
          p,
    ]..sort((a, b) => a.anchor.y != b.anchor.y
        ? a.anchor.y.compareTo(b.anchor.y)
        : a.anchor.x.compareTo(b.anchor.x));
    if (fresh.isEmpty) return;
    if (_queue.isEmpty) _batch = 0;
    _batch += fresh.length;
    _found = null;
    _foundTimer?.cancel();
    _queue.addAll(fresh.map((p) => p.id));
    _ticker ??= Timer.periodic(_popGap, (_) => _pop());
  }

  @override
  void dispose() {
    _ticker?.cancel();
    _foundTimer?.cancel();
    super.dispose();
  }

  void _pop() => setState(() {
        if (_queue.isNotEmpty) _popped.add(_queue.removeAt(0));
        if (_queue.isEmpty) _endRead();
      });

  void _skipRead() => setState(() {
        _popped.addAll(_queue);
        _queue.clear();
        _endRead();
      });

  void _endRead() {
    _ticker?.cancel();
    _ticker = null;
    _found = _batch > 0 ? _batch : null;
    _foundTimer = Timer(_foundFor, () {
      if (mounted) setState(() => _found = null);
    });
  }

  /// A label's first build after it pops in: scales up from its dot.
  Widget _popIn(String id, Widget child) => !_popped.contains(id)
      ? child
      : TweenAnimationBuilder<double>(
          tween: Tween(begin: 0, end: 1),
          duration: const Duration(milliseconds: 260),
          curve: Curves.easeOutBack,
          builder: (context, t, child) => Opacity(
              opacity: t.clamp(0.0, 1.0),
              child: Transform.scale(scale: t, child: child)),
          child: child,
        );

  /// The bottom chip: 「跳過動畫」 while labels are still popping in, then
  /// 「找到 N 個字」.
  Widget _revealChip() {
    final skipping = _queue.isNotEmpty;
    final pill = Container(
      padding: const EdgeInsets.symmetric(
          horizontal: MSpace.md, vertical: MSpace.sm - 2),
      decoration: MDecor.overlayPill(radius: MRadii.xl),
      child: UiText(skipping ? '跳過動畫' : '找到 $_found 個字',
          style: MFont.manrope(13, FontWeight.w700, Colors.white)),
    );
    return skipping ? GestureDetector(onTap: _skipRead, child: pill) : pill;
  }

  // layoutPins tries a few hundred spots per label (~10 ms a photo), so the
  // result is kept until the labels, their dots or the photo's size change —
  // not recomputed on every drag frame.
  List<Object>? _layoutKey;
  List<PinPlacement> _layout = const [];

  /// M-PERF2: the last layouts of every photo, so opening a photo again
  /// (or its card back) does not lay its labels out again.
  static final _recent = <_LayoutKey, List<PinPlacement>>{};

  /// 問題回報 #665: where each label was laid out (before any drag) in
  /// [_memoryFrame]. A label already on the photo keeps its spot when the
  /// list changes (難度 bar, 加字／刪字); only new ones look for a place,
  /// in the space left.
  final Map<String, PinPlacement> _memory = {};
  List<Object>? _memoryFrame;

  /// Lays the labels out inside [area], the part of [box] the photo
  /// covers (問題回報 #664: never on a part cropped away or on the bars).
  List<PinPlacement> _placements(List<PinItem> items, Size box, Rect area) {
    final frame = <Object>[
      box,
      area,
      widget.reserveTop,
      widget.reserveBottom,
      ...widget.avoid,
    ];
    final key = <Object>[
      ...frame,
      for (final it in items) ...[it.id, it.anchor, it.badge],
    ];
    if (_layoutKey == null || !listEquals(_layoutKey, key)) {
      _layoutKey = key;
      if (!listEquals(_memoryFrame, frame)) {
        _memory.clear();
        _memoryFrame = frame;
      }
      final shared = _LayoutKey(key);
      final hit = _recent.remove(shared);
      final origin = area.topLeft;
      final keep = _memory.isEmpty
          ? const <PinPlacement>[]
          : [
              // Labels on the photo now first, then ones seen before.
              for (final pl in _layout)
                if (_memory[pl.id] case final m?) m,
              for (final m in _memory.values)
                if (!_layout.any((pl) => pl.id == m.id)) m,
            ];
      _layout = keep.isEmpty && hit != null
          ? hit
          : [
              for (final pl in layoutPins([
                for (final it in items)
                  PinItem(it.id, it.anchor - origin, it.badge),
              ], area.size,
                  reserveTop: math.max(0.0, widget.reserveTop - area.top),
                  reserveBottom: math.max(
                      0.0, widget.reserveBottom - (box.height - area.bottom)),
                  avoid: [for (final a in widget.avoid) a.shift(-origin)],
                  keep: [
                    for (final k in keep)
                      PinPlacement(
                          k.id, k.anchor - origin, k.badge.shift(-origin)),
                  ]))
                PinPlacement(pl.id, pl.anchor + origin, pl.badge.shift(origin)),
            ];
      for (final pl in _layout) {
        _memory[pl.id] = pl;
      }
      _recent[shared] = _layout;
      if (_recent.length > 64) _recent.remove(_recent.keys.first);
    }
    return _layout;
  }

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(widget.radius),
      child: LayoutBuilder(
        builder: (context, c) {
          final box = Size(c.maxWidth, c.maxHeight);
          final focus = widget.focus ??
              (widget.pins.length == 1 ? widget.pins.single.anchor : null);
          final fit = PinnedPhoto.fitFor(widget.photo, widget.fit);
          final alignment = focus == null || fit == BoxFit.contain
              ? Alignment.center
              : CoverGeometry.focusing(box, widget.photo, focus);
          final geo =
              CoverGeometry(box, widget.photo, alignment: alignment, fit: fit);
          // Labels and their dots stay on the photo itself (問題回報 #664).
          final area = geo.visibleIn(box);
          final scaler = MediaQuery.textScalerOf(context);
          final byId = {for (final p in widget.pins) p.id: p};
          final placed = _placements([
            for (final p in widget.pins)
              PinItem(
                  p.id,
                  geo.toBox(p.anchor),
                  WordPin._sizeOf(p.word, p.zh, widget.largePins, scaler,
                      entryType: p.entryType,
                      linked: p.linked,
                      // layoutPins' margin: a long label wraps in full.
                      maxWidth: area.width - 12,
                      base: DefaultTextStyle.of(context).style)),
          ], box, area);
          // While a label is dragged, it and its dot move together.
          PinPlacement shown(PinPlacement pl) => pl.id == _dragging
              ? PinPlacement(
                  pl.id, pl.anchor + _dragBy, pl.badge.shift(_dragBy))
              : pl;
          final visible = [for (final pl in placed) shown(pl)];
          for (final pl in visible) {
            _lastPlaced[pl.id] = pl;
          }
          Offset clampToBox(Offset o) => Offset(
              o.dx.clamp(area.left + 4, math.max(area.left + 4, area.right - 4)),
              o.dy.clamp(area.top + 4, math.max(area.top + 4, area.bottom - 4)));
          return Stack(
            clipBehavior: Clip.hardEdge,
            children: [
              Positioned.fill(
                  child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTapUp: widget.onPhotoTap == null
                    ? null
                    : (d) => widget.onPhotoTap!(geo.fromBox(d.localPosition)),
                onLongPressStart: widget.onPhotoLongPressAt == null &&
                        widget.onPhotoLongPress == null
                    ? null
                    : (d) {
                        final at = widget.onPhotoLongPressAt;
                        if (at != null) {
                          HapticFeedback.mediumImpact();
                          at(geo.fromBox(d.localPosition));
                        } else {
                          widget.onPhotoLongPress?.call();
                        }
                      },
                // The photo stays still while labels pop in (#409).
                child: RepaintBoundary(
                  child: PhotoImage(widget.photo,
                      fit: fit,
                      alignment: alignment,
                      imageErrorBuilder: widget.imageErrorBuilder,
                      onImageState: widget.onImageState),
                ),
              )),
              Positioned.fill(
                child: IgnorePointer(
                  child: CustomPaint(
                    painter: _LeaderPainter([
                      for (final pl in visible)
                        if (!_queue.contains(pl.id)) (pl, byId[pl.id]!.muted),
                    ], frames: [
                      for (final p in widget.pins)
                        if (p.frame case final f?
                            when p.id != _dragging && !_queue.contains(p.id))
                          (
                            Rect.fromPoints(
                                geo.toBox(LabelPoint(f.left, f.top)),
                                geo.toBox(LabelPoint(
                                    f.left + f.width, f.top + f.height))),
                            p.muted,
                          ),
                    ]),
                  ),
                ),
              ),
              for (final pl in visible)
                if (!_queue.contains(pl.id))
                  Positioned(
                    key: ValueKey(pl.id),
                    left: pl.badge.left,
                    top: pl.badge.top,
                    child: _popIn(
                        pl.id,
                        GestureDetector(
                          onPanStart:
                              widget.onPinMoved == null || byId[pl.id]!.muted
                                  ? null
                                  : (_) => setState(() {
                                        _dragging = pl.id;
                                        _dragBy = Offset.zero;
                                      }),
                          onPanUpdate: widget.onPinMoved == null ||
                                  byId[pl.id]!.muted
                              ? null
                              : (d) => setState(() {
                                    final base = placed
                                        .firstWhere((x) => x.id == pl.id)
                                        .anchor;
                                    _dragBy =
                                        clampToBox(base + _dragBy + d.delta) -
                                            base;
                                  }),
                          onPanEnd:
                              widget.onPinMoved == null || byId[pl.id]!.muted
                                  ? null
                                  : (_) {
                                      final base = placed
                                          .firstWhere((x) => x.id == pl.id)
                                          .anchor;
                                      final to = base + _dragBy;
                                      setState(() {
                                        _dragging = null;
                                        _dragBy = Offset.zero;
                                      });
                                      widget.onPinMoved!(
                                          byId[pl.id]!, geo.fromBox(to));
                                    },
                          child: Tap(
                            onTap: widget.onPinTap == null
                                ? null
                                : () => widget.onPinTap!(byId[pl.id]!),
                            label: '${byId[pl.id]!.word} ${byId[pl.id]!.zh}',
                            child: WordPin(
                              word: byId[pl.id]!.word,
                              zh: byId[pl.id]!.zh,
                              entryType: byId[pl.id]!.entryType,
                              large: widget.largePins,
                              muted: byId[pl.id]!.muted,
                              lifted: _dragging == pl.id,
                              linked: byId[pl.id]!.linked,
                              maxWidth: pl.badge.width,
                            ),
                          ),
                        )),
                  ),
              for (final e in _leaving.entries)
                if (_lastPlaced[e.key] case final pl?)
                  Positioned(
                    key: ValueKey('leaving-${e.key}'),
                    left: pl.badge.left,
                    top: pl.badge.top,
                    child: IgnorePointer(
                      child: _FadeOutPin(
                        onGone: () => setState(() => _leaving.remove(e.key)),
                        child: WordPin(
                          word: e.value.word,
                          zh: e.value.zh,
                          entryType: e.value.entryType,
                          large: widget.largePins,
                          muted: e.value.muted,
                          linked: e.value.linked,
                          maxWidth: pl.badge.width,
                        ),
                      ),
                    ),
                  ),
              if (widget.scanning case final spot?)
                Positioned(
                  left: geo.toBox(spot).dx - 28,
                  top: geo.toBox(spot).dy - 28,
                  child: const IgnorePointer(
                    child: SizedBox(
                      key: ValueKey('spot-scanning'),
                      width: 56,
                      height: 56,
                      child: CircularProgressIndicator(
                          strokeWidth: 3, color: Colors.white),
                    ),
                  ),
                ),
              if (widget.overlay != null)
                Positioned.fill(
                    child: PhotoAlignment(
                        alignment: alignment,
                        fit: fit,
                        child: widget.overlay!)),
              if (_queue.isNotEmpty || _found != null)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 12,
                  child: Center(child: _revealChip()),
                ),
            ],
          );
        },
      ),
    );
  }
}

/// [_PinnedPhotoState._placements]' inputs as a map key (M-PERF2).
class _LayoutKey {
  final List<Object> parts;
  @override
  final int hashCode;

  _LayoutKey(this.parts) : hashCode = Object.hashAll(parts);

  @override
  bool operator ==(Object other) =>
      other is _LayoutKey &&
      other.hashCode == hashCode &&
      listEquals(other.parts, parts);
}

/// 問題回報 #442: a label that has dropped off the photo fades out, then
/// tells its photo to forget it ([onGone]).
class _FadeOutPin extends StatefulWidget {
  final Widget child;
  final VoidCallback onGone;

  const _FadeOutPin({required this.child, required this.onGone});

  @override
  State<_FadeOutPin> createState() => _FadeOutPinState();
}

class _FadeOutPinState extends State<_FadeOutPin>
    with SingleTickerProviderStateMixin {
  late final AnimationController _fade = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 220),
  )..forward().whenComplete(() {
      if (mounted) widget.onGone();
    });

  @override
  void dispose() {
    _fade.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeTransition(
        opacity: Tween<double>(begin: 1, end: 0).animate(_fade),
        child: widget.child,
      );
}

/// Leader lines and focal dots under the badges: a soft shadow, then a
/// white line from each object's dot to its badge, then the dot.
class _LeaderPainter extends CustomPainter {
  final List<(PinPlacement, bool)> pins;

  /// Boxes around printed words (問題回報 #324), and whether muted.
  final List<(Rect, bool)> frames;

  _LeaderPainter(this.pins, {this.frames = const []});

  @override
  void paint(Canvas canvas, Size size) {
    for (final (r, muted) in frames) {
      final a = muted ? 0.55 : 1.0;
      final box =
          RRect.fromRectAndRadius(r.inflate(2), const Radius.circular(4));
      canvas.drawRRect(
          box,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 3
            ..color = Color.fromRGBO(20, 28, 46, 0.28 * a));
      canvas.drawRRect(
          box,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1.5
            ..color = MColors.primary.withValues(alpha: 0.9 * a));
    }
    for (final (pl, muted) in pins) {
      final a = muted ? 0.55 : 1.0;
      if (pl.leaderLength > 1) {
        canvas.drawLine(
            pl.anchor,
            pl.joint,
            Paint()
              ..color = Color.fromRGBO(20, 28, 46, 0.28 * a)
              ..strokeWidth = 3
              ..strokeCap = StrokeCap.round);
        canvas.drawLine(
            pl.anchor,
            pl.joint,
            Paint()
              ..color = Colors.white.withValues(alpha: 0.95 * a)
              ..strokeWidth = 1.5
              ..strokeCap = StrokeCap.round);
      }
      canvas.drawCircle(pl.anchor, 5.5,
          Paint()..color = Color.fromRGBO(20, 28, 46, 0.25 * a));
      canvas.drawCircle(
          pl.anchor, 4.5, Paint()..color = Colors.white.withValues(alpha: a));
      canvas.drawCircle(pl.anchor, 2.5,
          Paint()..color = MColors.primary.withValues(alpha: a));
    }
  }

  @override
  bool shouldRepaint(_LeaderPainter old) => true;
}

/// The quiz front's 目標區域: a ring around the label's anchor, with no
/// words anywhere on the photo (spec: 其他標籤全部遮蔽).
class TargetRing extends StatelessWidget {
  final Photo photo;
  final LabelPoint anchor;

  /// The word's box (0–1 of the original image), outlined when known.
  final Rect? box;

  const TargetRing(
      {super.key, required this.photo, required this.anchor, this.box});

  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, c) => Stack(
          children: [
            if (box case final b?)
              if (CoverGeometry.of(context, c.biggest, photo) case final geo)
                Positioned.fromRect(
                  rect: Rect.fromPoints(geo.toBox(LabelPoint(b.left, b.top)),
                      geo.toBox(LabelPoint(b.right, b.bottom))),
                  child: IgnorePointer(
                    child: Container(
                      key: const ValueKey('target-box'),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.white, width: 2.5),
                      ),
                      // A thin primary line inside the white one, so the
                      // outline reads on light and dark photos alike.
                      child: Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(10),
                          border:
                              Border.all(color: MColors.primary, width: 1.5),
                        ),
                      ),
                    ),
                  ),
                ),
            if (CoverGeometry.of(context, c.biggest, photo).toBox(anchor)
                case final at)
              Positioned(
                left: at.dx - 28,
                top: at.dy - 28,
                child: Container(
                  key: const ValueKey('target-ring'),
                  width: 56,
                  height: 56,
                  // A circle cannot also have softPanel's border radius.
                  decoration: BoxDecoration(
                    color: MColors.primary.withValues(alpha: 0.18),
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 3),
                    boxShadow: MShadows.pin,
                  ),
                  child: const Center(child: MSvg(MIcon.focalDot, size: 10)),
                ),
              ),
          ],
        ),
      );
}

/// The hourglass on a photo waiting for AI tagging (spec section 7: 相片冊
/// 縮圖右上角顯示沙漏).
class HourglassBadge extends StatelessWidget {
  const HourglassBadge({super.key});

  @override
  Widget build(BuildContext context) => Semantics(
        label: '等待 AI 辨識',
        child: Container(
          width: 24,
          height: 24,
          decoration: BoxDecoration(
            color: MColors.ink.withValues(alpha: 0.72),
            shape: BoxShape.circle,
            boxShadow: MShadows.soft,
          ),
          child: const Icon(Icons.hourglass_top_rounded,
              size: 14, color: Colors.white),
        ),
      );
}

/// A dot that is picked up with a long press and dragged to the right spot
/// (問題回報 #410: the AI may put a label on the wrong object). [at] is the
/// dot's centre in the parent Stack's box; [onMoved] gets the dropped
/// centre in the same box. Plain taps and scrolls pass through untouched.
class DraggableAnchorDot extends StatefulWidget {
  final Offset at;
  final ValueChanged<Offset> onMoved;

  const DraggableAnchorDot(
      {super.key, required this.at, required this.onMoved});

  @override
  State<DraggableAnchorDot> createState() => _DraggableAnchorDotState();
}

class _DraggableAnchorDotState extends State<DraggableAnchorDot> {
  Offset? _drag;

  @override
  Widget build(BuildContext context) {
    final lifted = _drag != null;
    final at = _drag ?? widget.at;
    final size = lifted ? 22.0 : 14.0;
    return Positioned(
      left: at.dx - 22,
      top: at.dy - 22,
      width: 44,
      height: 44,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onLongPressStart: (_) => setState(() => _drag = widget.at),
        onLongPressMoveUpdate: (d) =>
            setState(() => _drag = widget.at + d.offsetFromOrigin),
        onLongPressEnd: (_) {
          final to = _drag;
          setState(() => _drag = null);
          if (to != null) widget.onMoved(to);
        },
        onLongPressCancel: () => setState(() => _drag = null),
        child: Center(
          child: AnimatedContainer(
            key: const ValueKey('draggable-anchor-dot'),
            duration: const Duration(milliseconds: 120),
            width: size,
            height: size,
            decoration: BoxDecoration(
              color: MColors.primary,
              shape: BoxShape.circle,
              border: Border.all(color: Colors.white, width: 2.5),
              boxShadow: MShadows.soft,
            ),
          ),
        ),
      ),
    );
  }
}
