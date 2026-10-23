// 問題回報 #664: a 意見回饋 carries a screenshot of the screen (the learner
// can leave it out).
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/services/card_report.dart';
import 'package:photo_english_app/widgets/feedback_button.dart';

// A 1×1 PNG.
final _png = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==');

void main() {
  test('the issue carries the screenshot as a data URL', () {
    final issue = feedbackIssue(
        page: '照片詳情', note: '標籤跑出去', screenshot: Uint8List.fromList(_png));
    expect(issue['screenshot'], startsWith('data:image/png;base64,'));
    expect(issue['detail'], contains('截圖：有'));
    expect(
        feedbackIssue(page: 'p', note: 'n').containsKey('screenshot'), isFalse);
  });

  testWidgets('the form shows the screenshot and can leave it out',
      (tester) async {
    final service = CardReportService(remote: false, persist: false);
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: Builder(
                builder: (context) => TextButton(
                    onPressed: () => showFeedbackDialog(context,
                        service: service, screenshot: Uint8List.fromList(_png)),
                    child: const Text('open'))))));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('feedback-screenshot')), findsOneWidget);
    expect(find.text('附上這個畫面的截圖'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('feedback-attach')));
    await tester.pump();
    await tester.enterText(
        find.byKey(const ValueKey('feedback-note')), '標籤跑出去');
    await tester.tap(find.text('送出'));
    await tester.pumpAndSettle();
    expect(service.pendingCount, 1);
  });
}
