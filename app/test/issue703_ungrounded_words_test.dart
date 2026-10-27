// 問題回報 #703 / #718, Windows 卡 #631: the tagger marks a candidate
// `pointUngrounded` when the vision model answered its default centre with
// no box for a scene word it can't place (night, city, sky…). Picture
// 9564's "city" pin sat in the middle of the photo at a wrong spot. Such a
// word — and one with no point at all — is a whole-picture word: listed,
// no pin on the photo, saved unplaced, skipped by the drag exercise. The
// catalog pictures honour the same flag.
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/screens/database_library_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

import 'helpers.dart';

WordCandidate _cand(String w, double x, {bool grounded = true}) =>
    WordCandidate(
        word: w,
        pos: 'noun',
        meaning: '$w 的意思',
        level: 'A2',
        levelSource: 'cefr-j',
        evidence: 'e',
        point: grounded ? LabelPoint(x, .5) : const LabelPoint(.5, .5),
        grounded: grounded,
        visualConfidence: .9,
        usefulness: .8);

Photo _photo() => Photo(
        id: 'p703',
        title: 'p703',
        takenAt: testNow,
        createdAt: testNow,
        networkUrl: 'http://127.0.0.1:1/x.jpg',
        width: 800,
        height: 600,
        taggingStatus: TaggingStatus.done,
        candidates: [
          _cand('street', .2),
          _cand('car', .4),
          _cand('lamp', .7),
          _cand('city', 0, grounded: false),
        ]);

