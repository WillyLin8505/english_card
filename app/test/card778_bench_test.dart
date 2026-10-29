import 'dart:math';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/card_template.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'helpers.dart';

void main() {
  test('bench session start', () {
    final rnd = Random(1);
    final entries = [
      for (var i = 0; i < 6000; i++)
        WordEntry.fromUserInput(id: 'w$i', word: 'word$i', pos: 'noun', meaning: '意思$i', level: 'A2', now: testNow),
    ];
    final cards = [
      for (final e in entries)
        LearningCard(id: LearningCard.idFor(e.id), wordEntryId: e.id, templateId: CardTemplate.photoWordCard.id),
    ];
    final occ = [
      for (var i = 0; i < 9000; i++)
        PhotoOccurrence(id: 'o$i', photoId: 'p${i ~/ 4}', wordEntryId: 'w${rnd.nextInt(6000)}', anchor: const LabelPoint(0.5, 0.5)),
    ];
    final repo = WordDatabaseRepository(entries: entries, cards: cards, occurrences: occ, clock: () => testNow);
    for (var k = 0; k < 3; k++) {
      var sw = Stopwatch()..start();
      repo.eligibleCards(newLimit: 20, reviewLimit: 100);
      final a = sw.elapsedMilliseconds;
      sw.reset();
      final p = FlashcardSession(repo, continuous: true);
      p.dispose();
      final b = sw.elapsedMilliseconds;
      sw.reset();
      final s = FlashcardSession(repo, continuous: true, newLimit: 20, reviewLimit: 100);
      final c = sw.elapsedMilliseconds;
      s.upcomingPhotos();
      print('eligible=$a probe=$b session=$c total=${sw.elapsedMilliseconds}');
      s.dispose();
    }
  });
}
