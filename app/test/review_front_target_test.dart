import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';
import 'helpers.dart';
import 'review_database_photos_test.dart' show image, pack, repository;

/// Card #253: the review front marks where the word is in the photo — a
/// ring (and the tagger's box when it has one) — without any word.
Map<String, dynamic> withApple(Map<String, dynamic> img, Map<String, dynamic> apple) =>
    {
      ...img,
      'labels': [
        for (final l in img['labels'] as List)
          if ((l as Map)['lexeme_id'] != 1) l,
        {'lexeme_id': 1, 'word': 'apple', ...apple},
      ],
    };

Photo photo(int w, int h) => Photo(
    id: 'p',
    title: '',
    takenAt: testNow,
    createdAt: testNow,
    networkUrl: 'http://127.0.0.1:1/x.jpg',
    width: w,
    height: h);

Future<FlashcardSession> pumpFront(
    WidgetTester tester, Map<String, dynamic> img) async {
  final lexicon = pack([img]);
  final repo = repository(lexicon);
  final session = FlashcardSession(repo, lexicon: lexicon, random: Random(1));
  expect(session.exercise!.type, ReviewExerciseType.photoRecall);
  await pumpApp(tester,
      repository: repo,
      home: Scaffold(
          body: SingleChildScrollView(
              child: FlashcardFront(
                  entry: repo.entryByWord('apple')!, session: session))));
  // One frame: the network image has not failed yet.
  await tester.pump();
  return session;
}

void main() {
  tearDown(() => LexiconPack.instance.clear());

  group('TargetRing maps the anchor through BoxFit.cover', () {
    Future<Offset> ringCenter(
        WidgetTester tester, Photo p, Size box, LabelPoint at) async {
      await pumpApp(tester,
          home: Center(
              child: SizedBox(
                  key: const ValueKey('box'),
                  width: box.width,
                  height: box.height,
                  child: TargetRing(photo: p, anchor: at))));
      final origin = tester.getTopLeft(find.byKey(const ValueKey('box')));
      return tester.getCenter(find.byKey(const ValueKey('target-ring'))) -
          origin;
    }

    testWidgets('landscape photo in a square box (sides cropped)',
        (tester) async {
      // 400×300 in 200×200: scale 2/3 → 266.7×200, shifted −33.3 px.
      final c = await ringCenter(tester, photo(400, 300), const Size(200, 200),
          const LabelPoint(0.25, 0.4));
      expect(c.dx, closeTo(-100 / 3 + 400 * 0.25 * 2 / 3, 0.01));
      expect(c.dy, closeTo(80, 0.01));
    });

    testWidgets('portrait photo in a wide box (top and bottom cropped)',
        (tester) async {
      // 300×400 in 300×200: scale 1 → 300×400, shifted −100 px.
      final c = await ringCenter(tester, photo(300, 400), const Size(300, 200),
          const LabelPoint(0.25, 0.4));
      expect(c.dx, closeTo(75, 0.01));
      expect(c.dy, closeTo(60, 0.01));
    });

    testWidgets('box outline lands on the box corners', (tester) async {
      await pumpApp(tester,
          home: Center(
              child: SizedBox(
                  key: const ValueKey('box'),
                  width: 300,
                  height: 200,
                  child: TargetRing(
                      photo: photo(300, 400),
                      anchor: const LabelPoint(0.5, 0.5),
                      box: const Rect.fromLTRB(0.2, 0.4, 0.6, 0.6)))));
      final origin = tester.getTopLeft(find.byKey(const ValueKey('box')));
      final r = tester.getRect(find.byKey(const ValueKey('target-box')));
      expect(r.topLeft - origin, const Offset(60, 60));
      expect(r.bottomRight - origin, const Offset(180, 140));
    });
  });

  testWidgets('front with coordinates shows the ring and no word',
      (tester) async {
    final session = await pumpFront(tester, image(1));
    expect(session.box, isNull, reason: '這張圖只有點，沒有框');
    expect(find.byType(TargetRing), findsOneWidget);
    expect(find.byKey(const ValueKey('target-ring')), findsOneWidget);
    expect(find.byKey(const ValueKey('target-box')), findsNothing);
    final ring = tester.widget<TargetRing>(find.byType(TargetRing));
    expect((ring.anchor.x, ring.anchor.y), (0.25, 0.4));
    // Nothing on the photo spells the answer (or another label).
    final onPhoto = find.descendant(
        of: find.byType(PinnedPhoto), matching: find.byType(Text));
    for (final t in tester.widgetList<Text>(onPhoto)) {
      expect(t.data?.toLowerCase(), isNot(anyOf(contains('apple'),
          contains('banana'), contains('蘋果'))));
    }
    expect(tester.widget<PinnedPhoto>(find.byType(PinnedPhoto)).pins, isEmpty);
    session.dispose();
  });

  testWidgets('front draws the tagger box when it has a real one',
      (tester) async {
    final session = await pumpFront(
        tester,
        withApple(image(1), {
          'point': [0.5, 0.5],
          'box': [0.1, 0.2, 0.5, 0.6]
        }));
    // "Middle of the picture" + a box → the box's middle.
    expect(session.anchor!.x, closeTo(0.3, 1e-9));
    expect(session.anchor!.y, closeTo(0.4, 1e-9));
    expect(session.box, const Rect.fromLTRB(0.1, 0.2, 0.5, 0.6));
    expect(find.byKey(const ValueKey('target-box')), findsOneWidget);
    session.dispose();
  });

  test('a whole-picture box, or one the dot is outside, is not drawn', () {
    for (final apple in [
      {
        'point': [0.4, 0.4],
        'box': [0.0, 0.0, 1.0, 0.98]
      },
      {
        'point': [0.5, 0.3],
        'box': [0.46, 0.46, 0.71, 0.82]
      },
    ]) {
      final lexicon = pack([withApple(image(1), apple)]);
      final session = FlashcardSession(repository(lexicon),
          lexicon: lexicon, random: Random(1));
      expect(session.anchor, isNotNull);
      expect(session.box, isNull, reason: '$apple');
      session.dispose();
    }
  });

  testWidgets('front without coordinates shows no mark', (tester) async {
    final session = await pumpFront(
        tester, withApple(image(1), {'point': <double>[]}));
    expect(session.photo, isNotNull);
    expect(session.anchor, isNull);
    expect(find.byType(PinnedPhoto), findsOneWidget);
    expect(find.byType(TargetRing), findsNothing);
    session.dispose();
  });
}
