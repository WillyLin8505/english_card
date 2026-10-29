import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';
import 'helpers.dart';
import 'review_database_photos_test.dart' show image, pack, repository;
import 'review_front_target_test.dart' show withApple;

// 問題回報 #849 複習：正面也要呈現藍點 — the review front shows the card
// back's blue dot on the word's spot, without the word.

const _dot = ValueKey('front-anchor-dot');

/// A photo-choice question for apple (three other A1 words as options).
FlashcardSession _choice(Map<String, dynamic> img) {
  final lexicon = pack([img]);
  final base = repository(lexicon);
  for (final (word, meaning) in [
    ('banana', '香蕉'),
    ('pear', '梨子'),
    ('orange', '橙子')
  ]) {
    base.addWord(word: word, pos: 'noun', meaning: meaning, level: 'A1');
  }
  final repo = WordDatabaseRepository(
      clock: () => testNow,
      entries: [for (final e in base.entries) e.copyWith(level: () => 'A1')],
      cards: [base.cardOf(base.entryByWord('apple')!.id)!]);
  final session = FlashcardSession(repo, lexicon: lexicon, random: Random(1));
  expect(session.exercise!.type, ReviewExerciseType.photoChoice);
  return session;
}

Future<void> _pump(WidgetTester tester, FlashcardSession session) async {
  await pumpApp(tester,
      repository: session.repo,
      home: Scaffold(
          body: SingleChildScrollView(
              child: SizedBox(
                  width: 400,
                  child: FlashcardFront(
                      entry: session.repo.entryByWord('apple')!,
                      session: session)))));
  // One frame: the network image has not failed yet.
  await tester.pump();
}

void main() {
  tearDown(() => LexiconPack.instance.clear());

  // 問題回報 #921: on a 375×667 screen the photo must not eat the screen.
  testWidgets('photo choice front: photo shrinks on a short screen',
      (tester) async {
    tester.view.physicalSize = const Size(375, 667);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final session = _choice(image(1));
    await _pump(tester, session);
    expect(tester.getSize(find.byType(PinnedPhoto)).height,
        lessThanOrEqualTo(667 * 0.3 + 0.5));
  });

  testWidgets('photo choice front: one dot on the word, no word text',
      (tester) async {
    final session = _choice(image(1));
    final anchor = session.anchor!;
    expect((anchor.x, anchor.y), (0.25, 0.4));
    await _pump(tester, session);
    expect(find.byKey(_dot), findsOneWidget);
    expect(find.byKey(const ValueKey('back-anchor-dot')), findsNothing);
    // Still no ring or box (問題回報 #697).
    expect(find.byType(TargetRing), findsNothing);
    expect(find.byKey(const ValueKey('target-box')), findsNothing);
    // The dot sits where the back puts it: the anchor through the photo's
    // cover geometry, shifted to keep the spot in view (#651).
    final photoRect = tester.getRect(find.byType(PinnedPhoto));
    final photo = session.photo!;
    final box = photoRect.size;
    final at = CoverGeometry(box, photo,
            alignment: CoverGeometry.focusing(box, photo, anchor))
        .toBox(anchor);
    final c = tester.getCenter(find.byKey(_dot)) - photoRect.topLeft;
    expect(c.dx, closeTo(at.dx, 0.5));
    expect(c.dy, closeTo(at.dy, 0.5));
    // Nothing on the photo spells the answer.
    expect(tester.widget<PinnedPhoto>(find.byType(PinnedPhoto)).pins, isEmpty);
    final onPhoto = find.descendant(
        of: find.byType(PinnedPhoto), matching: find.byType(Text));
    for (final t in tester.widgetList<Text>(onPhoto)) {
      expect(t.data?.toLowerCase(),
          isNot(anyOf(contains('apple'), contains('蘋果'))));
    }
    session.dispose();
  });

  testWidgets('photo choice front: a word with no spot has no dot',
      (tester) async {
    for (final apple in [
      {'point': <double>[]},
      // 問題回報 #703: a whole-picture (整張圖) label gives no dot either.
      {
        'point': [0.5, 0.5],
        'point_ungrounded': true
      },
    ]) {
      final session = _choice(withApple(image(1), apple));
      expect(session.photo, isNotNull);
      expect(session.anchor, isNull, reason: '$apple');
      await _pump(tester, session);
      expect(find.byType(PinnedPhoto), findsOneWidget);
      expect(find.byKey(_dot), findsNothing, reason: '$apple');
      session.dispose();
    }
  });

  testWidgets('photo recall front keeps its ring, no second dot',
      (tester) async {
    final lexicon = pack([image(1)]);
    final repo = repository(lexicon);
    final session = FlashcardSession(repo, lexicon: lexicon, random: Random(1));
    expect(session.exercise!.type, ReviewExerciseType.photoRecall);
    await _pump(tester, session);
    expect(find.byKey(const ValueKey('target-ring')), findsOneWidget);
    expect(find.byKey(_dot), findsNothing);
    session.dispose();
  });

  testWidgets('drag question: no dot (it would point at the answer)',
      (tester) async {
    Map<String, dynamic> lexeme(int id, String word, String zh) => {
          'id': id,
          'lemma': word,
          'normalized': word,
          'pos': 'noun',
          'status': 'full',
          'senses': [
            {'id': id * 10 + 1, 'native': zh, 'definition': word}
          ]
        };
    final lexicon = LexiconPack()
      ..loadJson({
        'target_language': 'en',
        'native_language': 'zh-TW',
        'catalog_version': 1,
        'lexemes': [
          lexeme(1, 'apple', '蘋果'),
          lexeme(2, 'banana', '香蕉'),
          lexeme(3, 'pear', '梨子'),
        ],
        'catalog_images': [
          {
            'id': 7,
            'url': '/api/image?id=7',
            'status': 'ready',
            'width': 480,
            'height': 240,
            'tags': [
              {'lexeme_id': 1, 'sense_id': 11, 'review_status': 'approved'}
            ],
            'labels': [
              {
                'lexeme_id': 1,
                'point': [0.05, 0.3]
              },
              {
                'lexeme_id': 2,
                'point': [0.5, 0.8]
              },
              {
                'lexeme_id': 3,
                'point': [0.9, 0.2]
              },
            ],
          }
        ],
      });
    final base = WordDatabaseRepository(clock: () => testNow);
    base.addWord(word: 'apple', pos: 'noun', meaning: '蘋果');
    base.addWord(word: 'banana', pos: 'noun', meaning: '香蕉');
    base.addWord(word: 'pear', pos: 'noun', meaning: '梨子');
    base.linkLexicon(lexicon);
    final repo = WordDatabaseRepository(
        clock: () => testNow,
        entries: base.entries,
        cards: base.eligibleCards());
    final session = FlashcardSession(repo,
        lexicon: lexicon, random: Random(1), continuous: true);
    for (var i = 0;
        i < 20 && session.exercise?.type != ReviewExerciseType.imageDrag;
        i++) {
      session.showAnswer();
      session.rate(Rating.good);
    }
    expect(session.exercise?.type, ReviewExerciseType.imageDrag);
    expect(session.anchor, isNotNull);
    await _pump(tester, session);
    expect(find.byKey(_dot), findsNothing);
    expect(find.byKey(const ValueKey('back-anchor-dot')), findsNothing);
    expect(find.byType(TargetRing), findsNothing);
    session.dispose();
  });
}
