import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_entry.dart';

void main() {
  test('examplesForLevel prefers bilingual pairs near the learner level', () {
    final now = DateTime(2026);
    final entry = WordEntry(
      id: 'w1',
      word: 'apple',
      pos: 'noun',
      meaning: '蘋果',
      createdAt: now,
      updatedAt: now,
      examples: const [
        WordExample(text: 'Exact without translation.', difficulty: 'B1'),
        WordExample(
            text: 'Nearby translated.', translation: '相鄰翻譯。', difficulty: 'A2'),
        WordExample(
            text: 'Exact translated.', translation: '同級翻譯。', difficulty: 'B1'),
        WordExample(
            text: 'Far translated.', translation: '較遠翻譯。', difficulty: 'C1'),
      ],
    );

    final result = entry.examplesForLevel('B1', minimum: 3);
    expect(result.map((e) => e.text), [
      'Exact translated.',
      'Nearby translated.',
      'Far translated.',
      'Exact without translation.',
    ]);
  });

  test('example CEFR survives JSON round trip', () {
    const example = WordExample(
      text: 'I ate an apple.',
      translation: '我吃了一顆蘋果。',
      difficulty: 'A2',
    );
    expect(WordExample.fromJson(example.toJson()).difficulty, 'A2');
  });
}
