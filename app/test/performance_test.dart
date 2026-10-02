import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/card_template.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/word_database_query.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

/// A heavy learner (3,000 words, 9,000 photo labels): the next card and the
/// word list must stay instant. Each used to scan every word and label per
/// card — about 2 s for every rating on a desktop.
void main() {
  test('reviewing and searching stay fast with thousands of words', () {
    final rnd = Random(1);
    final entries = [
      for (var i = 0; i < 3000; i++)
        WordEntry.fromUserInput(id: 'w$i', word: 'word$i', pos: 'noun', meaning: '意思$i', level: 'A2', now: testNow),
    ];
    final cards = [
      for (final e in entries)
        LearningCard(id: LearningCard.idFor(e.id), wordEntryId: e.id, templateId: CardTemplate.photoWordCard.id),
    ];
    final occurrences = [
      for (var i = 0; i < 9000; i++)
        PhotoOccurrence(id: 'o$i', photoId: 'p${i ~/ 4}', wordEntryId: 'w${rnd.nextInt(3000)}',
            anchor: const LabelPoint(0.5, 0.5)),
    ];
    final repo = WordDatabaseRepository(
        entries: entries, cards: cards, occurrences: occurrences, clock: () => testNow);
    final sw = Stopwatch()..start();
    final s = FlashcardSession(repo, random: rnd);
    for (var i = 0; i < 20; i++) {
      s.showAnswer();
      s.rate(Rating.good);
    }
    repo.query(const WordDatabaseFilter(search: 'word12'));
    repo.query(const WordDatabaseFilter(sort: SortOrder.nextDue));
    expect(sw.elapsedMilliseconds, lessThan(3000),
        reason: '20 cards and two searches; was about 40 s before the lookup tables');
    // The album grid: every photo's labels (相片冊縮圖) and word counts.
    sw.reset();
    var labels = 0;
    for (var p = 0; p < 2250; p++) {
      labels += repo.activeLabels('p$p').length;
    }
    expect(labels, greaterThan(0));
    expect(sw.elapsedMilliseconds, lessThan(1000), reason: 'was a scan of every label per photo');
  });
}
