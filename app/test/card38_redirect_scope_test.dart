import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/photo.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'helpers.dart';

// Read-only audit of card123's 04:48 snapshot (before its final apply).
// No database/config imports. This is not a current-live-DB assertion.
void main() {
  test('card123 snapshot pointers never grant ownership to their destination', () {
    final raw = jsonDecode(File('../lexicon/logs/agents/card123.resume.pack.json')
        .readAsStringSync()) as Map<String, dynamic>;
    final pack = LexiconPack()..loadJson(raw);
    final pointers = (raw['lexemes'] as List).where((e) => e['redirect_to'] != null);
    var checked = 0;
    for (final pointer in pointers) {
      final form = LexiconPack.normalize(pointer['lemma'] as String);
      final destination = pack.byId(pointer['id'] as int);
      expect(destination, isNotNull);
      if (destination!.lemma == form || {'coat', 'goat'}.contains(form) ||
          {'coat', 'goat'}.contains(destination.lemma)) continue;
      for (final photo in [false, true]) {
        final entries = [
          for (final (word, meaning) in [('coat', '外套'), ('goat', '山羊'), (form, '測試持有詞')])
            WordEntry.fromUserInput(id: word, word: word, pos: 'noun',
                meaning: meaning, level: 'A1', now: testNow),
        ];
        entries[0] = entries[0].copyWith(related: [
          RelatedWord(destination.lemma, RelationType.associated),
          RelatedWord(form, RelationType.associated),
          const RelatedWord('goat', RelationType.associated),
        ]);
        final repo = WordDatabaseRepository(clock: () => testNow, entries: entries,
            cards: [const LearningCard(id: 'c', wordEntryId: 'coat', templateId: 'test')],
            photos: [if (photo) Photo(id: 'mine', title: 'Coat', takenAt: testNow,
                createdAt: testNow, assetPath: 'assets/photos/kitchen.jpg')],
            occurrences: [if (photo) const PhotoOccurrence(id: 'o', photoId: 'mine',
                wordEntryId: 'coat', anchor: LabelPoint(0.5, 0.5))]);
        final session = FlashcardSession(repo, lexicon: pack, random: Random(1));
        final exercise = session.exercise!;
        expect(exercise.type, photo ? ReviewExerciseType.photoChoice : ReviewExerciseType.similarMatch);
        final words = photo ? exercise.options : exercise.pairs.map((p) => p.word).toList();
        expect(words.toSet(), {'coat', 'goat', form}, reason: '$form -> ${destination.lemma}');
        expect(repo.entryByWord(destination.lemma), isNull);
        session.dispose();
        checked++;
      }
    }
    expect(checked, greaterThan(1000));
    print('card38 snapshot pointer exercises: $checked; unowned replacements: 0');
  }, skip: !File('../lexicon/logs/agents/card123.resume.pack.json').existsSync()
      ? 'Requires the local card123 04:48 audit snapshot' : false);

  test('redirected catalog drag labels cannot introduce an unowned base', () {
    for (final ownBase in [false, true]) {
      final pack = LexiconPack()..loadJson({
        'target_language': 'en', 'native_language': 'zh-TW',
        'redirects': {'9': 2},
        'lexemes': [
          for (final (id, word, meaning) in [(1, 'coat', '外套'), (2, 'boat', '船'), (3, 'goat', '山羊')])
            {'id': id, 'lemma': word, 'normalized': word, 'pos': 'noun', 'status': 'full',
              'senses': [{'id': id * 10, 'native': meaning}]},
          {'id': 9, 'lemma': 'boats', 'normalized': 'boats', 'status': 'stub', 'redirect_to': 2},
        ],
        'catalog_images': [{
          'id': 1, 'url': '/api/image?id=1', 'status': 'ready',
          'tags': [{'lexeme_id': 1, 'sense_id': 10, 'review_status': 'approved'}],
          'labels': [for (final id in [1, 9, 3]) {'lexeme_id': id, 'point': [0.5, 0.5]}],
        }],
      });
      final names = {'coat', 'goat', 'boats', if (ownBase) 'boat'};
      final repo = WordDatabaseRepository(clock: () => testNow,
        entries: [for (final name in names) WordEntry.fromUserInput(id: name, word: name,
          lexemeId: name == 'coat' ? 1 : null,
          pos: 'noun', meaning: '詞義 $name', level: 'A1', now: testNow)],
        cards: [for (var i = 0; i < 5; i++) LearningCard(id: 'c$i', wordEntryId: 'coat', templateId: 'test')]);
      final session = FlashcardSession(repo, lexicon: pack, random: Random(1));
      var drag = 0;
      while (!session.finished) {
        final exercise = session.exercise!;
        if (exercise.type == ReviewExerciseType.imageDrag) {
          drag++;
          expect(exercise.targets.every((t) => names.contains(t.word)), isTrue);
        }
        session.showAnswer();
        session.rate(Rating.good);
      }
      expect(drag, ownBase ? greaterThan(0) : 0);
      expect(repo.entryByWord('boats'), isNotNull);
      session.dispose();
    }
  });
}
