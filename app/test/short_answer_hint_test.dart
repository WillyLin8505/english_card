import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';

void main() {
  test(
      'one-letter answers retain a hidden letter instead of revealing the answer',
      () {
    expect(firstLetterHint('a'), '_');
    expect(firstLetterHint('I'), '_');
    expect(firstLetterHint('é'), '_');
    expect(firstLetterHint('A.'), '_ .');
  });

  test('longer words and phrases keep the existing first-letter hint', () {
    expect(firstLetterHint('at'), 'a _');
    expect(firstLetterHint('a cup'), 'a   _ _ _');
    expect(firstLetterHint('I am'), 'I   _ _');
  });
}
