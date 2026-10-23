import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/onboarding_screen.dart';
import 'package:photo_english_app/services/card_report.dart';
import 'package:photo_english_app/services/feedback_context.dart';
import 'package:photo_english_app/widgets/feedback_button.dart';

import 'helpers.dart';

/// 問題回報 #587: every page has the 意見回饋 entry.
void main() {
  final button = find.byKey(const ValueKey('feedback-button'));

  test('issue title, reporter and detail', () {
    final issue = feedbackIssue(
        page: '單字詳情',
        note: '一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十多出來',
        subject: 'w1',
        language: 'en');
    expect(issue['title'], '[意見回饋] 單字詳情：一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十');
    expect(issue['reporter'], 'App 使用者');
    expect(issue['detail'], allOf(contains('w1'), contains('App 版本')));
  });

  testWidgets('every tab and pushed page has the entry', (tester) async {
    final seen = <http.Request>[];
    final service = CardReportService(
        remote: true,
        persist: false,
        client: MockClient((r) async {
          seen.add(r);
          return http.Response('{}', 200);
        }));
    final app = await pumpApp(tester, reports: service);
    final pages = <String>[];
    for (final tab in AppTab.values) {
      app.navigator.selectTab(tab);
      await tester.pumpAndSettle();
      expect(button, findsOneWidget, reason: tab.name);
      pages.add(FeedbackContext.instance.page);
    }
    expect(pages, ['拍照', '相片冊', '複習', '單字本', '設定']);

    final photoId = app.repository.photos.first.id;
    app.navigator.openPhoto(photoId);
    await tester.pumpAndSettle();
    expect(button, findsOneWidget);
    expect(FeedbackContext.instance.page, '照片詳情');
    expect(FeedbackContext.instance.subject, photoId);

    app.navigator.openWord(app.repository.entryByWord('apple')!.id);
    await tester.pumpAndSettle();
    expect(button, findsOneWidget);
    expect(FeedbackContext.instance.page, '單字詳情');

    await tester.tap(button);
    // The screenshot is given up to 2.5 s (#669); in a test it never comes.
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('feedback-note')), findsOneWidget);
    await tester.enterText(find.byKey(const ValueKey('feedback-note')), '字太小');
    await tester.tap(find.text('送出'));
    await tester.pumpAndSettle();
    final body = jsonDecode(seen.single.body) as Map<String, dynamic>;
    expect(body['title'], '[意見回饋] 單字詳情：字太小');
    expect(body['reporter'], 'App 使用者');
  });

  testWidgets('新手引導 has the entry', (tester) async {
    FeedbackContext.instance.tab = null;
    final key = GlobalKey<NavigatorState>();
    await tester.pumpWidget(MaterialApp(
      navigatorKey: key,
      builder: (context, child) =>
          FeedbackOverlay(navigatorKey: key, child: child!),
      home: OnboardingScreen(lexicon: testLexicon(), onDone: (_) {}),
    ));
    expect(button, findsOneWidget);
    expect(FeedbackContext.instance.page, '新手引導');
  });
}
