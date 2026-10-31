// Card #894: a review card's picture must show the sense the card tests, and
// the carousel starts on the picture the front shows (the best one).
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

Map<String, dynamic> _image(int id, int sense, {bool dot = true}) => {
      'id': id,
      'url': '/api/image?id=$id',
      'status': 'ready',
      'tags': [
        {'lexeme_id': 1, 'sense_id': sense, 'review_status': 'approved'}
      ],
      'labels': [
        {
          'lexeme_id': 1,
          if (dot) 'point': [0.4, 0.5],
        }
      ],
    };

List<String> _options(List<Map<String, dynamic>> images) {
  final lexicon = LexiconPack()
    ..loadJson({
      'target_language': 'en',
      'native_language': 'zh-TW',
      'lexemes': [
        {
          'id': 1,
          'lemma': 'run',
          'normalized': 'run',
          'pos': 'verb',
          'status': 'full',
          'senses': [
            {'id': 10, 'native': '跑步'},
            {'id': 11, 'native': '用完'},
          ]
        }
      ],
      'catalog_images': images,
    });
  final entry = WordEntry.fromUserInput(
          id: 'run',
          word: 'run',
          pos: 'verb',
          meaning: '跑步',
          level: 'A1',
          lexemeId: 1,
          now: testNow)
      .copyWith(usages: lexicon.usagesFor('run'));
  final repo = WordDatabaseRepository(clock: () => testNow, entries: [
    entry
  ], cards: [
    LearningCard(id: 'run-0', wordEntryId: 'run', templateId: 't'),
  ])
    ..linkLexicon(lexicon);
  final session = FlashcardSession(repo, lexicon: lexicon, random: Random(1));
  final ids = [for (final o in session.photoOptions) o.$1.id];
  session.dispose();
  return ids;
}

void main() {
  test('only pictures of the tested sense; best first', () {
    expect(
        _options([
          _image(1, 11), // 用完: another sense
          _image(2, 10, dot: false),
          _image(3, 10),
        ]),
        ['db-3', 'db-2']);
  });

  test('no picture of the tested sense: no picture', () {
    expect(_options([_image(1, 11)]), isEmpty);
  });
}
