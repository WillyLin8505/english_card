import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/onboarding_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';

import 'helpers.dart';

/// 卡 #737 (問題回報 #882): French has only an English-native dictionary.
void main() {
  test('pair rule: French needs English native, English any', () {
    expect(languagePairAvailable('fr', 'zh-TW'), isFalse);
    expect(languagePairAvailable('fr', 'en'), isTrue);
    expect(languagePairAvailable('en', 'zh-TW'), isTrue);
    expect(languagePairAvailable('en', 'fr'), isTrue);
  });

  test('pair rule opens when the 法→繁中 pack is added (#738)', () {
    frenchNativeLanguages.add('zh-TW');
    addTearDown(() => frenchNativeLanguages.remove('zh-TW'));
    expect(languagePairAvailable('fr', 'zh-TW'), isTrue);
  });

  Future<void> pump(WidgetTester tester) async {
    tester.view.physicalSize = const Size(402, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      theme: MobileTheme.light(),
      home: OnboardingScreen(
          lexicon: testLexicon(), onDone: (_) {}, uiLanguage: 'zh-TW'),
    ));
  }

  testWidgets('onboarding: 繁中母語 cannot pick French', (tester) async {
    await pump(tester);
    expect(find.text(frenchNeedsEnglishNative), findsOneWidget);
    await tester.tap(find.text('法文（Français）').first);
    await tester.pump();
    expect(find.text('你對英文熟悉嗎？'), findsNothing);
    await tester.tap(find.text('下一步'));
    await tester.pumpAndSettle();
    expect(find.text('你對英文熟悉嗎？'), findsOneWidget);
  });

  testWidgets('onboarding: English native can pick French', (tester) async {
    await pump(tester);
    await tester.tap(find.text('英文（English）').last);
    await tester.pump();
    // French is now the learning language; only the 繁中 native row is shut.
    // The UI follows the native language now, so the note is in English
    // (問題回報 #1120).
    expect(find.text(frenchNeedsEnglishNative), findsNothing);
    expect(
        find.text(
            'French is currently only available with English as the native language'),
        findsOneWidget);
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    expect(find.text('How well do you know French?'), findsOneWidget);
  });
}
