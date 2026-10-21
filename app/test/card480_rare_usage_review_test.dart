// 問題回報 #468 (card #480): review rotates through a word's common parts of
// speech only; a rare usage (rare_usage) is never the one asked.

import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';

import 'helpers.dart';

void main() {
  tearDown(() => LexiconPack.instance.clear());

  test('rare usage is skipped when rotating usages', () {
    final repo = testRepository();
    final pack = {
      'target_language': 'en',
      'native_language': 'zh-TW',
      'created_at': 'v1',
      'lexemes': [
        for (final r in [
          [1, 'noun', false],
          [2, 'verb', true],
        ])
          {
            'id': r[0],
            'lemma': 'galaxy',
            'normalized': 'galaxy',
            'pos': r[1],
            'status': 'full',
            'cefr': 'B1',
            'rare_usage': r[2],
            'senses': [
              {'id': r[0], 'definition': 'galaxy', 'native': '${r[1]}意思'}
            ],
          }
      ],
    };
    repo.addWord(word: 'galaxy', pos: 'noun', meaning: '');
    repo.linkLexicon(LexiconPack.instance..loadJson(pack));
    final usages = repo.entryByWord('galaxy')!.effectiveUsages;
    expect(usages.map((u) => u.rare), [false, true]);

    final session = FlashcardSession(repo, random: math.Random(3));
    addTearDown(session.dispose);
    for (var i = 0; i < 12; i++) {
      final id = session.usageId;
      final card = session.card;
      if (card != null && repo.entry(card.wordEntryId)?.word == 'galaxy') {
        expect(id, isNot(contains(':2')));
      }
      session.showAnswer();
      session.rate(Rating.good);
    }
  });
}
