import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/onboarding_screen.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';
import 'package:photo_english_app/widgets/mobile/common.dart';

import 'helpers.dart';

/// 卡 #876 (問題回報 #1147): on a short phone (375×667) the onboarding text
/// scrolls above the Next button; scrolled to the end, every line must sit
/// fully inside the scroll area, above the button.
void main() {
  for (final lang in ['en', 'fr', 'zh-TW']) {
    testWidgets('短螢幕新手引導不被按鈕蓋到 ($lang 375×667)', (tester) async {
      tester.view.physicalSize = const Size(375, 667);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        theme: MobileTheme.light(),
        home: OnboardingScreen(
            lexicon: testLexicon(), onDone: (_) {}, uiLanguage: lang),
      ));
      await tester.pumpAndSettle();

      // Pages reached by tapping the primary button while it is enabled.
      for (var step = 0; step < 2; step++) {
        final texts = find.byType(Text);

        // Scrolled to the end: every line sits inside the scroll area.
        final list = find.byType(ListView);
        if (list.evaluate().isNotEmpty) {
          await tester.drag(list.first, const Offset(0, -3000));
          await tester.pumpAndSettle();
          final area = tester.getRect(list.first);
          for (final el in texts.evaluate()) {
            final r = tester.getRect(find.byWidget(el.widget));
            if (r.top < area.top || r.top > area.bottom) continue;
            expect(r.bottom <= area.bottom + 0.5, isTrue,
                reason: '$lang step $step: "${(el.widget as Text).data}" '
                    'cut at ${r.bottom} > ${area.bottom}');
          }
        }

        await tester.tap(find.byType(PrimaryButton).first);
        await tester.pumpAndSettle();
      }
    });
  }
}
