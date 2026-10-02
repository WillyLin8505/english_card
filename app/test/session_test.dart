import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/photo_intake.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/photo_word_session.dart';
import 'package:photo_english_app/services/tagging_queue.dart';
import 'package:photo_english_app/services/tagging_service.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_enricher.dart';
import 'package:photo_english_app/services/word_selector.dart';

import 'helpers.dart';

/// The breakfast photo as if just tagged: its pool, nothing saved yet.
WordDatabaseRepository freshBreakfast() {
  final repo = testRepository();
  final p = repo.photo('photo-breakfast')!;
  repo.savePhotoWords(p.id, const [],
      difficultyOffset: 0); // drop the mock's labels
  repo.updatePhoto(Photo(
    id: p.id,
    albumId: p.albumId,
    title: p.title,
    takenAt: p.takenAt,
    assetPath: p.assetPath,
    width: p.width,
    height: p.height,
    createdAt: p.createdAt,
    taggingStatus: TaggingStatus.done,
    candidates: p.candidates,
  ));
  return repo;
}

void main() {
  group('PhotoWordSession (照片選詞)', () {
    test('legacy photo overflow becomes context-only without deleting cards',
        () {
      final entries = [
        for (var i = 0; i < 8; i++)
          WordEntry(
            id: 'w$i',
            word: 'word$i',
            pos: 'noun',
            meaning: '詞$i',
            createdAt: testNow,
            updatedAt: testNow,
          ),
      ];
      final repo = WordDatabaseRepository(
        entries: entries,
        photos: [
          Photo(
            id: 'legacy',
            title: '舊照片',
            takenAt: testNow,
            createdAt: testNow,
            wordsSavedAt: testNow,
          ),
        ],
        occurrences: [
          for (var i = 0; i < 8; i++)
            PhotoOccurrence(
              id: 'o$i',
              photoId: 'legacy',
              wordEntryId: 'w$i',
              anchor: LabelPoint((i + 1) / 10, 0.5),
            ),
        ],
        cards: [
          for (var i = 0; i < 8; i++)
            LearningCard(id: 'c$i', wordEntryId: 'w$i', templateId: 't'),
        ],
        clock: () => testNow,
      );

      final session = PhotoWordSession(repo: repo, photoId: 'legacy');
      expect(session.words, hasLength(WordSelector.maxWords));
      expect(repo.occurrencesInPhoto('legacy'), hasLength(8));
      expect(repo.occurrencesInPhoto('legacy').where((o) => o.contextOnly),
          hasLength(3));
      expect(repo.visibleLabels('legacy'), hasLength(WordSelector.maxWords),
          reason: 'context-only words are retained but are not drawn as pins');
      expect(repo.cardCount, 8,
          reason: 'overflow keeps its card and FSRS state');
    });

    test('a fresh photo: up to five new words, none already studied', () {
      final repo = freshBreakfast();
      final s = PhotoWordSession(repo: repo, photoId: 'photo-breakfast');
      final words = s.words.map((w) => w.word).toList();
      expect(words.length, inInclusiveRange(2, 5));
      expect(words.where((w) => repo.studyingWords.contains(w)), isEmpty,
          reason: 'coffee, apple… are studied from other photos');
      expect(s.target, repo.profile.level);
      expect(s.hasUnsavedChanges, isTrue);
      // Nothing is created until the page is left.
      expect(repo.entryByWord(words.first), isNull);
    });

    test('the dial re-picks live; ☆ keeps a word; save stores the offset', () {
      final repo = freshBreakfast();
      final s = PhotoWordSession(repo: repo, photoId: 'photo-breakfast');
      final starred = s.words.first;
      s.toggleStar(starred);
      s.setTarget(4, live: true);
      expect(s.words, contains(starred));
      expect(s.targetLevel, 'C1');
      final saved = s.save();
      expect(saved.photoRemoved, isFalse);
      expect(repo.photo('photo-breakfast')!.difficultyOffset,
          4 - repo.profile.level);
      expect(repo.entryByWord(starred.word), isNotNull);
      expect(saved.created.map((e) => e.word),
          containsAll(s.words.map((w) => w.word)));
    });

    test('swipe left → 已學會 and the next word fills in; restore brings it back',
        () {
      final repo = freshBreakfast();
      final s = PhotoWordSession(repo: repo, photoId: 'photo-breakfast');
      final first = s.words.first;
      final count = s.words.length;
      s.swipe(first);
      expect(s.words.map((w) => w.word), isNot(contains(first.word)));
      expect(s.words.length, count, reason: 'refilled from the pool');
      expect(repo.profile.learned, contains(first.word));
      s.setShowLearned(true);
      final old = s.oldWords.firstWhere((o) => o.word == first.word);
      expect(old.learned, isTrue);
      expect(s.oldWords.any((o) => o.word == 'coffee' && !o.learned), isTrue,
          reason: 'studied from another photo');
      s.restore(old);
      expect(s.words.map((w) => w.word), contains(first.word));
      expect(repo.profile.learned, isNot(contains(first.word)));
    });

    test(
        'a saved photo reopens with its saved words; archived ones stay hidden',
        () {
      final repo = testRepository();
      final s = PhotoWordSession(repo: repo, photoId: 'photo-kitchen');
      expect(s.words.map((w) => w.word),
          ['bread', 'cutting board', 'apple', 'coffee', 'knife']);
      expect(s.hasUnsavedChanges, isFalse);
      s.swipe(s.words.firstWhere((w) => w.word == 'knife'));
      expect(repo.isArchived(repo.entryByWord('knife')!.id), isTrue);
      s.save();
      final again = PhotoWordSession(repo: repo, photoId: 'photo-kitchen');
      expect(again.words.map((w) => w.word), isNot(contains('knife')));
      expect(repo.occurrencesInPhoto('photo-kitchen').length,
          greaterThanOrEqualTo(5),
          reason: 'the archived occurrence is kept for 顯示已學會單字');
    });

    test('dragging and correcting a label are saved with the AI word kept', () {
      final repo = testRepository();
      final s = PhotoWordSession(repo: repo, photoId: 'photo-kitchen');
      final bread = s.words.firstWhere((w) => w.word == 'bread');
      s.move(bread, const LabelPoint(0.1, 0.9));
      s.correct(bread, word: 'toast', meaning: '吐司', level: 'A2');
      s.save();
      final toast = repo.entryByWord('toast')!;
      final occ = repo
          .occurrencesInPhoto('photo-kitchen')
          .firstWhere((o) => o.wordEntryId == toast.id);
      expect((occ.anchor.x, occ.anchor.y), (0.1, 0.9));
      expect(occ.aiLabel, 'bread');
      expect(occ.userEdited, isTrue);
    });

    test('removing every word takes the photo out of the album', () {
      final repo = testRepository();
      final s = PhotoWordSession(repo: repo, photoId: 'photo-cafe');
      while (s.words.isNotEmpty) {
        s.swipe(s.words.first);
      }
      expect(s.save().photoRemoved, isTrue);
      expect(repo.photo('photo-cafe'), isNull);
    });

    test('a photo still waiting for the tagger isn\'t saved empty', () {
      final repo = testRepository();
      repo.addPhoto(Photo(
        id: 'p-new',
        title: '新照片',
        takenAt: testNow,
        storedKey: 'p-new',
        createdAt: testNow,
        taggingStatus: TaggingStatus.pending,
      ));
      final s = PhotoWordSession(repo: repo, photoId: 'p-new');
      expect(s.words, isEmpty);
      s.save();
      expect(repo.photo('p-new')!.wordsSavedAt, isNull);
    });

    test('更多描述 re-picks toward adjectives', () {
      final repo = freshBreakfast();
      final s = PhotoWordSession(repo: repo, photoId: 'photo-breakfast');
      s.setBias(PosBias.descriptions);
      expect(s.bias, PosBias.descriptions);
      expect(s.words.any((w) => w.candidate.isDescription), isTrue);
      s.setBias(PosBias.descriptions);
      expect(s.bias, PosBias.none);
    });
  });

  group('FlashcardSession (連續卡流)', () {
    test('runs until nothing is due; Again comes back later in the run', () {
      final repo = testRepository();
      final session = FlashcardSession(repo, random: math.Random(1));
      final eligible = repo.eligibleCards().length;
      String? again;
      var shown = 0;
      final seen = <String>[];
      while (!session.finished && shown < 100) {
        final id = session.card!.id;
        seen.add(id);
        session.showAnswer();
        if (shown == 0) {
          again = id;
          session.rate(Rating.again);
        } else {
          session.rate(Rating.good);
        }
        shown++;
      }
      expect(session.finished, isTrue);
      expect(shown, eligible + 1,
          reason: 'every card once, the Again card twice');
      final firstAgain = seen.indexOf(again!);
      final second = seen.lastIndexOf(again);
      expect(
          second - firstAgain, greaterThanOrEqualTo(FlashcardSession.againGap));
      expect(repo.logsOf(again), hasLength(2));
      expect(repo.eligibleCards(), isEmpty);
    });

    test('a card answered Again forever only repeats twice in one run', () {
      final repo = testRepository();
      final session = FlashcardSession(repo, random: math.Random(3));
      final alwaysForgotten = session.card!.id;
      var appearances = 0;
      var steps = 0;

      while (!session.finished && steps < 200) {
        final id = session.card!.id;
        if (id == alwaysForgotten) appearances++;
        session.showAnswer();
        session.rate(id == alwaysForgotten ? Rating.again : Rating.good);
        steps++;
      }

      expect(session.finished, isTrue);
      expect(appearances, 1 + FlashcardSession.maxAgainRepeats);
      expect(repo.logsOf(alwaysForgotten),
          hasLength(1 + FlashcardSession.maxAgainRepeats));
    });

    test(
        'rating needs the answer shown; the back shows one of the word\'s photos',
        () {
      final repo = testRepository();
      final session = FlashcardSession(repo, random: math.Random(2));
      final id = session.card!.id;
      session.rate(Rating.good);
      expect(repo.logsOf(id), isEmpty);
      final word = repo.card(id)!.wordEntryId;
      final photos =
          repo.photosOfWord(word).where((p) => p.hasImage).map((p) => p.id);
      if (photos.isNotEmpty) expect(photos, contains(session.photo!.id));
    });
  });

  group('TaggingQueue (待處理佇列)', () {
    TaggingQueue queueFor(
        WordDatabaseRepository repo, AppSettings settings, MockClient client) {
      final intake = PhotoIntake(
        repository: () => repo,
        photoStore: PhotoStore.inMemory(),
        createTagger: (uri, key) =>
            TaggingService(endpoint: uri, apiKey: key, client: client),
      );
      return TaggingQueue(
          repository: () => repo,
          settings: settings,
          intake: intake,
          lexicon: testLexicon);
    }

    Photo waiting(WordDatabaseRepository repo) {
      final base = repo.photo('photo-kitchen')!;
      final p = Photo(
        id: 'p-queued',
        title: '排隊中',
        takenAt: testNow,
        assetPath: base.assetPath,
        createdAt: testNow,
        taggingStatus: TaggingStatus.pending,
      );
      repo.addPhoto(p);
      return p;
    }

    testWidgets('offline → stays pending with the reason; online → candidates',
        (tester) async {
      final repo = testRepository();
      final settings = AppSettings.inMemory(
          taggingUrl: 'http://127.0.0.1:8765/tag', apiKey: 'k');
      var online = false;
      late http.Request seen;
      final queue = queueFor(repo, settings, MockClient((r) async {
        if (!online) throw http.ClientException('Connection refused');
        seen = r;
        return jsonResponse({
          'candidates': [
            {
              'word': 'toast',
              'pos': 'noun',
              'meaning': '吐司',
              'cefr': 'A1',
              'point': [0.4, 0.6]
            },
          ],
        });
      }));
      final p = waiting(repo);
      await tester.runAsync(queue.process);
      expect(repo.photo(p.id)!.taggingStatus, TaggingStatus.pending);
      expect(repo.photo(p.id)!.taggingError, contains('連不到'));
      expect(repo.photo(p.id)!.awaitingTagging, isTrue);
      expect(queue.offline, isTrue);

      online = true;
      await tester.runAsync(queue.process);
      final done = repo.photo(p.id)!;
      expect(done.taggingStatus, TaggingStatus.done);
      expect(done.candidates.single.word, 'toast');
      expect(seen.headers['X-API-Key'], 'k');
      expect(seen.url.queryParameters, containsPair('native', 'zh-TW'));
      expect(seen.url.queryParameters['level'], repo.profile.cefr);
    });

    testWidgets('a wrong key fails the photo; top-up asks once per focus',
        (tester) async {
      final repo = testRepository();
      final settings =
          AppSettings.inMemory(taggingUrl: 'http://x/tag', apiKey: 'bad');
      var calls = 0;
      final queue = queueFor(repo, settings, MockClient((r) async {
        calls++;
        if (r.headers['X-API-Key'] == 'bad') {
          return jsonResponse({'error': 'key'}, 401);
        }
        expect(r.url.queryParameters['focus'], 'harder');
        expect(r.url.queryParameters['exclude'], contains('coffee'));
        return jsonResponse({
          'candidates': [
            {
              'word': 'stoneware',
              'pos': 'noun',
              'meaning': '石器',
              'cefr': 'C1',
              'point': [0.5, 0.4]
            },
          ],
        });
      }));
      final p = waiting(repo);
      await tester.runAsync(queue.process);
      expect(repo.photo(p.id)!.taggingStatus, TaggingStatus.failed);
      expect(repo.photo(p.id)!.taggingError, contains('API Key'));

      settings.apiKey = 'good';
      final added = await tester.runAsync(
          () => queue.topUp('photo-kitchen', focus: 'harder', level: 'C1'));
      expect(added, 1);
      expect(repo.photo('photo-kitchen')!.candidates.last.focus, 'harder');
      final before = calls;
      await tester.runAsync(
          () => queue.topUp('photo-kitchen', focus: 'harder', level: 'C1'));
      expect(calls, before, reason: 'each focus once');
    });
  });

  group('WordEnricher (背景補資料)', () {
    testWidgets(
        'uses local IPA, never asks the photo model for dictionary fields',
        (tester) async {
      final repo = testRepository();
      final settings =
          AppSettings.inMemory(taggingUrl: 'http://x/tag', apiKey: 'k');
      var calls = 0;
      final intake = PhotoIntake(
        repository: () => repo,
        photoStore: PhotoStore.inMemory(),
        createTagger: (uri, key) => TaggingService(
          endpoint: uri,
          apiKey: key,
          client: MockClient((r) async {
            calls++;
            return jsonResponse({});
          }),
        ),
      );
      final enricher = WordEnricher(
          repository: () => repo,
          settings: settings,
          intake: intake,
          lexicon: testLexicon);
      final e = repo.addWord(word: 'mug', pos: 'noun', meaning: '杯子');
      repo.editEntry(e.copyWith(meaning: '我的杯子'), {WordField.meaning});
      await tester.runAsync(enricher.process);

      final after = repo.entry(e.id)!;
      expect(after.dataStatus, WordDataStatus.failed);
      expect(after.meaning, '我的杯子', reason: 'user edit wins');
      expect(after.definition, isNull);
      expect((after.ipa, after.ipaSource), ('/mʌɡ/', 'cmudict'),
          reason: 'local IPA first');
      expect(after.examples, isEmpty);
      expect(after.dataError, contains('離線字庫缺少'));
      expect(calls, 0);
    });

    testWidgets('without the AI service the word is marked failed',
        (tester) async {
      final repo = testRepository();
      final settings = AppSettings.inMemory();
      final intake = PhotoIntake(
          repository: () => repo, photoStore: PhotoStore.inMemory());
      final enricher = WordEnricher(
          repository: () => repo,
          settings: settings,
          intake: intake,
          lexicon: testLexicon);
      final e = repo.addWord(word: 'window', pos: 'noun', meaning: '窗戶');
      await tester.runAsync(enricher.process);
      final after = repo.entry(e.id)!;
      expect(after.dataStatus, WordDataStatus.failed);
      expect(after.ipa, '/ˈwɪndoʊ/', reason: 'local CMUdict IPA still applied');
      expect(after.dataError, contains('離線字庫缺少'));
    });
  });
}
