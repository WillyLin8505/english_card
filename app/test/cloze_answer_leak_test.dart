import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'helpers.dart';

FlashcardSession sessionFor(String word, List<String> texts,
    {List<WordForm> forms = const []}) {
  final original = WordEntry.fromUserInput(
      id: 'test',
      word: word,
      pos: 'noun',
      meaning: '測試意思',
      level: 'A1',
      now: testNow);
  final entry = WordEntry.fromJson({
    ...original.toJson(),
    'forms': [for (final form in forms) form.toJson()],
  // Distinct translations: learningExamples keeps one sentence per
  // translation (問題回報 #555), so a shared placeholder would hide the rest.
  }).copyWith(examples: [
    for (final (i, text) in texts.indexed)
      WordExample(text: text, translation: '測試翻譯$i')
  ]);
  final repo = WordDatabaseRepository(clock: () => testNow, entries: [
    entry
  ], cards: [
    LearningCard(
        id: LearningCard.idFor(entry.id),
        wordEntryId: entry.id,
        templateId: 'test')
  ]);
  return FlashcardSession(repo, lexicon: LexiconPack());
}

void main() {
  test(
      'a sentence exposing another form is skipped without recording a failure',
      () {
    final s = sessionFor('apple', ['The apple is beside apples.'],
        forms: const [WordForm('apples', 'plural')]);
    addTearDown(s.dispose);
    // No safe exercise falls back to the traditional flip card rather than
    // skipping the card (問題回報 #207 decision A).
    expect(s.finished, isFalse);
    expect(s.exercise, isNull);
    expect(s.repo.logsOf(LearningCard.idFor('test')), isEmpty);
    expect(s.repo.card(LearningCard.idFor('test'))!.fsrs.reps, 0);
  });
  test(
      'compound answer leakage is skipped in favour of a safe translated example',
      () {
    final s = sessionFor('apple', [
      'An applecart holds apple.',
      'This ripe apple is on the wooden table.'
    ]);
    addTearDown(s.dispose);
    expect(s.exercise!.prompt, 'This ripe _ _ _ _ _ is on the wooden table.');
    expect(s.exercise!.answer, 'apple');
  });
  test('the chosen strict substring policy also rejects men inside women', () {
    final s = sessionFor('men', ['Many men love women.']);
    addTearDown(s.dispose);
    expect(s.finished, isFalse);
    expect(s.exercise, isNull);
  });
}
