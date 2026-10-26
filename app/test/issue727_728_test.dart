// 問題回報 #727: 拍照 shows a clean camera, not the last photo's words.
// 問題回報 #728: 我的意見回饋 shows 處理中／已處理 per sent report.
// 問題回報 #716: deleting a sent report deletes it on the server too.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/screens/camera_screen.dart';
import 'package:photo_english_app/screens/my_feedback_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/card_report.dart';
import 'package:photo_english_app/widgets/feedback_button.dart';
import 'package:photo_english_app/widgets/mobile/photo_widgets.dart';

import 'helpers.dart';

/// A server that numbers reports from 900 and answers status / delete.
class _Server {
  var next = 900;
  var statusCode = 200;
  var deleteCode = 200;
  String statusBody = '[]';
  final requests = <http.Request>[];

  late final client = MockClient((r) async {
    requests.add(r);
    if (r.method == 'POST') return http.Response('{"id": ${next++}}', 201);
    if (r.method == 'DELETE') return http.Response('{}', deleteCode);
    if (r.url.path == '/api/issues/status') {
      return http.Response(statusBody, statusCode);
    }
    return http.Response('nope', 404);
  });

  CardReportService service() =>
      CardReportService(client: client, remote: true, persist: false);
}

void main() {
  testWidgets('拍照 has no last-photo words pill or pinned last photo',
      (tester) async {
    await pumpApp(tester);
    await tester.pumpAndSettle();
    expect(find.byType(CameraScreen), findsOneWidget);
    final camera = find.byType(CameraScreen);
    expect(find.descendant(of: camera, matching: find.byType(PinnedPhoto)),
        findsNothing);
    expect(find.text('最近一張照片的單字'), findsNothing);
    expect(find.text('查看這張照片的單字'), findsNothing);
    expect(find.textContaining('點照片看單字'), findsNothing);
  });

  test('refreshStatus reads 處理中／已處理 and degrades quietly', () async {
    final server = _Server();
    final service = server.service();
    await service.submitIssue(feedbackIssue(page: 'a', note: '1'), apiKey: 'k');
    await service.submitIssue(feedbackIssue(page: 'b', note: '2'));

    // No status endpoint yet (404): nothing changes.
    server.statusCode = 404;
    expect(await service.refreshStatus(), isFalse);
    expect((await service.history()).map((r) => r.handled), [null, null]);

    server.statusCode = 200;
    server.statusBody =
        '[{"id": 900, "status": "fixed"}, {"id": 901, "status": "in_progress"}]';
    expect(await service.refreshStatus(apiKey: 'k'), isTrue);
    final get = server.requests.last;
    expect(get.url.queryParameters['ids'], '900,901');
    expect(get.headers['X-API-Key'], 'k');
    final list = await service.history();
    expect(
        {for (final r in list) r.issueNo: r.handled}, {900: true, 901: false});

    // Garbage keeps what is known.
    server.statusBody = '<html>';
    expect(await service.refreshStatus(), isFalse);
    expect((await service.history()).first.status, 'in_progress');

    // The status survives a JSON round trip.
    final back = FeedbackRecord.fromJson(list.last.toJson())!;
    expect(back.status, 'fixed');
  });

  test('deleting a sent report asks the server; a refusal keeps it', () async {
    final server = _Server();
    final service = server.service();
    await service.submitIssue(feedbackIssue(page: 'a', note: '1'));
    final id = (await service.history()).single.id;

    server.deleteCode = 401;
    expect(await service.delete(id, apiKey: 'k'), isFalse);
    expect(await service.history(), hasLength(1));
    final del = server.requests.last;
    expect((del.method, del.url.path, del.headers['X-API-Key']),
        ('DELETE', '/api/issues/900', 'k'));

    server.deleteCode = 204;
    expect(await service.delete(id, apiKey: 'k'), isTrue);
    expect(await service.history(), isEmpty);
  });

  testWidgets('我的意見回饋 shows 處理中／已處理 and deletes on the server', (tester) async {
    final server = _Server()
      ..statusBody =
          '[{"id": 900, "status": "open"}, {"id": 901, "status": "fixed"}]';
    final service = server.service();
    await tester.runAsync(() async {
      await service.submitIssue(feedbackIssue(page: 'a', note: '1'));
      await service.submitIssue(feedbackIssue(page: 'b', note: '2'));
    });
    await pumpApp(tester,
        settings: AppSettings.inMemory()..apiKey = 'k',
        home: MyFeedbackScreen(service: service));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pumpAndSettle();
    expect(find.text('處理中 · #900'), findsOneWidget);
    expect(find.text('已處理 · #901'), findsOneWidget);

    final records = await tester.runAsync(service.history);
    final first = records!.firstWhere((r) => r.issueNo == 900);

    // The server refuses: the learner is told and the record stays.
    server.deleteCode = 500;
    await tester.tap(find.byKey(ValueKey('feedback-delete-${first.id}')));
    await tester.pumpAndSettle();
    expect(find.text('會從這支手機和問題回報一起刪除。'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('feedback-delete-confirm')));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pumpAndSettle();
    expect(find.text('沒辦法從問題回報刪除'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('feedback-delete-keep')));
    await tester.pumpAndSettle();
    expect(find.text('處理中 · #900'), findsOneWidget);

    // Accepted: gone here too.
    server.deleteCode = 200;
    await tester.tap(find.byKey(ValueKey('feedback-delete-${first.id}')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('feedback-delete-confirm')));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pumpAndSettle();
    expect(find.text('處理中 · #900'), findsNothing);
    expect(find.text('已處理 · #901'), findsOneWidget);
    expect(server.requests.where((r) => r.method == 'DELETE'), hasLength(2));
  });

  testWidgets('the new states speak French', (tester) async {
    final server = _Server()..statusBody = '[{"id": 900, "status": "fixed"}]';
    final service = server.service();
    await tester.runAsync(
        () => service.submitIssue(feedbackIssue(page: 'a', note: '1')));
    await pumpApp(tester,
        settings: AppSettings.inMemory()..nativeLanguage = 'fr',
        home: MyFeedbackScreen(service: service));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pumpAndSettle();
    expect(find.text('Traité · #900'), findsOneWidget);
  });
}
