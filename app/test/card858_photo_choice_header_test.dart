import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/word_database_repository.dart';
import 'package:photo_english_app/theme/card_style.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';
import 'helpers.dart';
import 'review_database_photos_test.dart' show image, pack, repository;

// 問題回報 #1116 (card #858): the photo-choice question, with the nav header
// above the card view as in the app, must keep its title and all three
// options above the 顯示答案 dock — every card style, a two-line title (text
// scale 1.5), on 375×667, 390×844 and an iPad.

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

  for (final style in CardStyle.values) {
    for (final size in const [
      Size(375, 667),
      Size(390, 844),
      Size(820, 1180)
    ]) {
      for (final scale in const [1.0, 1.5]) {
        testWidgets(
            'photo choice under header: ${style.name} $size scale $scale',
            (tester) async {
          final session = _choice(image(1));
          await pumpApp(tester,
              repository: session.repo,
              size: size,
              home: Scaffold(
                  body: MediaQuery.withClampedTextScaling(
                      minScaleFactor: scale,
                      maxScaleFactor: scale,
                      child: Column(children: [
                        const SizedBox(height: 100),
                        Expanded(
                            child: CardLookScope(
                                look: CardLook.forStyle(style),
                                child: FlashcardCardView(session: session))),
                      ]))));
          await tester.pump();

          final answer = tester.getRect(find.byType(PrimaryButton));
          final title = tester.getRect(find.text(session.exercise!.prompt));
          expect(title.bottom, lessThanOrEqualTo(answer.top),
              reason: 'the question is under the 顯示答案 dock');
          final options = find.byType(OutlinedButton);
          expect(options, findsNWidgets(session.exercise!.options.length));
          for (final option in tester.widgetList(options)) {
            final rect = tester.getRect(find.byWidget(option));
            expect(rect.bottom, lessThanOrEqualTo(answer.top),
                reason: 'an option is under the 顯示答案 dock');
          }
          session.dispose();
        });
      }
    }
  }
}
