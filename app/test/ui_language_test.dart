import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';
import 'package:photo_english_app/main.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/screens/onboarding_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/photo_store.dart';
import 'package:photo_english_app/services/speaker.dart';

import 'helpers.dart';

void main() {
  testWidgets(
      'native-language chip updates settings, retained tabs and semantics',
      (tester) async {
    final semantics = tester.ensureSemantics();
    final app = await pumpApp(tester,
        initialTab: AppTab.settings, size: const Size(360, 800));
    expect(find.text('設定'), findsWidgets);
    await tester.tap(find.widgetWithText(ChoiceChip, '法文（Français）'));
    await tester.pumpAndSettle();
    expect(app.settings.nativeLanguage, 'fr');
    expect(find.text('Langue maternelle'), findsOneWidget);
    expect(find.text('Réglages'), findsWidgets);
    expect(find.bySemanticsLabel('Révision'), findsOneWidget);
    expect(find.text('設定'), findsNothing);

    await tester.tap(find.text('Mots'));
    await tester.pumpAndSettle();
    expect(find.text('Mes mots'), findsOneWidget);
    expect(find.text('Ajouter un mot'), findsOneWidget);
    // Native French: the meaning language is French, not Chinese (#495).
    expect(find.text('Rechercher en anglais ou en français'), findsOneWidget);
    await tester.tap(find.text('Ajouter un mot'));
    await tester.pumpAndSettle();
    expect(find.text('Annuler'), findsOneWidget);
    await tester.enterText(find.byType(TextField).last, '設定');
    app.settings.nativeLanguage = 'en';
    await tester.pumpAndSettle();
    expect(find.text('Cancel'), findsOneWidget);
    expect(find.text('設定'), findsOneWidget,
        reason: 'learner input must not be translated');
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(find.text('My words'), findsOneWidget);
    await tester.tap(find.text('Review'));
    await tester.pumpAndSettle();
    expect(find.text('Which one to review?'), findsOneWidget);
    expect(find.text('All together'), findsOneWidget);
    app.settings.nativeLanguage = 'zh-TW';
    await tester.pumpAndSettle();
    expect(find.text('想複習哪一本？'), findsOneWidget);
    semantics.dispose();
    expect(tester.takeException(), isNull);
  });

  testWidgets('database labels change in place with native language',
      (tester) async {
    final app =
        await pumpApp(tester, initialTab: AppTab.words, databaseLibrary: true);
    expect(find.text('資料庫'), findsOneWidget);
    app.settings.nativeLanguage = 'fr';
    await tester.pump();
    expect(find.text('Base de données'), findsOneWidget);
    expect(find.text('Mes mots'), findsOneWidget);
    app.settings.nativeLanguage = 'en';
    await tester.pump();
    expect(find.text('Database'), findsOneWidget);
    expect(find.text('My words'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'review controls change language while content and grades retain their pipeline',
      (tester) async {
    final app = await pumpApp(tester,
        initialTab: AppTab.review,
        settings: AppSettings.inMemory(nativeLanguage: 'fr'));
    await tester.tap(find.text('Tout'));
    await tester.pumpAndSettle();
    expect(find.text('Afficher la réponse'), findsOneWidget);
    await tester.tap(find.text('Afficher la réponse'));
    await tester.pumpAndSettle();
    for (final rating in Rating.values) {
      expect(find.text(rating.labelIn('fr')), findsOneWidget);
    }
    app.settings.nativeLanguage = 'en';
    await tester.pumpAndSettle();
    for (final rating in Rating.values) {
      expect(find.text(rating.labelIn('en')), findsOneWidget);
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('real app updates Material locale without resetting navigation',
      (tester) async {
    tester.view.physicalSize = const Size(402, 874);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final settings = AppSettings.inMemory();
    await tester.pumpWidget(PhotoEnglishApp(
        repository: testRepository(),
        settings: settings,
        photoStore: PhotoStore.inMemory(),
        lexicon: testLexicon(),
        runWorkers: false,
        speaker: SilentSpeaker()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('設定').last);
    await tester.pumpAndSettle();
    settings.nativeLanguage = 'fr';
    await tester.pumpAndSettle();
    expect(tester.widget<MaterialApp>(find.byType(MaterialApp)).locale,
        const Locale('fr'));
    expect(find.text('Langue maternelle'), findsOneWidget);
    settings.nativeLanguage = 'en';
    await tester.pumpAndSettle();
    expect(tester.widget<MaterialApp>(find.byType(MaterialApp)).locale,
        const Locale('en'));
    expect(find.text('Native language'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('onboarding previews chosen native language before finishing',
      (tester) async {
    tester.view.physicalSize = const Size(402, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
        home: OnboardingScreen(lexicon: testLexicon(), onDone: (_) {})));
    await tester.tap(find.text('法文（Français）'));
    await tester.pumpAndSettle();
    expect(find.text('Suivant'), findsOneWidget);
    await tester.tap(find.text('Suivant'));
    await tester.pumpAndSettle();
    expect(find.text('Quel est votre niveau d’anglais ?'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('dynamic UI copy preserves values and unknown content', () {
    expect(translateUi('第 1–20 個，共 100 個', 'en'), '1–20 of 100');
    expect(translateUi('資料庫圖片（3）', 'fr'), 'Photos du dictionnaire (3)');
    expect(translateUi('你的答案：設定', 'en'), 'Your answer: 設定');
    expect(translateUi('a learner’s custom text', 'fr'),
        'a learner’s custom text');
    expect(translateUi('設定', 'de'), '設定');
  });

  test('copy names the learning language (問題回報 #495)', () {
    // English native, learning French: nothing says English words.
    expect(translateUi('搜尋{L}或{N}', 'en', learning: 'fr'),
        'Search French or English');
    expect(translateUi('點標籤查看{N}意思與例句。', 'en'),
        'Tap a label for its English meaning and examples.');
    expect(translateUi('拍照或選一張照片，找出生活中的{L}單字', 'en', learning: 'fr'),
        'Take or choose a photo to find French words around you');
    expect(translateUi('搜尋圖片上的{L}或{N}標籤', 'fr', learning: 'en'),
        'Rechercher les étiquettes en anglais ou en français');
    // Chinese native, learning French.
    expect(translateUi('搜尋{L}或{N}', 'zh-TW', learning: 'fr'), '搜尋法文或中文');
    expect(translateUi('點標籤查看{N}意思與例句。', 'zh-TW', learning: 'fr'),
        '點標籤查看中文意思與例句。');
    expect(translateUi('搜尋{L}或{N}', 'zh-TW'), '搜尋英文或中文');
  });

  test('catalog copy has no unfilled placeholders', () {
    for (final entry in uiCatalog.entries) {
      for (final learning in const ['en', 'fr']) {
        final out = translateUi(entry.key, 'en', learning: learning);
        expect(out.contains('{L}') || out.contains('{N}'), isFalse,
            reason: entry.key);
      }
    }
    for (final entry in uiCatalog.entries) {
      expect(entry.value.$1.trim(), isNotEmpty, reason: entry.key);
      expect(entry.value.$2.trim(), isNotEmpty, reason: entry.key);
    }
  });
}