void main() {
  group('parsing', () {
    List<WordCandidate> parse(List<Map<String, Object?>> items) =>
        parseCandidates({'candidates': items}, lexicon: testLexicon());

    test('pointUngrounded → ungrounded; no point → ungrounded; else grounded',
        () {
      final cs = parse([
        {
          'word': 'city',
          'pos': 'noun',
          'point': [500, 500],
          'pointUngrounded': true
        },
        {
          'word': 'night',
          'pos': 'noun',
          'point': [500, 400],
          'point_ungrounded': true
        },
        {'word': 'sky', 'pos': 'noun'},
        {
          'word': 'car',
          'pos': 'noun',
          'point': [300, 700]
        },
        {
          'word': 'lamp',
          'pos': 'noun',
          'point': [500, 500],
          'pointUngrounded': false
        },
      ]);
      final by = {for (final c in cs) c.word: c};
      expect(by['city']!.grounded, isFalse);
      expect(by['night']!.grounded, isFalse);
      expect(by['sky']!.grounded, isFalse);
      expect(by['car']!.grounded, isTrue);
      expect(by['car']!.point.x, closeTo(.3, 1e-9));
      expect(by['lamp']!.grounded, isTrue);
    });

    test('kept through toJson / fromJson; old saves stay grounded', () {
      final city = _cand('city', 0, grounded: false);
      expect(WordCandidate.fromJson(city.toJson()).grounded, isFalse);
      final car = _cand('car', .4);
      expect(car.toJson().containsKey('grounded'), isFalse);
      expect(WordCandidate.fromJson(car.toJson()).grounded, isTrue);
      // A save without a point at all is a whole-picture word too.
      final noPoint = car.toJson()..remove('point');
      expect(WordCandidate.fromJson(noPoint).grounded, isFalse);
    });
  });

  group('photo word list', () {
    WordDatabaseRepository repo() {
      final r = WordDatabaseRepository(
          clock: () => testNow,
          profile: UserVocabularyProfile.start('A2', now: testNow));
      r.addPhoto(_photo());
      return r;
    }

    test('listed without a pin, saved as an unplaced occurrence', () {
      final r = repo();
      final s = PhotoWordSession(repo: r, photoId: 'p703');
      final city = s.words.singleWhere((w) => w.word == 'city');
      expect(city.placed, isFalse);
      expect(s.words.where((w) => w.word != 'city').every((w) => w.placed),
          isTrue);
      s.save();
      final occ = {
        for (final o in r.occurrencesInPhoto('p703'))
          r.entry(o.wordEntryId)!.word: o
      };
      expect(occ['city']!.placed, isFalse);
      expect(occ['car']!.placed, isTrue);
      s.dispose();

      // Reopened: still listed, still without a pin.
      final again = PhotoWordSession(repo: r, photoId: 'p703');
      final w = again.words.singleWhere((w) => w.word == 'city');
      expect(w.placed, isFalse);
      expect(w.candidate.grounded, isFalse);
      again.dispose();
    });

    testWidgets('photo detail lists it, marks it 整張圖, draws no pin',
        (tester) async {
      final r = testRepository()..addPhoto(_photo());
      final app = await pumpApp(tester,
          initialTab: AppTab.album, repository: r, size: const Size(402, 1400));
      app.navigator.openPhoto('p703');
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('word:city')), findsOneWidget);
      expect(find.text('整張圖'), findsOneWidget);
      final pins = tester
          .widget<PinnedPhoto>(find.byType(PinnedPhoto))
          .pins
          .map((p) => p.id);
      expect(pins, isNot(contains('city')));
      expect(pins, contains('car'));
    });

    testWidgets('long-press recognition stays grounded at the pressed spot',
        (tester) async {
      // A sample photo: its picture can be cropped around the spot.
      final app = await pumpApp(
        tester,
        initialTab: AppTab.album,
        settings: AppSettings.inMemory(
            taggingUrl: 'http://predator:8765/tag', apiKey: 'k'),
        size: const Size(402, 1400),
        createTagger: (uri, key) => TaggingService(
          endpoint: uri,
          apiKey: key,
          client: MockClient((http.Request request) async => jsonResponse({
                'candidates': [
                  {
                    'word': 'teapot',
                    'pos': 'noun',
                    'meaning': '茶壺',
                    'cefr': 'B1',
                    'point': [500, 500],
                    'pointUngrounded': true,
                    'visualConfidence': 0.9,
                  }
                ],
              })),
        ),
      );
      app.navigator.openPhoto('photo-breakfast');
      await tester.pumpAndSettle();
      final photo = find.byType(PinnedPhoto).first;
      final rect = tester.getRect(photo);
      await tester.longPressAt(
          rect.topLeft + Offset(rect.width * .15, rect.height * .9));
      final choice = find.byKey(const ValueKey('spot-teapot'));
      for (var i = 0; i < 30 && choice.evaluate().isEmpty; i++) {
        await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 100)));
        await tester.pump(const Duration(milliseconds: 100));
      }
      await tester.pump(const Duration(milliseconds: 500));
      await tester.tap(choice);
      await tester.pumpAndSettle();
      final teapot = tester
          .widget<PinnedPhoto>(photo)
          .pins
          .singleWhere((p) => p.id == 'teapot');
      expect(teapot.anchor.x, closeTo(.15, .05));
      expect(teapot.anchor.y, closeTo(.9, .05));
      expect(find.text('整張圖'), findsNothing);
      await tester.pump(const Duration(seconds: 5));
    });
  });

  group('drag exercise', () {
    int drags(WordDatabaseRepository repo, {LexiconPack? lexicon}) {
      final session =
          FlashcardSession(repo, lexicon: lexicon, random: Random(1));
      var n = 0;
      while (!session.finished) {
        if (session.exercise!.type == ReviewExerciseType.imageDrag) n++;
        session.showAnswer();
        session.rate(Rating.good);
      }
      session.dispose();
      return n;
    }

    for (final cityPlaced in [true, false]) {
      test('own photo: an unplaced word is no drop spot, placed=$cityPlaced',
          () {
        final words = ['car', 'lamp', 'city'];
        final repo = WordDatabaseRepository(clock: () => testNow, entries: [
          for (final w in words)
            WordEntry.fromUserInput(
                id: w,
                word: w,
                pos: 'noun',
                meaning: '$w 的意思',
                level: 'A1',
                now: testNow)
        ], cards: [
          for (var i = 0; i < 5; i++)
            LearningCard(id: 'car-$i', wordEntryId: 'car', templateId: 't'),
        ], photos: [
          Photo(
              id: 'mine',
              title: 'street',
              takenAt: testNow,
              createdAt: testNow,
              assetPath: 'assets/photos/kitchen.jpg')
        ], occurrences: [
          for (final (i, w) in words.indexed)
            PhotoOccurrence(
                id: 'o$i',
                photoId: 'mine',
                wordEntryId: w,
                anchor: LabelPoint(.2 + .3 * i, .5),
                placed: w != 'city' || cityPlaced),
        ]);
        expect(drags(repo), cityPlaced ? greaterThan(0) : 0);
      });
    }

    for (final flagged in [false, true]) {
      test('catalog picture: a pointUngrounded label is skipped, $flagged', () {
        final lexicon = LexiconPack()
          ..loadJson({
            'target_language': 'en',
            'native_language': 'zh-TW',
            'lexemes': [
              for (final (id, name) in [(1, 'coat'), (2, 'boat'), (3, 'goat')])
                {
                  'id': id,
                  'lemma': name,
                  'normalized': name,
                  'pos': 'noun',
                  'status': 'full',
                  'senses': [
                    {'id': id * 10, 'native': '$name 的意思'}
                  ]
                },
            ],
            'catalog_images': [
              {
                'id': 1,
                'url': '/api/image?id=1',
                'status': 'ready',
                'tags': [
                  {'lexeme_id': 1, 'sense_id': 10, 'review_status': 'approved'}
                ],
                'labels': [
                  for (final id in [1, 2, 3])
                    {
                      'lexeme_id': id,
                      'point': [id * 0.2, 0.5],
                      if (id == 3 && flagged) 'point_ungrounded': true,
                    }
                ],
              }
            ],
          });
        final repo = WordDatabaseRepository(clock: () => testNow, entries: [
          for (final w in ['coat', 'boat', 'goat'])
            WordEntry.fromUserInput(
                id: w,
                word: w,
                pos: 'noun',
                meaning: '$w 的意思',
                level: 'A1',
                now: testNow)
        ], cards: [
          for (var i = 0; i < 5; i++)
            LearningCard(id: 'coat-$i', wordEntryId: 'coat', templateId: 't'),
        ])
          ..linkLexicon(lexicon);
        expect(drags(repo, lexicon: lexicon), flagged ? 0 : greaterThan(0));
      });
    }

    testWidgets('catalog picture: pointUngrounded draws no pin, reads 整張圖',
        (tester) async {
      final image = {
        'id': 9564,
        'tags': [
          {'lexeme_id': 1, 'review_status': 'approved'},
          {'lexeme_id': 2, 'review_status': 'approved'},
        ],
        'labels': [
          {
            'word': 'night',
            'point': [0.5, 0.4],
            'lexeme_id': 1,
            'pointUngrounded': true
          },
          {
            'word': 'street',
            'point': [0.3, 0.7],
            'lexeme_id': 2
          },
        ],
      };
      final pack = LexiconPack()
        ..loadJson({
          'catalog_version': 1,
          'target_language': 'en',
          'native_language': 'zh-TW',
          'lexemes': [
            for (final (id, lemma) in [(1, 'night'), (2, 'street')])
              {
                'id': id,
                'lemma': lemma,
                'normalized': lemma,
                'pos': 'noun',
                'status': 'full',
                'senses': [
                  {'id': id, 'native': '意思$id'}
                ],
              },
          ],
          'catalog_images': [image],
        });
      expect(labelPointUngrounded((image['labels'] as List)[0] as Map), isTrue);
      expect(
          labelPointUngrounded((image['labels'] as List)[1] as Map), isFalse);
      final pins = databasePins(image, pack);
      expect(pins.map((p) => p.word), ['street']);
      await pumpApp(tester,
          size: const Size(402, 1200),
          home: Scaffold(
            body: SingleChildScrollView(
                child: DatabaseTagSections(image: image, pack: pack)),
          ));
      expect(find.byKey(const ValueKey('whole-picture-1')), findsOneWidget);
      expect(find.byKey(const ValueKey('whole-picture-2')), findsNothing);
    });
  });
}
