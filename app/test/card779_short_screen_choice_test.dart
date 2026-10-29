import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/theme/card_style.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';
import 'helpers.dart';
import 'review_database_photos_test.dart' show image, pack, repository;

// 問題回報 #920 / #921: on a 375×667 screen the photo-choice question and its
// three options must sit above the fixed 顯示答案 dock, not under it.

/// A photo-choice question for apple (three other A1 words as options).
FlashcardSession _choice(Map<String, dynamic> img) {
  final lexicon = pack([img]);
  final base = repository(lexicon);
  for (final (word, meaning) in [
    ('banana', '香蕉'),
    ('pear', '梨子'),
    ('orange', '橙子')
  ]) {
    base.addWord(word: word, pos: 'noun', meaning: meaning, level: 'A1');
  }
  final repo = WordDatabaseRepository(
      clock: () => testNow,
      entries: [for (final e in base.entries) e.copyWith(level: () => 'A1')],
      cards: [base.cardOf(base.entryByWord('apple')!.id)!]);
  final session = FlashcardSession(repo, lexicon: lexicon, random: Random(1));
  expect(session.exercise!.type, ReviewExerciseType.photoChoice);
  return session;
}

void main() {
  tearDown(() => LexiconPack.instance.clear());

  testWidgets('photo choice: question and options sit above 顯示答案',
      (tester) async {
    final session = _choice(image(1));
    await pumpApp(tester,
        size: const Size(375, 667),
        home: Scaffold(
            body: CardLookScope(
                look: CardLook.forStyle(AppSettings.inMemory().cardStyle),
                child: FlashcardCardView(session: session))));
    await tester.pump();

    final answer = tester.getRect(find.widgetWithText(PrimaryButton, '顯示答案'));
    final title = tester.getRect(find.text(session.exercise!.prompt));
    expect(title.bottom, lessThanOrEqualTo(answer.top));
    for (final option in session.exercise!.options) {
      final rect = tester.getRect(find.widgetWithText(OutlinedButton, option));
      expect(rect.bottom, lessThanOrEqualTo(answer.top),
          reason: '$option is under the 顯示答案 dock');
    }
    session.dispose();
  });
}
