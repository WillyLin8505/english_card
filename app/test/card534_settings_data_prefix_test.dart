// 問題回報 #572: with one learning language the 資料 stats row has no
// 「英文（English）：」 prefix; a second learning language brings it back.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'helpers.dart';

void main() {
  testWidgets('one learning language: stats row without language prefix',
      (tester) async {
    await pumpApp(tester,
        initialTab: AppTab.settings, size: const Size(402, 2400));
    expect(find.textContaining('英文（English）：'), findsNothing);
    expect(find.textContaining(RegExp(r'^\S+ 個單字 · ')), findsOneWidget);
  });

  testWidgets('two learning languages: stats row names the language',
      (tester) async {
    availableLearningLanguages.add('fr');
    addTearDown(() => availableLearningLanguages.remove('fr'));
    await pumpApp(tester,
        initialTab: AppTab.settings, size: const Size(402, 2400));
    expect(find.textContaining('英文（English）：'), findsOneWidget);
  });
}
