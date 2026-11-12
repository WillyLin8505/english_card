import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/screens/onboarding_screen.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/event_report.dart';
import 'package:photo_english_app/services/usage_report.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

import 'helpers.dart';

/// Card #1009 (問題回報 #1530): nothing is sent before an explicit yes (5.1.1(ii)).
void main() {
  test('events: unanswered sends nothing, yes sends, withdrawn stops', () async {
    final settings = AppSettings.inMemory(onboarded: false);
    final bodies = <Map>[];
    EventReport.instance.attach(settings,
        client: MockClient((r) async {
          bodies.add(jsonDecode(r.body) as Map);
          return http.Response('{}', 200);
        }),
        baseUrl: 'https://x.test');
    expect(settings.anonymousEventsChoice, isNull);
    EventReport.instance.appStarted();
    EventReport.instance.once('first_photo');
    await Future<void>.delayed(Duration.zero);
    expect(bodies, isEmpty);
    expect(settings.usageValue('evt_queue'), isNull);

    settings.anonymousEvents = true;
    EventReport.instance.once('install');
    await Future<void>.delayed(Duration.zero);
    expect(bodies.length, 1);

    settings.anonymousEvents = false;
    EventReport.instance.once('first_review');
    await Future<void>.delayed(Duration.zero);
    expect(bodies.length, 1);
  });

  test('account stats: not sent until agreed, not after withdrawn, row deleted',
      () async {
    final calls = <String>[];
    final settings = AppSettings.inMemory(taggingUrl: 'https://x.test')
      ..setCloudAccount('tok', 'a@x.com');
    final report = UsageReport(settings, WordDatabaseRepository(),
        client: MockClient((r) async {
          calls.add('${r.method} ${r.url.path}');
          return http.Response('{}', 200);
        }),
        baseUrl: 'https://x.test');
    expect(settings.accountStatsChoice, isNull);
    expect(await report.sendIfDue(), isFalse);
    expect(calls, isEmpty);

    settings.accountStats = true;
    expect(await report.sendIfDue(), isTrue);
    expect(calls, ['POST /api/account/stats']);

    settings.accountStats = false;
    expect(await report.sendIfDue(force: true), isFalse);
    expect(await report.deleteRemote(), isTrue);
    expect(calls.last, 'DELETE /api/account/stats');
  });

  test('a failed delete is retried at the next start', () async {
    var ok = false;
    final calls = <String>[];
    final settings = AppSettings.inMemory(taggingUrl: 'https://x.test')
      ..setCloudAccount('tok', 'a@x.com')
      ..accountStats = false;
    final report = UsageReport(settings, WordDatabaseRepository(),
        client: MockClient((r) async {
          calls.add(r.method);
          return http.Response('{}', ok ? 200 : 500);
        }),
        baseUrl: 'https://x.test');
    expect(await report.deleteRemote(), isFalse);
    ok = true;
    await report.sendIfDue();
    expect(calls, ['DELETE', 'DELETE']);
    expect(settings.usageValue('acctStatsDelete'), 'done');
  });

  testWidgets('guide asks first; an old saved choice is not asked again',
      (tester) async {
    Future<void> pump(AppSettings s) async {
      await tester.pumpWidget(MaterialApp(
          home: OnboardingScreen(
              lexicon: testLexicon(), onDone: (_) {}, settings: s)));
      await tester.pump();
    }

    final fresh = AppSettings.inMemory(onboarded: false);
    await pump(fresh);
    expect(find.byKey(const ValueKey('consent-allow')), findsOneWidget);
    expect(fresh.anonymousEventsChoice, isNull); // still nothing chosen
    await tester.tap(find.byKey(const ValueKey('consent-deny')));
    await tester.pump();
    expect(fresh.anonymousEventsChoice, isFalse);
    expect(find.byKey(const ValueKey('consent-allow')), findsNothing);

    final old = AppSettings.inMemory(onboarded: false)..anonymousEvents = true;
    await pump(old);
    expect(find.byKey(const ValueKey('consent-allow')), findsNothing);
  });
}
