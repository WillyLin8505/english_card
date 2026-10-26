// 問題回報 #701: 設定 → 我的意見回饋 lists what this phone sent (title, time,
// sent / still queued, #number, screenshot) and lets the learner delete it.
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/app/app_scope.dart';
import 'package:photo_english_app/screens/my_feedback_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/card_report.dart';
import 'package:photo_english_app/widgets/feedback_button.dart';

import 'helpers.dart';

// A 1×1 PNG.
final _png = Uint8List.fromList(base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='));

void main() {
  test('a sent report keeps its 問題回報 number; a refused one stays queued',
      () async {
    var status = 201;
    final posted = <String>[];
    final service = CardReportService(
        remote: true,
        persist: false,
        now: () => DateTime(2026, 10, 26, 9, 5),
        client: MockClient((r) async {
          posted.add(r.body);
          return http.Response('{"id": 812, "title": "x"}', status);
        }));
    expect(
        await service.submitIssue(
            feedbackIssue(page: '設定', note: '要清單', screenshot: _png)),
        isTrue);
    status = 503;
    expect(await service.submitIssue(feedbackIssue(page: '設定', note: '排隊')),
        isFalse);

    final list = await service.history();
    expect(list, hasLength(2));
    // Newest first.
    expect(list.first.title, '[意見回饋] 設定：排隊');
    expect(list.first.queued, isTrue);
    expect(list.first.issueNo, isNull);
    expect(list.last.queued, isFalse);
    expect(list.last.issueNo, 812);
    expect(list.last.screenshotBytes, _png);
    expect(list.last.createdAt, DateTime(2026, 10, 26, 9, 5));
    // The server gets the issue itself, not the local record id.
    expect(jsonDecode(posted.first).containsKey('id'), isFalse);

    // Deleting the queued one means it is never sent.
    await service.delete(list.first.id);
    expect(service.pendingCount, 0);
    status = 201;
    posted.clear();
    expect(await service.flush(), 0);
    expect(posted, isEmpty);
    expect((await service.history()).map((r) => r.issueNo), [812]);
  });

  test('the record survives a JSON round trip', () {
    final r = FeedbackRecord(
        id: 'a-1',
        title: '[卡片回報] apple（noun）翻譯錯',
        createdAt: DateTime(2026, 10, 26, 14, 45),
        queued: false,
        issueNo: 701,
        screenshot: 'data:image/png;base64,${base64Encode(_png)}');
    final back = FeedbackRecord.fromJson(jsonDecode(jsonEncode(r.toJson())))!;
    expect((back.id, back.title, back.createdAt, back.queued, back.issueNo),
        (r.id, r.title, r.createdAt, false, 701));
    expect(back.screenshotBytes, _png);
    expect(FeedbackRecord.fromJson('nope'), isNull);
  });

  testWidgets('設定 opens 我的意見回饋; a record can be deleted', (tester) async {
    final service = CardReportService.instance;
    await service.submitIssue(
        feedbackIssue(page: '設定', note: '我需要一個清單', screenshot: _png));
    addTearDown(() async {
      for (final r in await service.history()) {
        await service.delete(r.id);
      }
    });
    await pumpApp(tester,
        initialTab: AppTab.settings, size: const Size(402, 1600));
    final button = find.byKey(const ValueKey('my-feedback-button'));
    await tester.scrollUntilVisible(button, 300);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -200));
    await tester.pumpAndSettle();
    await tester.tap(button);
    await tester.pumpAndSettle();

    expect(find.byType(MyFeedbackScreen), findsOneWidget);
    expect(find.text('[意見回饋] 設定：我需要一個清單'), findsOneWidget);
    expect(find.text('還在排隊，連上網路後會送出'), findsOneWidget);
    final id = (await service.history()).single.id;
    expect(find.byKey(ValueKey('feedback-thumb-$id')), findsOneWidget);

    await tester.tap(find.byKey(ValueKey('feedback-delete-$id')));
    await tester.pumpAndSettle();
    expect(find.text('刪除這筆紀錄？'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('feedback-delete-confirm')));
    await tester.pumpAndSettle();
    expect(find.text('[意見回饋] 設定：我需要一個清單'), findsNothing);
    expect(find.text('還沒有送過意見回饋'), findsOneWidget);
    expect(service.pendingCount, 0);
  });

  testWidgets('the list speaks French for a French speaker', (tester) async {
    final service = CardReportService(remote: false, persist: false);
    await service.submitIssue(feedbackIssue(page: 'p', note: 'n'));
    await pumpApp(tester,
        settings: AppSettings.inMemory()..nativeLanguage = 'fr',
        home: MyFeedbackScreen(service: service));
    await tester.pumpAndSettle();
    expect(find.text('Mes commentaires'), findsOneWidget);
    expect(find.text('En attente ; envoyé dès la connexion'), findsOneWidget);
    expect(find.textContaining(RegExp(r'[一-鿿]')), findsOneWidget,
        reason: 'only the sent title keeps the learner’s words');
  });
}
