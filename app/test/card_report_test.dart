import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/services/card_report.dart';

import 'helpers.dart';
import 'review_archive_session_test.dart' show smallRepo;

void main() {
  const report = CardReport(
      kind: 'translation',
      note: '意思不對',
      word: 'apple',
      pos: 'noun',
      meaning: '蘋果',
      photoId: 'p1',
      cardType: 'recall 背面');

  test('issue carries the card, 卡片回報 title and App 使用者 reporter', () {
    final issue = report.toIssue();
    expect(issue['title'], startsWith('[卡片回報]'));
    expect(issue['reporter'], 'App 使用者');
    final detail = issue['detail'] as String;
    for (final part in [
      'apple',
      'noun',
      '蘋果',
      'p1',
      'recall 背面',
      '意思不對',
      'App 版本'
    ]) {
      expect(detail, contains(part));
    }
  });

  test('sends with the key, keeps the report when the server refuses',
      () async {
    final seen = <http.Request>[];
    var status = 401;
    final service = CardReportService(
        remote: true,
        persist: false,
        client: MockClient((r) async {
          seen.add(r);
          return http.Response('{}', status);
        }));
    expect(await service.submit(report), false);
    expect(service.pendingCount, 1);
    status = 200;
    expect(await service.flush(apiKey: 'k'), 0);
    expect(seen.last.headers['X-API-Key'], 'k');
    expect(seen.last.url.path, '/api/issues');
    expect(jsonDecode(seen.last.body)['reporter'], 'App 使用者');
  });

  testWidgets('review card has a report button that opens the dialog',
      (tester) async {
    await pumpApp(tester,
        repository: smallRepo(2),
        initialTab: AppTab.review,
        size: const Size(402, 1400));
    await tester.tap(find.text('開始複習'));
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('回報此卡片'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('回報此卡片'));
    await tester.pumpAndSettle();
    expect(find.text('哪裡有問題？'), findsOneWidget);
    for (final k in CardReport.kinds) {
      expect(find.text(k.$2), findsOneWidget);
    }
    await tester.tap(find.text('圖片不對'));
    await tester.enterText(
        find.descendant(
            of: find.byType(AlertDialog), matching: find.byType(TextField)),
        '照片不是這個字');
    await tester.tap(find.text('送出'));
    await tester.pumpAndSettle();
    expect(find.text('哪裡有問題？'), findsNothing);
    expect(find.textContaining('已存在這支手機'), findsOneWidget);
    expect(CardReportService.instance.pendingCount, 1);
  });
}
