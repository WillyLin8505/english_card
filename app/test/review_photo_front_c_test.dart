import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/photo_cache.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';
import 'helpers.dart';
import 'review_database_photos_test.dart' show image, pack, repository;

// 問題回報 #693 / #696 / #697 / #702: the review front's photos.

Map<String, dynamic> _lexeme(int id, String word, String zh) => {
      'id': id,
      'lemma': word,
      'normalized': word,
      'pos': 'noun',
      'status': 'full',
      'senses': [
        {'id': id * 10 + 1, 'native': zh, 'definition': word}
      ]
    };

/// A 2:1 picture with apple, banana and pear labelled far apart.
LexiconPack _dragPack() => LexiconPack()
  ..loadJson({
    'target_language': 'en',
    'native_language': 'zh-TW',
    'catalog_version': 1,
    'lexemes': [
      _lexeme(1, 'apple', '蘋果'),
      _lexeme(2, 'banana', '香蕉'),
      _lexeme(3, 'pear', '梨子'),
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

void main() {
  tearDown(() => LexiconPack.instance.clear());

  group('#702 bundled pack pictures', () {
    test('an assets/ picture is read from the app, a server one downloaded',
        () {
      final bundled = {
        ...image(1),
        'url': 'assets/lexicon/media/images/1.webp',
      };
      final lexicon = pack([bundled, image(2)]);
      final repo = repository(lexicon);
      final session =
          FlashcardSession(repo, lexicon: lexicon, random: Random(1));
      final byId = {for (final o in session.photoOptions) o.$1.id: o.$1};
      expect(byId['db-1']!.assetPath, 'assets/lexicon/media/images/1.webp');
      expect(byId['db-1']!.networkUrl, isNull);
      expect(byId['db-2']!.assetPath, isNull);
      expect(byId['db-2']!.networkUrl, contains('/api/image?id=2'));
      session.dispose();
    });
  });

  group('#693 swiping the back', () {
    test('a swipe updates the photo without rebuilding the review screen', () {
      final lexicon = pack([image(1), image(2)]);
      final repo = repository(lexicon);
      final session =
          FlashcardSession(repo, lexicon: lexicon, random: Random(1));
      session.showAnswer();
      var rebuilds = 0;
      final selected = <String?>[];
      session.addListener(() => rebuilds++);
      session.photoSelection
          .addListener(() => selected.add(session.photoSelection.value));
      final other =
          session.photoOptions.indexWhere((o) => o.$1.id != session.photo!.id);
      session.selectPhoto(other);
      expect(session.photo!.id, session.photoOptions[other].$1.id);
      expect(rebuilds, 0);
      expect(selected, [session.photoOptions[other].$1.id]);
      session.dispose();
      // After the run ends a late swipe callback does nothing.
      session.selectPhoto(0);
    });
  });

  group('#697 選單字題', () {
    testWidgets('the photo choice front has no target ring', (tester) async {
      final lexicon = pack([image(1)]);
      final base = repository(lexicon);
      for (final (word, meaning) in [
        ('banana', '香蕉'),
        ('pear', '梨子'),
        ('orange', '橙子')
      ]) {
        base.addWord(word: word, pos: 'noun', meaning: meaning, level: 'A1');
      }
      final repo = WordDatabaseRepository(clock: () => testNow, entries: [
        for (final e in base.entries) e.copyWith(level: () => 'A1')
      ], cards: [
        base.cardOf(base.entryByWord('apple')!.id)!
      ]);
      final session =
          FlashcardSession(repo, lexicon: lexicon, random: Random(1));
      expect(session.exercise!.type, ReviewExerciseType.photoChoice);
      expect(session.anchor, isNotNull);
      await pumpApp(tester,
          repository: repo,
          home: Scaffold(
              body: SingleChildScrollView(
                  child: FlashcardFront(
                      entry: repo.entryByWord('apple')!, session: session))));
      await tester.pump();
      expect(find.byType(PinnedPhoto), findsOneWidget);
      expect(find.byType(TargetRing), findsNothing);
      expect(find.byKey(const ValueKey('target-ring')), findsNothing);
      session.dispose();
    });
  });

  group('#696 drag question', () {
    testWidgets('drop spots sit on their labels in a photo-shaped frame',
        (tester) async {
      final lexicon = _dragPack();
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
      // The question kind rotates with the step (step 4 tries drag first);
      // the other two cards move the step on.
      for (var i = 0;
          i < 20 && session.exercise?.type != ReviewExerciseType.imageDrag;
          i++) {
        session.showAnswer();
        session.rate(Rating.good);
      }
      expect(session.exercise?.type, ReviewExerciseType.imageDrag);
      await pumpApp(tester,
          repository: repo,
          home: Scaffold(
              body: SingleChildScrollView(
                  child: SizedBox(
                      width: 400,
                      child: FlashcardFront(
                          entry: repo.entryByWord('apple')!,
                          session: session)))));
      await tester.pump();
      final photoRect = tester.getRect(find.byType(PinnedPhoto));
      // 480 × 240 shown whole: the frame is 2:1, not a cropped 4:3.
      expect(photoRect.height, closeTo(photoRect.width / 2, 0.5));
      for (final t in session.exercise!.targets) {
        final at = tester.getCenter(find.byKey(ValueKey('drop-${t.word}'))) -
            photoRect.topLeft;
        expect(at.dx, closeTo(t.anchor.x * photoRect.width, 0.5),
            reason: t.word);
        expect(at.dy, closeTo(t.anchor.y * photoRect.height, 0.5),
            reason: t.word);
      }
      session.dispose();
    });
  });

  group('#702 network photo downloads', () {
    late int fetches;
    late List<Duration> delays;
    setUp(() {
      fetches = 0;
      delays = CachedNetworkPhoto.retryDelays;
      CachedNetworkPhoto.retryDelays = const [Duration.zero, Duration.zero];
      CachedNetworkPhoto.cacheDirectory = () async => null;
    });
    tearDown(() => CachedNetworkPhoto.retryDelays = delays);

    test('two decode sizes at once share one download', () async {
      CachedNetworkPhoto.fetch = (uri) async {
        fetches++;
        await Future<void>.delayed(const Duration(milliseconds: 5));
        return Uint8List.fromList([1, 2, 3]);
      };
      const url = 'https://example.com/shared.jpg';
      final both = await Future.wait(
          [CachedNetworkPhoto.bytesFor(url), CachedNetworkPhoto.bytesFor(url)]);
      expect(fetches, 1);
      expect(both[0], both[1]);
      // Done: the next ask downloads again (no cache folder here).
      await CachedNetworkPhoto.bytesFor(url);
      expect(fetches, 2);
    });

    test('a dropped connection is tried again; a 404 is not', () async {
      CachedNetworkPhoto.fetch = (uri) async {
        fetches++;
        if (fetches < 3) throw const SocketException('reset');
        return Uint8List.fromList([4]);
      };
      expect(
          await CachedNetworkPhoto.bytesFor('https://example.com/r.jpg'), [4]);
      expect(fetches, 3);

      fetches = 0;
      CachedNetworkPhoto.fetch = (uri) async {
        fetches++;
        throw NetworkImageLoadException(statusCode: 404, uri: uri);
      };
      await expectLater(
          CachedNetworkPhoto.bytesFor('https://example.com/missing.jpg'),
          throwsA(isA<NetworkImageLoadException>()));
      expect(fetches, 1);
    });
  });
}
