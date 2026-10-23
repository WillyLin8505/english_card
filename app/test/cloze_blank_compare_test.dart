// 問題回報 #606: the 句子填空 blank shows how many letters (one underscore
// each, spaced so they can be counted) and the back compares your answer
// with the right one letter by letter.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/flashcard_screen.dart';
import 'package:photo_english_app/services/flashcard_session.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';

void main() {
  test('one spaced underscore per letter', () {
    expect(clozeBlank('apple'), '_ _ _ _ _');
    expect(clozeBlank('ice cream'), '_ _ _   _ _ _ _ _');
    expect(clozeBlank('well-known'), '_ _ _ _ - _ _ _ _ _');
  });

  test('letters that differ', () {
    expect(AnswerComparison.differences('chanje', 'change'),
        [false, false, false, false, true, false]);
    expect(
        AnswerComparison.differences('CHANGE', 'change'), everyElement(false));
    expect(AnswerComparison.differences('changed', 'change').last, isTrue);
  });

  testWidgets('a wrong letter is marked in both lines', (tester) async {
    await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
            body: AnswerComparison(submitted: 'chanje', answer: 'change'))));
    final spans = <TextSpan>[];
    for (final rich in tester.widgetList<RichText>(find.byType(RichText))) {
      rich.text.visitChildren((s) {
        if (s is TextSpan && s.text != null && s.text!.length == 1) {
          spans.add(s);
        }
        return true;
      });
    }
    final red = spans.where((s) => s.style?.color == MColors.againFg);
    expect(red.map((s) => s.text), ['j']);
    final green = spans.where((s) => s.style?.color == MColors.success);
    expect(green.map((s) => s.text), ['g']);
  });
}
