import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

void main() {
  test('photo label keeps only its part of speech and sense', () {
    final all = [
      const LexemeUsage(id: 'n', pos: 'noun', senses: [
        WordSense(id: 's1', meaning: '植物'),
        WordSense(id: 's2', meaning: '工廠'),
      ], examples: [
        WordExample(text: 'A plant.', senseId: 's1'),
        WordExample(text: 'Workers at the plant.', senseId: 's2'),
      ]),
      const LexemeUsage(
          id: 'v', pos: 'verb', senses: [WordSense(id: 's3', meaning: '種植')]),
    ];
    final r = WordDatabaseRepository.usagesForSenseForTest(all, 'noun', '植物');
    expect(r.length, 1);
    expect(r.single.senses.single.id, 's1');
    expect(r.single.examples.map((e) => e.text), ['A plant.']);
  });
}
