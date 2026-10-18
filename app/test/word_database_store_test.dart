import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:photo_english_app/data/sample_word_database.dart';
import 'package:photo_english_app/models/card_template.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/services/word_database_store.dart';

import 'helpers.dart';

void main() {
  final now = testNow;
  late Directory dir;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('word_db_test');
    Hive.init(dir.path);
  });

  tearDown(() async {
    await Hive.close();
    await dir.delete(recursive: true);
  });

  Future<WordDatabaseRepository> reopen({String language = 'en'}) async {
    await Hive.close();
    Hive.init(dir.path);
    final store = await HiveWordDatabaseStore.open(language: language);
    expect(store.needsSeed, isFalse);
    return WordDatabaseRepository.fromData(store.load(),
        language: language, store: store, clock: () => now);
  }

  test('seeds once, and every change survives a restart', () async {
    final store = await HiveWordDatabaseStore.open();
    expect(store.needsSeed, isTrue);
    await store.seed(sampleWordDatabaseData(now: now, lexicon: testLexicon()));
    expect(store.needsSeed, isFalse);

    final repo = WordDatabaseRepository.fromData(store.load(),
        store: store, clock: () => now);
    final counts =
        (repo.wordCount, repo.photoCount, repo.cardCount, repo.albums.length);
    expect(repo.photo('photo-breakfast')!.candidates, isNotEmpty);

    repo.addWord(word: 'patio', pos: 'noun', meaning: '露台');
    final album = repo.addAlbum(name: '旅行', category: '戶外');
    repo.addPhoto(Photo(
      id: 'photo-new',
      albumId: album.id,
      title: '新照片',
      takenAt: now,
      storedKey: 'photo-new',
      createdAt: now,
    ));
    final breakfastPool = repo.photo('photo-breakfast')!.candidates;
    repo.savePhotoWords(
      'photo-new',
      [
        ListedWord(breakfastPool.firstWhere((c) => c.word == 'mug'),
            const LabelPoint(0.4, 0.6))
      ],
      difficultyOffset: -1,
    );
    repo.archiveWord(repo.entryByWord('knife')!.id);
    final balcony = repo.cardOf(repo.entryByWord('balcony')!.id)!;
    final log = repo.review(balcony.id, Rating.good,
        duration: const Duration(seconds: 4),
        templateType: 'cloze',
        correct: true,
        hintCount: 1,
        attempts: 2);
    final fields = [...repo.template.backFields];
    fields.add(fields.removeAt(0).copyWith(visible: false));
    repo.updateTemplate(repo.template.copyWith(backFields: fields));
    repo.setLevel('B2');

    await repo.flush();
    final again = await reopen();
    expect(
      (again.wordCount, again.photoCount, again.cardCount, again.albums.length),
      // +patio +mug · +1 photo · +2 −1 (knife archived) cards · +1 album
      (counts.$1 + 2, counts.$2 + 1, counts.$3 + 1, counts.$4 + 1),
    );
    final mugOcc = again.occurrencesInPhoto('photo-new').single;
    expect(mugOcc.anchor.x, 0.4);
    expect(mugOcc.evidence, isNotEmpty);
    expect(again.photo('photo-new')!.difficultyOffset, -1);
    expect(again.photo('photo-new')!.wordsSavedAt, isNotNull);
    expect(again.isArchived(again.entryByWord('knife')!.id), isTrue);
    expect(again.photo('photo-breakfast')!.candidates.length,
        breakfastPool.length);

    final card = again.card(balcony.id)!;
    expect(card.fsrs.due, log.after.due);
    expect(card.fsrs.algorithmVersion, 'fsrs-5');
    expect(again.logsOf(card.id).single.requestedRating, Rating.good);
    expect(again.logsOf(card.id).single.durationMs, 4000);
    expect(again.logsOf(card.id).single.templateType, 'cloze');
    expect(again.logsOf(card.id).single.correct, isTrue);
    expect(again.logsOf(card.id).single.hintCount, 1);
    expect(again.logsOf(card.id).single.attempts, 2);

    expect(again.template.backFields.first.field, CardBackField.posAndMeaning);
    expect(again.template.backFields.last.visible, isFalse);
    expect(again.profile.cefr, 'B2');
    expect(again.profile.learned, contains('knife'));
  });

  test('original and effective grades survive restart and archive restore',
      () async {
    final store = await HiveWordDatabaseStore.open();
    await store.seed(sampleWordDatabaseData(now: now, lexicon: testLexicon()));
    final repo = WordDatabaseRepository.fromData(store.load(),
        store: store, clock: () => now);
    final entry = repo.entryByWord('balcony')!;
    final card = repo.cardOf(entry.id)!;
    repo.review(card.id, Rating.hard,
        requestedRating: Rating.good,
        templateType: 'photoChoice',
        correct: true);
    repo.review(card.id, Rating.hard,
        requestedRating: Rating.hard,
        templateType: 'photoChoice',
        correct: true);
    repo.archiveWord(entry.id);
    await repo.flush();
    final again = await reopen();
    expect(
        again.logsOf(card.id).map((l) => l.rating), [Rating.hard, Rating.hard]);
    expect(again.logsOf(card.id).map((l) => l.requestedRating),
        [Rating.good, Rating.hard]);
    final old = again.logsOf(card.id).first.toJson()..remove('requestedRating');
    final legacy = ReviewLog.fromJson(old);
    expect(legacy.requestedRating, isNull);
    expect(legacy.rating, Rating.hard);
    expect(legacy.toJson().containsKey('requestedRating'), isFalse);
    expect(legacy.after.toJson(), again.logsOf(card.id).first.after.toJson());
    expect(again.isArchived(entry.id), isTrue);
    final state = again.card(card.id)!.fsrs.toJson();
    again.restoreWord(entry.word);
    await again.flush();
    expect(again.card(card.id)!.fsrs.toJson(), state);
    final box = Hive.box<String>('wd_review_logs');
    await box.add(jsonEncode(old));
    final restored = await reopen();
    expect(restored.isArchived(entry.id), isFalse);
    expect(restored.card(card.id)!.fsrs.toJson(), state);
    expect(restored.logsOf(card.id).map((l) => l.requestedRating),
        [Rating.good, Rating.hard, null]);
    expect(restored.logsOf(card.id).last.rating, Rating.hard);
  });

  test('a burst of reviews is durable before an orderly close', () async {
    final store = await HiveWordDatabaseStore.open();
    await store.seed(const WordDatabaseData());
    final repo = WordDatabaseRepository.fromData(store.load(),
        store: store, clock: () => now);
    for (var i = 0; i < 100; i++) {
      final e = repo.addWord(word: 'word$i', pos: 'noun', meaning: '意思$i');
      final c = repo.cardOf(e.id)!;
      for (var j = 0; j < 4; j++) {
        repo.review(c.id, Rating.good);
      }
    }
    await repo.flush();
    await store.close();
    final loaded = (await HiveWordDatabaseStore.open()).load();
    expect(loaded.entries, hasLength(100));
    expect(loaded.cards, hasLength(100));
    expect(loaded.reviewLogs, hasLength(400));
    expect(loaded.cards.every((c) => c.fsrs.reps == 4), isTrue);
  });

  test('flush reports writes that failed instead of silently passing',
      () async {
    final store = await HiveWordDatabaseStore.open();
    await store.seed(const WordDatabaseData());
    final repo = WordDatabaseRepository.fromData(store.load(),
        store: store, clock: () => now);
    await store.close();
    repo.addWord(word: 'apple', pos: 'noun', meaning: '蘋果');
    await Future<void>.delayed(Duration.zero);
    await expectLater(repo.flush(), throwsA(isA<HiveError>()));
  });

  test('each learning language has its own data', () async {
    final en = await HiveWordDatabaseStore.open();
    await en.seed(sampleWordDatabaseData(now: now));
    final fr = await HiveWordDatabaseStore.open(language: 'fr');
    expect(fr.needsSeed, isTrue);
    await fr.seed(const WordDatabaseData());
    final frRepo = WordDatabaseRepository.fromData(fr.load(),
        language: 'fr',
        store: fr,
        clock: () => now,
        profile: UserVocabularyProfile.start('A1', now: now));
    frRepo.addWord(word: 'pomme', pos: 'noun', meaning: '蘋果');

    final frAgain = await reopen(language: 'fr');
    expect(frAgain.entries.single.word, 'pomme');
    expect(frAgain.entries.single.language, 'fr');
    final enAgain = await reopen();
    expect(enAgain.entryByWord('pomme'), isNull);
    expect(enAgain.wordCount, 21);
  });

  test('a version-2 store is migrated to one card per word', () async {
    // Two photos' cards for the same word, as version 2 stored them.
    Future<Box<String>> box(String name) => Hive.openBox<String>('wd_$name');
    final entries = await box('entries');
    await entries.put(
        'w-cup',
        jsonEncode({
          'id': 'w-cup',
          'word': 'cup',
          'pos': 'noun',
          'meaningZh': '杯子',
          'examples': [
            {'en': 'A cup of tea.', 'zh': '一杯茶。', 'audioUrl': null},
          ],
          'createdAt': now.toIso8601String(),
          'updatedAt': now.toIso8601String(),
        }));
    final photos = await box('photos');
    for (final id in ['p1', 'p2']) {
      await photos.put(
          id,
          jsonEncode({
            'id': id,
            'title': id,
            'takenAt': now.toIso8601String(),
            'createdAt': now.toIso8601String(),
          }));
    }
    final occurrences = await box('occurrences');
    final cards = await box('cards');
    for (final (i, id) in ['p1', 'p2'].indexed) {
      await occurrences.put(
          'o$i',
          jsonEncode({
            'id': 'o$i',
            'photoId': id,
            'wordEntryId': 'w-cup',
            'anchor': {'x': 0.5, 'y': 0.5},
          }));
      await cards.put(
          'card:o$i',
          jsonEncode({
            'id': 'card:o$i',
            'occurrenceId': 'o$i',
            'wordEntryId': 'w-cup',
            'templateId': 'photo-word-card',
            'suspended': i == 0,
            'fsrs': {
              'state': i == 1 ? 'review' : 'newCard',
              'reps': i * 3,
              'stability': 4.0
            },
          }));
    }
    final logs = await box('review_logs');
    await logs.add(jsonEncode({
      'cardId': 'card:o1',
      'reviewedAt': now.toIso8601String(),
      'rating': 'good',
      'before': {'state': 'newCard'},
      'after': {'state': 'review', 'reps': 3},
      'elapsedDays': 0,
      'scheduledDays': 3,
    }));
    await (await box('meta')).put('schema', '2');
    await Hive.close();
    Hive.init(dir.path);

    final repo = await reopen();
    expect(repo.cardCount, 1);
    final card = repo.cardOf('w-cup')!;
    expect(card.id, LearningCard.idFor('w-cup'));
    expect(card.fsrs.reps, 3, reason: 'the most-reviewed card wins');
    expect(repo.logsOf(card.id), hasLength(1));
    expect(repo.entryByWord('cup')!.meaning, '杯子');
    expect(repo.entryByWord('cup')!.examples.single.translation, '一杯茶。');
    expect(repo.photo('p1')!.wordsSavedAt, isNotNull);
    expect(repo.occurrencesOf('w-cup'), hasLength(2));
  });
}
