import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/event_report.dart';

void main() {
  late AppSettings settings;
  late List<Map<String, dynamic>> bodies;
  late int status;
  late DateTime now;

  setUp(() {
    settings = AppSettings.inMemory();
    bodies = [];
    status = 200;
    now = DateTime(2026, 10, 31, 9);
    final client = MockClient((http.Request r) async {
      expect(r.url.path, '/api/events');
      expect(r.headers.containsKey('Authorization'), isFalse);
      bodies.add(jsonDecode(r.body) as Map<String, dynamic>);
      return http.Response('{"ok":true}', status);
    });
    EventReport.instance.attach(settings,
        client: client, baseUrl: 'https://x.test', now: () => now);
  });

  List<String> names() => [
        for (final b in bodies)
          for (final e in b['events'] as List) (e as Map)['event'] as String
      ];

  test('install once, open once per day, anonymous id stays', () async {
    EventReport.instance.appStarted();
    await Future<void>.delayed(Duration.zero);
    EventReport.instance.appStarted(); // same day: nothing new
    await Future<void>.delayed(Duration.zero);
    expect(names(), ['install', 'open']);
    now = DateTime(2026, 11, 1, 8);
    EventReport.instance.appStarted();
    await Future<void>.delayed(Duration.zero);
    expect(names(), ['install', 'open', 'open']);
    final ids = {for (final b in bodies) b['install_id']};
    expect(ids.length, 1);
    expect((ids.first as String).length, greaterThanOrEqualTo(16));
  });

  test('first-time events are sent once only', () async {
    EventReport.instance.once('first_review');
    EventReport.instance.once('first_review');
    await Future<void>.delayed(Duration.zero);
    expect(names(), ['first_review']);
  });

  test('switched off: nothing queued or sent', () async {
    settings.anonymousEvents = false;
    EventReport.instance.appStarted();
    EventReport.instance.once('onboarded');
    await Future<void>.delayed(Duration.zero);
    expect(bodies, isEmpty);
    expect(settings.usageValue('evt_queue'), isNull);
  });

  test('server error keeps the queue for the next try', () async {
    status = 500;
    EventReport.instance.once('first_photo');
    await Future<void>.delayed(Duration.zero);
    expect(await EventReport.instance.flush(), isFalse);
    status = 200;
    expect(await EventReport.instance.flush(), isTrue);
    expect(names().last, 'first_photo');
    expect(jsonDecode(settings.usageValue('evt_queue')!), isEmpty);
  });
}
