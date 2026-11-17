import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';

import 'package:photo_english_app/l10n/ui_text.dart';

import 'helpers.dart';

void main() {
  // 問題回報 #1659: after learning French (native English) the owner could
  // not get back to native 中文 / learning English.
  Finder chip(String label, int n) => find
      .byWidgetPredicate((w) =>
          w is ChoiceChip &&
          w.label is UiText &&
          (w.label as UiText).data == label)
      .at(n);

  Future<void> tapChip(WidgetTester t, Finder f) async {
    await t.ensureVisible(f);
    await t.pumpAndSettle();
    await t.tap(f);
    await t.pumpAndSettle();
  }

  Future<void> confirm(WidgetTester t) async {
    await t.tap(find.byWidgetPredicate((w) => w is UiText && w.data == '確定'));
    await t.pump();
    await t.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 300)));
    await t.pumpAndSettle();
  }

  for (final viaNative in [true, false]) {
    testWidgets(
        'en/zh-TW <-> fr/en twice, back via ${viaNative ? 'native' : 'learning'} chip',
        (tester) async {
      final app = await pumpApp(tester,
          initialTab: AppTab.settings, size: const Size(402, 2200));
      app.settings.nativeLanguage = 'zh-TW';
      app.settings.learningLanguage = 'en';
      await tester.pumpAndSettle();
      for (var round = 0; round < 2; round++) {
        // en/zh-TW -> fr/en: learning chip 法文 moves native to English.
        await tapChip(tester, chip('法文（Français）', 0));
        expect(
            find.byWidgetPredicate((w) => w is UiText && w.data == '切換學習語言？'),
            findsOneWidget);
        await confirm(tester);
        expect(app.settings.learningLanguage, 'fr');
        expect(app.settings.nativeLanguage, 'en');
        // fr/en -> en/zh-TW.
        if (viaNative) {
          await tapChip(tester, chip('繁體中文', 0));
        } else {
          await tapChip(tester, chip('英文（English）', 0));
        }
        expect(
            find.byWidgetPredicate((w) => w is UiText && w.data == '切換學習語言？'),
            findsOneWidget);
        await confirm(tester);
        expect(app.settings.learningLanguage, 'en');
        expect(app.settings.nativeLanguage, 'zh-TW');
      }
    });
  }
}
