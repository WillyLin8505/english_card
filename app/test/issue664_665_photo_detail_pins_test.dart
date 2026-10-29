import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';
import 'package:photo_english_app/widgets/mobile/pin_layout.dart';
import 'helpers.dart';

/// 問題回報 #664: 照片詳情 showed a portrait photo (720×1280) cropped to a
/// wide frame with BoxFit.cover, so labels at y = 0.18 / 0.76 / 0.85 fell
/// on the cropped-away part — 「我的標籤都跑出去了」.
/// 問題回報 #665: labels already on the photo popped in and moved again
/// whenever the list changed.
Photo _portrait() => Photo(
    id: 'photo-1792769785574157',
    title: '',
    takenAt: testNow,
    createdAt: testNow,
    networkUrl: 'http://127.0.0.1:1/x.jpg',
    width: 720,
    height: 1280);

// The owner's photo: 7 labels, two pairs on the same spot.
const _anchors = [
  LabelPoint(0.15, 0.76),
  LabelPoint(0.1, 0.18),
  LabelPoint(0.6, 0.85),
  LabelPoint(0.14, 0.42),
  LabelPoint(0.6, 0.85),
  LabelPoint(0.5, 0.42),
  LabelPoint(0.5, 0.42),
];
const _words = ['Chair', 'Lamp', 'Table', 'Window', 'Cup', 'Curtain', 'Plant'];
const _zh = ['椅子', '檯燈', '桌子', '窗戶', '杯子', '窗簾', '植物'];

List<PinData> _pins([int n = 7]) => [
      for (var i = 0; i < n; i++)
        PinData(
            id: _words[i], anchor: _anchors[i], word: _words[i], zh: _zh[i]),
    ];

Widget _host(Photo photo, List<PinData> pins, Size frame,
        {BoxFit fit = BoxFit.contain,
        bool revealNew = false,
        ValueChanged<LabelPoint>? onTap}) =>
    MaterialApp(
      theme: MobileTheme.light(),
      home: Align(
        alignment: Alignment.topLeft,
        child: SizedBox(
          width: frame.width,
          height: frame.height,
          child: PinnedPhoto(
              photo: photo,
              pins: pins,
              fit: fit,
              revealNew: revealNew,
              onPhotoTap: onTap),
        ),
      ),
    );

