import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_entry.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'helpers.dart';

void main() {
  test('卡 #826 / 問題回報 #947: no pack for the native language blanks the old meaning',
      () {
    final repo = WordDatabaseRepository(clock: () => testNow);
    final e = repo.addWord(word: 'plate', pos: 'noun', meaning: '盤子', level: 'A1');
    repo.applyWordData(e.id,
        newExamples: [WordExample(text: 'A plate.', translation: '一個盤子')],
        status: WordDataStatus.complete);
    repo.applyWordData(e.id, dropStale: true, status: WordDataStatus.failed);
    final x = repo.entry(e.id)!;
    expect(x.meaning, '');
    expect(x.examples.single.translation, '');
    expect(x.examples.single.text, 'A plate.');
  });
}
