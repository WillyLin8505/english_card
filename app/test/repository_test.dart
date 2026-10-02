import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/models/word_detail.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/word_database_query.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

WordCandidate cand(String word,
        {String pos = 'noun', String level = 'A2', String meaning = ''}) =>
    WordCandidate(
      word: word,
      pos: pos,
      meaning: meaning.isEmpty ? '$word 的意思' : meaning,
      level: level,
      levelSource: 'cefr-j',
      evidence: '$word in the photo',
      point: const LabelPoint(0.3, 0.4),
      visualConfidence: 0.9,
    );

ListedWord listed(String word, {double x = 0.3}) =>
    ListedWord(cand(word), LabelPoint(x, 0.4));

void main() {
  late WordDatabaseRepository repo;

  setUp(() => repo = testRepository());

  List<String> words([WordDatabaseFilter f = const WordDatabaseFilter()]) =>
      [for (final r in repo.query(f)) r.entry.word];

  group('sample data', () {
    test('one card per word; at most five words per photo', () {
      expect(repo.wordCount, 21);
      expect(repo.cardCount, 21);
      for (final e in repo.entries) {
        expect(repo.cardOf(e.id), isNotNull, reason: e.word);
      }
      for (final p in repo.photos) {
        expect(repo.occurrencesInPhoto(p.id).length, lessThanOrEqualTo(5),
            reason: p.title);
      }
      // coffee is on three photos but has one card and one FSRS state.
      final coffee = repo.entryByWord('coffee')!;
      expect(repo.photosOfWord(coffee.id).map((p) => p.title),
          ['廚房早晨', '早餐桌', '咖啡館二樓']);
    });

    test('the sample photos carry candidate pools with corrected levels', () {
      final pool = repo.photo('photo-breakfast')!.candidates;
      expect(pool.length, greaterThan(15));
      final mug = pool.firstWhere((c) => c.word == 'mug');
      expect(
          (mug.level, mug.levelSource, mug.modelLevel), ('A2', 'cefr-j', 'A1'));
      expect(pool.map((c) => c.word),
          containsAll(['espresso', 'croissant', 'rustic']));
      expect(repo.photo('photo-kitchen')!.wordsSavedAt, isNotNull);
    });

    test('word list: alphabetical by default, statuses', () {
      expect(words().take(8), [
        'apple',
        'balcony',
        'bread',
        'breeze',
        'brick',
        'coffee',
        'cutting board',
        'dappled'
      ]);
      final rows = {
        for (final r in repo.query(const WordDatabaseFilter())) r.entry.word: r
      };
      expect(rows['balcony']!.status, StudyStatus.learning);
      expect(rows['potted']!.status, StudyStatus.stable);
      expect(rows['apple']!.status, StudyStatus.newWord);
      expect(rows['balcony']!.photoCount, 6);
      expect(words(const WordDatabaseFilter(sort: SortOrder.nextDue)).take(2),
          ['balcony', 'railing']);
      expect(
          words(const WordDatabaseFilter(search: '陽台')), contains('balcony'));
      expect(words(const WordDatabaseFilter(level: 'B2')),
          ['overlook', 'veranda']);
    });
  });

  group('saving a photo\'s list (自動保存)', () {
    test('new words get entry + occurrence + card; known words only a context',
        () {
      final before = repo.wordCount;
      final plate = repo.entryByWord('plate')!;
      final created = repo.savePhotoWords(
        'photo-breakfast',
        [listed('mug'), listed('saucer'), listed('coffee')],
        difficultyOffset: 1,
      );
      expect(created.map((e) => e.word), ['mug', 'saucer']);
      expect(
          created.every((e) => e.dataStatus == WordDataStatus.pending), isTrue);
      expect(repo.wordCount, before + 2 - 1); // +mug +saucer −plate (see below)
      final mug = repo.entryByWord('mug')!;
      expect(repo.cardOf(mug.id)!.archived, isFalse);
      expect(repo.occurrencesOf(mug.id).single.evidence, 'mug in the photo');
      // coffee keeps its one card; the breakfast photo was already a context.
      final coffee = repo.entryByWord('coffee')!;
      expect(repo.occurrencesOf(coffee.id), hasLength(3));
      // The mock's apple/bread/knife/plate left the list: their breakfast
      // occurrence goes, but their cards (other photos) stay.
      expect(repo.occurrencesOf(plate.id), isEmpty);
      expect(repo.entryByWord('plate'), isNull,
          reason: 'unused and never reviewed');
      expect(repo.cardOf(repo.entryByWord('apple')!.id), isNotNull);
      expect(repo.photo('photo-breakfast')!.difficultyOffset, 1);
      expect(repo.profile.familiarityOf('mug'), Familiarity.learning);
      expect(repo.profile.exposure['mug']!.count, 1);
    });

    test('saving twice doesn\'t duplicate; a moved pin keeps its occurrence',
        () {
      repo.savePhotoWords('photo-kitchen', [listed('mug')],
          difficultyOffset: 0);
      final occ = repo.occurrencesOf(repo.entryByWord('mug')!.id).single;
      repo.savePhotoWords('photo-kitchen', [listed('mug', x: 0.7)],
          difficultyOffset: 0);
      final again = repo.occurrencesOf(repo.entryByWord('mug')!.id).single;
      expect(again.id, occ.id);
      expect(again.anchor.x, 0.7);
      expect(again.userEdited, isTrue);
    });

    test('also-seen studied words gain this photo as a context', () {
      repo.savePhotoWords('photo-kitchen', [listed('mug')],
          difficultyOffset: 0, alsoSeen: [listed('balcony')]);
      expect(repo.photosOfWord(repo.entryByWord('balcony')!.id).first.id,
          'photo-kitchen');
    });

    test('a corrected label keeps the AI word and the user\'s meaning', () {
      repo.savePhotoWords(
        'photo-kitchen',
        [
          ListedWord(cand('coffee', meaning: '黑咖啡'), const LabelPoint(0.5, 0.4),
              aiLabel: 'coffee', edited: true)
        ],
        difficultyOffset: 0,
      );
      final coffee = repo.entryByWord('coffee')!;
      expect(coffee.meaning, '黑咖啡');
      expect(coffee.userEdited, contains(WordField.meaning));
    });
  });

  group('已學會 (archive) and 復原', () {
    test('archive keeps card, history and FSRS; restore brings them back', () {
      final balcony = repo.entryByWord('balcony')!;
      final card = repo.cardOf(balcony.id)!;
      repo.review(card.id, Rating.good);
      final fsrs = repo.cardOf(balcony.id)!.fsrs;
      final abilityBefore = repo.profile.ability;

      repo.archiveWord(balcony.id);
      expect(repo.cardOf(balcony.id)!.archived, isTrue);
      expect(repo.profile.learned, contains('balcony'));
      expect(repo.profile.ability, greaterThan(abilityBefore),
          reason: 'known-word signal');
      expect(
          repo.activeLabels('photo-morning-balcony').map((l) => l.entry.word),
          isNot(contains('balcony')));
      expect(repo.eligibleCards().any((c) => c.id == card.id), isFalse);
      expect(repo.albumWordCount('album-balcony'), 15);

      repo.restoreWord('balcony');
      final back = repo.cardOf(balcony.id)!;
      expect(back.archived, isFalse);
      expect(back.fsrs.stability, fsrs.stability);
      expect(repo.logsOf(card.id), hasLength(1));
      expect(repo.profile.learned, isNot(contains('balcony')));
    });

    test('a suggested word swiped away has no card, only the learned list', () {
      repo.markKnown(cand('mug'));
      expect(repo.profile.learned, contains('mug'));
      expect(repo.entryByWord('mug'), isNull);
      repo.restoreWord('mug');
      expect(repo.profile.learned, isEmpty);
    });

    test('removing a photo keeps reviewed cards and drops unused words', () {
      final railing = repo.entryByWord('railing')!;
      repo.review(repo.cardOf(railing.id)!.id, Rating.hard);
      repo.removePhoto('photo-morning-balcony');
      expect(repo.photo('photo-morning-balcony'), isNull);
      expect(repo.entryByWord('railing'), isNotNull, reason: 'has history');
      expect(repo.entryByWord('sunlight'), isNull, reason: 'fresh and unused');
      expect(repo.entryByWord('balcony'), isNotNull, reason: 'other photos');
    });
  });

  group('review', () {
    test('review() updates the one card, logs it, and nudges the ability', () {
      final coffee = repo.entryByWord('coffee')!;
      final id = repo.cardOf(coffee.id)!.id;
      final preview = repo.previewReview(id);
      final ability = repo.profile.ability;
      final log = repo.review(id, Rating.good);
      expect(repo.card(id)!.fsrs.state, FsrsCardState.review);
      expect(repo.card(id)!.fsrs.scheduledDays,
          preview[Rating.good]!.scheduledDays);
      expect(repo.logsOf(id), [log]);
      expect(repo.profile.ability, isNot(ability));
      expect(repo.profile.events, 1);
    });

    test('eligible: new cards and cards due by today', () {
      final eligible = {
        for (final c in repo.eligibleCards()) repo.entry(c.wordEntryId)!.word
      };
      expect(eligible, containsAll(['balcony', 'railing', 'apple', 'coffee']));
      expect(eligible, isNot(contains('dappled')), reason: 'due tomorrow');
      expect(eligible, isNot(contains('potted')));
      expect(eligible, hasLength(16));
    });

    test('a card waits for its native meaning, then becomes eligible', () {
      final word = repo.addWord(word: 'unfilled', pos: 'adj.', meaning: '');
      final card = repo.cardOf(word.id)!;
      expect(repo.isEligible(card, testNow), isFalse);
      expect(repo.hasCardsWaitingForMeaning, isTrue);

      repo.applyWordData(word.id,
          meaning: '尚未填寫的', status: WordDataStatus.complete);
      expect(repo.isEligible(card, testNow), isTrue);
    });
  });

  group('word data', () {
    test('background data fills gaps; user edits are never overwritten', () {
      final e = repo.addWord(word: 'patio', pos: 'noun', meaning: '露台');
      expect(repo.cardOf(e.id), isNotNull);
      expect(e.dataStatus, WordDataStatus.pending);
      repo.editEntry(e.copyWith(meaning: '中庭'), {WordField.meaning});
      repo.applyWordData(
        e.id,
        meaning: '天井',
        definition: '房屋旁的鋪面空地。',
        ipa: '/ˈpætioʊ/',
        ipaSource: 'cmudict',
        newExamples: const [
          WordExample(
              text: 'We ate on the patio.',
              translation: '我們在露台吃飯。',
              aiGenerated: true,
              aiTranslated: true),
        ],
        translatedFor: 'zh-TW',
        status: WordDataStatus.complete,
      );
      final after = repo.entry(e.id)!;
      expect(after.meaning, '中庭');
      expect(after.definition, '房屋旁的鋪面空地。');
      expect(after.ipa, '/ˈpætioʊ/');
      expect(after.examples.single.aiTranslated, isTrue);
      expect(after.dataStatus, WordDataStatus.complete);
    });

    test('a new native language replaces meanings and translations', () {
      final apple = repo.entryByWord('apple')!;
      repo.applyWordData(
        apple.id,
        meaning: 'apple (fruit)',
        translations: {0: 'I eat one apple every day.'},
        translatedFor: 'en',
        status: WordDataStatus.complete,
      );
      final after = repo.entry(apple.id)!;
      expect(after.meaning, 'apple (fruit)');
      expect(after.examples.first.translation, 'I eat one apple every day.');
      expect(after.examples.first.aiTranslated, isTrue);
      expect(after.nativeOfData, 'en');
    });

    test('failures count attempts; retry makes it pending again', () {
      final e = repo.addWord(word: 'patio', pos: 'noun', meaning: '露台');
      repo.applyWordData(e.id, status: WordDataStatus.failed, error: '連不到');
      expect((repo.entry(e.id)!.dataAttempts, repo.entry(e.id)!.dataError),
          (1, '連不到'));
      expect(words(const WordDatabaseFilter(missing: MissingField.failed)),
          ['patio']);
      repo.retryWordData(e.id);
      expect(repo.entry(e.id)!.dataStatus, WordDataStatus.pending);
    });

    test('addWord merges pipeline data and rejects duplicates', () {
      final withLookup = WordDatabaseRepository(
        clock: () => testNow,
        lookupDetail: (w) => w == 'happy'
            ? WordDetail.fromJson({
                'word': 'happy',
                'ipa': '/ˈhæp.i/',
                'definitions': [
                  {'pos': 'adjective', 'gloss': 'feeling pleasure'},
                ],
                'synonyms': ['glad'],
                'inflections': [
                  {'form': 'happier', 'label': 'comparative'},
                ],
                'derivations': [
                  {'word': 'happiness', 'pos': 'noun'},
                ],
              })
            : null,
      );
      final entry =
          withLookup.addWord(word: ' Happy ', pos: 'adj.', meaning: '快樂的');
      expect(entry.word, 'happy');
      expect(entry.ipa, '/ˈhæp.i/');
      expect(entry.forms.single.form, 'happier');
      expect([for (final r in entry.related) r.word], ['glad', 'happiness']);
      expect(
        () => withLookup.addWord(word: 'HAPPY', pos: 'adj.', meaning: '高興'),
        throwsA(isA<DuplicateWordException>()),
      );
    });
  });

  group('labels & paging helpers', () {
    LearningCard card(FsrsCardState s, DateTime? due,
            {bool archived = false}) =>
        LearningCard(
          id: 'c',
          wordEntryId: 'w',
          templateId: 't',
          archived: archived,
          fsrs: FsrsState(state: s, due: due, stability: 3),
        );

    test('dueLabel never shows overdue pressure', () {
      final now = testNow;
      expect(
          dueLabel(
              card(FsrsCardState.review, now.subtract(const Duration(days: 5))),
              now),
          '今天');
      expect(
          dueLabel(
              card(FsrsCardState.review, now.add(const Duration(hours: 20))),
              now),
          '明天');
      expect(
          dueLabel(
              card(FsrsCardState.review, now.add(const Duration(days: 12))),
              now),
          '12 天後');
      expect(dueLabel(card(FsrsCardState.newCard, null), now), '尚未開始');
      expect(
          dueLabel(card(FsrsCardState.review, now, archived: true), now), '—');
      expect(StudyStatus.of(card(FsrsCardState.review, now, archived: true)),
          StudyStatus.learned);
    });

    test('formatCount, pageWindow, PageSlice', () {
      expect(formatCount(1284), '1,284');
      expect(pageWindow(5, 10), [4, 5, 6]);
      expect(pageWindow(0, 2), [0, 1]);
      final slice = PageSlice.of(List.generate(10, (i) => i), 5, 8);
      expect(slice.items, [8, 9]);
      expect((slice.page, slice.start, slice.end), (1, 9, 10));
    });
  });
}
