import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:photo_english_app/services/app_settings.dart';
import 'package:photo_english_app/services/usage_report.dart';
import 'package:photo_english_app/services/word_database_repository.dart';

void main() {
  test('signed out: nothing is sent', () async {
    var calls = 0;
    final settings = AppSettings.inMemory(taggingUrl: 'https://x.test');
    final report = UsageReport(settings, WordDatabaseRepository(),
        client: MockClient((_) async {
      calls++;
      return http.Response('{}', 200);
    }), baseUrl: 'https://x.test');
    expect(await report.sendIfDue(), isFalse);
    expect(calls, 0);
  });

  test('signed in: sends numbers once, failure is retried', () async {
    final bodies = <Map>[];
    var ok = false;
    final settings = AppSettings.inMemory(taggingUrl: 'https://x.test')..setCloudAccount('tok', 'a@x.com');
    final report = UsageReport(settings, WordDatabaseRepository(),
        client: MockClient((r) async {
          expect(r.headers['Authorization'], 'Bearer tok');
          bodies.add(jsonDecode(r.body) as Map);
          return http.Response('{}', ok ? 200 : 500);
        }),
        baseUrl: 'https://x.test');
    expect(await report.sendIfDue(), isFalse); // 500 → not recorded
    ok = true;
    expect(await report.sendIfDue(), isTrue);
    expect(await report.sendIfDue(), isFalse); // sent today
    expect(bodies.length, 2);
    expect(bodies.last.keys,
        containsAll(['albums', 'reviews_total', 'reviews_7d', 'photos_taken', 'photos_opened', 'app_version']));
  });
}
