import 'dart:math';
import 'package:flutter/services.dart';
import 'package:flutter/material.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';
import 'helpers.dart';

Map<String, dynamic> image(int id,
        {String review = 'approved', int word = 1}) =>
    {
      'id': id,
      'url': '/api/image?id=$id',
      'status': 'ready',
      'width': 400,
      'height': 300,
      'author': 'Test author',
      'license': 'CC0',
      'source': 'wikimedia_commons',
      'attribution': 'Own work',
      'tags': [
        {'lexeme_id': word, 'sense_id': 11, 'review_status': review}
      ],
      'labels': [
        {
          'lexeme_id': 2,
          'word': 'banana',
          'point': [0.7, 0.5]
        },
        {
          'lexeme_id': 1,
          'word': 'apple',
          'point': [0.25, 0.4]
        },
      ],
    };

LexiconPack pack(List<Map<String, dynamic>> images, {String target = 'en'}) =>
    LexiconPack()
      ..loadJson({
        'target_language': target,
        'native_language': 'zh-TW',
        'catalog_version': 1,
        'lexemes': [
          {
            'id': 1,
            'lemma': 'apple',
            'normalized': 'apple',
            'pos': 'noun',
            'status': 'full',
            'senses': [
              {'id': 11, 'native': '蘋果', 'definition': 'fruit'}
            ]
          }
        ],
        'catalog_images': images,
      });

WordDatabaseRepository repository(LexiconPack pack, {bool personal = false}) {
  final base = WordDatabaseRepository(clock: () => testNow);
  final word = base.addWord(word: 'apple', pos: 'noun', meaning: '蘋果');
  base.linkLexicon(pack);
  if (!personal) return base;
  return WordDatabaseRepository(
      clock: () => testNow,
      entries: base.entries,
      cards: base.eligibleCards(),
      photos: [
        Photo(
            id: 'mine',
            title: '我的照片',
            takenAt: testNow,
            createdAt: testNow,
            assetPath: 'assets/photos/kitchen.jpg')
      ],
      occurrences: [
        PhotoOccurrence(
            id: 'occ',
            photoId: 'mine',
            wordEntryId: word.id,
            anchor: const LabelPoint(0.5, 0.5))
      ]);
}

