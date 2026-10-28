import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/screens/onboarding_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/theme/mobile_theme.dart';

import 'helpers.dart';

/// 問題回報 #496: the first page speaks the device's language, and an English
/// speaker can pick French to learn once French is opened.
void main() {
  Future<OnboardingResult? Function()> pump(WidgetTester tester,
      {required String uiLanguage}) async {
    tester.view.physicalSize = const Size(402, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    OnboardingResult? result;
    await tester.pumpWidget(MaterialApp(
      theme: MobileTheme.light(),
      home: OnboardingScreen(
          lexicon: testLexicon(),
          onDone: (r) => result = r,
          uiLanguage: uiLanguage),
    ));
    return () => result;
  }

  void openFrench() {
    final added = availableLearningLanguages.add('fr');
    addTearDown(() {
      if (added) availableLearningLanguages.remove('fr');
    });
  }

  test('device locale → supported language', () {
    expect(deviceLanguage(const Locale('zh', 'TW')), 'zh-TW');
    expect(deviceLanguage(const Locale('zh', 'CN')), 'zh-TW');
    expect(deviceLanguage(const Locale('fr', 'CA')), 'fr');
    expect(deviceLanguage(const Locale('en', 'US')), 'en');
    expect(deviceLanguage(const Locale('de')), 'en');
  });

  test('every check list has three words for each level', () {
    for (final words in placementCheckWords.values) {
      for (final l in ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']) {
        expect(words[l], hasLength(3), reason: l);
      }
    }
  });

  testWidgets('an English phone sees English before choosing (French closed)',
      (tester) async {
    closeFrench();
    final result = await pump(tester, uiLanguage: 'en');
    expect(find.text('Welcome to photo vocabulary'), findsOneWidget);
    expect(find.text('歡迎使用拍照學單字'), findsNothing);
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Know basic words'));
    await tester.pump();
    await tester.tap(find.text('Get started'));
    expect((result()!.learningLanguage, result()!.nativeLanguage),
        ('en', 'zh-TW'));
  });

  testWidgets('a French phone gets French as native, English to learn',
      (tester) async {
    final result = await pump(tester, uiLanguage: 'fr');
    expect(
        find.text('Bienvenue dans l’apprentissage par photos'), findsOneWidget);
    await tester.tap(find.text('Suivant'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Je connais les bases'));
    await tester.pump();
    await tester.tap(find.text('Commencer'));
    expect(
        (result()!.learningLanguage, result()!.nativeLanguage), ('en', 'fr'));
  });

  testWidgets(
      'French open: English phone → learn French, native English, '
      'French check words', (tester) async {
    openFrench();
    final result = await pump(tester, uiLanguage: 'en');
    expect(find.text('Welcome to photo vocabulary'), findsOneWidget);
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    expect(find.text('How well do you know French?'), findsOneWidget);
    await tester.tap(find.text('Know basic words'));
    await tester.pump();
    await tester.tap(find.text('Try a vocabulary check (optional)'));
    await tester.pumpAndSettle();
    expect(find.text('pomme'), findsOneWidget);
    for (final w in ['pomme', 'livre']) {
      await tester.tap(find.text(w));
      await tester.pump();
    }
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('épaule'), findsOneWidget);
    await tester.tap(find.text('Finish check and start learning'));
    expect((
      result()!.learningLanguage,
      result()!.nativeLanguage,
      result()!.level,
      result()!.source
    ), (
      'fr',
      'en',
      'A1',
      'check'
    ));
  });

  testWidgets(
      'French open: learning the native language moves the native '
      'choice', (tester) async {
    openFrench();
    final result = await pump(tester, uiLanguage: 'fr');
    // Device French → native French, English to learn; now learn French.
    await tester.tap(find.text('Français').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Suivant'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Je connais les bases'));
    await tester.pump();
    await tester.tap(find.text('Commencer'));
    expect((result()!.learningLanguage, result()!.nativeLanguage),
        ('fr', 'en'));
  });
}
