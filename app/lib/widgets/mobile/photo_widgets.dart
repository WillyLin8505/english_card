import '../../services/learning_content.dart';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show kIsWeb, listEquals;
import 'package:flutter/material.dart';

import '../../app/app_scope.dart';
import '../../models/learning_card.dart';
import '../../models/photo.dart';
import '../../services/photo_store.dart';
import '../../theme/mobile_theme.dart';
import 'common.dart';
import 'm_icon.dart';
import 'pin_layout.dart';

/// Where a label anchor (a fraction of the ORIGINAL image) lands in a box
/// that shows the photo with [BoxFit.cover], and back. Photos without a
/// known size (placeholders) simply fill the box.
class CoverGeometry {
  final double scale;
  final double imageWidth;
  final double imageHeight;
  final Offset offset;

  CoverGeometry._(this.scale, this.imageWidth, this.imageHeight, this.offset);

  factory CoverGeometry(Size box, Photo photo) {
    final w = photo.width?.toDouble(), h = photo.height?.toDouble();
    if (!photo.hasImage || w == null || h == null || w <= 0 || h <= 0) {
      return CoverGeometry._(1, box.width, box.height, Offset.zero);
    }
    final s = box.width / w > box.height / h ? box.width / w : box.height / h;
    return CoverGeometry._(
        s, w, h, Offset((box.width - w * s) / 2, (box.height - h * s) / 2));
  }

  Offset toBox(LabelPoint p) =>
      offset + Offset(p.x * imageWidth * scale, p.y * imageHeight * scale);

