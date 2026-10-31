import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/onboarding_screen.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';

import 'helpers.dart';

// 問題回報 #1147: on 375×667 the last line of each onboarding page must end
// above the Next button once the list is scrolled to the end.
void main() {
  for (final lang in const ['en', 'fr', 'zh']) {
    testWidgets('onboarding last line clear of the button ($lang, 375×667)',
        (tester) async {
      tester.view.physicalSize = const Size(375, 667);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        theme: MobileTheme.light(),
        home: OnboardingScreen(
            lexicon: testLexicon(), onDone: (_) {}, uiLanguage: lang),
      ));
      for (var page = 0; page < 3; page++) {
        final list = find.byType(ListView);
        final scroll = tester.state<ScrollableState>(
            find.descendant(of: list, matching: find.byType(Scrollable)));
        scroll.position.jumpTo(scroll.position.maxScrollExtent);
        await tester.pump();
        final button = tester.getTopLeft(find.byType(PrimaryButton).first).dy;
        double lowest = 0;
        for (final t in tester.widgetList<RichText>(
            find.descendant(of: list, matching: find.byType(RichText)))) {
          final box = tester.renderObject<RenderBox>(find.byWidget(t));
          lowest = lowest > box.localToGlobal(Offset(0, box.size.height)).dy
              ? lowest
              : box.localToGlobal(Offset(0, box.size.height)).dy;
        }
        expect(lowest, lessThanOrEqualTo(button - 8), reason: 'page $page');
        expect(tester.takeException(), isNull);
        if (page == 1) {
          await tester.tap(find.byType(Tap).at(1));
          await tester.pump();
        }
        await tester.tap(find.byType(PrimaryButton).first);
        await tester.pumpAndSettle();
      }
    });
  }
}