void main() {
  final photo = _portrait();

  group('#664 the whole photo, every label on it', () {
    test('the frame takes the photo\'s shape, capped', () {
      // 358 wide: 358 × 1280 / 720 ≈ 636, capped at 520.
      expect(PinnedPhoto.frameHeight(photo, 358, maxHeight: 520), 520);
      expect(PinnedPhoto.frameHeight(photo, 200, maxHeight: 520),
          closeTo(355.6, 0.1));
      final landscape = Photo(
          id: 'l',
          title: '',
          takenAt: testNow,
          createdAt: testNow,
          networkUrl: 'http://127.0.0.1:1/x.jpg',
          width: 1600,
          height: 900);
      expect(PinnedPhoto.frameHeight(landscape, 358, maxHeight: 520),
          closeTo(201.4, 0.1));
      // No size known: the old 320.
      final unknown =
          Photo(id: 'u', title: '', takenAt: testNow, createdAt: testNow);
      expect(PinnedPhoto.frameHeight(unknown, 358, maxHeight: 520), 320);
    });

    test('cover crops the labels away; contain keeps every one on the photo',
        () {
      const box = Size(358, 320); // the old fixed frame
      final cover = CoverGeometry(box, photo);
      expect(
          _anchors.where((a) {
            final p = cover.toBox(a);
            return p.dy < 0 || p.dy > box.height;
          }).length,
          greaterThan(0));
      final contain = CoverGeometry(box, photo, fit: BoxFit.contain);
      final visible = contain.visibleIn(box);
      for (final a in _anchors) {
        expect(visible.contains(contain.toBox(a)), isTrue, reason: '$a');
        final back = contain.fromBox(contain.toBox(a));
        expect(back.x, closeTo(a.x, 1e-9));
        expect(back.y, closeTo(a.y, 1e-9));
      }
    });

    test('#940 a dot on the edge, or cropped away, stays on the picture', () {
      const box = Size(358, 320);
      for (final fit in const [BoxFit.contain, BoxFit.cover]) {
        final geo = CoverGeometry(box, photo, fit: fit);
        final area = geo.visibleIn(box).deflate(5.5);
        for (final p in const [
          LabelPoint(0, 0.5),
          LabelPoint(1, 0),
          LabelPoint(0.5, 1),
          LabelPoint(0.1, 0.02), // cover crops this part away
        ]) {
          final dot = geo.dotIn(box, p);
          expect(area.contains(dot), isTrue, reason: '$fit $p $dot');
        }
        // A point well inside is not moved.
        const mid = LabelPoint(0.5, 0.5);
        expect(geo.dotIn(box, mid), geo.toBox(mid));
      }
    });

    for (final frame in const [Size(358, 520), Size(358, 320)]) {
      testWidgets('dots and badges stay on the photo in a $frame frame',
          (tester) async {
        await tester.pumpWidget(_host(photo, _pins(), frame));
        await tester.pump();
        final origin = tester.getTopLeft(find.byType(PinnedPhoto));
        final geo = CoverGeometry(frame, photo, fit: BoxFit.contain);
        final visible = geo.visibleIn(frame).shift(origin);
        for (var i = 0; i < _anchors.length; i++) {
          final dot = geo.toBox(_anchors[i]) + origin;
          expect(visible.contains(dot), isTrue, reason: _words[i]);
          final badge = tester.getRect(find
              .ancestor(
                  of: find.text(_words[i]), matching: find.byType(WordPin))
              .first);
          expect(visible.inflate(0.5).contains(badge.topLeft), isTrue,
              reason: '${_words[i]} $badge in $visible');
          expect(visible.inflate(0.5).contains(badge.bottomRight), isTrue,
              reason: '${_words[i]} $badge in $visible');
        }
      });
    }

    testWidgets('a tap maps back through the letterbox', (tester) async {
      const frame = Size(358, 320);
      LabelPoint? tapped;
      await tester
          .pumpWidget(_host(photo, const [], frame, onTap: (p) => tapped = p));
      final geo = CoverGeometry(frame, photo, fit: BoxFit.contain);
      const spot = LabelPoint(0.3, 0.7);
      await tester.tapAt(geo.toBox(spot));
      await tester.pump(const Duration(milliseconds: 500));
      expect(tapped!.x, closeTo(spot.x, 1e-6));
      expect(tapped!.y, closeTo(spot.y, 1e-6));
    });
  });

  group('#665 labels already there stay put', () {
    test('layoutPins keeps the given badges and places only the new one', () {
      const box = Size(300, 500);
      final items = [
        for (var i = 0; i < 6; i++)
          PinItem(
              _words[i],
              Offset(_anchors[i].x * box.width, _anchors[i].y * box.height),
              const Size(80, 24)),
      ];
      final first = layoutPins(items.take(5).toList(), box);
      final next = layoutPins(items, box, keep: first);
      for (final pl in first) {
        expect(next.firstWhere((x) => x.id == pl.id).badge, pl.badge);
      }
      final added = next.firstWhere((x) => x.id == items[5].id);
      for (final pl in first) {
        expect(added.badge.overlaps(pl.badge), isFalse);
      }
    });

    Map<String, Rect> badges(WidgetTester tester, Iterable<String> words) => {
          for (final w in words)
            w: tester.getRect(find
                .ancestor(of: find.text(w), matching: find.byType(WordPin))
                .first),
        };

    bool popping(WidgetTester tester, String word) => find
        .ancestor(
            of: find.text(word),
            matching: find
                .byWidgetPredicate((w) => w is TweenAnimationBuilder<double>))
        .evaluate()
        .isNotEmpty;

    testWidgets('adding a 6th label leaves the 5 where they were',
        (tester) async {
      const frame = Size(358, 520);
      final five = _words.take(5);
      await tester.pumpWidget(_host(photo, _pins(5), frame, revealNew: true));
      await tester.pump();
      final before = badges(tester, five);
      final elements = {
        for (final w in five) w: tester.element(find.text(w)),
      };

      await tester.pumpWidget(_host(photo, _pins(6), frame, revealNew: true));
      await tester.pump();
      expect(badges(tester, five), before);
      for (final w in five) {
        // Same element: not rebuilt from scratch, no pop-in animation.
        expect(tester.element(find.text(w)), same(elements[w]));
        expect(popping(tester, w), isFalse, reason: w);
      }
      // Only the new one pops in.
      expect(find.text('Curtain'), findsNothing);
      await tester.pump(const Duration(milliseconds: 200));
      expect(find.text('Curtain'), findsOneWidget);
      expect(popping(tester, 'Curtain'), isTrue);
      final added = badges(tester, ['Curtain'])['Curtain']!;
      for (final r in before.values) {
        expect(added.overlaps(r), isFalse);
      }
      await tester.pump(const Duration(seconds: 3));
      expect(badges(tester, five), before);
    });

    testWidgets('a label gone for a moment (難度 bar) comes back in place',
        (tester) async {
      const frame = Size(358, 520);
      await tester.pumpWidget(_host(photo, _pins(5), frame, revealNew: true));
      await tester.pump();
      final before = badges(tester, _words.take(5));

      await tester.pumpWidget(_host(photo, _pins(3), frame, revealNew: true));
      await tester.pump(const Duration(milliseconds: 500));
      expect(badges(tester, _words.take(3)),
          {for (final w in _words.take(3)) w: before[w]});

      await tester.pumpWidget(_host(photo, _pins(5), frame, revealNew: true));
      await tester.pump();
      // Shown at once, where it was, without popping in again.
      expect(find.text('Window'), findsOneWidget);
      expect(find.text('跳過動畫'), findsNothing);
      expect(popping(tester, 'Window'), isFalse);
      expect(badges(tester, _words.take(5)), before);
    });
  });
}
