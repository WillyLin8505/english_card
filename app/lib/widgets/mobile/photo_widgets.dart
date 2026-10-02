import 'dart:io';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import '../../app/app_scope.dart';
import '../../models/learning_card.dart';
import '../../models/photo.dart';
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

  const PhotoImage(
    this.photo, {
    super.key,
    this.fit = BoxFit.cover,
    this.alignment = Alignment.center,
  });

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
        errorBuilder: (_, __, ___) => _placeholder(),
      );
    }
    return _placeholder();
  }

  ImageProvider? _provider(BuildContext context) {
    if (photo.assetPath != null) return AssetImage(photo.assetPath!);
    if (photo.networkUrl != null) return NetworkImage(photo.networkUrl!);
    if (photo.filePath != null && !kIsWeb) {
      return FileImage(File(photo.filePath!));
    }
    if (photo.storedKey != null) {
      final bytes =
          AppScope.of(context).photoStore.storedBytes(photo.storedKey!);
      if (bytes != null) return MemoryImage(bytes);
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

/// One label badge (Figma "pin-Coffee"): the word and its native meaning
/// on a white pill. [PinnedPhoto] draws the focal dot on the object and a
/// leader line from the dot to the badge. [large] is the camera view's
/// bigger variant; [muted] badges are words already learned, shown only
/// with 「顯示已學會單字」; [linked] is false for a word the downloaded
/// language pack doesn't have yet (shown as 未收錄).
class WordPin extends StatelessWidget {
  final String word;
  final String zh;
  final bool large;
  final bool muted;
  final bool lifted;
  final bool linked;

  const WordPin({
    super.key,
    required this.word,
    required this.zh,
    this.large = false,
    this.muted = false,
    this.lifted = false,
    this.linked = true,
  });

  static TextStyle wordStyle(bool large) =>
      MFont.manrope(large ? 13 : 12, FontWeight.w700, MColors.primary);
  static TextStyle zhStyle(bool large) =>
      MFont.manrope(large ? 11 : 10, FontWeight.w600, MColors.muted);

  /// What the badge shows after the word.
  static String secondLine(String zh, bool linked) =>
      zh.isNotEmpty ? zh : (linked ? '' : '未收錄');

  /// The badge's size, measured the way it will be laid out.
  static Size badgeSize(String word, String zh, bool large, TextScaler scaler,
      {bool linked = true}) {
    TextPainter measure(String text, TextStyle style) => TextPainter(
        text: TextSpan(text: text, style: style),
        textDirection: TextDirection.ltr,
        textScaler: scaler)
      ..layout();
    final second = secondLine(zh, linked);
    final w = measure(word, wordStyle(large));
    final z = second.isEmpty ? null : measure(second, zhStyle(large));
    final width =
        20 + w.width + (z == null ? 0 : (large ? 6 : 4) + z.width) + 2;
    final height = (large ? 12 : 8) +
        (z == null ? w.height : (w.height > z.height ? w.height : z.height)) +
        2;
    return Size(width, height);
  }

  @override
  Widget build(BuildContext context) {
    final second = secondLine(zh, linked);
    final badge = Container(
      padding: EdgeInsets.symmetric(horizontal: 10, vertical: large ? 6 : 4),
      decoration: MDecor.card(
        radius: MRadii.xl,
        borderColor: lifted
            ? MColors.primary
            : (linked ? MColors.hairline : MColors.muted.withValues(alpha: 0.45)),
        shadow: lifted
            ? MShadows.pinLifted
            : (large ? MShadows.pin : MShadows.soft),
      ).copyWith(
        border: lifted ? Border.all(color: MColors.primary, width: 1.5) : null,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: [
          Text(word, style: wordStyle(large)),
          if (second.isNotEmpty) ...[
            SizedBox(width: large ? 6 : 4),
            Text(second,
                style: zh.isEmpty && !linked
                    ? zhStyle(large).copyWith(fontStyle: FontStyle.italic)
                    : zhStyle(large)),
          ],
        ],
      ),
    );
    return muted ? Opacity(opacity: 0.55, child: badge) : badge;
  }
}

class PinData {
  final String id;
  final LabelPoint anchor;
  final String word;
  final String zh;
  final bool muted;

  /// In the downloaded language pack (has a lexeme id).
  final bool linked;

  const PinData({
    required this.id,
    required this.anchor,
    required this.word,
    required this.zh,
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
          final placed = layoutPins([
            for (final p in widget.pins)
              PinItem(
                  p.id,
                  geo.toBox(p.anchor),
                  WordPin.badgeSize(p.word, p.zh, widget.largePins, scaler,
                      linked: p.linked)),
          ], box,
              reserveTop: widget.reserveTop,
              reserveBottom: widget.reserveBottom,
              avoid: widget.avoid);
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
              Positioned.fill(child: PhotoImage(widget.photo)),
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
                        large: widget.largePins,
                        muted: byId[pl.id]!.muted,
                        lifted: _dragging == pl.id,
                        linked: byId[pl.id]!.linked,
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
