import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/onboarding_screen.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';

import 'helpers.dart';

void main() {
  testWidgets('screen readers read a button once (問題回報 #26)', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(MaterialApp(
      theme: MobileTheme.light(),
      home: OnboardingScreen(lexicon: testLexicon(), onDone: (_) {}),
    ));
    expect(find.bySemanticsLabel('下一步'), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('下一步.*下一步')), findsNothing);
    await tester.tap(find.text('下一步'));
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('會基礎單字，認得日常生活的簡單單字'), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('會基礎單字.*會基礎單字')), findsNothing);
    handle.dispose();
  });
}
