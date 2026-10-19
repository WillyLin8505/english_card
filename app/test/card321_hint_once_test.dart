import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/flashcard_session.dart';

import 'helpers.dart';

/// Card #321 / 問題回報 #309: the first-letter hint never changes, so
/// pressing it again must not raise the recorded hint count.
void main() {
  test('useHint counts once per card', () {
    final repo = testRepository();
    final session = FlashcardSession(repo, random: math.Random(1));
    addTearDown(session.dispose);
    expect(session.hintCount, 0);
    session.useHint();
    session.useHint();
    session.useHint();
    expect(session.hintCount, 1);
  });
}