  LabelPoint fromBox(Offset o) => LabelPoint(
        ((o.dx - offset.dx) / (imageWidth * scale)).clamp(0.0, 1.0),
        ((o.dy - offset.dy) / (imageHeight * scale)).clamp(0.0, 1.0),
      );
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
    if (synchronous || frame != null) _report(true);
    return child;
  }

  @override
  Widget build(BuildContext context) {
    final image = _provider(context);
    if (image != null) {
      return Image(
        image: image,
        fit: fit,
        alignment: alignment,
        width: double.infinity,
        height: double.infinity,
        frameBuilder: _frame,
        errorBuilder: (context, _, __) => _error(context),
      );
    }
    if (photo.storedKey != null) {
      return _StoredPhotoImage(photoImage: this);
    }
    _report(false);
    return _placeholder();
  }

  ImageProvider? _provider(BuildContext context) {
    if (photo.assetPath != null) return AssetImage(photo.assetPath!);
    if (photo.networkUrl != null) return NetworkImage(photo.networkUrl!);
    if (photo.filePath != null && !kIsWeb) {
      return FileImage(File(photo.filePath!));
    }
    return null;
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

/// Retain one read per mounted photo instead of rereading on every rebuild.
class _StoredPhotoImage extends StatefulWidget {
  final PhotoImage photoImage;
  const _StoredPhotoImage({required this.photoImage});

  @override
  State<_StoredPhotoImage> createState() => _StoredPhotoImageState();
}

class _StoredPhotoImageState extends State<_StoredPhotoImage> {
  PhotoStore? _store;
  String? _key;
  Future<Uint8List?>? _bytes;

  void _load() {
    final store = AppScope.of(context).photoStore;
    final key = widget.photoImage.photo.storedKey!;
    if (identical(store, _store) && key == _key) return;
    _store = store;
    _key = key;
    _bytes = store.storedBytes(key);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _load();
  }

  @override
  void didUpdateWidget(_StoredPhotoImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final view = widget.photoImage;
    return FutureBuilder<Uint8List?>(
      future: _bytes,
      builder: (context, snapshot) {
        // FutureBuilder retains old data/errors while a replacement read is
        // pending. Neither belongs to the new photo's load attempt.
        if (snapshot.connectionState != ConnectionState.done) {
          return view._placeholder();
        }
        if (snapshot.hasError) {
          return view._error(context);
        }
        if (snapshot.data == null) return view._error(context);
        return Image(
          image: MemoryImage(snapshot.data!),
          fit: view.fit,
          alignment: view.alignment,
          width: double.infinity,
          height: double.infinity,
          frameBuilder: view._frame,
          errorBuilder: (context, _, __) => view._error(context),
        );
      },
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
      {bool linked = true, double? maxWidth, TextStyle? base, String entryType = 'word'}) {
    final second = secondLine(typedMeaning(zh, entryType), linked);
    final line = _measure(word, second, large, scaler, null, base);
    if (maxWidth == null || line.width <= maxWidth) return line;
    return _measure(word, second, large, scaler, maxWidth, base);
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
        badgeSize(word, zh, large, MediaQuery.textScalerOf(context),
                    linked: linked, entryType: entryType, base: DefaultTextStyle.of(context).style)
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

class PinData {
  final String id;
  final LabelPoint anchor;
  final String word;
  final String zh;
  final String entryType;
  final bool muted;

  /// In the downloaded language pack (has a lexeme id).
  final bool linked;

  const PinData({
    required this.id,
    required this.anchor,
    required this.word,
    required this.zh,
    this.entryType = 'word',
    this.muted = false,
    this.linked = true,
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
  final Widget? overlay;
  final WidgetBuilder? imageErrorBuilder;
  final ValueChanged<bool>? onImageState;

  /// Bands at the top / bottom that labels keep clear of (chips or
  /// notices drawn over the photo).
  final double reserveTop;
  final double reserveBottom;

  /// Rectangles over the photo (in its coordinates) that labels avoid.
  final List<Rect> avoid;

  const PinnedPhoto({
    super.key,
    required this.photo,
    required this.pins,
    this.radius = 24,
    this.largePins = false,
    this.onPinTap,
    this.onPinMoved,
    this.overlay,
    this.imageErrorBuilder,
    this.onImageState,
    this.reserveTop = 0,
    this.reserveBottom = 0,
    this.avoid = const [],
  });

  @override
  State<PinnedPhoto> createState() => _PinnedPhotoState();
}

class _PinnedPhotoState extends State<PinnedPhoto> {
  String? _dragging;
  Offset _dragBy = Offset.zero;

  // layoutPins tries a few hundred spots per label (~10 ms a photo), so the
  // result is kept until the labels, their dots or the photo's size change —
  // not recomputed on every drag frame.
  List<Object>? _layoutKey;
  List<PinPlacement> _layout = const [];

  List<PinPlacement> _placements(List<PinItem> items, Size box) {
    final key = <Object>[
      box,
      widget.reserveTop,
      widget.reserveBottom,
      ...widget.avoid,
      for (final it in items) ...[it.id, it.anchor, it.badge],
    ];
    if (_layoutKey == null || !listEquals(_layoutKey, key)) {
      _layoutKey = key;
      _layout = layoutPins(items, box,
          reserveTop: widget.reserveTop,
          reserveBottom: widget.reserveBottom,
          avoid: widget.avoid);
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
          final geo = CoverGeometry(box, widget.photo);
          final scaler = MediaQuery.textScalerOf(context);
          final byId = {for (final p in widget.pins) p.id: p};
          final placed = _placements([
            for (final p in widget.pins)
              PinItem(
                  p.id,
                  geo.toBox(p.anchor),
                  WordPin.badgeSize(p.word, p.zh, widget.largePins, scaler, entryType: p.entryType,
                      linked: p.linked,
                      // layoutPins' margin: a long label wraps in full.
                      maxWidth: box.width - 12,
                      base: DefaultTextStyle.of(context).style)),
          ], box);
          // While a label is dragged, it and its dot move together.
          PinPlacement shown(PinPlacement pl) => pl.id == _dragging
              ? PinPlacement(
                  pl.id, pl.anchor + _dragBy, pl.badge.shift(_dragBy))
              : pl;
          final visible = [for (final pl in placed) shown(pl)];
          Offset clampToBox(Offset o) => Offset(
              o.dx.clamp(4.0, box.width - 4), o.dy.clamp(4.0, box.height - 4));
          return Stack(
            clipBehavior: Clip.hardEdge,
            children: [
              Positioned.fill(
                  child: PhotoImage(widget.photo,
                      imageErrorBuilder: widget.imageErrorBuilder,
                      onImageState: widget.onImageState)),
              Positioned.fill(
                child: IgnorePointer(
                  child: CustomPaint(
                    painter: _LeaderPainter([
                      for (final pl in visible) (pl, byId[pl.id]!.muted),
                    ]),
                  ),
                ),
              ),
              for (final pl in visible)
                Positioned(
                  left: pl.badge.left,
                  top: pl.badge.top,
                  child: GestureDetector(
                    onPanStart: widget.onPinMoved == null || byId[pl.id]!.muted
                        ? null
                        : (_) => setState(() {
                              _dragging = pl.id;
                              _dragBy = Offset.zero;
                            }),
                    onPanUpdate: widget.onPinMoved == null || byId[pl.id]!.muted
                        ? null
                        : (d) => setState(() {
                              final base = placed
                                  .firstWhere((x) => x.id == pl.id)
                                  .anchor;
                              _dragBy =
                                  clampToBox(base + _dragBy + d.delta) - base;
                            }),
                    onPanEnd: widget.onPinMoved == null || byId[pl.id]!.muted
                        ? null
                        : (_) {
                            final base =
                                placed.firstWhere((x) => x.id == pl.id).anchor;
                            final to = base + _dragBy;
                            setState(() {
                              _dragging = null;
                              _dragBy = Offset.zero;
                            });
                            widget.onPinMoved!(byId[pl.id]!, geo.fromBox(to));
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
                  ),
                ),
              if (widget.overlay != null)
                Positioned.fill(child: widget.overlay!),
            ],
          );
        },
      ),
    );
  }
}

/// Leader lines and focal dots under the badges: a soft shadow, then a
/// white line from each object's dot to its badge, then the dot.
class _LeaderPainter extends CustomPainter {
  final List<(PinPlacement, bool)> pins;

  _LeaderPainter(this.pins);

  @override
  void paint(Canvas canvas, Size size) {
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

  const TargetRing({super.key, required this.photo, required this.anchor});

  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, c) => Stack(
          children: [
            if (CoverGeometry(c.biggest, photo).toBox(anchor) case final at)
              Positioned(
                left: at.dx - 28,
                top: at.dy - 28,
                child: Container(
                  width: 56,
                  height: 56,
                  decoration: MDecor.softPanel(
                    color: MColors.primary.withValues(alpha: 0.18),
                    radius: 28,
                  ).copyWith(
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
