import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/l10n/ui_catalog.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/widgets/tab_tutorial.dart';

import 'helpers.dart';

// 卡 #893: first-visit tutorial per tab, skippable, re-readable from 設定.
void main() {
  test('each tab remembers its own tutorial; reset one or all', () {
    final s = AppSettings.inMemory(tutorialsSeen: false);
    for (final t in AppTab.values) {
      expect(s.tutorialSeen(t.name), isFalse);
    }
    s.markTutorialSeen('camera');
    expect(s.tutorialSeen('camera'), isTrue);
    expect(s.tutorialSeen('album'), isFalse);
    s.markTutorialSeen('album');
    s.resetTutorials('camera');
    expect(s.tutorialSeen('camera'), isFalse);
    expect(s.tutorialSeen('album'), isTrue);
    s.resetTutorials();
    expect(s.tutorialSeen('album'), isFalse);
  });

  test('every tab has steps and every tutorial text has en and fr', () {
    final cjk = RegExp(r'[一-鿿]');
    expect(tabTutorials.keys.toSet(), AppTab.values.toSet());
    final texts = [
      for (final t in AppTab.values) ...[
        ...tabTutorials[t]!,
        tabTutorialTitles[t]!,
        tabTutorialNames[t]!,
      ],
      '全部重看',
      '使用教學',
      '切到各分頁時會再顯示教學',
      '每個分頁第一次進入會顯示教學。想再看，選分頁或全部重看。',
    ];
    for (final source in texts) {
      for (final lang in const ['en', 'fr']) {
        expect(cjk.hasMatch(translateUi(source, lang)), isFalse,
            reason: '$lang: $source');
      }
    }
  });

  for (final height in [320.0, 600.0]) {
    testWidgets('overlay steps through and can be skipped at height $height',
        (tester) async {
      tester.view.physicalSize = Size(360, height);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      var done = 0;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Align(
            alignment: Alignment.bottomCenter,
            child: TabTutorialOverlay(tab: AppTab.review, onDone: () => done++),
          ),
        ),
      ));
      expect(find.byKey(const ValueKey('tab-tutorial')), findsOneWidget);
      expect(find.text('1/3'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('tab-tutorial-next')));
      await tester.pump();
      expect(find.text('2/3'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('tab-tutorial-next')));
      await tester.pump();
      expect(find.text('知道了'), findsOneWidget);
      expect(done, 0);
      await tester.tap(find.byKey(const ValueKey('tab-tutorial-next')));
      expect(done, 1);
      await tester.tap(find.byKey(const ValueKey('tab-tutorial-skip')));
      expect(done, 2);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('shell shows a tab tutorial once, after a short delay',
      (tester) async {
    final settings = AppSettings.inMemory(tutorialsSeen: false);
    final app = await pumpApp(tester, settings: settings);
    const tutorial = ValueKey('tab-tutorial');
    expect(find.byKey(tutorial), findsNothing);
    await tester.pump(const Duration(milliseconds: 1600));
    expect(find.byKey(tutorial), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('tab-tutorial-skip')));
    await tester.pump();
    expect(find.byKey(tutorial), findsNothing);
    expect(settings.tutorialSeen('camera'), isTrue);
    expect(settings.tutorialSeen('album'), isFalse);
    app.navigator.selectTab(AppTab.album);
    await tester.pump();
    expect(find.byKey(tutorial), findsOneWidget);
    app.navigator.selectTab(AppTab.camera);
    await tester.pump();
    expect(find.byKey(tutorial), findsNothing);
  });
}
