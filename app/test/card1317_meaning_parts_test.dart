import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';

void main() {
  test('semicolon inside brackets does not split a sense (card 1317)', () {
    expect(
        FlashcardBack.meaningParts(
            'not (used alone to negate a verb; see usage notes)'),
        ['not (used alone to negate a verb; see usage notes)']);
    expect(FlashcardBack.meaningParts('國民、民族；人們'), ['國民、民族', '人們']);
  });
}