void main() {
  tearDown(() => LexiconPack.instance.clear());
  test(
      'database-only card uses approved matching photos without writing photos',
      () {
    final lexicon =
        pack([image(1), image(2, review: 'rejected'), image(3, word: 2)]);
    final repo = repository(lexicon);
    final session = FlashcardSession(repo, lexicon: lexicon, random: Random(1));
    expect(session.photo!.id, 'db-1');
    expect(session.photo!.networkUrl, contains('/api/image?id=1'));
    expect(session.anchor!.x, 0.25);
    expect(session.photoCredit, contains('Test author'));
    expect(session.photoCredit, contains('Own work'));
    expect(session.photoCredit, contains('CC0'));
    expect(session.photoCredit, isNot(contains('wikimedia_commons')));
    expect(repo.photos, isEmpty);
    expect(repo.logsOf(session.card!.id), isEmpty);
    session.dispose();
  });
  test('photo choice excludes other visible database labels', () {
    final lexicon = pack([image(1)]);
    final base = repository(lexicon);
    base.addWord(word: 'banana', pos: 'noun', meaning: '香蕉', level: 'A1');
    base.addWord(word: 'pear', pos: 'noun', meaning: '梨子', level: 'A1');
    final repo = WordDatabaseRepository(
        clock: () => testNow,
        entries: [for (final e in base.entries) e.copyWith(level: () => 'A1')],
        cards: [base.cardOf(base.entryByWord('apple')!.id)!]);
    final session = FlashcardSession(repo, lexicon: lexicon, random: Random(1));
    expect(session.photo!.id, 'db-1');
    expect(session.exercise!.type, isNot(ReviewExerciseType.photoChoice));
    expect(session.reviewed, 0);
    expect(repo.logsOf(session.card!.id), isEmpty);
    session.dispose();
  });

  test('photo choice keeps three options when safe alternatives remain', () {
    final lexicon = pack([image(1)]);
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
    expect(session.exercise!.options.toSet(), {'apple', 'pear', 'orange'});
    session.submitAnswer('pear');
    expect(session.answerCorrect, isFalse);
    expect(repo.logsOf(session.card!.id), isEmpty);
    session.dispose();
  });

  testWidgets(
      'loading image shows a loading notice and blocks answering until it resolves',
      (tester) async {
    final lexicon = pack([image(1)]);
    LexiconPack.instance.loadJson({
      'target_language': 'en',
      'native_language': 'zh-TW',
      'catalog_version': 1,
      'lexemes': [
        {
          'id': 1,
          'lemma': 'apple',
          'normalized': 'apple',
          'pos': 'noun',
          'status': 'full',
          'senses': [
            {'id': 11, 'native': '蘋果', 'definition': 'fruit'}
          ]
        }
      ],
      'catalog_images': [image(1)]
    });
    final repo = repository(lexicon);
    await pumpApp(tester, initialTab: AppTab.review, repository: repo);
    await tester.tap(find.text('開始複習'));
    // One frame, not pumpAndSettle: the network request has not resolved
    // (to success or failure) yet, so the card must still be in the
    // loading state rather than skipping straight to an error or answer.
    await tester.pump();
    expect(find.text('正在載入圖片…'), findsOneWidget);
    expect(find.text('圖片暫時無法載入'), findsNothing);
    expect(find.text('重試圖片'), findsNothing);
    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    await tester.pump();
    expect(find.byType(RatingBar), findsNothing);
    expect(find.byType(FlashcardFront), findsOneWidget);
    await tester.pumpAndSettle();
    expect(repo.logsOf(repo.cardOf(repo.entries.single.id)!.id), isEmpty);
  });

  testWidgets('failed required image cannot reveal and grade a photo question',
      (tester) async {
    final lexicon = pack([image(1)]);
    LexiconPack.instance.loadJson({
      'target_language': 'en',
      'native_language': 'zh-TW',
      'catalog_version': 1,
      'lexemes': [
        {
          'id': 1,
          'lemma': 'apple',
          'normalized': 'apple',
          'pos': 'noun',
          'status': 'full',
          'senses': [
            {'id': 11, 'native': '蘋果', 'definition': 'fruit'}
          ]
        }
      ],
      'catalog_images': [image(1)]
    });
    final repo = repository(lexicon);
    await pumpApp(tester, initialTab: AppTab.review, repository: repo);
    await tester.tap(find.text('開始複習'));
    await tester.pumpAndSettle();
    expect(find.text('圖片暫時無法載入'), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    await tester.pumpAndSettle();
    expect(find.byType(RatingBar), findsNothing);
    expect(find.byType(FlashcardFront), findsOneWidget);
    expect(repo.logsOf(repo.cardOf(repo.entries.single.id)!.id), isEmpty);
  });

  test('rendered image guard blocks all answer paths and ignores stale retries',
      () {
    final lexicon = pack([image(1)]);
    final repo = repository(lexicon);
    final session = FlashcardSession(repo, lexicon: lexicon);
    session.guardPhoto();
    final old = session.photoAttempt;
    session.showAnswer();
    session.submitAnswer('apple');
    session.completeInteraction(correct: true, attempts: 1);
    expect(session.showingBack, isFalse);
    expect(session.attempts, 0);
    expect(repo.logsOf(session.card!.id), isEmpty);
    session.reportPhotoState(old, false);
    expect(session.photoFailed, isTrue);
    session.retryPhoto();
    session.reportPhotoState(old, true);
    expect(session.canAnswer, isFalse);
    session.reportPhotoState(session.photoAttempt, true);
    expect(session.canAnswer, isTrue);
    final readyAttempt = session.photoAttempt;
    session.showAnswer();
    session.rate(Rating.again);
    session.guardPhoto();
    session.reportPhotoState(readyAttempt, true);
    expect(session.canAnswer, isFalse);
    expect(repo.logsOf(session.card!.id).single.rating, Rating.again);
    session.dispose();
    session.reportPhotoState(session.photoAttempt, true);
    expect(session.canAnswer, isFalse);
  });

  test('personal and database photos rotate without immediate repeats', () {
    final lexicon = pack([image(1), image(2)]);
    final repo = repository(lexicon, personal: true);
    final session = FlashcardSession(repo, lexicon: lexicon, random: Random(2));
    final seen = <String>[];
    while (!session.finished) {
      seen.add(session.photo!.id);
      session.showAnswer();
      session.rate(Rating.again);
    }
    expect(seen.toSet(), {'mine', 'db-1', 'db-2'});
    expect(repo.photos, hasLength(1));
    session.dispose();
  });
  test(
      'unapproved, failed and missing photos cannot create a photo-only exercise',
      () {
    final broken = image(3)..['status'] = 'failed';
    final lexicon =
        pack([image(1, review: 'pending'), image(2, word: 2), broken]);
    final session = FlashcardSession(repository(lexicon), lexicon: lexicon);
    expect(session.photo, isNull);
    expect(session.anchor, isNull);
    expect(session.photoCredit, isNull);
    // No safe exercise falls back to the traditional flip card rather than
    // skipping the card (問題回報 #207 decision A).
    expect(session.finished, isFalse);
    expect(session.exercise, isNull);
    session.dispose();
  });
  testWidgets(
      'back displays only target pin (no credits) and load fallback independently of the front',
      (tester) async {
    final lexicon = pack([image(1)]);
    LexiconPack.instance.loadJson({
      'target_language': 'en',
      'native_language': 'zh-TW',
      'catalog_version': 1,
      'lexemes': [
        {
          'id': 1,
          'lemma': 'apple',
          'normalized': 'apple',
          'pos': 'noun',
          'status': 'full',
          'senses': [
            {'id': 11, 'native': '蘋果', 'definition': 'fruit'}
          ]
        }
      ],
      'catalog_images': [image(1)],
    });
    final repo = repository(lexicon);
    final session = FlashcardSession(repo, lexicon: lexicon);
    await pumpApp(tester,
        repository: repo,
        home: Scaffold(
            body: SingleChildScrollView(
                child: FlashcardBack(
                    entry: repo.entries.single,
                    card: session.card!,
                    photo: session.photo,
                    anchor: session.anchor,
                    photoCredit: session.photoCredit,
                    template: repo.template,
                    learnerLevel: 'A1',
                    onPlay: () {},
                    onOpen: () {}))));
    await tester.pumpAndSettle();
    expect(find.byType(PinnedPhoto), findsOneWidget);
    session.dispose();
    final view = tester.widget<PinnedPhoto>(find.byType(PinnedPhoto));
    // Card #251 item 3: no word label over the photo, no 「照片情境」 title.
    expect(view.pins, isEmpty);
    expect(find.text('照片情境'), findsNothing);
    expect(find.textContaining('Test author'), findsNothing);
    expect(find.textContaining('Own work'), findsNothing);
    expect(find.textContaining('CC0'), findsNothing);
    expect(find.text('圖片暫時無法載入，稍後再試'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('long-press photo shows attribution dialog, not on the card back',
      (tester) async {
    final lexicon = pack([image(1)]);
    LexiconPack.instance.loadJson({
      'target_language': 'en',
      'native_language': 'zh-TW',
      'catalog_version': 1,
      'lexemes': [
        {
          'id': 1,
          'lemma': 'apple',
          'normalized': 'apple',
          'pos': 'noun',
          'status': 'full',
          'senses': [
            {'id': 11, 'native': '蘋果', 'definition': 'fruit'}
          ]
        }
      ],
      'catalog_images': [image(1)],
    });
    final repo = repository(lexicon);
    final session = FlashcardSession(repo, lexicon: lexicon);
    await pumpApp(tester,
        repository: repo,
        home: Scaffold(
            body: SingleChildScrollView(
                child: FlashcardBack(
                    entry: repo.entries.single,
                    card: session.card!,
                    photo: session.photo,
                    anchor: session.anchor,
                    photoCredit: session.photoCredit,
                    template: repo.template,
                    learnerLevel: 'A1',
                    onPlay: () {},
                    onOpen: () {}))));
    await tester.pumpAndSettle();
    expect(find.textContaining('Test author'), findsNothing);
    await tester.longPress(find.byType(PinnedPhoto));
    await tester.pumpAndSettle();
    expect(find.text('圖片來源'), findsOneWidget);
    expect(find.textContaining('Test author'), findsOneWidget);
    expect(find.textContaining('CC0'), findsOneWidget);
    await tester.tap(find.text('關閉'));
    await tester.pumpAndSettle();
    expect(find.text('圖片來源'), findsNothing);
    session.dispose();
  });

  testWidgets(
      '看圖選單字 back marks the target word\'s position in the photo',
      (tester) async {
    final lexicon = pack([image(1)]);
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
    expect(session.exercise!.type, ReviewExerciseType.photoChoice,
        reason: '這組資料只能產生看圖選單字題');
    expect(session.anchor, isNotNull);
    await pumpApp(tester,
        repository: repo,
        home: Scaffold(
            body: SingleChildScrollView(
                child: FlashcardBack(
                    entry: repo.entryByWord('apple')!,
                    card: session.card!,
                    photo: session.photo,
                    anchor: session.anchor,
                    photoCredit: session.photoCredit,
                    template: repo.template,
                    learnerLevel: 'A1',
                    onPlay: () {},
                    onOpen: () {}))));
    await tester.pumpAndSettle();
    session.dispose();
    expect(find.byType(PinnedPhoto), findsOneWidget);
    final view = tester.widget<PinnedPhoto>(find.byType(PinnedPhoto));
    // Card #251 item 3: a dot marks the word's spot, with no word label.
    expect(view.pins, isEmpty, reason: '背面照片上不疊單字標籤');
    expect(find.byKey(const ValueKey('back-anchor-dot')), findsOneWidget,
        reason: '背面仍標出正確單字在圖片中的位置');
    expect((session.anchor!.x, session.anchor!.y), (0.25, 0.4));
  });

  testWidgets(
      '母語說明＋照片 back marks the target word\'s position in the photo',
      (tester) async {
    final lexicon = pack([image(1)]);
    final repo = repository(lexicon);
    final session = FlashcardSession(repo, lexicon: lexicon, random: Random(1));
    expect(session.exercise!.type, ReviewExerciseType.photoRecall,
        reason: '只有一個單字、沒有例句、沒有相關詞，只能產生母語說明＋照片題');
    expect(session.anchor, isNotNull);
    await pumpApp(tester,
        repository: repo,
        home: Scaffold(
            body: SingleChildScrollView(
                child: FlashcardBack(
                    entry: repo.entryByWord('apple')!,
                    card: session.card!,
                    photo: session.photo,
                    anchor: session.anchor,
                    photoCredit: session.photoCredit,
                    template: repo.template,
                    learnerLevel: 'A1',
                    onPlay: () {},
                    onOpen: () {}))));
    await tester.pumpAndSettle();
    session.dispose();
    expect(find.byType(PinnedPhoto), findsOneWidget);
    final view = tester.widget<PinnedPhoto>(find.byType(PinnedPhoto));
    expect(view.pins, isEmpty, reason: '背面照片上不疊單字標籤');
    expect(find.byKey(const ValueKey('back-anchor-dot')), findsOneWidget,
        reason: '背面仍標出正確單字在圖片中的位置');
    expect((session.anchor!.x, session.anchor!.y), (0.25, 0.4));
  });
}
