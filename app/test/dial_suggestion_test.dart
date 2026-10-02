import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/vocabulary_profile.dart';

import 'helpers.dart';

void main() {
  test('accepting the dial suggestion does not suggest the next level at once', () {
    var p = UserVocabularyProfile.start('A2', now: testNow);
    for (var i = 0; i < 5; i++) {
      p = p.dialled(1, testNow);
    }
    expect(p.suggestedShift, 1);
    final b1 = p.withLevel('B1', 'user', testNow);
    expect(b1.cefr, 'B1');
    expect(b1.suggestedShift, 0);
    expect(b1.dialHistory, isEmpty);
  });
}
